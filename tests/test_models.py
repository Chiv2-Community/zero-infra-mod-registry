from dataclasses import replace
import json

import pytest
from zero_infra_mod_registry.models import Mod
from zero_infra_mod_registry.models.manifest import (
    ArbitraryAssetInfo, AssetReplacementInfo, BlueprintModInfo, GameMapInfo, Manifest, ModMarkerInfo,
)
from zero_infra_mod_registry.utils.json_types import JsonObject, JsonValue, decode_json
from tests.fakes import mod_fixture


def test_full_asset_manifest_round_trip() -> None:
    manifest = Manifest(
        markers=[ModMarkerInfo("/Game/Marker", "markerhash", "MarkerClass", "/Game/MarkerClass", ["/Game/Blueprint"])],
        blueprints=[BlueprintModInfo(
            path="/Game/Blueprint", hash="blueprinthash", object_class="BlueprintClass", class_path="/Game/BlueprintClass",
            mod_name="Mod", version="1.0.0", author="Author", mod_description="Description", mod_repo_url="https://example.com/mod",
            silent_load=True, show_in_gui=True, enable_by_default=True, is_client_side=True,
            online_only=True, host_only=True, allow_on_frontend=True, is_hidden=True,
        )],
        maps=[GameMapInfo("/Game/Map", "maphash", "MapClass", "/Game/MapClass", "Mode", "Map", "Agatha", "Mason", "TO")],
        replacements=[AssetReplacementInfo("/Game/Replacement", "replacementhash", "AssetClass", "/Game/AssetClass")],
        arbitrary=[ArbitraryAssetInfo("/Game/Asset", "assethash", "AssetClass", "/Game/AssetClass", "Mod")],
    )
    assert Manifest.from_dict(decode_json(json.dumps(manifest.asdict()))) == manifest


def test_mod_metadata_round_trip_preserves_dates_and_dependencies() -> None:
    original = mod_fixture()
    manifest = Manifest([], [], [GameMapInfo("/Game/Map", "hash", attacking_faction="Mason")], [], [])
    mod = replace(original, releases=[replace(original.releases[0], manifest=manifest)])
    assert Mod.from_dict(decode_json(json.dumps(mod.asdict()))) == mod


@pytest.mark.parametrize("field,value", [
    ("path", None), ("hash", False), ("class_path", 7), ("silent_load", "true"), ("show_in_gui", 1),
])
def test_asset_parser_rejects_incorrect_scalar_types(field: str, value: JsonValue) -> None:
    invalid: JsonObject = {"path": "/Game/Blueprint", "hash": "hash", field: value}
    with pytest.raises(ValueError):
        BlueprintModInfo.from_dict(invalid)


@pytest.mark.parametrize("value", [None, "markers", {"markers": "not an array"}, {"blueprints": [None]}])
def test_manifest_parser_rejects_incorrect_container_types(value: JsonValue) -> None:
    with pytest.raises(ValueError):
        Manifest.from_dict(value)


def test_marker_defaults_are_independent_and_null_compatible() -> None:
    first = ModMarkerInfo("first", "hash")
    second = ModMarkerInfo("second", "hash")
    first.associated_blueprints.append("/Game/Blueprint")
    assert second.associated_blueprints == []
    value: JsonObject = {"path": "marker", "hash": "hash", "associated_blueprints": None}
    assert ModMarkerInfo.from_dict(value).associated_blueprints == []
