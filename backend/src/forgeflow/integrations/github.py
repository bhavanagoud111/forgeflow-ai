"""GitHub REST client.

Authentication is either a token (PAT or OAuth user token) or a GitHub App, in which
case short-lived installation tokens are minted on demand. Credentials stay in this
process: workspaces receive source tarballs, never tokens or remotes.

Write operations (branch creation, commits, pull requests) are only invoked by the
Pull Request agent after a recorded human approval, and they are idempotent: re-running
an approved step finds the existing branch / pull request instead of duplicating it.
"""

from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from forgeflow.config import Settings

_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubNotConfigured(GitHubError):
    pass


def parse_repo(value: str) -> str:
    v = value.strip().removesuffix(".git").removesuffix("/")
    m = re.match(r"^(?:https?://github\.com/)?([^/\s]+/[^/\s]+)$", v)
    if not m or not _REPO.match(m.group(1)):
        raise ValueError(f"not a GitHub repository reference: {value!r}")
    return m.group(1)


@dataclass
class FileChange:
    path: str
    content: str | None  # None deletes the file


class GitHubClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._installation_token: tuple[str, float] | None = None

    @property
    def configured(self) -> bool:
        return self.settings.github_configured

    async def _token(self) -> str:
        s = self.settings
        if s.github_token:
            return s.github_token.get_secret_value()
        if s.github_app_id and s.github_app_private_key:
            if self._installation_token and self._installation_token[1] - 60 > time.time():
                return self._installation_token[0]
            now = int(time.time())
            app_jwt = jwt.encode(
                {"iat": now - 60, "exp": now + 540, "iss": s.github_app_id},
                s.github_app_private_key.get_secret_value(),
                algorithm="RS256",
            )
            async with self._client(auth=f"Bearer {app_jwt}") as c:
                inst = s.github_app_installation_id
                if not inst:
                    r = await c.get("/app/installations")
                    self._check(r)
                    installs = r.json()
                    if not installs:
                        raise GitHubError("GitHub App has no installations")
                    inst = str(installs[0]["id"])
                r = await c.post(f"/app/installations/{inst}/access_tokens")
                self._check(r)
                data = r.json()
                self._installation_token = (data["token"], time.time() + 3600)
                return data["token"]
        raise GitHubNotConfigured("GitHub credentials are not configured (read-only demo mode)")

    def _client(self, auth: str | None = None) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "forgeflow-ai",
        }
        if auth:
            headers["Authorization"] = auth
        return httpx.AsyncClient(
            base_url=self.settings.github_api_url,
            headers=headers,
            timeout=30,
            transport=self._transport,
            follow_redirects=True,
        )

    @staticmethod
    def _check(r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                msg = r.json().get("message", r.text)
            except ValueError:
                msg = r.text
            raise GitHubError(
                f"GitHub API {r.request.method} {r.request.url.path} -> {r.status_code}: {msg[:300]}", r.status_code
            )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        token = await self._token()
        async with self._client(auth=f"Bearer {token}") as c:
            r = await c.request(method, path, **kwargs)
            self._check(r)
            if r.status_code == 204 or not r.content:
                return None
            ctype = r.headers.get("content-type", "")
            return r.json() if "json" in ctype else r.content

    # ------------------------------------------------------------------ read

    async def get_repo(self, repo: str) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{parse_repo(repo)}")

    async def list_issues(self, repo: str, state: str = "open", limit: int = 30) -> list[dict[str, Any]]:
        items = await self._request(
            "GET", f"/repos/{parse_repo(repo)}/issues", params={"state": state, "per_page": min(limit, 100)}
        )
        return [i for i in items if "pull_request" not in i]

    async def get_issue(self, repo: str, number: int) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{parse_repo(repo)}/issues/{int(number)}")

    async def list_pulls(self, repo: str, state: str = "open", limit: int = 30) -> list[dict[str, Any]]:
        return await self._request(
            "GET", f"/repos/{parse_repo(repo)}/pulls", params={"state": state, "per_page": min(limit, 100)}
        )

    async def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{parse_repo(repo)}/pulls/{int(number)}")

    async def get_pull_diff(self, repo: str, number: int) -> str:
        token = await self._token()
        async with self._client(auth=f"Bearer {token}") as c:
            r = await c.get(
                f"/repos/{parse_repo(repo)}/pulls/{int(number)}", headers={"Accept": "application/vnd.github.diff"}
            )
            self._check(r)
            return r.text

    async def list_branches(self, repo: str, limit: int = 50) -> list[dict[str, Any]]:
        return await self._request("GET", f"/repos/{parse_repo(repo)}/branches", params={"per_page": min(limit, 100)})

    async def get_branch_sha(self, repo: str, branch: str) -> str:
        data = await self._request("GET", f"/repos/{parse_repo(repo)}/git/ref/heads/{branch}")
        return data["object"]["sha"]

    async def ci_status(self, repo: str, ref: str) -> dict[str, Any]:
        r = parse_repo(repo)
        combined = await self._request("GET", f"/repos/{r}/commits/{ref}/status")
        checks = await self._request("GET", f"/repos/{r}/commits/{ref}/check-runs", params={"per_page": 50})
        return {
            "state": combined.get("state"),
            "statuses": [{"context": s["context"], "state": s["state"]} for s in combined.get("statuses", [])],
            "check_runs": [
                {"name": c["name"], "status": c["status"], "conclusion": c.get("conclusion")}
                for c in checks.get("check_runs", [])
            ],
        }

    async def get_tree(self, repo: str, ref: str) -> list[str]:
        data = await self._request("GET", f"/repos/{parse_repo(repo)}/git/trees/{ref}", params={"recursive": "1"})
        return [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"]

    async def get_file(self, repo: str, path: str, ref: str) -> str:
        data = await self._request("GET", f"/repos/{parse_repo(repo)}/contents/{path}", params={"ref": ref})
        return base64.b64decode(data["content"]).decode(errors="replace")

    async def download_tarball(self, repo: str, ref: str) -> bytes:
        data = await self._request("GET", f"/repos/{parse_repo(repo)}/tarball/{ref}")
        if not isinstance(data, bytes):
            raise GitHubError("unexpected tarball response")
        return data

    # ------------------------------------------------------------------ write (approval-gated)

    async def find_pull_for_branch(self, repo: str, branch: str) -> dict[str, Any] | None:
        r = parse_repo(repo)
        owner = r.split("/")[0]
        pulls = await self._request("GET", f"/repos/{r}/pulls", params={"head": f"{owner}:{branch}", "state": "all"})
        return pulls[0] if pulls else None

    async def push_branch(self, repo: str, branch: str, base_sha: str, message: str, changes: list[FileChange]) -> str:
        """Create (or fast-forward) ``branch`` with one commit on top of ``base_sha``."""
        if not branch.startswith("forgeflow/"):
            raise GitHubError("refusing to write outside forgeflow/* branches")
        r = parse_repo(repo)
        tree = []
        for ch in changes:
            if ch.content is None:
                tree.append({"path": ch.path, "mode": "100644", "type": "blob", "sha": None})
            else:
                blob = await self._request(
                    "POST", f"/repos/{r}/git/blobs", json={"content": ch.content, "encoding": "utf-8"}
                )
                tree.append({"path": ch.path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        base_commit = await self._request("GET", f"/repos/{r}/git/commits/{base_sha}")
        new_tree = await self._request(
            "POST", f"/repos/{r}/git/trees", json={"base_tree": base_commit["tree"]["sha"], "tree": tree}
        )
        commit = await self._request(
            "POST", f"/repos/{r}/git/commits", json={"message": message, "tree": new_tree["sha"], "parents": [base_sha]}
        )
        try:
            await self._request(
                "POST", f"/repos/{r}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit["sha"]}
            )
        except GitHubError as exc:
            if exc.status != 422:
                raise
            # The branch already exists (e.g. a retried step). Reuse it only if it holds
            # exactly this tree; never force-update a branch.
            existing = await self._request("GET", f"/repos/{r}/git/ref/heads/{branch}")
            head = await self._request("GET", f"/repos/{r}/git/commits/{existing['object']['sha']}")
            if head["tree"]["sha"] != new_tree["sha"]:
                raise GitHubError(f"branch {branch} already exists with different content", 409) from exc
            return str(existing["object"]["sha"])
        return str(commit["sha"])

    async def create_pull(
        self, repo: str, *, head: str, base: str, title: str, body: str, draft: bool = True
    ) -> dict[str, Any]:
        existing = await self.find_pull_for_branch(repo, head)
        if existing:
            return existing
        return await self._request(
            "POST",
            f"/repos/{parse_repo(repo)}/pulls",
            json={"head": head, "base": base, "title": title, "body": body, "draft": draft},
        )
