from dataclasses import dataclass
from typing import List, Dict


@dataclass(frozen=True)
class BaseAsset:
    path: str
    hash: str
    object_class: str | None = None

    @staticmethod
    def from_dict(data: Dict) -> "BaseAsset":
        return BaseAsset(
            path=data["path"],
            hash=data["hash"],
            object_class=data.get("object_class"),
        )


@dataclass(frozen=True)
class BlueprintModInfo(BaseAsset):
    mod_name: str | None = None
    version: str | None = None
    author: str | None = None
    is_clientside: bool = False
    orphaned: bool = False

    @staticmethod
    def from_dict(data: Dict) -> "BlueprintModInfo":
        return BlueprintModInfo(
            path=data["path"],
            hash=data["hash"],
            object_class=data.get("object_class"),
            mod_name=data.get("mod_name"),
            version=data.get("version"),
            author=data.get("author"),
            is_clientside=data.get("is_clientside", False),
            orphaned=data.get("orphaned", False),
        )


@dataclass(frozen=True)
class GameMapInfo(BaseAsset):
    gamemode: str | None = None

    @staticmethod
    def from_dict(data: Dict) -> "GameMapInfo":
        return GameMapInfo(
            path=data["path"],
            hash=data["hash"],
            object_class=data.get("object_class"),
            gamemode=data.get("gamemode"),
        )


@dataclass(frozen=True)
class AssetReplacementInfo(BaseAsset):
    @staticmethod
    def from_dict(data: Dict) -> "AssetReplacementInfo":
        return AssetReplacementInfo(
            path=data["path"],
            hash=data["hash"],
            object_class=data.get("object_class"),
        )


@dataclass(frozen=True)
class ArbitraryAssetInfo(BaseAsset):
    mod_name: str | None = None

    @staticmethod
    def from_dict(data: Dict) -> "ArbitraryAssetInfo":
        return ArbitraryAssetInfo(
            path=data["path"],
            hash=data["hash"],
            object_class=data.get("object_class"),
            mod_name=data.get("mod_name"),
        )


@dataclass(frozen=True)
class ModMarkerInfo(BaseAsset):
    associated_blueprints: List[str] | None = None

    def __post_init__(self):
        if self.associated_blueprints is None:
            object.__setattr__(self, "associated_blueprints", [])

    @staticmethod
    def from_dict(data: Dict) -> "ModMarkerInfo":
        return ModMarkerInfo(
            path=data["path"],
            hash=data["hash"],
            object_class=data.get("object_class"),
            associated_blueprints=data.get("associated_blueprints", []),
        )


@dataclass(frozen=True)
class Manifest:
    markers: List[ModMarkerInfo]
    blueprints: List[BlueprintModInfo]
    maps: List[GameMapInfo]
    replacements: List[AssetReplacementInfo]
    arbitrary: List[ArbitraryAssetInfo]

    @staticmethod
    def from_dict(data: Dict) -> "Manifest":
        return Manifest(
            markers=[ModMarkerInfo.from_dict(m) for m in data.get("markers", [])],
            blueprints=[
                BlueprintModInfo.from_dict(b) for b in data.get("blueprints", [])
            ],
            maps=[GameMapInfo.from_dict(m) for m in data.get("maps", [])],
            replacements=[
                AssetReplacementInfo.from_dict(r) for r in data.get("replacements", [])
            ],
            arbitrary=[ArbitraryAssetInfo.from_dict(a) for a in data.get("arbitrary", [])],
        )

@dataclass(frozen=True)
class PakInventory:
    pak_path: str
    pak_hash: str | None
    inventory: Manifest

    @staticmethod
    def from_dict(data: Dict) -> "PakInventory":
        return PakInventory(
            pak_path=data["pak_path"],
            pak_hash=data.get("pak_hash"),
            inventory=Manifest.from_dict(data.get("inventory", {})),
        )

