#!/usr/bin/env python3
"""Validate an OpenAPI contract against the standard, then project rules."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
    from openapi_spec_validator import OpenAPIV30SpecValidator
    from referencing.exceptions import Unresolvable
except ModuleNotFoundError:  # pragma: no cover - environment-specific failure
    requirements = Path(__file__).resolve().parents[1] / "requirements.txt"
    print(f'ERROR: validator dependencies are missing (python -m pip install -r "{requirements}").')
    raise SystemExit(2)


HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
PATH_PARAMETER = re.compile(r"\{([^{}]+)\}")


def resolve_pointer(document: Any, reference: str) -> Any:
    if not reference.startswith("#/"):
        raise KeyError(reference)

    current = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(reference)
    return current


def iter_references(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str):
            yield reference
        for child in value.values():
            yield from iter_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_references(child)


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from iter_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_strings(child)


def resolve_parameter(document: dict[str, Any], parameter: Any) -> Any:
    if isinstance(parameter, dict) and isinstance(parameter.get("$ref"), str):
        reference = parameter["$ref"]
        if reference.startswith("#/"):
            try:
                return resolve_pointer(document, reference)
            except KeyError:
                return parameter
    return parameter


def validate_standard(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def collect(iterator: Iterable[Any]) -> None:
        for error in iterator:
            parts = [
                str(part).replace("~", "~0").replace("/", "~1")
                for part in error.absolute_path
            ]
            location = "/" + "/".join(parts) if parts else "<root>"
            errors.append(
                f"[OPENAPI_STANDARD] {location}: {type(error).__name__}: {error.message}"
            )

    try:
        # 0.7.2 continues into semantic checks even after structural errors;
        # reject those first so malformed objects cannot crash that traversal.
        collect(OpenAPIV30SpecValidator.schema_validator.iter_errors(document))
        if errors:
            return errors
        collect(OpenAPIV30SpecValidator(document).iter_errors())
    except (Unresolvable, RecursionError) as error:
        errors.append(
            f"[OPENAPI_STANDARD] reference validation could not complete: {type(error).__name__}"
        )
    return errors


def validate(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["document root must be an object"]
    if document.get("openapi") != "3.0.3":
        return ["openapi must declare version 3.0.3"]

    # Single-file contracts must not depend on external files or network access.
    errors: list[str] = []
    for reference in sorted(set(iter_references(document))):
        if not reference.startswith("#/"):
            errors.append(f"[REFERENCE] only local #/ references are supported: {reference}")
            continue
        try:
            resolve_pointer(document, reference)
        except KeyError:
            errors.append(f"[REFERENCE] unresolved $ref: {reference}")
    if errors:
        return errors

    errors = validate_standard(document)
    if errors:
        return errors
    return validate_project_rules(document)


def validate_project_rules(document: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["document root must be an object"]

    version = document.get("openapi")
    if not isinstance(version, str) or not version.startswith("3.0."):
        errors.append("openapi must declare a 3.0.x version")

    info = document.get("info")
    if not isinstance(info, dict) or not info.get("title") or not info.get("version"):
        errors.append("info.title and info.version are required")

    assumptions = document.get("x-ai-assumptions")
    if assumptions is not None and (
        not isinstance(assumptions, list)
        or len(assumptions) > 5
        or any(not isinstance(item, str) or not item.strip() for item in assumptions)
    ):
        errors.append("x-ai-assumptions must be an array of at most five non-empty strings")

    if any(re.search(r"\b(?:TODO|TBD)\b", value) for value in iter_strings(document)):
        errors.append("placeholder text such as TODO or TBD is not allowed")

    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        errors.append("paths must contain at least one path item")
        paths = {}

    operation_ids: dict[str, str] = {}
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            errors.append(f"invalid path item: {path!r}")
            continue

        path_parameters = path_item.get("parameters", [])
        if not isinstance(path_parameters, list):
            path_parameters = []

        for method, operation in path_item.items():
            if str(method).lower() not in HTTP_METHODS:
                continue
            location = f"{str(method).upper()} {path}"
            if not isinstance(operation, dict):
                errors.append(f"{location}: operation must be an object")
                continue

            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                errors.append(f"{location}: operationId is required")
            elif operation_id in operation_ids:
                errors.append(
                    f"{location}: duplicate operationId '{operation_id}' "
                    f"(already used by {operation_ids[operation_id]})"
                )
            else:
                operation_ids[operation_id] = location

            responses = operation.get("responses")
            if not isinstance(responses, dict) or not any(
                re.fullmatch(r"2\d\d", str(status)) for status in responses
            ):
                errors.append(f"{location}: at least one explicit 2xx response is required")

            operation_parameters = operation.get("parameters", [])
            if not isinstance(operation_parameters, list):
                operation_parameters = []
            effective_parameters = [
                resolve_parameter(document, parameter)
                for parameter in [*path_parameters, *operation_parameters]
            ]
            for parameter_name in PATH_PARAMETER.findall(path):
                matches = [
                    parameter
                    for parameter in effective_parameters
                    if isinstance(parameter, dict)
                    and parameter.get("name") == parameter_name
                    and parameter.get("in") == "path"
                ]
                if not matches:
                    errors.append(f"{location}: path parameter '{parameter_name}' is not defined")
                elif not any(parameter.get("required") is True for parameter in matches):
                    errors.append(f"{location}: path parameter '{parameter_name}' must be required")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_openapi.py <openapi.yaml>")
        return 2

    path = Path(sys.argv[1])
    if not path.is_file():
        print(f"ERROR: file not found: {path}")
        return 2

    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        print(f"ERROR: cannot parse YAML: {error}")
        return 1

    errors = validate(document)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"OK: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
