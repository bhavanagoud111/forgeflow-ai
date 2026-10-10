import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx
import pytest
from pydantic import SecretStr

from forgeflow.api.app import create_app
from forgeflow.container import build_container
from tests.conftest import make_settings

SECRET = "slack-signing-secret"


def signed(body: bytes, ts: str | None = None) -> dict[str, str]:
    ts = ts or str(int(time.time()))
    sig = "v0=" + hmac.new(SECRET.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
        "Content-Type": "application/x-www-form-urlencoded",
    }


@pytest.fixture
async def slack_client(tmp_path):
    settings = make_settings(
        tmp_path, slack_signing_secret=SecretStr(SECRET), slack_user_roles={"UOPS": "operator", "UVIEW": "viewer"}
    )
    c = await build_container(settings)
    app = create_app(settings, container=c)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client
    await c.close()


async def command(client, text, user="UOPS", trigger="t1"):
    body = urlencode({"text": text, "user_id": user, "trigger_id": trigger}).encode()
    return await client.post("/api/slack/commands", content=body, headers=signed(body))


async def test_rejects_bad_signatures(slack_client):
    body = b"text=help&user_id=UOPS"
    headers = signed(body)
    headers["X-Slack-Signature"] = "v0=" + "0" * 64
    assert (await slack_client.post("/api/slack/commands", content=body, headers=headers)).status_code == 401
    stale = signed(body, ts=str(int(time.time()) - 3600))
    assert (await slack_client.post("/api/slack/commands", content=body, headers=stale)).status_code == 401


async def test_unknown_users_are_denied(slack_client):
    r = await command(slack_client, "analyze local/taskboard-api", user="USTRANGER")
    assert "not authorised" in r.json()["text"]


async def test_viewers_cannot_start_work(slack_client):
    r = await command(slack_client, "analyze local/taskboard-api", user="UVIEW")
    assert "operator role" in r.json()["text"]


async def test_operator_analyze_and_status_and_dedup(slack_client):
    r = await command(slack_client, "analyze local/taskboard-api", trigger="trig-a")
    text = r.json()["text"]
    assert text.startswith("Started `exec_")
    eid = text.split("`")[1]
    dup = await command(slack_client, "analyze local/taskboard-api", trigger="trig-a")
    assert dup.json()["text"] == "Already processing this command."
    status = await command(slack_client, f"status {eid}", user="UVIEW", trigger="trig-b")
    assert eid in status.json()["text"]


async def test_invalid_command_returns_help(slack_client):
    r = await command(slack_client, "deploy production", trigger="trig-c")
    assert "Unrecognised command" in r.json()["text"]


async def test_events_url_verification_and_dedup(slack_client):
    body = b'{"type":"url_verification","challenge":"abc"}'
    r = await slack_client.post("/api/slack/events", content=body, headers=signed(body))
    assert r.json() == {"challenge": "abc"}
    ev = b'{"type":"event_callback","event_id":"Ev1","event":{"type":"app_mention"}}'
    assert (await slack_client.post("/api/slack/events", content=ev, headers=signed(ev))).json() == {"ok": True}
    assert (await slack_client.post("/api/slack/events", content=ev, headers=signed(ev))).json() == {"ok": True}


async def test_slack_disabled_when_unconfigured(client):
    r = await client.post("/api/slack/commands", content=b"text=help")
    assert r.status_code == 404
