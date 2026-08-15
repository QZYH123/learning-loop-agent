from backend.app.domain import (
    CHAT_COMPLETE,
    CHAT_SEND,
    CHAT_STOP,
    MODEL_ADD,
    SUBJECT_CREATE,
    SUBJECT_DELETE,
    SUBJECT_RENAME,
    SUBJECT_SWITCH,
    apply_action,
    build_chat_request_messages,
    initial_workspace,
    normalize_workspace,
)


def test_subject_lifecycle_and_isolation():
    workspace = initial_workspace(now=1000)
    result = apply_action(workspace, {"type": SUBJECT_CREATE, "name": " 数学 "}, now=2000, id_factory=lambda: "s1")
    assert result["ok"] is True
    assert result["workspace"]["active_subject_id"] == "s1"
    assert result["workspace"]["subjects"][0]["name"] == "数学"

    second = apply_action(result["workspace"], {"type": SUBJECT_CREATE, "name": "英语"}, now=3000, id_factory=lambda: "s2")
    renamed = apply_action(second["workspace"], {"type": SUBJECT_RENAME, "subject_id": "s2", "name": "大学英语"}, now=4000)
    switched = apply_action(renamed["workspace"], {"type": SUBJECT_SWITCH, "subject_id": "s1"}, now=5000)
    deleted = apply_action(switched["workspace"], {"type": SUBJECT_DELETE, "subject_id": "s1"}, now=6000)
    assert deleted["workspace"]["active_subject_id"] == "s2"
    assert [s["name"] for s in deleted["workspace"]["subjects"]] == ["大学英语"]

    duplicate = apply_action(deleted["workspace"], {"type": SUBJECT_CREATE, "name": " 大学英语 "}, now=7000, id_factory=lambda: "s3")
    assert duplicate["ok"] is False
    assert duplicate["error"]["code"] == "SUBJECT_NAME_DUPLICATE"


def test_model_validation_and_chat_message_snapshot():
    workspace = initial_workspace(now=1000)
    created = apply_action(workspace, {"type": SUBJECT_CREATE, "name": "数学"}, now=1001, id_factory=lambda: "s1")
    added = apply_action(created["workspace"], {
        "type": MODEL_ADD,
        "provider": "Fake",
        "model": "fake-1",
        "base_url": "http://localhost/v1/",
    }, now=1002, id_factory=lambda: "m1")
    model = added["workspace"]["models"][0]
    assert model["base_url"] == "http://localhost/v1"
    assert model["capabilities"] == {"text": True, "vision": False, "source": "configured"}

    message_ids = iter(["user-1", "assistant-1"])
    sent = apply_action(added["workspace"], {
        "type": CHAT_SEND,
        "subject_id": "s1",
        "model_id": "m1",
        "content": "问题",
    }, now=1003, id_factory=lambda: next(message_ids))
    assert sent["ok"] is True
    assert sent["request"]["messages"] == [{"role": "user", "content": "问题"}]
    chat = sent["workspace"]["subjects"][0]["data"]["chat"]
    assert chat["messages"][1]["status"] == "generating"
    assert chat["messages"][1]["mode"] == "general-knowledge"
    assert chat["messages"][1]["model"]["model"] == "fake-1"

    completed = apply_action(sent["workspace"], {
        "type": CHAT_COMPLETE,
        "subject_id": "s1",
        "message_id": "assistant-1",
        "text": "回答",
    }, now=1004)
    chat = completed["workspace"]["subjects"][0]["data"]["chat"]
    assert chat["messages"][1]["status"] == "complete"
    assert build_chat_request_messages(chat) == [
        {"role": "user", "content": "问题"},
        {"role": "assistant", "content": "回答"},
    ]


def test_stop_and_switch_model_keep_history_snapshot():
    workspace = initial_workspace(now=1000)
    workspace = apply_action(workspace, {"type": SUBJECT_CREATE, "name": "数学"}, now=1001, id_factory=lambda: "s1")["workspace"]
    workspace = apply_action(workspace, {"type": MODEL_ADD, "provider": "A", "model": "a", "base_url": "http://a/v1"}, now=1002, id_factory=lambda: "m1")["workspace"]
    workspace = apply_action(workspace, {"type": MODEL_ADD, "provider": "B", "model": "b", "base_url": "http://b/v1"}, now=1003, id_factory=lambda: "m2")["workspace"]
    first_ids = iter(["user-1", "assistant-1"])
    first = apply_action(workspace, {"type": CHAT_SEND, "subject_id": "s1", "model_id": "m1", "content": "第一问"}, now=1004, id_factory=lambda: next(first_ids))
    workspace = apply_action(first["workspace"], {"type": CHAT_STOP, "subject_id": "s1", "message_id": "assistant-1"}, now=1005)["workspace"]
    second_ids = iter(["user-2", "assistant-2"])
    second = apply_action(workspace, {"type": CHAT_SEND, "subject_id": "s1", "model_id": "m2", "content": "第二问"}, now=1006, id_factory=lambda: next(second_ids))
    chat = second["workspace"]["subjects"][0]["data"]["chat"]
    assert chat["messages"][1]["status"] == "stopped"
    assert chat["messages"][1]["model"]["model"] == "a"
    assert chat["messages"][3]["model"]["model"] == "b"
    assert chat["active_model_id"] == "m2"


def test_chat_state_is_isolated_between_subjects():
    workspace = initial_workspace(now=1000)
    workspace = apply_action(workspace, {"type": SUBJECT_CREATE, "name": "数学"}, now=1001, id_factory=lambda: "s1")["workspace"]
    workspace = apply_action(workspace, {"type": SUBJECT_CREATE, "name": "英语"}, now=1002, id_factory=lambda: "s2")["workspace"]
    workspace = apply_action(workspace, {"type": MODEL_ADD, "provider": "Fake", "model": "fake", "base_url": "http://x/v1"}, now=1003, id_factory=lambda: "m1")["workspace"]
    result = apply_action(workspace, {"type": CHAT_SEND, "subject_id": "s1", "model_id": "m1", "content": "数学问题"}, now=1004, id_factory=lambda: "msg")
    assert len(result["workspace"]["subjects"][0]["data"]["chat"]["messages"]) == 2
    assert result["workspace"]["subjects"][1]["data"].get("chat", {}).get("messages", []) == []


def test_normalize_workspace_recovers_generating_message_as_stopped():
    raw = {
        "schema_version": 1,
        "active_subject_id": "s1",
        "models": [],
        "subjects": [{
            "id": "s1",
            "name": "数学",
            "created_at": 1,
            "updated_at": 2,
            "data": {"chat": {
                "active_model_id": "missing",
                "messages": [
                    {"id": "m1", "role": "user", "content": "你好", "created_at": 1},
                    {"id": "m2", "role": "assistant", "content": "半截", "status": "generating", "created_at": 1, "model": {}},
                ],
            }},
        }],
    }
    workspace, issue = normalize_workspace(raw, now=1000)
    assert issue is None
    chat = workspace["subjects"][0]["data"]["chat"]
    assert chat["active_model_id"] is None
    assert chat["messages"][1]["status"] == "stopped"
    assert chat["messages"][1]["content"] == "半截"


def test_normalize_workspace_recovers_processing_source_as_retryable_failure():
    raw = {
        "schema_version": 1,
        "active_subject_id": "s1",
        "models": [],
        "subjects": [{
            "id": "s1",
            "name": "数学",
            "created_at": 1,
            "updated_at": 2,
            "data": {
                "sources": [{
                    "id": "source-1",
                    "subject_id": "s1",
                    "display_name": "notes.md",
                    "media_kind": "markdown",
                    "status": "processing",
                    "current_version": {"id": "version-1", "status": "processing"},
                    "version_count": 1,
                    "failure": None,
                    "created_at": 1,
                    "updated_at": 2,
                }],
                "source_versions": [{
                    "id": "version-1",
                    "source_id": "source-1",
                    "number": 1,
                    "status": "processing",
                    "content_hash": "abc",
                    "mime_type": "text/markdown",
                    "size_bytes": 10,
                    "anchor_count": 0,
                    "cache_hit": False,
                    "assets": [],
                    "failure": None,
                    "created_at": 2,
                    "processed_at": None,
                }],
            },
        }],
    }

    workspace, issue = normalize_workspace(raw, now=1000)

    assert issue is None
    data = workspace["subjects"][0]["data"]
    source = data["sources"][0]
    version = data["source_versions"][0]
    assert source["status"] == "failed"
    assert source["current_version"]["status"] == "failed"
    assert source["failure"]["retryable"] is True
    assert version["status"] == "failed"
    assert version["failure"]["code"] == "SOURCE_PROCESSING_FAILED"
    assert version["processed_at"] == 1000
