"""Registry semantic checks and package adapters for the generated JSON codec."""
from generated_models.loading import JsonCodec
from generated_models.metadata import DllRelease, Plugin, PluginInfo
from zero_infra_mod_registry.models.dll_metadata import dll_package_dict, plugin_dict, validate_plugin_dependencies

CODEC = JsonCodec()
CODEC.register_validator(PluginInfo, validate_plugin_dependencies)
CODEC.register_serializer(Plugin, plugin_dict)
CODEC.register_serializer(DllRelease, dll_package_dict)

load = CODEC.load
serialize = CODEC.serialize
loads = CODEC.loads
dumps = CODEC.dumps
