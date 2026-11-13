from generated_models.json_types import JsonObject, json_array, json_object
from generated_models.loading import load, serialize
from generated_models.metadata import PakInventory


def test_scanner_visibility_survives_inventory_roundtrip() -> None:
    """Do not turn a scanner's missing flag into an explicit GUI opt-out."""
    actors: list[JsonObject] = [
        {"path": "missing", "hash": "hash"},
        {"path": "null", "hash": "hash", "show_in_gui": None},
        {"path": "visible", "hash": "hash", "show_in_gui": True},
        {"path": "hidden", "hash": "hash", "show_in_gui": False, "is_hidden": True},
    ]
    raw: JsonObject = {
        "pak_name": "test.pak", "pak_path": "test.pak",
        "inventory": {"blueprints": [actor for actor in actors]},
    }

    inventory = load(raw, PakInventory)
    assert [actor.show_in_gui for actor in inventory.inventory.blueprints] == [None, None, True, False]

    wire = serialize(inventory)
    blueprints = json_array(json_object(wire["inventory"])["blueprints"])
    assert [json_object(actor).get("show_in_gui") for actor in blueprints] == [None, None, True, False]
    assert all("is_hidden" not in json_object(actor) for actor in blueprints)
    assert load(wire, PakInventory) == inventory
