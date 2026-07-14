"""Settings tab package (composed mixins)."""
from __future__ import annotations

from .build import SettingsBuildMixin
from .captcha import SettingsCaptchaMixin
from .cookies_pull import SettingsCookiePullMixin
from .cookies_status import SettingsCookieStatusMixin
from .paths import SettingsPathsMixin
from .persist_collect import SettingsCollectMixin
from .persist_sync import SettingsDbSyncMixin
from .shell import SettingsShellMixin


class SettingsTabMixin(
    SettingsShellMixin,
    SettingsBuildMixin,
    SettingsCaptchaMixin,
    SettingsCookiePullMixin,
    SettingsCookieStatusMixin,
    SettingsCollectMixin,
    SettingsDbSyncMixin,
    SettingsPathsMixin,
):
    """Settings: General prefs + Scrape sub-tab; DB, cookies, CAPTCHA, sync."""


__all__ = ["SettingsTabMixin"]
