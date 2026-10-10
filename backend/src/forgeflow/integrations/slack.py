"""Slack request verification and command parsing.

Slack text is untrusted. Commands are parsed with a strict grammar into a small set of
operations; nothing in a message is passed to a model as an instruction, and the
caller's ForgeFlow role comes from server configuration, never from the message.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import Literal

import httpx

MAX_SKEW_SECONDS = 300

HELP = (
    "*ForgeFlow commands*\n"
    "`/forgeflow analyze <owner/repo>` - analyse a repository and refresh its memory\n"
    "`/forgeflow plan issue-<n> [owner/repo]` - plan and implement a GitHub issue (stops for approval)\n"
    "`/forgeflow review pull-request-<n> [owner/repo]` - review a pull request\n"
    "`/forgeflow status <execution-id>` - show execution status\n"
    "`/forgeflow help`"
)


def verify_signature(
    secret: str, timestamp: str | None, body: bytes, signature: str | None, now: float | None = None
) -> bool:
    if not timestamp or not signature or not timestamp.isdigit():
        return False
    if abs((now or time.time()) - int(timestamp)) > MAX_SKEW_SECONDS:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class SlackCommand:
    action: Literal["analyze", "plan", "review", "status", "help"]
    repo: str | None = None
    number: int | None = None
    execution_id: str | None = None


class CommandError(ValueError):
    pass


_REPO = r"(?:local|[A-Za-z0-9_.-]+)/[A-Za-z0-9_.-]+"


def parse_command(text: str) -> SlackCommand:
    t = " ".join((text or "").strip().split())
    if not t or t == "help":
        return SlackCommand("help")
    m = re.fullmatch(rf"analyze ({_REPO})", t)
    if m:
        return SlackCommand("analyze", repo=m.group(1))
    m = re.fullmatch(rf"plan (?:issue-|#)?(\d+)(?: ({_REPO}))?", t)
    if m:
        return SlackCommand("plan", number=int(m.group(1)), repo=m.group(2))
    m = re.fullmatch(rf"review (?:pull-request-|pr-|#)?(\d+)(?: ({_REPO}))?", t)
    if m:
        return SlackCommand("review", number=int(m.group(1)), repo=m.group(2))
    m = re.fullmatch(r"status (?:execution-)?((?:exec_)?[a-f0-9]{16})", t)
    if m:
        eid = m.group(1)
        return SlackCommand("status", execution_id=eid if eid.startswith("exec_") else f"exec_{eid}")
    raise CommandError(f"Unrecognised command `{t[:80]}`.\n{HELP}")


async def post_response(response_url: str, text: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
    if not response_url.startswith("https://hooks.slack.com/"):
        return  # only post back to Slack-owned URLs
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        await client.post(response_url, json={"response_type": "ephemeral", "text": text})
