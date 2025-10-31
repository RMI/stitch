from typing import Final

from pluggy import HookspecMarker, HookimplMarker


PLUGIN_MARKER: Final[str] = "stitchcli"

hookspec = HookspecMarker(PLUGIN_MARKER)
hookimpl = HookimplMarker(PLUGIN_MARKER)



