"""결과 JSON을 schema/forecast.v1.schema.json 으로 검증."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "forecast.v1.schema.json"


@lru_cache
def _root() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(obj, kind: str) -> None:
    """kind: forecast | summary | manifest | candles. 실패하면 jsonschema.ValidationError."""
    root = _root()
    reg = Registry().with_resource(root["$id"], Resource.from_contents(root))
    Draft202012Validator({"$ref": f"{root['$id']}#/$defs/{kind}"}, registry=reg).validate(obj)
