import re
from pathlib import Path

import yaml
from fastapi.openapi.models import OpenAPI, Schema


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = PROJECT_ROOT / "docs" / "api" / "openapi.yaml"
SCHEMAS_PATH = PROJECT_ROOT / "docs" / "api" / "schemas.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
TICKETS = {f"{number:02d}" for number in range(1, 17)}


def load_contract():
    return (
        yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8")),
        yaml.safe_load(SCHEMAS_PATH.read_text(encoding="utf-8")),
    )


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def resolve_pointer(document, pointer):
    value = document
    path = pointer.removeprefix("#").removeprefix("/")
    for part in path.split("/") if path else []:
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def resolve_ref(reference, openapi, schemas, current_document):
    if reference.startswith("./schemas.yaml#"):
        return resolve_pointer(schemas, reference.split("#", 1)[1])
    if reference.startswith("#"):
        return resolve_pointer(current_document, reference)
    raise AssertionError(f"unsupported contract reference: {reference}")


def normalized_schema(value):
    if isinstance(value, dict):
        if "$ref" in value:
            return {"$ref": value["$ref"].rsplit("/", 1)[-1]}
        return {
            key: normalized_schema(child)
            for key, child in value.items()
            if key != "title"
        }
    if isinstance(value, list):
        return [normalized_schema(child) for child in value]
    return value


def iter_operations(openapi):
    for path, path_item in openapi["paths"].items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS:
                yield path, method, operation


def test_contract_is_parseable_and_all_references_resolve():
    openapi, schemas = load_contract()

    assert openapi["openapi"] == "3.1.0"
    assert openapi["info"]["x-contract-status"] == "target"
    OpenAPI.model_validate(openapi)
    for schema in schemas["components"]["schemas"].values():
        Schema.model_validate(schema)

    for document in (openapi, schemas):
        for value in walk(document):
            if isinstance(value, dict) and "$ref" in value:
                resolve_ref(value["$ref"], openapi, schemas, document)


def test_operations_are_unique_and_cover_every_ticket():
    openapi, _ = load_contract()
    operations = list(iter_operations(openapi))
    operation_ids = [operation["operationId"] for _, _, operation in operations]
    covered_tickets = {
        ticket
        for _, _, operation in operations
        for ticket in operation.get("x-tickets", [])
    }

    assert len(operation_ids) == len(set(operation_ids))
    assert all(operation.get("x-tickets") for _, _, operation in operations)
    assert covered_tickets == TICKETS


def test_operations_declare_success_and_structured_error_responses():
    openapi, schemas = load_contract()

    for path, method, operation in iter_operations(openapi):
        responses = operation.get("responses", {})
        assert responses, f"missing responses in {method.upper()} {path}"
        assert any(str(status).startswith("2") for status in responses), f"missing success response in {method.upper()} {path}"
        for status, response in responses.items():
            if "$ref" in response:
                response = resolve_ref(response["$ref"], openapi, schemas, openapi)
            assert response.get("description"), f"missing response description for {status} in {method.upper()} {path}"


def test_every_path_parameter_is_declared_once():
    openapi, schemas = load_contract()

    for path, path_item in openapi["paths"].items():
        expected = set(re.findall(r"{([^}]+)}", path))
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            parameters = [*path_item.get("parameters", []), *operation.get("parameters", [])]
            actual = []
            for parameter in parameters:
                if "$ref" in parameter:
                    parameter = resolve_ref(parameter["$ref"], openapi, schemas, openapi)
                if parameter.get("in") == "path":
                    actual.append(parameter["name"])
                    assert parameter["required"] is True
            assert set(actual) == expected, f"{method.upper()} {path}"
            assert len(actual) == len(set(actual)), f"duplicate path parameter in {method.upper()} {path}"


def test_sensitive_and_answer_visibility_boundaries_are_explicit():
    _, schemas = load_contract()
    definitions = schemas["components"]["schemas"]

    assert "api_key" not in definitions["ModelService"]["properties"]
    assert definitions["ModelServiceInput"]["properties"]["api_key"]["writeOnly"] is True

    attempt_question = definitions["AttemptQuestion"]
    assert {"answer", "explanation", "evidence"}.isdisjoint(attempt_question["properties"])
    assert "feedback" in definitions["Attempt"]["required"]
    assert definitions["RenderQuestion"]["properties"]["solution"]["description"] == "edition=questions 时必须为 null。"


def test_issue16_contract_covers_context_lifecycle_boundaries():
    openapi, schemas = load_contract()
    paths = openapi["paths"]
    assert "/api/subjects/{subject_id}/sessions" in paths
    assert "/api/sessions/{session_id}/sources/{version_id}" in paths
    assert "/api/subjects/{subject_id}/attachments" in paths
    assert "/api/models/discover" in paths
    assert "/api/subjects/{subject_id}/documents" in paths
    assert "/api/attempts/{attempt_id}/complete" in paths
    assert "source_context" in schemas["components"]["schemas"]["ChatMessage"]["properties"]
    assert "only_use_specified_sources" in schemas["components"]["schemas"]["ChatMessageInput"]["properties"]
    assert "completion_status" in schemas["components"]["schemas"]["Attempt"]["properties"]
    assert "grading_status" in schemas["components"]["schemas"]["Attempt"]["properties"]

    example_schemas = {
        "OperationAccepted",
        "SourceAnchorList",
        "SessionInput",
        "SessionPatch",
        "Session",
        "SessionList",
        "SessionSource",
        "SessionSourceList",
        "SessionSourceInput",
        "SessionSourcePatch",
        "TempAttachment",
        "ModelService",
        "ModelDiscoveryInput",
        "ModelDiscoveryResponse",
        "ModelSelection",
        "AiDocumentCreateInput",
        "AiDocumentVersion",
        "AiDocumentVersionList",
        "AiDocument",
        "AiDocumentList",
        "AiDocumentRevisionInput",
        "AiDocumentRevisionProposal",
        "AiDocumentRevisionProposalList",
        "Attempt",
    }
    definitions = schemas["components"]["schemas"]
    assert all("example" in definitions[name] for name in example_schemas)


def test_issue16_request_models_keep_key_closed_constraints(tmp_path):
    from backend.app.main import create_app

    _, target_schemas = load_contract()
    target = target_schemas["components"]["schemas"]
    actual = create_app(data_dir=tmp_path).openapi()["components"]["schemas"]

    unique_fields = {
        "SessionInput": ["source_version_ids"],
        "ChatMessageInput": ["source_version_ids", "focused_source_version_ids", "attachment_ids"],
        "AiDocumentCreateInput": ["source_version_ids"],
    }
    for model_name, field_names in unique_fields.items():
        for field_name in field_names:
            assert target[model_name]["properties"][field_name]["uniqueItems"] is True
            assert actual[model_name]["properties"][field_name]["uniqueItems"] is True

    assert "null" not in str(actual["SessionInput"]["properties"]["title"])
    assert {"completion_status", "grading_status"} <= set(actual["Attempt"]["required"])
    assert {"before", "after"} <= set(actual["AiDocumentChange"]["required"])
    assert {
        "source_version_ids",
        "focused_source_version_ids",
        "only_use_specified_sources",
        "grounding_mode",
        "attachment_ids",
        "citations",
    } <= set(actual["MessageSourceContext"]["required"])
    assert "source_context" in actual["ChatMessage"]["required"]
    assert actual["Session"]["properties"]["source_version_ids"]["uniqueItems"] is True
    discovery = actual["ModelDiscoveryInput"]["properties"]
    assert discovery["base_url"]["format"] == "uri"
    assert "minLength" not in discovery["base_url"]
    assert "maxLength" not in discovery["base_url"]
    assert discovery["api_key"]["writeOnly"] is True
    assert "default" not in discovery["api_key"]
    capabilities_ref = actual["DiscoveredModel"]["properties"]["capabilities"]["$ref"]
    capabilities = actual[capabilities_ref.rsplit("/", 1)[-1]]
    assert capabilities["additionalProperties"] is False
    assert set(capabilities["properties"]) == {"text", "vision"}


def test_error_codes_are_closed_and_upper_snake_case():
    _, schemas = load_contract()
    error_codes = schemas["components"]["schemas"]["ErrorCode"]["enum"]

    assert len(error_codes) == len(set(error_codes))
    assert all(re.fullmatch(r"[A-Z][A-Z0-9_]+", code) for code in error_codes)


def test_current_backend_routes_are_present_in_target_contract(tmp_path):
    from backend.app.main import create_app

    target, _ = load_contract()
    implemented = create_app(data_dir=tmp_path).openapi()

    for path, path_item in implemented["paths"].items():
        assert path in target["paths"]
        for method in path_item:
            if method in HTTP_METHODS:
                assert method in target["paths"][path]


def test_implemented_backend_operations_match_target_contract(tmp_path):
    from backend.app.main import create_app

    target, _ = load_contract()
    implemented = create_app(data_dir=tmp_path).openapi()

    for path, method, target_operation in iter_operations(target):
        if not set(target_operation["x-tickets"]) & TICKETS:
            continue
        actual_operation = implemented["paths"][path][method]
        assert actual_operation["operationId"] == target_operation["operationId"]

        target_errors = {status for status in target_operation["responses"] if not str(status).startswith("2")}
        actual_errors = {status for status in actual_operation["responses"] if not str(status).startswith("2")}
        assert target_errors <= actual_errors
        if "16" in target_operation["x-tickets"]:
            assert actual_errors == target_errors

        target_success = {status for status in target_operation["responses"] if str(status).startswith("2")}
        actual_success = {status for status in actual_operation["responses"] if str(status).startswith("2")}
        assert actual_success == target_success

        for status in target_success:
            target_schema = (
                target_operation["responses"][status]
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            actual_schema = (
                actual_operation["responses"][status]
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if target_schema and "$ref" in target_schema:
                assert actual_schema["$ref"].rsplit("/", 1)[-1] == target_schema["$ref"].rsplit("/", 1)[-1]
            elif target_schema:
                assert normalized_schema(actual_schema) == normalized_schema(target_schema)

        target_media = set(target_operation.get("requestBody", {}).get("content", {}))
        actual_media = set(actual_operation.get("requestBody", {}).get("content", {}))
        assert actual_media == target_media
