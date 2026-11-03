"""Validated structuring and wire compatibility, outside generated models."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from collections.abc import Callable
from typing import TypeVar, cast

from cattrs import Converter
from generated_models.requests import RegistrationRequest
from mod_registry_core.json_types import JsonObject, JsonValue, json_object
from generated_models.metadata import (
    DllRelease, Plugin,
    ModInfo, ModMarkerInfo, PluginInfo,
    PluginRelease, Release,
)
from zero_infra_mod_registry.utils.schema_validation import validate_schema
from zero_infra_mod_registry.utils.validation_errors import validation_context

T = TypeVar("T")
CONVERTER = Converter(detailed_validation=False)


def _datetime(value: JsonValue, _: type[datetime]) -> datetime:
    with validation_context("release_date"):
        if not isinstance(value, str):
            raise ValueError("Expected ISO timestamp")
        return datetime.fromisoformat(value)


CONVERTER.register_structure_hook(datetime, _datetime)
def _datetime_string(value: datetime) -> str:
    return value.isoformat()


CONVERTER.register_unstructure_hook(datetime, _datetime_string)

SCHEMAS: dict[str, tuple[str, str]] = {
    "Dependency": ("mod-metadata", "dependency"), "ModInfo": ("mod-metadata", "modInfo"),
    "Release": ("mod-metadata", "modRelease"), "Mod": ("mod-metadata", "mod"),
    "PluginInfo": ("dll-metadata", "pluginInfo"), "PluginRelease": ("dll-metadata", "pluginRelease"),
    "BaseAsset": ("pak-manifest", "asset"), "BlueprintModInfo": ("pak-manifest", "blueprint"),
    "GameMapInfo": ("pak-manifest", "map"), "AssetReplacementInfo": ("pak-manifest", "replacement"),
    "ArbitraryAssetInfo": ("pak-manifest", "arbitrary"), "ModMarkerInfo": ("pak-manifest", "marker"),
    "Manifest": ("pak-manifest", "manifest"), "PakInventory": ("pak-manifest", "inventory"),
    "RegistrationRequest": ("request", "request"),
}


def _mod_info(value: JsonValue, _: type[ModInfo]) -> ModInfo:
    from zero_infra_mod_registry.models.mod_metadata import mod_dependencies_from_dict

    data = json_object(value)
    merged = mod_dependencies_from_dict(data)
    # Structure each declared field first; normalization never conceals bad input.
    info = _structure_mod_info(data, ModInfo)
    return replace(info, mod_dependencies=merged, dependencies=[])


def _plugin_info(value: JsonValue, _: type[PluginInfo]) -> PluginInfo:
    from zero_infra_mod_registry.models.dll_metadata import validate_plugin_dependencies

    info = _structure_plugin_info(value, PluginInfo)
    validate_plugin_dependencies(info)
    return info


def _marker(value: JsonValue, _: type[ModMarkerInfo]) -> ModMarkerInfo:
    data = json_object(value)
    if data.get("associated_blueprints") is None:
        data = {**data, "associated_blueprints": []}
    return _structure_marker(data, ModMarkerInfo)


_structure_mod_info = cast(Callable[[JsonValue, type[ModInfo]], ModInfo], CONVERTER.get_structure_hook(ModInfo))
_structure_plugin_info = cast(Callable[[JsonValue, type[PluginInfo]], PluginInfo], CONVERTER.get_structure_hook(PluginInfo))
_structure_marker = cast(Callable[[JsonValue, type[ModMarkerInfo]], ModMarkerInfo], CONVERTER.get_structure_hook(ModMarkerInfo))
CONVERTER.register_structure_hook(ModInfo, _mod_info)
CONVERTER.register_structure_hook(PluginInfo, _plugin_info)
CONVERTER.register_structure_hook(ModMarkerInfo, _marker)


def _release(value: JsonValue, _: type[Release]) -> Release:
    data = json_object(value)
    with validation_context(f"release {data['tag']}"):
        return _structure_release(value, Release)


_structure_release = cast(Callable[[JsonValue, type[Release]], Release], CONVERTER.get_structure_hook(Release))
CONVERTER.register_structure_hook(Release, _release)


def load(value: JsonValue, cls: type[T]) -> T:
    kind, definition = SCHEMAS[cls.__name__]
    validate_schema(value, kind, definition)
    return CONVERTER.structure(value, cls)


def serialize(value: T) -> JsonObject:
    if isinstance(value, (Plugin, DllRelease)):
        from zero_infra_mod_registry.models.dll_metadata import dll_package_dict, plugin_dict

        return plugin_dict(value) if isinstance(value, Plugin) else dll_package_dict(value)
    data = json_object(cast(JsonValue, CONVERTER.unstructure(value)))
    if isinstance(value, PluginInfo):
        data = {"$schema" if key == "field_schema" else key: item for key, item in data.items()
                if item is not None and not (key == "image_urls" and not item)}
    return data


# Nested serialization must use the same compatibility rules as top-level metadata.
def _unstructure_mod_info(value: ModInfo) -> JsonObject:
    from zero_infra_mod_registry.models.mod_metadata import mod_dependencies_from_dict

    data = _raw_mod_info(value)
    merged = mod_dependencies_from_dict(data)
    return {**data, "mod_dependencies": [serialize(dependency) for dependency in merged],
            "dependencies": [serialize(dependency) for dependency in merged]}


_raw_mod_info = cast(Callable[[ModInfo], JsonObject], CONVERTER.get_unstructure_hook(ModInfo))
CONVERTER.register_unstructure_hook(ModInfo, _unstructure_mod_info)
