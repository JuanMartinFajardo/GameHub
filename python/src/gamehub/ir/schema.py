# SPDX-License-Identifier: Apache-2.0
"""Validación de documentos GameIR contra el JSON Schema v0 (spec/ir/v0)."""

from __future__ import annotations

from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gamehub.ir.problems import Problem
from gamehub.ir.spec import SCHEMA_NAMES, load_schema


@cache
def _validator() -> Draft202012Validator:
    resources = [
        (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
        for schema in map(load_schema, SCHEMA_NAMES)
    ]
    registry: Registry[Any] = Registry().with_resources(resources)
    return Draft202012Validator(load_schema("ir"), registry=registry)


def schema_problems(doc: Any) -> list[Problem]:
    """Errores de forma según el JSON Schema; lista vacía si el documento es válido."""
    problems = set()
    for error in _validator().iter_errors(doc):
        detail = best_match([error]) or error
        path = "/".join(str(p) for p in detail.absolute_path)
        problems.add(Problem(path, detail.message))
    return sorted(problems)
