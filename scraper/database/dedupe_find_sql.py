from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from scraper.database.dedupe_keys import *  # noqa: F401,F403
from scraper.database.constants import (
    SCHEMA_VERSION,
    DUPLICATE_STRATEGIES,
    DEFAULT_DEDUPE_STRATEGIES,
    _VOLATILE_URL_PARAMS,
    _MERGE_SEP,
    _MERGE_UNION_FIELDS,
    DEFAULT_DB_PATH,
    _OFFENDER_INSERT_COLUMNS,
    _OFFENDER_INSERT_SQL,
    _record_to_insert_tuple,
    _utc_now_iso,
    _escape_like,
)

class DedupeFindSqlMixin:
    @staticmethod
    def _state_match_sql(column_expr: str = "state") -> str:
        """
        SQL fragment: column matches a state code even when multi-state
        merged values use ' | ' separators (e.g. 'FL | TX').
        """
        # Normalize spaces around | then test token membership
        return (
            f"("
            f"UPPER(TRIM(COALESCE({column_expr}, ''))) = UPPER(?) "
            f"OR ('|' || REPLACE(REPLACE(UPPER(COALESCE({column_expr}, '')), ' ', ''), "
            f"'{_MERGE_SEP.strip()}', '|') || '|') "
            f"LIKE '%|' || UPPER(?) || '|%'"
            f")"
        )


    def _append_state_filter(self, query: str, params: List[Any], state: str) -> str:
        """Append OR of state / source_state match (supports merged multi-state)."""
        st = (state or "").strip()
        if not st or st.upper() == "ALL":
            return query
        frag_state = self._state_match_sql("state")
        frag_src = self._state_match_sql("source_state")
        query += f" AND ({frag_state} OR {frag_src})"
        # each fragment uses ? twice
        params.extend([st, st, st, st])
        return query


    def _duplicate_group_sql(self, strategy: str) -> Tuple[str, str]:
        """
        Return (select_sql, key_label) for a strategy.

        select_sql must yield rows with columns: dup_key, cnt, id_list
        (id_list = comma-separated ids).
        """
        s = (strategy or "source_url").strip().lower()
        if s == "source_url":
            sql = """
                SELECT TRIM(source_url) AS dup_key,
                       COUNT(*) AS cnt,
                       GROUP_CONCAT(id) AS id_list
                FROM offenders
                WHERE source_url IS NOT NULL AND TRIM(source_url) != ''
                GROUP BY TRIM(source_url)
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
            """
            return sql, "source_url"
        if s == "external_id":
            sql = """
                SELECT LOWER(TRIM(external_id)) || '|' ||
                       UPPER(COALESCE(NULLIF(TRIM(state), ''),
                                      NULLIF(TRIM(source_state), ''), '')) AS dup_key,
                       COUNT(*) AS cnt,
                       GROUP_CONCAT(id) AS id_list
                FROM offenders
                WHERE external_id IS NOT NULL AND TRIM(external_id) != ''
                GROUP BY LOWER(TRIM(external_id)),
                         UPPER(COALESCE(NULLIF(TRIM(state), ''),
                                        NULLIF(TRIM(source_state), ''), ''))
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
            """
            return sql, "external_id+state"
        if s == "name_state_dob":
            sql = """
                SELECT LOWER(TRIM(COALESCE(first_name, ''))) || '|' ||
                       LOWER(TRIM(COALESCE(last_name, ''))) || '|' ||
                       UPPER(COALESCE(NULLIF(TRIM(state), ''),
                                      NULLIF(TRIM(source_state), ''), '')) || '|' ||
                       LOWER(TRIM(date_of_birth)) AS dup_key,
                       COUNT(*) AS cnt,
                       GROUP_CONCAT(id) AS id_list
                FROM offenders
                WHERE last_name IS NOT NULL AND TRIM(last_name) != ''
                  AND date_of_birth IS NOT NULL AND TRIM(date_of_birth) != ''
                GROUP BY LOWER(TRIM(COALESCE(first_name, ''))),
                         LOWER(TRIM(COALESCE(last_name, ''))),
                         UPPER(COALESCE(NULLIF(TRIM(state), ''),
                                        NULLIF(TRIM(source_state), ''), '')),
                         LOWER(TRIM(date_of_birth))
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
            """
            return sql, "name+state+dob"
        if s == "name_dob":
            # Cross-state: same person registered in multiple states
            sql = """
                SELECT LOWER(TRIM(COALESCE(first_name, ''))) || '|' ||
                       LOWER(TRIM(COALESCE(last_name, ''))) || '|' ||
                       LOWER(TRIM(date_of_birth)) AS dup_key,
                       COUNT(*) AS cnt,
                       GROUP_CONCAT(id) AS id_list
                FROM offenders
                WHERE first_name IS NOT NULL AND TRIM(first_name) != ''
                  AND last_name IS NOT NULL AND TRIM(last_name) != ''
                  AND date_of_birth IS NOT NULL AND TRIM(date_of_birth) != ''
                GROUP BY LOWER(TRIM(COALESCE(first_name, ''))),
                         LOWER(TRIM(COALESCE(last_name, ''))),
                         LOWER(TRIM(date_of_birth))
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
            """
            return sql, "name+dob (multi-state)"
        if s in ("name_state", "name_state_soft"):
            sql = """
                SELECT LOWER(TRIM(COALESCE(first_name, ''))) || '|' ||
                       LOWER(TRIM(COALESCE(last_name, ''))) || '|' ||
                       UPPER(COALESCE(NULLIF(TRIM(state), ''),
                                      NULLIF(TRIM(source_state), ''), '')) AS dup_key,
                       COUNT(*) AS cnt,
                       GROUP_CONCAT(id) AS id_list
                FROM offenders
                WHERE last_name IS NOT NULL AND TRIM(last_name) != ''
                  AND (
                    (state IS NOT NULL AND TRIM(state) != '')
                    OR (source_state IS NOT NULL AND TRIM(source_state) != '')
                  )
                GROUP BY LOWER(TRIM(COALESCE(first_name, ''))),
                         LOWER(TRIM(COALESCE(last_name, ''))),
                         UPPER(COALESCE(NULLIF(TRIM(state), ''),
                                        NULLIF(TRIM(source_state), ''), ''))
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC
            """
            label = (
                "name+state (photo/address corroborated)"
                if s == "name_state_soft"
                else "name+state"
            )
            return sql, label
        raise ValueError(
            f"Unknown duplicate strategy {strategy!r}; "
            f"choose one of {', '.join(DUPLICATE_STRATEGIES)}"
        )


