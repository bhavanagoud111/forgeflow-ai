"""Slack slash commands and Events API."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from forgeflow.api.deps import ContainerDep, audit
from forgeflow.api.errors import APIError
from forgeflow.container import Container
from forgeflow.db.models import Execution, InboundDelivery, Repository
from forgeflow.integrations.github import GitHubError, GitHubNotConfigured, parse_repo
from forgeflow.integrations.slack import (
    HELP,
    CommandError,
    SlackCommand,
    parse_command,
    post_response,
    verify_signature,
)
from forgeflow.operations import OperationError, create_execution
from forgeflow.schemas import TERMINAL_STATUSES, Workflow
from forgeflow.security.auth import Role
from forgeflow.security.untrusted import injection_signals

router = APIRouter(prefix="/api/slack", tags=["slack"])


async def _verified_body(request: Request, c: Container) -> bytes:
    secret = c.services.settings.slack_signing_secret
    if secret is None:
        raise APIError(404, "not_found", "Slack integration is not configured")
    body = await request.body()
    if not verify_signature(
        secret.get_secret_value(),
        request.headers.get("X-Slack-Request-Timestamp"),
        body,
        request.headers.get("X-Slack-Signature"),
    ):
        raise APIError(401, "unauthorized", "Invalid Slack signature")
    return body


async def _first_delivery(c: Container, key: str) -> bool:
    try:
        async with c.services.db.session() as s:
            s.add(InboundDelivery(key=key[:200], source="slack"))
        return True
    except IntegrityError:
        return False


def _reply(text: str) -> dict[str, Any]:
    return {"response_type": "ephemeral", "text": text}


async def _resolve_repo(c: Container, name: str | None, role: Role, actor: str) -> Repository:
    async with c.services.db.session() as s:
        if name is None:
            repos = list(await s.scalars(select(Repository).limit(2)))
            if len(repos) != 1:
                raise CommandError("Specify a repository (owner/repo); more than one is connected.")
            return repos[0]
        repo = await s.scalar(select(Repository).where(Repository.full_name == name))
    if repo is not None:
        return repo
    if name.startswith("local/") or role < Role.operator:
        raise CommandError(f"Repository `{name}` is not connected.")
    try:
        meta = await c.services.github.get_repo(parse_repo(name))
    except (GitHubNotConfigured, GitHubError, ValueError) as exc:
        raise CommandError(f"Cannot connect `{name}`: {exc}") from exc
    repo = Repository(
        provider="github",
        full_name=meta["full_name"],
        default_branch=meta["default_branch"],
        description=meta.get("description"),
    )
    async with c.services.db.session() as s:
        s.add(repo)
    await audit(c, actor, "repository.connect", repo.id, name=repo.full_name, source="slack")
    return repo


async def _follow(c: Container, execution_id: str, response_url: str) -> None:
    """Post approval requests and the final outcome back to the Slack thread."""
    notified_approval = False
    deadline = asyncio.get_running_loop().time() + c.services.settings.execution_timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        async with c.services.db.session() as s:
            ex = await s.get(Execution, execution_id)
        if ex is None:
            return
        if ex.status == "awaiting_approval" and not notified_approval:
            notified_approval = True
            await post_response(
                response_url, f"`{execution_id}` is waiting for approval in the ForgeFlow Approval Center."
            )
        if ex.status in TERMINAL_STATUSES:
            await post_response(response_url, f"`{execution_id}` {ex.status}: {ex.summary or ex.error or ''}"[:2900])
            return
        await asyncio.sleep(5)


async def _execute(c: Container, cmd: SlackCommand, user_id: str, role: Role) -> tuple[str, str | None]:
    actor = f"slack:{user_id}"
    if cmd.action == "help":
        return HELP, None
    if cmd.action == "status":
        async with c.services.db.session() as s:
            ex = await s.get(Execution, cmd.execution_id)
        if ex is None:
            return f"No execution `{cmd.execution_id}`.", None
        return f"`{ex.id}` ({ex.workflow}) is *{ex.status}*" + (
            f" at `{ex.current_node}`" if ex.current_node else ""
        ) + (f"\n{ex.summary}" if ex.summary else ""), None
    if role < Role.operator:
        raise CommandError("You need the operator role to start executions.")
    repo = await _resolve_repo(c, cmd.repo, role, actor)
    if cmd.action == "analyze":
        ex = await create_execution(
            c,
            repository_id=repo.id,
            workflow=Workflow.repo_onboarding,
            request=f"Analyse {repo.full_name}",
            params={},
            actor=actor,
            source="slack",
        )
    elif cmd.action == "review":
        if repo.provider != "github":
            raise CommandError("Pull request review needs a GitHub repository.")
        ex = await create_execution(
            c,
            repository_id=repo.id,
            workflow=Workflow.code_review,
            request=f"Review pull request #{cmd.number}",
            params={"pr_number": cmd.number},
            actor=actor,
            source="slack",
        )
    else:  # plan
        if repo.provider != "github":
            raise CommandError("Planning from an issue needs a GitHub repository.")
        try:
            issue = await c.services.github.get_issue(repo.full_name, int(cmd.number or 0))
        except GitHubError as exc:
            raise CommandError(f"Cannot read issue #{cmd.number}: {exc}") from exc
        # Issue text is untrusted data; it becomes the request content, fenced by every agent prompt.
        request = f"{issue['title']}\n\n{issue.get('body') or ''}"[:8000]
        ex = await create_execution(
            c,
            repository_id=repo.id,
            workflow=Workflow.feature,
            request=request,
            params={"issue": cmd.number},
            actor=actor,
            source="slack",
        )
        signals = injection_signals(request)
        if signals:
            await c.services.events.emit(
                ex.id,
                "log",
                "Issue text contains instruction-like phrases; treated as data.",
                data={"signals": signals},
            )
    return f"Started `{ex.id}` ({ex.workflow}) on `{repo.full_name}`.", ex.id


@router.post("/commands", summary="Slack slash command endpoint (/forgeflow)")
async def commands(request: Request, c: ContainerDep, background: BackgroundTasks) -> dict[str, Any]:
    body = await _verified_body(request, c)
    form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
    user_id = form.get("user_id", "")
    key = f"cmd:{form.get('trigger_id') or request.headers.get('X-Slack-Request-Timestamp')}:{user_id}"
    if not await _first_delivery(c, key):
        return _reply("Already processing this command.")
    role_name = c.services.settings.slack_user_roles.get(user_id)
    if role_name is None:
        await audit(c, f"slack:{user_id}", "slack.denied", None, command=form.get("text", "")[:200])
        return _reply("You are not authorised to use ForgeFlow. Ask an admin to add your Slack user ID.")
    role = Role[role_name]
    try:
        cmd = parse_command(form.get("text", ""))
        message, execution_id = await _execute(c, cmd, user_id, role)
    except (CommandError, OperationError) as exc:
        return _reply(str(exc) if isinstance(exc, CommandError) else exc.message)
    if execution_id and form.get("response_url"):
        background.add_task(_follow, c, execution_id, form["response_url"])
    return _reply(message)


@router.post("/events", summary="Slack Events API endpoint")
async def events(request: Request, c: ContainerDep) -> dict[str, Any]:
    body = await _verified_body(request, c)
    data = json.loads(body or b"{}")
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
    event_id = data.get("event_id")
    if not event_id or not await _first_delivery(c, f"evt:{event_id}"):
        return {"ok": True}  # duplicate or retried delivery
    event = data.get("event", {})
    if event.get("type") == "app_mention" and not event.get("bot_id") and c.services.settings.slack_bot_token:
        # Mentions never start work: free text is not a trusted instruction channel.
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {c.services.settings.slack_bot_token.get_secret_value()}"},
                json={"channel": event.get("channel"), "thread_ts": event.get("ts"), "text": HELP},
            )
    return {"ok": True}
