from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def to_openapi_30(value: Any) -> Any:
    """Convert the JSON Schema constructs emitted by this API to OpenAPI 3.0."""
    if isinstance(value, list):
        return [to_openapi_30(item) for item in value]
    if not isinstance(value, dict):
        return value
    schema = dict(value)
    alternatives = schema.get("anyOf", [])
    non_null = [item for item in alternatives if item != {"type": "null"}]
    if alternatives and len(non_null) != len(alternatives):
        if len(non_null) != 1:
            raise ValueError("Unsupported nullable union in OpenAPI schema")
        schema.pop("anyOf")
        schema = {**non_null[0], **schema, "nullable": True}
    schema = {key: to_openapi_30(item) for key, item in schema.items()}
    for exclusive, inclusive in (
        ("exclusiveMinimum", "minimum"), ("exclusiveMaximum", "maximum")
    ):
        bound = schema.get(exclusive)
        if isinstance(bound, (int, float)) and not isinstance(bound, bool):
            schema[inclusive] = bound
            schema[exclusive] = True
    if "const" in schema:
        schema["enum"] = [schema.pop("const")]
    if "$ref" in schema and len(schema) > 1:
        schema["allOf"] = [{"$ref": schema.pop("$ref")}]
    if schema.get("type") == "null" or isinstance(schema.get("type"), list):
        raise ValueError("Unsupported type in OpenAPI 3.0 schema")
    return schema


def install_openapi(app: FastAPI) -> None:
    app.openapi_version = "3.0.3"

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = to_openapi_30(get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
                openapi_version="3.0.3",
            ))
        return app.openapi_schema

    app.openapi = openapi
