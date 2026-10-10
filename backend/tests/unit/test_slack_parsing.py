import hashlib
import hmac
import time

import pytest

from forgeflow.integrations.slack import CommandError, parse_command, verify_signature


def sign(secret: str, ts: str, body: bytes) -> str:
    return "v0=" + hmac.new(secret.encode(), b"v0:" + ts.encode() + b":" + body, hashlib.sha256).hexdigest()


def test_signature_verification():
    ts = str(int(time.time()))
    body = b"text=help"
    assert verify_signature("s3cret", ts, body, sign("s3cret", ts, body))
    assert not verify_signature("s3cret", ts, body + b"x", sign("s3cret", ts, body))
    assert not verify_signature("other", ts, body, sign("s3cret", ts, body))
    old = str(int(time.time()) - 600)
    assert not verify_signature("s3cret", old, body, sign("s3cret", old, body))
    assert not verify_signature("s3cret", None, body, None)


@pytest.mark.parametrize(
    ("text", "action", "repo", "number"),
    [
        ("analyze octo/repo", "analyze", "octo/repo", None),
        ("plan issue-42", "plan", None, 42),
        ("plan issue-42 octo/repo", "plan", "octo/repo", 42),
        ("review pull-request-17 octo/repo", "review", "octo/repo", 17),
        ("review #9", "review", None, 9),
        ("", "help", None, None),
    ],
)
def test_parse_commands(text, action, repo, number):
    cmd = parse_command(text)
    assert (cmd.action, cmd.repo, cmd.number) == (action, repo, number)


def test_status_normalises_execution_id():
    assert parse_command("status execution-0123456789abcdef").execution_id == "exec_0123456789abcdef"


@pytest.mark.parametrize("text", ["deploy prod", "analyze ../../etc", "plan issue-x", "status 123; rm -rf"])
def test_invalid_commands(text):
    with pytest.raises(CommandError):
        parse_command(text)
