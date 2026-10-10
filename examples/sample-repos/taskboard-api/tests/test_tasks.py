def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_get_task(client):
    created = client.post("/tasks", json={"title": "Write docs"})
    assert created.status_code == 201
    task_id = created.json()["id"]
    fetched = client.get(f"/tasks/{task_id}")
    assert fetched.json()["title"] == "Write docs"


def test_complete_task(client):
    task_id = client.post("/tasks", json={"title": "Ship"}).json()["id"]
    updated = client.patch(f"/tasks/{task_id}", json={"completed": True})
    assert updated.json()["completed"] is True


def test_filter_completed(client):
    a = client.post("/tasks", json={"title": "a"}).json()["id"]
    client.post("/tasks", json={"title": "b"})
    client.patch(f"/tasks/{a}", json={"completed": True})
    done = client.get("/tasks", params={"completed": True}).json()
    assert [t["title"] for t in done] == ["a"]


def test_delete_missing_task(client):
    assert client.delete("/tasks/999").status_code == 404
