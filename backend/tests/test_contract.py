import re
from pathlib import Path

import yaml
from fastapi.openapi.models import OpenAPI, Schema


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = PROJECT_ROOT / "docs" / "api" / "openapi.yaml"
SCHEMAS_PATH = PROJECT_ROOT / "docs" / "api" / "schemas.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
TICKETS = {f"{number:02d}" for number in range(1, 16)}


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
        if not set(target_operation["x-tickets"]) & {f"{number:02d}" for number in range(1, 16)}:
            continue
        actual_operation = implemented["paths"][path][method]
        assert actual_operation["operationId"] == target_operation["operationId"]

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

        target_media = set(target_operation.get("requestBody", {}).get("content", {}))
        actual_media = set(actual_operation.get("requestBody", {}).get("content", {}))
        assert actual_media == target_media
