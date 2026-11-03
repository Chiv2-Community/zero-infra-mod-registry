"""Handwritten manifest compatibility beyond generated field handling."""
from generated_models.metadata import ModMarkerInfo
from zero_infra_mod_registry.models.loading import load
from mod_registry_core.json_types import JsonObject


def test_marker_defaults_are_independent_and_null_compatible() -> None:
    first = ModMarkerInfo("first", "hash")
    second = ModMarkerInfo("second", "hash")
    assert first.associated_blueprints is not None
    first.associated_blueprints.append("/Game/Blueprint")
    assert second.associated_blueprints == []
    value: JsonObject = {"path": "marker", "hash": "hash", "associated_blueprints": None}
    assert load(value, ModMarkerInfo).associated_blueprints == []
