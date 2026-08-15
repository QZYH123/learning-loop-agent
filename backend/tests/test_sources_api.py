from backend.tests.conftest import make_client, wait_for


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


def test_source_versions_cache_delete_and_subject_isolation(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        math_id = create_subject(client, "数学")
        english_id = create_subject(client, "英语")

        uploaded = upload_source(
            client,
            math_id,
            "notes.md",
            b"# Limits\n\nA limit describes nearby behavior.\n",
            "text/markdown",
            "极限笔记",
        )
        assert uploaded.status_code == 202
        accepted = uploaded.json()
        assert accepted["operation"]["kind"] == "source-parsing"
        assert accepted["resource"]["type"] == "source"
        source_id = accepted["resource"]["id"]
        operation = wait_for_operation(client, accepted["operation"]["id"])
        assert operation["status"] == "succeeded"
        assert operation["result"]["type"] == "source-version"

        source = client.get(f"/api/sources/{source_id}").json()
        assert source["display_name"] == "极限笔记"
        assert source["status"] == "ready"
        assert source["current_version"]["number"] == 1
        assert source["current_version"]["cache_hit"] is False
        assert source["current_version"]["processed_at"] is not None
        first_version_id = source["current_version"]["id"]

        reopened = client.get(f"/api/sources/{source_id}").json()
        assert reopened["updated_at"] == source["updated_at"]

        duplicate = upload_source(
            client,
            math_id,
            "copy.txt",
            b"# Limits\n\nA limit describes nearby behavior.\n",
        )
        duplicate_operation = wait_for_operation(client, duplicate.json()["operation"]["id"])
        duplicate_source = client.get(f"/api/sources/{duplicate.json()['resource']['id']}").json()
        assert duplicate_operation["status"] == "succeeded"
        assert duplicate_source["current_version"]["cache_hit"] is True

        changed = client.post(
            f"/api/sources/{source_id}/versions",
            files={"file": ("notes.md", b"# Limits\n\nUpdated content.\n", "text/markdown")},
        )
        assert changed.status_code == 202
        wait_for_operation(client, changed.json()["operation"]["id"])

        versions = client.get(f"/api/sources/{source_id}/versions").json()["items"]
        assert [version["number"] for version in versions] == [1, 2]
        assert client.get(f"/api/source-versions/{first_version_id}").json()["status"] == "ready"

        math_sources = client.get(f"/api/subjects/{math_id}/sources").json()["items"]
        english_sources = client.get(f"/api/subjects/{english_id}/sources").json()["items"]
        assert len(math_sources) == 2
        assert english_sources == []

        deleted = client.delete(f"/api/sources/{source_id}")
        assert deleted.status_code == 204
        assert client.get(f"/api/sources/{source_id}").status_code == 404
        preserved = client.get(f"/api/source-versions/{first_version_id}")
        assert preserved.status_code == 200
        assert preserved.json()["status"] == "unavailable"


def test_failed_source_is_visible_without_affecting_ready_sources(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        subject_id = create_subject(client, "数学")

        good = upload_source(client, subject_id, "good.txt", b"valid text")
        wait_for_operation(client, good.json()["operation"]["id"])

        bad = upload_source(client, subject_id, "bad.txt", b"\xff\xfe")
        assert bad.status_code == 202
        failed_operation = wait_for_operation(client, bad.json()["operation"]["id"])
        assert failed_operation["status"] == "failed"
        assert failed_operation["error"]["code"] == "SOURCE_PROCESSING_FAILED"

        sources = client.get(f"/api/subjects/{subject_id}/sources").json()["items"]
        assert {source["status"] for source in sources} == {"ready", "failed"}
        failed_source = next(source for source in sources if source["status"] == "failed")
        assert failed_source["failure"]["code"] == "SOURCE_PROCESSING_FAILED"

        unsupported = upload_source(client, subject_id, "book.pdf", b"%PDF", "application/pdf")
        assert unsupported.status_code == 202
        invalid_pdf = wait_for_operation(client, unsupported.json()["operation"]["id"])
        assert invalid_pdf["status"] == "failed"
        assert invalid_pdf["error"]["code"] == "SOURCE_PROCESSING_FAILED"


def test_source_metadata_and_parse_cache_survive_restart(tmp_path):
    client, _ = make_client(tmp_path)
    with client:
        subject_id = create_subject(client, "数学")
        uploaded = upload_source(client, subject_id, "notes.txt", b"persistent notes")
        operation_id = uploaded.json()["operation"]["id"]
        completed = wait_for_operation(client, operation_id)
        version_id = completed["result"]["id"]

    reopened, _ = make_client(tmp_path)
    with reopened:
        restored_operation = reopened.get(f"/api/operations/{operation_id}")
        assert restored_operation.status_code == 200
        assert restored_operation.json()["status"] == "succeeded"
        assert restored_operation.json()["result"] == {"type": "source-version", "id": version_id}

        restored = reopened.get(f"/api/subjects/{subject_id}/sources").json()["items"]
        assert len(restored) == 1
        assert restored[0]["status"] == "ready"

        duplicate = upload_source(reopened, subject_id, "copy.txt", b"persistent notes")
        wait_for_operation(reopened, duplicate.json()["operation"]["id"])
        duplicate_source = reopened.get(f"/api/sources/{duplicate.json()['resource']['id']}").json()
        assert duplicate_source["current_version"]["cache_hit"] is True
