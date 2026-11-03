"""Handwritten manifest compatibility beyond generated field handling."""
from zero_infra_mod_registry.models.pak_manifest import ModMarkerInfo
from mod_registry_core.json_types import JsonObject


def test_marker_defaults_are_independent_and_null_compatible() -> None:
    first = ModMarkerInfo("first", "hash")
    second = ModMarkerInfo("second", "hash")
    assert first.associated_blueprints is not None
    first.associated_blueprints.append("/Game/Blueprint")
    assert second.associated_blueprints == []
    value: JsonObject = {"path": "marker", "hash": "hash", "associated_blueprints": None}
    assert ModMarkerInfo.from_dict(value).associated_blueprints == []
