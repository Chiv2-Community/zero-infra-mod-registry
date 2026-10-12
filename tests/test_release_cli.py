import sys

import pytest

from zero_infra_mod_registry.main import main


@pytest.mark.parametrize("arguments", [
    ["add-package", "https://github.com/Test/Plugin"],
    ["process-registry-updates"],
    ["add-package-release", "https://github.com/Test/Plugin"],
    ["add-dll-release", "https://github.com/Test/Plugin"],
])
def test_cli_rejects_bulk_registration_and_missing_tags(arguments: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["zero-infra-mod-registry", *arguments])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
