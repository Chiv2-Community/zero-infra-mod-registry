"""Keep every Python JSON boundary on the strict shared decoder."""
import pytest

from mod_registry_core.json_types import decode_json, json_bool, json_int, json_string


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("template", ["{}", '{{"ignored":{}}}', '[{{"ignored":[{}]}}]'])
def test_decode_json_rejects_nonstandard_constants(constant: str, template: str) -> None:
    with pytest.raises(ValueError, match="Invalid JSON constant"):
        decode_json(template.format(constant))


def test_decode_json_preserves_standard_json() -> None:
    assert decode_json('[null,true,false,123,-1.5,"NaN",{"Infinity":"-Infinity"}]') == [
        None, True, False, 123, -1.5, "NaN", {"Infinity": "-Infinity"},
    ]
    # Overflowing standard JSON numbers are accepted by JSON.parse too.
    assert decode_json('1e400') == float("inf")
    assert decode_json('{"value":1,"value":2}') == {"value": 2}


def test_decode_json_does_not_coerce_field_types() -> None:
    with pytest.raises(ValueError, match="Expected a JSON integer"):
        json_int(decode_json('true'))
    with pytest.raises(ValueError, match="Expected a JSON boolean"):
        json_bool(decode_json('1'))
    with pytest.raises(ValueError, match="Expected a JSON string"):
        json_string(decode_json('123'))
