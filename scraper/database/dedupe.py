"""Dedupe mixins composition."""
from __future__ import annotations

from scraper.database.dedupe_attrs import DedupeAttrsMixin
from scraper.database.dedupe_url_norm import DedupeUrlNormMixin
from scraper.database.dedupe_url_flags import DedupeUrlFlagsMixin
from scraper.database.dedupe_merge_fields import DedupeMergeFieldsMixin
from scraper.database.dedupe_merge_members import DedupeMergeMembersMixin
from scraper.database.dedupe_find_sql import DedupeFindSqlMixin
from scraper.database.dedupe_find_groups import DedupeFindGroupsMixin
from scraper.database.dedupe_find_filter import DedupeFindFilterMixin
from scraper.database.dedupe_ops_count import DedupeOpsCountMixin
from scraper.database.dedupe_ops_remove import DedupeOpsRemoveMixin


class DedupeMixin(
    DedupeAttrsMixin,
    DedupeUrlNormMixin,
    DedupeUrlFlagsMixin,
    DedupeMergeFieldsMixin,
    DedupeMergeMembersMixin,
    DedupeFindSqlMixin,
    DedupeFindGroupsMixin,
    DedupeFindFilterMixin,
    DedupeOpsCountMixin,
    DedupeOpsRemoveMixin,
):
    """Find/merge/remove duplicate offender rows."""
