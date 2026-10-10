from sqlalchemy import select

from forgeflow.db.models import ExecutionEvent, Repository


async def _repo(c):
    async with c.services.db.session() as s:
        r = Repository(provider="local", full_name="local/x", local_path="/tmp")
        s.add(r)
        await s.flush()
        return r.id


async def test_memory_store_roundtrip_recall_and_forget(container):
    mem = container.services.memory
    rid = await _repo(container)
    await mem.save_repository(rid, {"conventions": {"items": ["pytest"], "token": "ghp_" + "z" * 36}})
    stored = await mem.repository(rid)
    assert stored["conventions"]["items"] == ["pytest"] and stored["conventions"]["token"] == "[REDACTED]"
    await mem.remember(rid, "failure_pattern", "JWT expiry inverted", "exp comparison was inverted in decode_token")
    await mem.remember(rid, "decision", "Rejected rate limiting", "Out of scope")
    hits = await mem.recall(rid, "token expiry decode")
    assert hits and hits[0]["title"] == "JWT expiry inverted"
    assert await mem.recall(rid, "decode", kinds=("decision",)) == []
    await mem.forget_repository(rid)
    assert await mem.repository(rid) == {} and await mem.recall(rid, "token") == []


async def test_event_bus_sequences_and_redacts(container):
    from forgeflow.db.models import Execution

    rid = await _repo(container)
    async with container.services.db.session() as s:
        ex = Execution(workflow="feature", repository_id=rid, request="r", created_by="t")
        s.add(ex)
        await s.flush()
        eid = ex.id
    bus = container.services.events
    for i in range(3):
        await bus.emit(eid, "log", f"message {i} xoxb-1234567890-abcdefghijkl", data={"password": "p"})
    events = await bus.since(eid, 1)
    assert [e.seq for e in events] == [2, 3]
    assert "xoxb" not in events[0].message and events[0].data["password"] == "[REDACTED]"
    async with container.services.db.session() as s:
        assert len(list(await s.scalars(select(ExecutionEvent).where(ExecutionEvent.execution_id == eid)))) == 3


async def test_concurrent_repository_memory_writes_do_not_conflict(container):
    import asyncio

    mem = container.services.memory
    rid = await _repo(container)
    await asyncio.gather(*[mem.save_repository(rid, {"conventions": {"items": [str(i)]}}) for i in range(8)])
    stored = await mem.repository(rid)
    assert list(stored) == ["conventions"] and len(stored["conventions"]["items"]) == 1
