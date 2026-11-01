"""Loads JSON strictly and validates documents against the shared schemas."""

import hashlib
import json
import os
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012

JsonDict = dict[str, Any]


class ContractError(ValueError):
    """A file or message does not satisfy the Roverloom contract."""


def repo_root() -> Path:
    """Return the checkout holding schemas/. Set ROVERLOOM_HOME to override."""
    configured = os.environ.get("ROVERLOOM_HOME")
    root = Path(configured) if configured else Path(__file__).resolve().parents[3]
    if not (root / "schemas").is_dir():
        raise ContractError(f"no schemas directory under {root}; set ROVERLOOM_HOME")
    return root


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> JsonDict:
    result: JsonDict = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(name: str) -> None:
    raise ContractError(f"non-finite number is not allowed: {name}")


def parse_json(text: str) -> Any:
    """Parse JSON, rejecting NaN, Infinity, and duplicate keys."""
    try:
        return json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant
        )
    except json.JSONDecodeError as error:
        raise ContractError(f"invalid JSON: {error}") from error


def dump_json(document: Any) -> str:
    """Serialize canonically, so that equal documents produce equal bytes."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)


def load_json_file(path: Path) -> JsonDict:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    try:
        document = parse_json(text)
    except ContractError as error:
        raise ContractError(f"{path}: {error}") from error
    if not isinstance(document, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return document


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@cache
def _validators() -> dict[str, Draft202012Validator]:
    schemas = {
        path.name.removesuffix(".schema.json"): load_json_file(path)
        for path in sorted((repo_root() / "schemas").glob("*.schema.json"))
    }
    registry: Registry[Any] = Registry().with_resources(
        (schema["$id"], DRAFT202012.create_resource(schema)) for schema in schemas.values()
    )
    return {
        name: Draft202012Validator(schema, registry=registry) for name, schema in schemas.items()
    }


def validate(schema_name: str, document: Any, context: str = "") -> None:
    """Raise ContractError if the document does not conform."""
    validators = _validators()
    if schema_name not in validators:
        raise ContractError(f"unknown schema: {schema_name}")
    errors = sorted(validators[schema_name].iter_errors(document), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "(root)"
        prefix = f"{context}: " if context else ""
        raise ContractError(f"{prefix}{schema_name} invalid at {location}: {first.message}")
