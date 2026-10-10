"""File contents used by the scripted demo scenarios for the taskboard sample repository.

These strings are the "model output" of the demo provider. They are applied to an
isolated workspace and then verified by actually running the repository's tests.
"""

SECURITY_PY_V1 = '''"""Minimal HS256 JSON Web Tokens using only the standard library."""

import base64
import hashlib
import hmac
import json
import time


class TokenError(Exception):
    """Raised when a token is malformed, has a bad signature, or has expired."""


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_token(subject: str, secret: str, ttl_seconds: int = 3600, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "iat": issued, "exp": issued + ttl_seconds}
    signing_input = f"{_b64encode(json.dumps(header).encode())}.{_b64encode(json.dumps(payload).encode())}"
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_token(token: str, secret: str, now: float | None = None) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    signing_input = f"{header_b64}.{payload_b64}"
    expected = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64decode(signature_b64)):
        raise TokenError("invalid signature")
    try:
        header = json.loads(_b64decode(header_b64))
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("malformed token") from exc
    if header.get("alg") != "HS256":
        raise TokenError("unsupported algorithm")
    current = now if now is not None else time.time()
    if payload.get("exp", 0) > current:
        raise TokenError("token expired")
    return payload
'''

# The scripted debugger's fix for the inverted expiry comparison above.
SECURITY_FIX_SEARCH = '    if payload.get("exp", 0) > current:\n'
SECURITY_FIX_REPLACEMENT = '    if payload.get("exp", 0) <= current:\n'

TEST_SECURITY_PY = """import pytest

from taskboard.security import TokenError, create_token, decode_token

SECRET = "test-secret"


def test_valid_token_round_trip():
    token = create_token("alice", SECRET, ttl_seconds=60, now=1_000)
    assert decode_token(token, SECRET, now=1_030)["sub"] == "alice"


def test_expired_token_rejected():
    token = create_token("alice", SECRET, ttl_seconds=60, now=1_000)
    with pytest.raises(TokenError, match="expired"):
        decode_token(token, SECRET, now=1_061)


def test_tampered_signature_rejected():
    token = create_token("alice", SECRET, now=1_000)
    with pytest.raises(TokenError, match="signature"):
        decode_token(token[:-2] + "xx", SECRET, now=1_001)


def test_wrong_secret_rejected():
    token = create_token("alice", SECRET, now=1_000)
    with pytest.raises(TokenError):
        decode_token(token, "other-secret", now=1_001)


def test_malformed_token_rejected():
    with pytest.raises(TokenError, match="malformed"):
        decode_token("not-a-token", SECRET)
"""

CONFIG_PY = '''"""Runtime settings for the Taskboard API."""

import os

DEFAULT_DEV_SECRET = "taskboard-dev-secret"


def jwt_secret() -> str:
    """Secret used to sign tokens. Set TASKBOARD_JWT_SECRET in any real deployment."""
    return os.environ.get("TASKBOARD_JWT_SECRET", DEFAULT_DEV_SECRET)


def token_ttl_seconds() -> int:
    return int(os.environ.get("TASKBOARD_TOKEN_TTL_SECONDS", "3600"))
'''

AUTH_PY = '''"""FastAPI dependency that requires a valid bearer token."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from taskboard.config import jwt_secret
from taskboard.security import TokenError, decode_token

_bearer = HTTPBearer(auto_error=False)


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_token(credentials.credentials, jwt_secret())
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return str(payload["sub"])
'''

MAIN_IMPORT_SEARCH = "from fastapi import FastAPI, HTTPException, status\n"
MAIN_IMPORT_REPLACEMENT = (
    "from fastapi import Depends, FastAPI, HTTPException, status\n\nfrom taskboard.auth import require_user\n"
)

MAIN_ROUTE_EDITS = [
    (
        "def create_task(data: TaskCreate) -> Task:\n",
        "def create_task(data: TaskCreate, _user: str = Depends(require_user)) -> Task:\n",
    ),
    (
        "def update_task(task_id: int, data: TaskUpdate) -> Task:\n",
        "def update_task(task_id: int, data: TaskUpdate, _user: str = Depends(require_user)) -> Task:\n",
    ),
    (
        "def delete_task(task_id: int) -> None:\n",
        "def delete_task(task_id: int, _user: str = Depends(require_user)) -> None:\n",
    ),
]

CONFTEST_SEARCH = """@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
"""

CONFTEST_REPLACEMENT = '''@pytest.fixture
def client() -> TestClient:
    """Client that sends a valid bearer token on every request."""
    token = create_token("test-user", jwt_secret())
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture
def anonymous_client() -> TestClient:
    return TestClient(app)
'''

CONFTEST_IMPORT_SEARCH = "from taskboard.main import app, store\n"
CONFTEST_IMPORT_REPLACEMENT = (
    "from taskboard.config import jwt_secret\nfrom taskboard.main import app, store\n"
    "from taskboard.security import create_token\n"
)

TEST_AUTH_ENDPOINTS_PY = """from taskboard.config import jwt_secret
from taskboard.security import create_token


def test_reads_do_not_require_auth(anonymous_client):
    assert anonymous_client.get("/tasks").status_code == 200


def test_create_requires_token(anonymous_client):
    response = anonymous_client.post("/tasks", json={"title": "x"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_invalid_token_rejected(anonymous_client):
    response = anonymous_client.post(
        "/tasks", json={"title": "x"}, headers={"Authorization": "Bearer not.a.token"}
    )
    assert response.status_code == 401


def test_expired_token_rejected(anonymous_client):
    token = create_token("bob", jwt_secret(), ttl_seconds=1, now=0)
    response = anonymous_client.post(
        "/tasks", json={"title": "x"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_valid_token_allows_writes(client):
    created = client.post("/tasks", json={"title": "secured"})
    assert created.status_code == 201
    assert client.delete(f"/tasks/{created.json()['id']}").status_code == 204
"""

# Bug investigation scenario.
REGRESSION_TEST_PY = """def test_reopen_completed_task(client):
    task_id = client.post("/tasks", json={"title": "Reopen me"}).json()["id"]
    client.patch(f"/tasks/{task_id}", json={"completed": True})
    reopened = client.patch(f"/tasks/{task_id}", json={"completed": False})
    assert reopened.status_code == 200
    assert reopened.json()["completed"] is False
"""

STORE_FIX_SEARCH = "        if data.completed:\n"
STORE_FIX_REPLACEMENT = "        if data.completed is not None:\n"

# Test generation scenario.
TEST_STORE_PY = """from taskboard.models import TaskCreate, TaskUpdate
from taskboard.store import TaskStore


def test_ids_are_sequential():
    store = TaskStore()
    first = store.create(TaskCreate(title="a"))
    second = store.create(TaskCreate(title="b"))
    assert (first.id, second.id) == (1, 2)


def test_update_missing_task_returns_none():
    assert TaskStore().update(42, TaskUpdate(title="x")) is None


def test_update_changes_only_given_fields():
    store = TaskStore()
    task = store.create(TaskCreate(title="a", description="keep"))
    store.update(task.id, TaskUpdate(title="b"))
    assert store.get(task.id).title == "b"
    assert store.get(task.id).description == "keep"


def test_list_filters_by_completion():
    store = TaskStore()
    done = store.create(TaskCreate(title="done"))
    store.create(TaskCreate(title="open"))
    store.update(done.id, TaskUpdate(completed=True))
    assert [t.title for t in store.list(completed=True)] == ["done"]
    assert [t.title for t in store.list(completed=False)] == ["open"]


def test_delete_and_reset():
    store = TaskStore()
    task = store.create(TaskCreate(title="a"))
    assert store.delete(task.id) is True
    assert store.delete(task.id) is False
    store.create(TaskCreate(title="b"))
    store.reset()
    assert store.list() == []
    assert store.create(TaskCreate(title="c")).id == 1
"""

# Second defect in SECURITY_PY_V1: malformed base64 in the signature segment raises
# binascii.Error instead of TokenError.
SIGNATURE_FIX_SEARCH = """    if not hmac.compare_digest(expected, _b64decode(signature_b64)):
        raise TokenError("invalid signature")
"""
SIGNATURE_FIX_REPLACEMENT = """    try:
        signature = _b64decode(signature_b64)
    except ValueError as exc:  # binascii.Error is a ValueError
        raise TokenError("malformed token") from exc
    if not hmac.compare_digest(expected, signature):
        raise TokenError("invalid signature")
"""
