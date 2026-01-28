import re
from typing import Any, Dict, List


def validate_json_schema(value: Any, schema: Dict[str, Any], path: str = "$") -> List[str]:
    """Minimal JSON Schema validator for tool inputs."""
    errors: List[str] = []
    if not schema:
        return errors

    schema_type = schema.get("type")
    if schema_type is None and "properties" in schema:
        schema_type = "object"

    if "enum" in schema:
        if value not in schema["enum"]:
            errors.append(f"{path}: value must be one of {schema['enum']}")
            return errors

    if schema_type == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: field required")
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value:
                errors.extend(validate_json_schema(value[key], subschema, f"{path}.{key}"))
        return errors

    if schema_type == "array":
        if not isinstance(value, list):
            return [f"{path}: expected array"]
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(validate_json_schema(item, item_schema, f"{path}[{idx}]"))
        return errors

    if schema_type == "string":
        if not isinstance(value, str):
            return [f"{path}: expected string"]
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: maxLength {schema['maxLength']}")
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], value):
                    errors.append(f"{path}: pattern mismatch")
            except re.error:
                errors.append(f"{path}: invalid pattern")
        return errors

    if schema_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return [f"{path}: expected number"]
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: maximum {schema['maximum']}")
        return errors

    if schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"{path}: expected integer"]
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: maximum {schema['maximum']}")
        return errors

    if schema_type == "boolean":
        if not isinstance(value, bool):
            return [f"{path}: expected boolean"]
        return errors

    if schema_type is None:
        return errors

    return errors


__all__ = ["validate_json_schema"]
