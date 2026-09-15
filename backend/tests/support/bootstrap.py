from backend.tests.conftest import wait_for


def create_subject_and_model(client, *, vision=False):
    subject = client.post("/api/subjects", json={"name": "数学"}).json()
    model = client.post("/api/models", json={
        "provider": "Fake",
        "api_format": "openai-chat-completions",
        "model": "fake-1",
        "base_url": "http://localhost/v1",
        "api_key": "secret",
        "capabilities": {"text": True, "vision": vision},
    }).json()
    return subject["id"], model["id"]


def create_subject_and_source(client):
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
    response = client.post(
        f"/api/subjects/{subject_id}/sources",
        files={"file": ("notes.md", b"# Limits\nThe limit of x is x.", "text/markdown")},
    )
    operation_id = response.json()["operation"]["id"]
    wait_for(lambda: client.get(f"/api/operations/{operation_id}").json()["status"] == "succeeded")
    source = client.get(f"/api/subjects/{subject_id}/sources").json()["items"][0]
    return subject_id, source["current_version"]["id"]


def create_subject_with_current_model(client):
    subject_id = client.post("/api/subjects", json={"name": "数学"}).json()["id"]
    model_id = client.post(
        "/api/models",
        json={"provider": "Fake", "api_format": "openai-chat-completions", "model": "fake-1", "base_url": "http://localhost/v1"},
    ).json()["id"]
    client.put("/api/models/current", json={"model_id": model_id})
    return subject_id, model_id
