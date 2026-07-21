from __future__ import annotations

import json

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.nsopw.builder_types import *  # noqa: F401,F403
from scraper.database import Database
from scraper.ethnic_names import get_ethnic_database
from scraper.reports.fetcher import ReportFetcher
from scraper.nsopw.client import (
    DEFAULT_JURISDICTIONS,
    NSOPWClient,
    NSOPWOffender,
    normalize_jurisdiction_code,
)
from scraper.nsopw.parallel import JurisdictionReportPool, ReportJob

class BuilderBuildMixin:
    def _find_existing_person_id(self, record: Dict[str, Any]) -> Optional[int]:
        """Id of an existing row that is the same person, or None.

        Prevents the build inserting a duplicate of a person already in the DB
        under a different source URL / registry id (e.g. two FDLE personIds for
        one person, or a CSV row + an NSOPW row). Uses the same score-gated
        identity check as dedupe (min_score=6, requires a 2nd identifier).
        """
        from scraper.database.identity import should_merge_records

        last = str(record.get("last_name") or "").strip()
        first = str(record.get("first_name") or "").strip()
        if not last or not first:
            return None
        first_tok = first.split()[0]
        try:
            rows = self.db._conn.execute(
                "SELECT * FROM offenders WHERE last_name = ? COLLATE NOCASE "
                "AND (first_name = ? COLLATE NOCASE OR first_name LIKE ? COLLATE NOCASE) "
                "LIMIT 8",
                (last, first_tok, first_tok + " %"),
            ).fetchall()
        except Exception:
            return None
        best_id: Optional[int] = None
        best_sc = -1
        for r in rows:
            existing = dict(r)
            try:
                ok, sc, _ = should_merge_records(
                    record, existing, min_score=6, unique_name_candidate=(len(rows) == 1)
                )
            except Exception:
                continue
            if ok and sc > best_sc:
                best_sc, best_id = sc, int(existing["id"])
        return best_id

    def build(
        self,
        ethnicity: str = "hispanic",
        surnames_limit: int = 10,
        all_surnames: bool = False,
        subcategory: Optional[str] = None,
        first_names: Optional[Sequence[str]] = None,
        first_mode: str = "initials",
        jurisdictions: Optional[Sequence[str]] = None,
        max_searches: Optional[int] = 50,
        max_report_fetches: Optional[int] = 100,
        max_names: Optional[int] = None,
        skip_existing_urls: bool = True,
        skip_completed_searches: bool = True,
        new_files_only: bool = True,
        enrich_reports: bool = True,
        enrich_scope: str = "all",
        save_html: bool = True,
        use_compact_prefixes: bool = True,
        min_combined_len: int = MIN_COMBINED_NAME_LEN,
        log: Optional[Callable[[str], None]] = None,
        on_insert: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        live_options: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> BuildStats:
        """
        Run the ethnic-name NSOPW search pipeline.

        enrich_scope (when enrich_reports is True):
          - ``all``: fetch report pages for every hit (default)
          - ``ethnicity_match``: only fetch reports for hits whose surname is
            on the selected ethnicity list; other surnames from the same search
            are still inserted but not report-enriched.

        first_mode:
          - "initials" (default): full A–Z firsts + all list surname digraphs
          - "indian" / "common": abbreviated BOTH first letters
            (ASRPMKVNBD) AND top ~30 Indian surname digraphs (RA/CH/KA/…)
          - "indian_wide" / "common_wide": wider firsts (+GJHT) and ~50 digraphs
          - "full": use DEFAULT_FIRST_NAMES or provided first_names list
          - "custom": only the provided first_names list

        Short last-name prefixes (min combined first+last length 3) collapse many
        list surnames into fewer queries (e.g. M+AH covers Ahmed and Ahmad).
        Prefixes are always derived from the selected surname list (never
        brute-force AA–ZZ). Abbreviated mode further cuts surname digraphs to
        the most common Indian-likely letter combos only.

        use_compact_prefixes:
          When True (default), collapse surnames to short last prefixes that
          satisfy NSOPW's min combined first+last length (usually 3 letters).
          When False, search each full surname × first token (many more queries).
        min_combined_len:
          NSOPW API minimum for len(first)+len(last); default 3.

        max_searches:
          Cap on new NSOPW API queries. None or <= 0 means unlimited.
        max_names / max_report_fetches:
          Cap on unique offender names processed (GUI "Max reports" = max names).
          max_report_fetches is an alias kept for CLI compatibility.
          None or <= 0 means unlimited.

        skip_completed_searches:
          When True (default), never re-run a (first, last) API query already in
          nsopw_query_log — ethnicity is ignored for this check. Set False only
          to explicitly repeat old searches.
        new_files_only:
          Skip report HTTP download when local HTML already exists for that URL.
        all_surnames:
          Ignore surnames_limit and use every name in the selected list(s).

        on_insert: optional callback with the stored record after each successful insert
        (used by the GUI for live Recent inserts).
        on_progress: optional callback with a progress dict after each plan step
        (plan_i, plan_total, searches, inserted, hits, current query, etc.).
        live_options: optional callable returning a dict of runtime knobs re-read
          during the run (delays, caps, skip/enrich/save flags). Ethnicity and
          surname plan are fixed at start; only operational knobs are live.
        """
        def _log(msg: str) -> None:
            if log:
                log(msg)
            else:
                print(msg)

        def _cap(value: Optional[int]) -> Optional[int]:
            """Normalize limit: None / <=0 → unlimited (None)."""
            if value is None:
                return None
            try:
                n = int(value)
            except (TypeError, ValueError):
                return None
            return None if n <= 0 else n

        # Fresh counters each run (do not accumulate across build() calls)
        self.stats = BuildStats()

        search_cap = _cap(max_searches)
        # "Max reports" in the GUI means max unique names, not HTTP report fetches.
        # Prefer explicit max_names; fall back to max_report_fetches for CLI.
        names_cap = _cap(max_names if max_names is not None else max_report_fetches)

        # Live-tunable operational flags (mutated by _apply_live_options each step)
        skip_existing_urls = bool(skip_existing_urls)
        skip_completed_searches = bool(skip_completed_searches)
        new_files_only = bool(new_files_only)
        enrich_reports = bool(enrich_reports)
        enrich_scope = (enrich_scope or "all").strip().lower()
        save_html = bool(save_html)
        _live_last_sig: Optional[str] = None

        def _apply_live_options(*, announce: bool = True) -> None:
            """Refresh delays/caps/flags from live_options callback (GUI mid-run)."""
            nonlocal search_cap, names_cap
            nonlocal skip_existing_urls, skip_completed_searches, new_files_only
            nonlocal enrich_reports, enrich_scope, save_html, _live_last_sig
            if not live_options:
                return
            try:
                opts = live_options() or {}
            except Exception:
                return
            if not isinstance(opts, dict):
                return

            if "max_searches" in opts:
                search_cap = _cap(opts.get("max_searches"))
            if "max_names" in opts:
                names_cap = _cap(opts.get("max_names"))
            elif "max_report_fetches" in opts:
                names_cap = _cap(opts.get("max_report_fetches"))

            if "skip_existing_urls" in opts:
                skip_existing_urls = bool(opts.get("skip_existing_urls"))
            if "skip_completed_searches" in opts:
                skip_completed_searches = bool(opts.get("skip_completed_searches"))
            if "new_files_only" in opts:
                new_files_only = bool(opts.get("new_files_only"))
            if "enrich_reports" in opts:
                enrich_reports = bool(opts.get("enrich_reports"))
            if "enrich_scope" in opts and opts.get("enrich_scope") is not None:
                enrich_scope = str(opts.get("enrich_scope") or "all").strip().lower()
            if "save_html" in opts:
                save_html = bool(opts.get("save_html"))

            if "search_delay" in opts and opts.get("search_delay") is not None:
                try:
                    sd = max(DEFAULT_MIN_SEARCH_INTERVAL, float(opts["search_delay"]))
                    self.search_delay = sd
                    self.search_limiter.set_interval(sd)
                except (TypeError, ValueError):
                    pass
            if "report_delay" in opts and opts.get("report_delay") is not None:
                try:
                    rd = max(DEFAULT_MIN_REPORT_INTERVAL, float(opts["report_delay"]))
                    self.report_delay = rd
                    self.report_limiter.set_interval(rd)
                except (TypeError, ValueError):
                    pass

            # Skip-existing turned on mid-run → load URL cache once
            if skip_existing_urls and not self._known_urls:
                self._load_known_urls()

            sig = (
                f"sc={search_cap}|nc={names_cap}|sd={self.search_delay:.2f}|"
                f"rd={self.report_delay:.2f}|se={int(skip_existing_urls)}|"
                f"sk={int(skip_completed_searches)}|nf={int(new_files_only)}|"
                f"en={int(enrich_reports)}|es={enrich_scope}|sh={int(save_html)}"
            )
            if announce and sig != _live_last_sig and _live_last_sig is not None:
                _log(
                    "Live options updated: "
                    f"max_searches={'∞' if search_cap is None else search_cap}, "
                    f"max_names={'∞' if names_cap is None else names_cap}, "
                    f"search_delay={self.search_delay:.2f}s, "
                    f"report_delay={self.report_delay:.2f}s, "
                    f"skip_urls={skip_existing_urls}, "
                    f"skip_done={skip_completed_searches}, "
                    f"new_html_only={new_files_only}, "
                    f"enrich={enrich_reports}, enrich_scope={enrich_scope}, "
                    f"save_html={save_html}"
                )
            _live_last_sig = sig

        mode = (first_mode or "initials").lower().strip()
        if first_names is not None:
            firsts = [f.strip() for f in first_names if f and str(f).strip()]
        else:
            firsts = first_initials_for_mode(mode)

        if not firsts:
            firsts = list(FIRST_INITIALS)  # default full A–Z, not abbreviated

        jurs = list(jurisdictions) if jurisdictions else list(DEFAULT_JURISDICTIONS)
        surname_pairs = self.surnames_for_ethnicity(
            ethnicity,
            limit_per_group=surnames_limit,
            all_surnames=all_surnames,
            subcategory=subcategory,
        )
        eth_key = (ethnicity or "").lower()
        sub_disp = (subcategory or "all").strip() or "all"

        # Collapse to short last prefixes (first+last ≥ min_combined) for fewer API calls.
        # Abbreviated mode shortens BOTH first letters (Indian set) AND surname
        # digraphs (top Indian-likely combos only).
        try:
            mcl = max(3, int(min_combined_len))
        except (TypeError, ValueError):
            mcl = MIN_COMBINED_NAME_LEN
        abbrev = is_abbreviated_first_mode(mode)
        last_allow = last_prefix_whitelist_for(
            eth_key, surname_pairs, abbreviated=abbrev, mode=mode
        )
        naive_queries = len(surname_pairs) * len(firsts)
        if use_compact_prefixes:
            search_plan = compact_search_plan(
                surname_pairs,
                firsts,
                min_combined=mcl,
                allowed_last_prefixes=last_allow,
            )
        else:
            # One query per full surname × first (no prefix collapse), de-duped.
            # Abbreviated mode still drops surnames whose digraph is not allowed.
            plan_map: Dict[Tuple[str, str], Tuple[str, str, str, Set[str]]] = {}
            for sn, eth_lab in surname_pairs:
                s = (sn or "").strip()
                if not s:
                    continue
                if last_allow is not None:
                    al = _surname_alnum(s)
                    dig = al[:2].upper() if len(al) >= 2 else al.upper()
                    if dig and dig not in last_allow:
                        continue
                for fn in firsts:
                    f = (fn or "").strip()
                    if not f:
                        continue
                    if len(f) + len(s) < mcl:
                        continue
                    key = self._query_key(f, s)
                    if key not in plan_map:
                        plan_map[key] = (f, s, eth_lab or "", {s})
                    else:
                        prev_f, prev_s, prev_eth, cov = plan_map[key]
                        cov.add(s)
                        if eth_lab and not prev_eth:
                            plan_map[key] = (prev_f, prev_s, eth_lab or "", cov)
            search_plan = [
                (f, s, eth, sorted(cov, key=str.lower))
                for f, s, eth, cov in plan_map.values()
            ]
            search_plan.sort(key=lambda t: (t[1].upper(), t[0].upper()))
        compact_queries = len(search_plan)
        # Full selected ethnicity surname list — used to bucket hits matched vs other
        eth_surnames_list = [s for s, _ in surname_pairs]

        _log(f"Ethnicity filter: {ethnicity}")
        _log(f"Subcategory: {sub_disp}")
        _log(
            f"Surnames in list: {len(surname_pairs)}"
            + (" (ALL in list)" if all_surnames or surnames_limit <= 0 else f" (cap {surnames_limit}/group)")
        )
        _log(
            "Result bucketing: ethnicity-list surnames → primary tab; "
            "other surnames from the same queries are still saved → other tab."
        )
        _log(f"First-name mode: {describe_first_mode(mode)}")
        _log(f"  Tokens ({len(firsts)}): {', '.join(firsts[:14])}{'…' if len(firsts) > 14 else ''}")
        if use_compact_prefixes:
            dig_note = ""
            if last_allow is not None:
                dig_note = (
                    f"; last prefixes restricted to {len(last_allow)} "
                    f"Indian-likely digraphs"
                )
            else:
                dig_note = "; last prefixes from selected surnames only (not AA–ZZ)"
            _log(
                f"Compact queries: {compact_queries:,} "
                f"(vs {naive_queries:,} full surname×first; "
                f"short last prefixes, min combined {mcl} letters{dig_note})"
            )
        else:
            _log(
                f"Full-surname queries: {compact_queries:,} "
                f"(compact prefixes OFF; min combined {mcl} letters)"
            )
        _log(f"Jurisdictions: {len(jurs)}")
        _log(
            f"Max new searches: {'unlimited' if search_cap is None else search_cap}, "
            f"max names: {'unlimited' if names_cap is None else names_cap}"
        )
        _log(
            f"Rate limits — search: {self.search_delay:.2f}s  |  "
            f"report/HTML: {self.report_delay:.2f}s  "
            f"(search is slower: Cloudflare on nsopw-api)"
        )
        _log(
            f"Skip completed searches: {skip_completed_searches} "
            f"({'default — will not re-hit finished first+last pairs' if skip_completed_searches else 'OFF — will re-run old searches'})"
        )
        _log(f"Skip known URLs in DB: {skip_existing_urls}")
        _log(f"New report files only (no re-download): {new_files_only}")
        _log(f"Save report HTML: {save_html} → {self.html_dir}")
        _log(f"Enrich demographics: {enrich_reports}" + (
            f" (scope={enrich_scope})" if enrich_reports else ""
        ))
        if skip_existing_urls:
            self._load_known_urls()
            _log(f"Known URLs cached for skip: {len(self._known_urls):,}")
        else:
            self._known_urls = set()

        # Preload completed API queries so we never re-hit NSOPW for the same
        # (first, last) unless skip_completed_searches is False (explicit repeat).
        already_done_n = 0
        planned_done_n = 0
        if skip_completed_searches:
            completed = self._load_completed_queries()
            already_done_n = len(completed)
            planned_done_n = sum(
                1
                for f, last_tok, *_rest in search_plan
                if self._query_key(f, last_tok) in completed
            )
            _log(
                f"Completed search log: {already_done_n:,} unique first+last pairs in DB; "
                f"{planned_done_n:,} of {len(search_plan):,} planned queries already done (will skip)"
            )
        else:
            self._completed_queries = set()
            _log("Repeat mode: completed-search log ignored for this run")

        _log("NSOPW Conditions of Use apply: https://www.nsopw.gov/")
        if use_compact_prefixes:
            _log(
                "Yield mode: short partials (e.g. M+AH) + keep all API hits "
                f"(aliases/fuzzy included; min combined {mcl}). "
                "Primary tab = ethnicity-list surnames only; other tab = rest."
            )
        else:
            _log(
                f"Full surname mode: each list name is searched as-is "
                f"(API min combined length {mcl})."
            )
        _log("")

        seen_urls: Set[str] = set()
        search_count = 0
        report_count = 0
        names_processed = 0  # unique names after dedupe (counts toward max names)
        plan_total = len(search_plan)
        # New work only: planned queries not already completed (when resume/skip on)
        remaining = plan_total - planned_done_n if skip_completed_searches else plan_total
        work_total = remaining
        if search_cap is not None:
            work_total = min(remaining, search_cap) if remaining else 0
        work_total = max(int(work_total or 0), 1)

        def _search_limit_reached() -> bool:
            return search_cap is not None and search_count >= search_cap

        def _names_limit_reached() -> bool:
            return names_cap is not None and names_processed >= names_cap

        def _progress(**extra: Any) -> None:
            if not on_progress:
                return
            try:
                pi = int(extra.get("plan_i", 0) or 0)
                pt = int(extra.get("plan_total", plan_total) or 0)
                # Refresh work_total from current caps for the progress bar
                if search_cap is not None:
                    total = max(int(search_cap), 1)
                else:
                    total = max(int(work_total or pt or 1), 1)
                on_progress({
                    "plan_i": pi,
                    "plan_total": pt,
                    "done": pi,
                    "total": total,
                    "searches": int(self.stats.searches),
                    "searches_skipped": int(self.stats.searches_skipped),
                    "search_hits": int(self.stats.search_hits),
                    "search_hits_matched": int(self.stats.search_hits_matched),
                    "search_hits_other": int(self.stats.search_hits_other),
                    "inserted": int(self.stats.inserted),
                    "inserted_matched": int(self.stats.inserted_matched),
                    "inserted_other": int(self.stats.inserted_other),
                    "skipped_existing": int(self.stats.skipped_existing),
                    "reports_fetched": int(self.stats.reports_fetched),
                    "reports_with_race": int(self.stats.reports_with_race),
                    "html_saved": int(self.stats.html_saved),
                    "photos_saved": int(getattr(self.stats, "photos_saved", 0) or 0),
                    "errors": len(self.stats.errors),
                    "current": str(extra.get("current") or ""),
                    "phase": str(extra.get("phase") or "running"),
                    # Explicit search terms for the GUI progress line
                    "search_first": str(extra.get("search_first") or ""),
                    "search_last": str(extra.get("search_last") or ""),
                    "search_covers": str(extra.get("search_covers") or ""),
                    "search_label": str(extra.get("search_label") or ""),
                    "search_cap": search_cap,
                    "names_cap": names_cap,
                    "search_delay": self.search_delay,
                    "report_delay": self.report_delay,
                })
            except Exception:
                pass

        if live_options:
            _log(
                "Live options enabled: max searches/names, delays, and checkboxes "
                "re-apply every step. Ethnicity / surname plan stay fixed for this run."
            )
            _apply_live_options(announce=False)

        _progress(plan_i=0, plan_total=plan_total, current="starting…", phase="start")

        # ---- report finalize + optional parallel report-fetch pool ----
        def _finalize_record(record, hit, st, is_eth_match, url, *, ensure_photo):
            """Main-thread: photo, then merge into an existing person or insert."""
            if url:
                record["source_url"] = record.get("source_url") or url
            if ensure_photo:
                self._ensure_photo(record, hit, st)
            try:
                # Merge into an existing record of the same person instead of
                # inserting a duplicate (same person under a different URL / id).
                existing_id = self._find_existing_person_id(record)
                merged = False
                if existing_id is not None:
                    try:
                        merged = bool(
                            self.db._merge_source_into_existing(
                                existing_id, record, commit=False
                            )
                        )
                    except Exception:
                        merged = False
                if not merged:
                    self.db.insert_offender(record)
                self.stats.inserted += 1
                if is_eth_match:
                    self.stats.inserted_matched += 1
                else:
                    self.stats.inserted_other += 1
                # Keep skip-cache in sync so same-run duplicates are skipped
                self._remember_url(record.get("source_url") or url)
                if on_insert:
                    try:
                        on_insert(dict(record))
                    except Exception:
                        pass
            except Exception as e:
                msg = f"  Insert error: {e}"
                self.stats.errors.append(msg)
                _log(msg)

        report_pool: Optional[JurisdictionReportPool] = None
        if self.report_threads > 1:
            report_pool = JurisdictionReportPool(
                num_threads=self.report_threads,
                make_fetcher=self._make_report_fetcher,
                worker_fn=self._worker_fetch,
                report_delay=self.report_delay,
                cancel_check=self.cancel_check,
                log=_log,
            )
            _log(
                f"Parallel report fetch: {self.report_threads} worker threads "
                "(per-state serialized — no two threads ever hit the same "
                "state website at once)"
            )

        def _drain_report_jobs(jobs: List[ReportJob]) -> bool:
            """Fetch queued report jobs in parallel; finalize here. True=cancelled."""
            if not jobs or report_pool is None:
                return False
            for j in jobs:
                report_pool.submit(j)
            for done in report_pool.collect(len(jobs)):
                _apply_live_options(announce=False)
                report_pool.set_report_delay(self.report_delay)
                if self.cancel_check():
                    return True
                if done.error:
                    self.stats.errors.append(done.error)
                    _log(f"  {done.error}")
                if done.demo is not None:
                    self._apply_report_result_stats(
                        done.record, done.demo, done.jurisdiction, _log
                    )
                _finalize_record(
                    done.record,
                    done.hit,
                    done.jurisdiction,
                    done.is_eth_match,
                    done.url,
                    ensure_photo=False,
                )
            return self.cancel_check()

        last_plan_i = 0
        for plan_i, (first, last_token, eth_label, covered_surnames) in enumerate(
            search_plan, start=1
        ):
            last_plan_i = plan_i
            # GUI may have changed delays/caps/checkboxes since last step
            _apply_live_options(announce=True)
            if self.cancel_check():
                _log("Cancelled by user.")
                _progress(
                    plan_i=plan_i - 1,
                    plan_total=plan_total,
                    current="cancelled",
                    phase="cancelled",
                )
                break
            if _search_limit_reached() or _names_limit_reached():
                _log(
                    "Limit reached: "
                    + (
                        f"searches {search_count}/{search_cap}"
                        if search_cap is not None and search_count >= search_cap
                        else f"names {names_processed}/{names_cap}"
                    )
                )
                break

            # Default: never re-hit an API query already logged (any ethnicity).
            # Only re-runs when skip_completed_searches is False (explicit repeat).
            if skip_completed_searches and self._query_done(first, last_token, eth_key):
                self.stats.searches_skipped += 1
                # Quiet skip log: only every 25th + first few (avoids spam looking like re-runs)
                if self.stats.searches_skipped <= 3 or self.stats.searches_skipped % 25 == 0:
                    cov = ",".join(covered_surnames[:4])
                    if len(covered_surnames) > 4:
                        cov += f"…(+{len(covered_surnames) - 4})"
                    _log(
                        f"  Skip completed search #{self.stats.searches_skipped}: "
                        f"'{first}' {last_token} [{cov}]"
                    )
                cov = ",".join(covered_surnames[:4])
                if len(covered_surnames) > 4:
                    cov += f"…(+{len(covered_surnames) - 4})"
                _progress(
                    plan_i=plan_i,
                    plan_total=plan_total,
                    current=f"skip first='{first}' last='{last_token}'",
                    phase="resume_skip",
                    search_first=first,
                    search_last=last_token,
                    search_covers=cov,
                    search_label=eth_label or "",
                )
                continue

            if self.cancel_check():
                _log("Cancelled by user.")
                _progress(
                    plan_i=plan_i - 1,
                    plan_total=plan_total,
                    current="cancelled",
                    phase="cancelled",
                )
                break
            search_count += 1
            self.stats.searches = search_count
            if self.search_limiter.wait(self.cancel_check):
                _log("Cancelled by user (during search delay).")
                _progress(
                    plan_i=plan_i - 1,
                    plan_total=plan_total,
                    current="cancelled",
                    phase="cancelled",
                )
                # Don't count a search we never issued
                search_count = max(0, search_count - 1)
                self.stats.searches = search_count
                break
            if self.cancel_check():
                _log("Cancelled by user.")
                _progress(
                    plan_i=plan_i - 1,
                    plan_total=plan_total,
                    current="cancelled",
                    phase="cancelled",
                )
                search_count = max(0, search_count - 1)
                self.stats.searches = search_count
                break
            cap_label = "∞" if search_cap is None else str(search_cap)
            cov = ",".join(covered_surnames[:4])
            if len(covered_surnames) > 4:
                cov += f"…(+{len(covered_surnames) - 4})"
            # Always search with normalized tokens (same as query log keys)
            first_q, last_q = self._query_key(first, last_token)
            # Preserve display casing of first if single letter already upper
            first_api = first_q
            last_api = last_token.strip()  # NSOPW accepts any case; log uses last_q
            _log(
                f"[{search_count}/{cap_label}] NSOPW: first='{first_api}' last='{last_api}' "
                f"({eth_label}; covers {len(covered_surnames)}: {cov})"
            )
            _progress(
                plan_i=plan_i,
                plan_total=plan_total,
                current=f"first='{first_api}' last='{last_api}'",
                phase="search",
                search_first=first_api,
                search_last=last_api,
                search_covers=cov,
                search_label=eth_label or "",
            )

            try:
                hits = self.client.search_by_name(first_api, last_api, jurisdictions=jurs)
            except Exception as e:
                msg = f"  Search error: {e}"
                self.stats.errors.append(msg)
                _log(msg)
                # Do not mark complete — next run will retry
                continue

            # Split hits: ethnicity-list surnames (primary) vs other surnames from
            # the same short-prefix search. Both are saved; GUI shows them in tabs.
            eth_matched: List[Any] = []
            other_hits: List[Any] = []
            for h in hits:
                if last_matches_target_surnames(h.last_name, eth_surnames_list):
                    eth_matched.append(h)
                else:
                    other_hits.append(h)

            # Log as done immediately after a successful API response (0 hits is still done)
            self._mark_query_done(
                first_api, last_q, eth_key, hit_count=len(eth_matched) + len(other_hits)
            )
            self.stats.search_hits += len(hits)
            self.stats.search_hits_matched += len(eth_matched)
            self.stats.search_hits_other += len(other_hits)
            sample_firsts = sorted({(h.first_name or "?") for h in eth_matched})[:8]
            _log(
                f"  Hits: {len(hits)}  "
                f"(ethnicity list: {len(eth_matched)}, other surnames: {len(other_hits)})"
                + (
                    f"  matched first-names: {', '.join(sample_firsts)}"
                    if sample_firsts
                    else ""
                )
            )

            # Process ethnicity matches first (count toward max names), then others.
            # Others are always saved/archived but do not consume the names cap.
            ordered_hits: List[Tuple[Any, bool]] = [
                (h, True) for h in eth_matched
            ] + [(h, False) for h in other_hits]

            cancelled = False
            # Parallel mode: report fetches for this search's hits are queued and
            # run across worker threads (serialized per state) after the loop.
            report_jobs: List[ReportJob] = []
            for hit, is_eth_match in ordered_hits:
                _apply_live_options(announce=False)
                if self.cancel_check():
                    cancelled = True
                    break
                # Max names applies only to ethnicity-list matches; still save "other".
                if is_eth_match and _names_limit_reached():
                    continue

                st = (hit.jurisdiction_id or hit.state or "UNK").upper()
                self._state_stats(st).hits += 1

                url = (hit.offender_uri or "").strip()
                dedupe_key = url or f"{hit.jurisdiction_id}:{hit.full_name}:{hit.date_of_birth}"
                if dedupe_key in seen_urls:
                    continue
                seen_urls.add(dedupe_key)
                self.stats.unique_offenders += 1
                if is_eth_match:
                    names_processed += 1
                ncap_label = "∞" if names_cap is None else str(names_cap)

                record = hit.to_record()
                record["likely_ethnicity"] = eth_label
                conf_eth, conf = self.ethnic_db.get_likely_ethnicity(
                    hit.last_name or last_token,
                    first_name=getattr(hit, "first_name", None) or None,
                    middle_name=getattr(hit, "middle_name", None) or None,
                )
                record["name_confidence"] = conf
                if conf_eth and conf_eth != "Unknown":
                    record["likely_ethnicity"] = conf_eth

                # GUI routing: matched ethnicity list vs other surnames
                record["nsopw_ethnicity_match"] = bool(is_eth_match)
                record["nsopw_result_bucket"] = "matched" if is_eth_match else "other"

                flags = [
                    "nsopw",
                    f"search_last:{last_token}",
                    f"search_first:{first}",
                    f"first_mode:{mode}",
                    f"covers:{len(covered_surnames)}",
                    "ethnicity_match" if is_eth_match else "other_surname",
                    f"filter_ethnicity:{eth_key}",
                ]
                record["flags"] = json.dumps(flags)

                # Tag NSOPW search hit as a source (race usually empty until report HTML)
                try:
                    from scraper.database.sources import (
                        attach_source_to_record,
                        extract_tracked_fields,
                        make_source,
                    )

                    nsopw_src = make_source(
                        source_type="nsopw",
                        jurisdiction=st,
                        origin="nsopw_search",
                        label=f"NSOPW ({st})",
                        external_id=str(record.get("external_id") or ""),
                        source_url=str(url or record.get("source_url") or ""),
                        fields=extract_tracked_fields(record),
                        html_verified=False,
                        html_status="pending" if url else "no_url",
                    )
                    attach_source_to_record(record, nsopw_src, prefer_new_fields=False)
                except Exception:
                    pass

                if skip_existing_urls and url and self._url_exists(url):
                    self.stats.skipped_existing += 1
                    continue

                do_enrich = bool(enrich_reports)
                if do_enrich and enrich_scope in (
                    "ethnicity_match", "matched", "ethnicity"
                ) and not is_eth_match:
                    do_enrich = False

                if do_enrich and url:
                    existing_html = (
                        self._existing_html_path(url, st) if new_files_only else None
                    )
                    if existing_html:
                        self.stats.reports_skipped_existing_file += 1
                        record["report_html_path"] = existing_html
                        flags_list = json.loads(record["flags"])
                        flags_list.append("html_cached")
                        record["flags"] = json.dumps(flags_list)
                        _log(f"  Report skip (local HTML): {existing_html}")
                        _finalize_record(
                            record, hit, st, is_eth_match, url, ensure_photo=True
                        )
                        continue
                    if self.cancel_check():
                        cancelled = True
                        break
                    report_count += 1
                    self.stats.reports_fetched = report_count
                    sst = self._state_stats(st)
                    sst.reports_attempted += 1
                    if report_pool is not None:
                        # Parallel: queue for a per-state worker; finalized after loop.
                        _log(
                            f"  Name ({names_processed}/{ncap_label}) "
                            f"report [{st}] queued: {url[:90]}"
                        )
                        report_jobs.append(
                            ReportJob(
                                jurisdiction=st,
                                url=url,
                                record=record,
                                hit=hit,
                                is_eth_match=is_eth_match,
                                save_html=save_html,
                            )
                        )
                        continue
                    # Sequential path (report_threads == 1): fetch inline.
                    if self.report_limiter.wait(self.cancel_check):
                        cancelled = True
                        break
                    if self.cancel_check():
                        cancelled = True
                        break
                    _log(
                        f"  Name ({names_processed}/{ncap_label}) "
                        f"report [{st}]: {url[:90]}"
                    )
                    demo = self.reports.fetch_demographics(
                        url,
                        save_html=save_html,
                        html_dir=self.html_dir,
                        jurisdiction=st,
                    )
                    self._merge_demographics(record, demo)
                    if demo.get("report_html_path"):
                        record["report_html_path"] = demo["report_html_path"]
                    if demo.get("photo_path"):
                        record["photo_path"] = demo["photo_path"]
                    if demo.get("photo_url") and not record.get("photo_url"):
                        record["photo_url"] = demo["photo_url"]
                    record["source_url"] = demo.get("report_final_url") or url
                    self._apply_report_result_stats(record, demo, st, _log)
                    if self.cancel_check():
                        cancelled = True
                        break
                    _finalize_record(
                        record, hit, st, is_eth_match, url, ensure_photo=True
                    )
                    continue

                # No enrichment (or no URL): attach photo + insert directly.
                _finalize_record(record, hit, st, is_eth_match, url, ensure_photo=True)

            # Run this search's queued report jobs in parallel (per-state serial).
            if not cancelled and report_jobs:
                if _drain_report_jobs(report_jobs):
                    cancelled = True

            if cancelled:
                _log("Cancelled by user.")
                _progress(
                    plan_i=plan_i,
                    plan_total=plan_total,
                    current="cancelled",
                    phase="cancelled",
                )
                break

        if report_pool is not None:
            report_pool.close()

        was_cancelled = bool(self.cancel_check())
        _progress(
            plan_i=last_plan_i if was_cancelled else plan_total,
            plan_total=plan_total,
            current="cancelled" if was_cancelled else "complete",
            phase="cancelled" if was_cancelled else "done",
        )
        _log("")
        _log("=== Build cancelled ===" if was_cancelled else "=== Build complete ===")
        _log(f"Searches (new):        {self.stats.searches}")
        _log(f"Searches skipped:      {self.stats.searches_skipped} (already completed)")
        _log(f"Raw hits:              {self.stats.search_hits}")
        _log(
            f"  · ethnicity list:    {self.stats.search_hits_matched}  · other surnames: "
            f"{self.stats.search_hits_other}"
        )
        _log(f"Unique offenders:      {self.stats.unique_offenders}")
        _log(
            f"Inserted:              {self.stats.inserted} "
            f"(matched {self.stats.inserted_matched}, other {self.stats.inserted_other})"
        )
        _log(f"Skipped existing URLs: {self.stats.skipped_existing}")
        _log(f"Reports fetched:       {self.stats.reports_fetched}")
        _log(f"Reports skipped HTML:  {self.stats.reports_skipped_existing_file}")
        _log(f"Reports with race:     {self.stats.reports_with_race}")
        _log(f"Reports with race/eth: {self.stats.reports_with_demographics}")
        _log(f"HTML pages saved:      {self.stats.html_saved}")
        _log(f"Photos saved:          {self.stats.photos_saved}")
        _log(f"Errors:                {len(self.stats.errors)}")
        if self.stats.by_state:
            _log("")
            _log("Per-state report coverage (attempted → ok / race / html):")
            for st in sorted(self.stats.by_state.keys()):
                s = self.stats.by_state[st]
                if s.reports_attempted == 0 and s.hits == 0:
                    continue
                blocks = ""
                if s.blocks:
                    top = sorted(s.blocks.items(), key=lambda x: -x[1])[:2]
                    blocks = "  blocks=" + ",".join(f"{k}:{v}" for k, v in top)
                _log(
                    f"  {st:6} hits={s.hits:4}  reports={s.reports_attempted:3} "
                    f"ok={s.reports_ok:3}  race={s.with_race:3}  html={s.html_saved:3}"
                    f"{blocks}"
                )
            _log(
                "Note: iCrimeWatch/OffenderWatch disclaimers are auto-accepted when possible. "
                "Interactive CAPTCHA/WAF pages are queued (data/captcha_queue.json) — "
                "solve in a browser, import cookies under Settings → Access assistance, then requeue."
            )
            try:
                n_q = len(self.captcha_queue.list_items())
                if n_q:
                    _log(f"CAPTCHA queue size: {n_q} (see Settings)")
            except Exception:
                pass
        return self.stats


