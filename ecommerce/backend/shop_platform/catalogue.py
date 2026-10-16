"""Load and validate the fixed experiment catalogue.

Operators can choose a scenario and its bounded parameters. They cannot
supply commands, code, container images, or a root-cause string.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .settings import get_settings

FORBIDDEN_FIELDS = {
    "command",
    "shell",
    "script",
    "code",
    "image",
    "docker",
    "sql",
    "query",
}
PARAMETER_FORBIDDEN = FORBIDDEN_FIELDS | {"expected_root_cause"}


class CatalogueError(ValueError):
    pass


def catalogue_file() -> Path:
    configured = get_settings().scenario_catalogue_path
    if configured:
        return Path(configured)
    packaged = Path(__file__).resolve().parents[2] / "scenarios" / "catalogue.json"
    if packaged.is_file():
        return packaged
    return Path("/scenarios/catalogue.json")


@lru_cache
def load_catalogue() -> dict:
    path = catalogue_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    for scenario in data["scenarios"]:
        if scenario["id"] in seen:
            raise CatalogueError(f"Duplicate scenario {scenario['id']}")
        seen.add(scenario["id"])
        if scenario["kind"] not in {"fault", "load"}:
            raise CatalogueError(f"Invalid kind for {scenario['id']}")
        if FORBIDDEN_FIELDS.intersection(scenario):
            raise CatalogueError(f"Forbidden field on {scenario['id']}")
        for name in scenario["parameters"]:
            if name in PARAMETER_FORBIDDEN:
                raise CatalogueError(f"Forbidden parameter {name}")
        if "expected_root_cause" not in scenario or not scenario["expected_root_cause"].strip():
            raise CatalogueError(f"Missing expected root cause for {scenario['id']}")
    return data


def scenarios_by_kind(kind: str) -> list[dict]:
    return [item for item in load_catalogue()["scenarios"] if item["kind"] == kind]


def get_scenario(scenario_id: str, kind: str) -> dict:
    for scenario in load_catalogue()["scenarios"]:
        if scenario["id"] == scenario_id and scenario["kind"] == kind:
            return scenario
    raise CatalogueError(f"Unknown {kind} scenario '{scenario_id}'")


def validate_selection(scenario_id: str, kind: str, target_service: str, raw: dict | None) -> dict:
    scenario = get_scenario(scenario_id, kind)
    if target_service not in scenario["targets"]:
        raise CatalogueError(
            f"{scenario_id} cannot target {target_service}. "
            f"Choose one of: {', '.join(scenario['targets'])}"
        )
    incoming = raw or {}
    if not isinstance(incoming, dict):
        raise CatalogueError("Parameters must be an object")
    unknown = set(incoming) - set(scenario["parameters"])
    if unknown:
        raise CatalogueError(f"Unknown parameters: {', '.join(sorted(unknown))}")
    if PARAMETER_FORBIDDEN.intersection(incoming):
        raise CatalogueError("That parameter is not allowed")
    cleaned: dict[str, int] = {}
    for name, rule in scenario["parameters"].items():
        value = incoming.get(name, rule["default"])
        if isinstance(value, bool) or not isinstance(value, int):
            raise CatalogueError(f"{name} must be an integer")
        if value < rule["min"] or value > rule["max"]:
            raise CatalogueError(
                f"{name} must be between {rule['min']} and {rule['max']}"
            )
        cleaned[name] = value
    return cleaned
