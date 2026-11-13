from generated_models.json_types import JsonObject, json_array, json_object
from generated_models.loading import load, serialize
from generated_models.metadata import PakInventory


def test_sorted_manifest_order_survives_registry_roundtrip() -> None:
    paths = ["I.uasset", "Z.uasset", "a.uasset", "i.uasset"]
    collections = ("markers", "blueprints", "maps", "replacements", "arbitrary")
    assets: JsonObject = {
        name: [{"path": path, "hash": "hash"} for path in paths]
        for name in collections
    }
    for marker in json_array(assets["markers"]):
        json_object(marker)["associated_blueprints"] = [path for path in paths]
    raw: JsonObject = {
        "pak_name": "test.pak", "pak_path": "test.pak", "inventory": assets,
    }

    wire = serialize(load(raw, PakInventory))

    inventory = json_object(wire["inventory"])
    for name in collections:
        assert [json_object(asset)["path"] for asset in json_array(inventory[name])] == paths
    for marker in json_array(inventory["markers"]):
        assert json_object(marker)["associated_blueprints"] == paths
    assert serialize(load(wire, PakInventory)) == wire
