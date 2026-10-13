"""Pak asset manifests and scanner inventories."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, override

from mod_registry_core.json_types import (
    JsonObject, JsonValue, json_array, json_bool, json_object, json_string,
    optional_string, string_array,
)


@dataclass(frozen=True)
class BaseAsset:
    path: str
    hash: str
    object_class: str | None = None
    class_path: str | None = None

    @staticmethod
    def from_dict(value: JsonValue) -> BaseAsset:
        data = json_object(value)
        return BaseAsset(json_string(data["path"]), json_string(data["hash"]),
                         optional_string(data.get("object_class")), optional_string(data.get("class_path")))

    def asdict(self) -> JsonObject:
        return {"path": self.path, "hash": self.hash,
                "object_class": self.object_class, "class_path": self.class_path}


@dataclass(frozen=True)
class BlueprintModInfo(BaseAsset):
    mod_name: str | None = None
    version: str | None = None
    author: str | None = None
    mod_description: str | None = None
    mod_repo_url: str | None = None
    silent_load: bool = False
    show_in_gui: bool = False
    enable_by_default: bool = False
    is_client_side: bool = False
    online_only: bool = False
    host_only: bool = False
    allow_on_frontend: bool = False
    is_hidden: bool = False

    @staticmethod
    @override
    def from_dict(value: JsonValue) -> BlueprintModInfo:
        data = json_object(value)
        base = BaseAsset.from_dict(data)
        return BlueprintModInfo(
            path=base.path, hash=base.hash, object_class=base.object_class, class_path=base.class_path,
            mod_name=optional_string(data.get("mod_name")), version=optional_string(data.get("version")),
            author=optional_string(data.get("author")), mod_description=optional_string(data.get("mod_description")),
            mod_repo_url=optional_string(data.get("mod_repo_url")),
            silent_load=json_bool(data.get("silent_load", False)), show_in_gui=json_bool(data.get("show_in_gui", False)),
            enable_by_default=json_bool(data.get("enable_by_default", False)),
            is_client_side=json_bool(data.get("is_client_side", False)), online_only=json_bool(data.get("online_only", False)),
            host_only=json_bool(data.get("host_only", False)), allow_on_frontend=json_bool(data.get("allow_on_frontend", False)),
            is_hidden=json_bool(data.get("is_hidden", False)),
        )

    @override
    def asdict(self) -> JsonObject:
        return {**super().asdict(), "mod_name": self.mod_name, "version": self.version,
                "author": self.author, "mod_description": self.mod_description, "mod_repo_url": self.mod_repo_url,
                "silent_load": self.silent_load, "show_in_gui": self.show_in_gui,
                "enable_by_default": self.enable_by_default, "is_client_side": self.is_client_side,
                "online_only": self.online_only, "host_only": self.host_only,
                "allow_on_frontend": self.allow_on_frontend, "is_hidden": self.is_hidden}


@dataclass(frozen=True)
class GameMapInfo(BaseAsset):
    game_mode: str | None = None
    map_name: str | None = None
    defending_faction: str | None = None
    attacking_faction: str | None = None
    game_mode_type: str | None = None

    @staticmethod
    @override
    def from_dict(value: JsonValue) -> GameMapInfo:
        data = json_object(value)
        base = BaseAsset.from_dict(data)
        return GameMapInfo(path=base.path, hash=base.hash, object_class=base.object_class, class_path=base.class_path,
                           game_mode=optional_string(data.get("game_mode")), map_name=optional_string(data.get("map_name")),
                           defending_faction=optional_string(data.get("defending_faction")),
                           attacking_faction=optional_string(data.get("attacking_faction")),
                           game_mode_type=optional_string(data.get("game_mode_type")))

    @override
    def asdict(self) -> JsonObject:
        return {**super().asdict(), "game_mode": self.game_mode, "map_name": self.map_name,
                "defending_faction": self.defending_faction, "attacking_faction": self.attacking_faction,
                "game_mode_type": self.game_mode_type}


@dataclass(frozen=True)
class AssetReplacementInfo(BaseAsset):
    @staticmethod
    @override
    def from_dict(value: JsonValue) -> AssetReplacementInfo:
        base = BaseAsset.from_dict(value)
        return AssetReplacementInfo(base.path, base.hash, base.object_class, base.class_path)


@dataclass(frozen=True)
class ArbitraryAssetInfo(BaseAsset):
    mod_name: str | None = None

    @staticmethod
    @override
    def from_dict(value: JsonValue) -> ArbitraryAssetInfo:
        data = json_object(value)
        base = BaseAsset.from_dict(data)
        return ArbitraryAssetInfo(base.path, base.hash, base.object_class, base.class_path,
                                  optional_string(data.get("mod_name")))

    @override
    def asdict(self) -> JsonObject:
        return {**super().asdict(), "mod_name": self.mod_name}


@dataclass(frozen=True)
class ModMarkerInfo(BaseAsset):
    associated_blueprints: List[str] = field(default_factory=list)

    @staticmethod
    @override
    def from_dict(value: JsonValue) -> ModMarkerInfo:
        data = json_object(value)
        base = BaseAsset.from_dict(data)
        blueprints = data.get("associated_blueprints")
        return ModMarkerInfo(base.path, base.hash, base.object_class, base.class_path,
                             [] if blueprints is None else string_array(blueprints))

    @override
    def asdict(self) -> JsonObject:
        return {**super().asdict(), "associated_blueprints": [name for name in self.associated_blueprints]}


@dataclass(frozen=True)
class Manifest:
    markers: List[ModMarkerInfo]
    blueprints: List[BlueprintModInfo]
    maps: List[GameMapInfo]
    replacements: List[AssetReplacementInfo]
    arbitrary: List[ArbitraryAssetInfo]

    @staticmethod
    def from_dict(value: JsonValue) -> Manifest:
        data = json_object(value)
        return Manifest(
            markers=[ModMarkerInfo.from_dict(item) for item in json_array(data.get("markers", []))],
            blueprints=[BlueprintModInfo.from_dict(item) for item in json_array(data.get("blueprints", []))],
            maps=[GameMapInfo.from_dict(item) for item in json_array(data.get("maps", []))],
            replacements=[AssetReplacementInfo.from_dict(item) for item in json_array(data.get("replacements", []))],
            arbitrary=[ArbitraryAssetInfo.from_dict(item) for item in json_array(data.get("arbitrary", []))],
        )

    def asdict(self) -> JsonObject:
        return {"markers": [item.asdict() for item in self.markers],
                "blueprints": [item.asdict() for item in self.blueprints],
                "maps": [item.asdict() for item in self.maps],
                "replacements": [item.asdict() for item in self.replacements],
                "arbitrary": [item.asdict() for item in self.arbitrary]}


@dataclass(frozen=True)
class PakInventory:
    pak_name: str
    pak_path: str
    pak_hash: str | None
    inventory: Manifest

    @staticmethod
    def from_dict(value: JsonValue) -> PakInventory:
        data = json_object(value)
        return PakInventory(json_string(data["pak_name"]), json_string(data["pak_path"]),
                            optional_string(data.get("pak_hash")), Manifest.from_dict(data.get("inventory", {})))
