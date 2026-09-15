from backend.tests.conftest import wait_for


def create_subject(client, name):
    return client.post("/api/subjects", json={"name": name}).json()["id"]


def upload_source(client, subject_id, filename, content, content_type="text/plain", display_name=None):
    data = {} if display_name is None else {"display_name": display_name}
    return client.post(
        f"/api/subjects/{subject_id}/sources",
        data=data,
        files={"file": (filename, content, content_type)},
    )


def wait_for_operation(client, operation_id):
    result = None

    def terminal():
        nonlocal result
        response = client.get(f"/api/operations/{operation_id}")
        assert response.status_code == 200
        result = response.json()
        return result["status"] in {"succeeded", "failed", "canceled"}

    wait_for(terminal)
    return result
