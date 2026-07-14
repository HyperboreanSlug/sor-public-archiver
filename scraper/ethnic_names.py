"""Ethnic surname database (composed)."""
from __future__ import annotations

from scraper.ethnic_names_base import *  # noqa: F401,F403
from scraper.ethnic_names_init import EthnicInitMixin
from scraper.ethnic_names_load_json import EthnicLoadJsonMixin
from scraper.ethnic_names_lookup import EthnicLookupMixin
from scraper.ethnic_names_signals import EthnicSignalsMixin
from scraper.ethnic_names_classify_name import EthnicClassifyNameMixin
from scraper.ethnic_names_classify_api import EthnicClassifyApiMixin
from scraper.ethnic_names_confidence import EthnicConfidenceMixin


class EthnicNameDatabase(
    EthnicInitMixin,
    EthnicLoadJsonMixin,
    EthnicLookupMixin,
    EthnicSignalsMixin,
    EthnicClassifyNameMixin,
    EthnicClassifyApiMixin,
    EthnicConfidenceMixin,
):
    """Surname/given-name ethnicity signals."""

_ethnic_db = None

def get_ethnic_database() -> EthnicNameDatabase:
    """Get the singleton ethnic name database."""
    global _ethnic_db
    if _ethnic_db is None:
        _ethnic_db = EthnicNameDatabase()
    return _ethnic_db

