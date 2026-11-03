"""Registry runtime checks and package adapters around generated loading."""
from collections.abc import Callable
from typing import TypeVar, cast

from generated_models.loading import load as load_model, make_converter, serialize as serialize_model
from generated_models.metadata import DllRelease, Plugin, PluginInfo, Release
from mod_registry_core.json_types import JsonObject, JsonValue, json_object
from zero_infra_mod_registry.utils.validation_errors import validation_context

T = TypeVar("T")
CONVERTER = make_converter()


def _plugin_info(value: JsonValue, _: type[PluginInfo]) -> PluginInfo:
    from zero_infra_mod_registry.models.dll_metadata import validate_plugin_dependencies

    info = _structure_plugin_info(value, PluginInfo)
    validate_plugin_dependencies(info)
    return info


_structure_plugin_info = cast(Callable[[JsonValue, type[PluginInfo]], PluginInfo], CONVERTER.get_structure_hook(PluginInfo))
CONVERTER.register_structure_hook(PluginInfo, _plugin_info)


def _release(value: JsonValue, _: type[Release]) -> Release:
    data = json_object(value)
    with validation_context(f"release {data['tag']}"):
        return _structure_release(value, Release)


_structure_release = cast(Callable[[JsonValue, type[Release]], Release], CONVERTER.get_structure_hook(Release))
CONVERTER.register_structure_hook(Release, _release)


def load(value: JsonValue, cls: type[T]) -> T:
    return load_model(value, cls, converter=CONVERTER)


def serialize(value: T) -> JsonObject:
    if isinstance(value, (Plugin, DllRelease)):
        from zero_infra_mod_registry.models.dll_metadata import dll_package_dict, plugin_dict

        return plugin_dict(value) if isinstance(value, Plugin) else dll_package_dict(value)
    return serialize_model(value, converter=CONVERTER)
