"""DeepFace tab package: Scan + Setup (composed mixins)."""
from __future__ import annotations

from .build_shell import DeepfaceShellMixin
from .scan_build import DeepfaceScanBuildMixin
from .scan_ctrl import DeepfaceScanCtrlMixin
from .scan_export import DeepfaceScanExportMixin
from .scan_opts import DeepfaceScanOptsMixin
from .scan_photo import DeepfaceScanPhotoMixin
from .scan_start import DeepfaceScanStartMixin
from .scan_verdict import DeepfaceScanVerdictMixin
from .setup_build import DeepfaceSetupBuildMixin
from .setup_log import DeepfaceSetupLogMixin
from .setup_run import DeepfaceSetupRunMixin
from .setup_status import DeepfaceSetupStatusMixin


class DeepfaceTabMixin(
    DeepfaceShellMixin,
    DeepfaceScanBuildMixin,
    DeepfaceScanOptsMixin,
    DeepfaceScanCtrlMixin,
    DeepfaceScanPhotoMixin,
    DeepfaceScanVerdictMixin,
    DeepfaceScanStartMixin,
    DeepfaceScanExportMixin,
    DeepfaceSetupBuildMixin,
    DeepfaceSetupLogMixin,
    DeepfaceSetupStatusMixin,
    DeepfaceSetupRunMixin,
):
    """DeepFace scan + setup UI."""


__all__ = ["DeepfaceTabMixin"]
