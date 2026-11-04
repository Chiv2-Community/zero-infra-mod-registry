"""Registration policy for DLL and PAK release-asset selection."""
from collections.abc import Iterable


def selected_dll_name(names: Iterable[str], dll_file: str | None = None) -> str:
    """Select by filename before checking upload eligibility or downloading."""
    dlls = [name for name in names if name.lower().endswith(".dll")]
    if dll_file is not None:
        dlls = [name for name in dlls if name == dll_file]
        if len(dlls) != 1:
            raise ValueError(f"Requested DLL asset must match exactly one DLL: {dll_file!r}")
    if not dlls:
        raise ValueError("The release contains no DLL assets")
    if len(dlls) != 1:
        raise ValueError("A DLL release must contain exactly one DLL asset unless --dll-file selects one")
    return dlls[0]


def single_pak_name(names: Iterable[str], tag: str) -> str:
    """Preserve the registry's case-sensitive, exactly-one-PAK contract."""
    paks = [name for name in names if name.endswith(".pak")]
    if not paks:
        raise ValueError(f"No pak file found for release {tag}.")
    if len(paks) > 1:
        raise ValueError(f"Multiple pak files found for release {tag}.")
    return paks[0]
