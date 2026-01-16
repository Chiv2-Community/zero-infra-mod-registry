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
    mod_description: str | None = None
    mod_repo_url: str | None = None
    silent_load: bool = False
    show_in_gui: bool = False
    is_client_side: bool = False
    online_only: bool = False
    host_only: bool = False
    allow_on_frontend: bool = False
    is_hidden: bool = False
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
            mod_description=data.get("mod_description"),
            mod_repo_url=data.get("mod_repo_url"),
            silent_load=data.get("silent_load", False),
            show_in_gui=data.get("show_in_gui", False),
            is_client_side=data.get("is_client_side", False),
            online_only=data.get("online_only", False),
            host_only=data.get("host_only", False),
            allow_on_frontend=data.get("allow_on_frontend", False),
            is_hidden=data.get("is_hidden", False),
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
    pak_name: str
    pak_path: str
    pak_hash: str | None
    inventory: Manifest

    @staticmethod
    def from_dict(data: Dict) -> "PakInventory":
        return PakInventory(
            pak_name=data["pak_name"],
            pak_path=data["pak_path"],
            pak_hash=data.get("pak_hash"),
            inventory=Manifest.from_dict(data.get("inventory", {})),
        )

