from __future__ import annotations

import time

from typing import Any, Dict, List, Optional, Sequence

from scraper.nsopw.client_types import (  # noqa: F401
    BROWSER_UA,
    DEFAULT_DELAY,
    DEFAULT_JURISDICTIONS,
    NSOPW_OFFLINE_URL,
    NSOPW_ORIGIN,
    NSOPW_SEARCH_PAGE,
    NSOPW_SEARCH_URL,
    NSOPWOffender,
    REQUEST_TIMEOUT,
    _CF_BACKOFF_SECONDS,
    _is_cloudflare_block,
    _make_http_session,
    _stable_external_id,
    _stable_source_url,
    _token_starts_with,
    _last_starts_with_prefix,
    normalize_jurisdiction_code,
    offender_matches_name_prefixes,
)

class NSOPWClientSearchRunMixin:
    def search_by_name(
        self,
        first_name: str,
        last_name: str,
        jurisdictions: Optional[Sequence[str]] = None,
        *,
        strict_prefix: bool = False,
    ) -> List[NSOPWOffender]:
        """
        Search NSOPW by first + last name.

        Both first and last name are required. The API accepts short *partial*
        prefixes; combined length must be at least 3 (e.g. first="M", last="AH").

        **Yield vs purity:** the national API also matches **aliases** and may
        return primary names that do not start with the query tokens. By default
        ``strict_prefix=False`` — we keep **all** API hits so one short query
        scrapes as much as possible. Set ``strict_prefix=True`` only when you
        need primary-name starts-with purity (see
        ``offender_matches_name_prefixes``). Ethnicity bucketing (matched vs
        other surnames) is applied later in the builder, not here.
        """
        first = (first_name or "").strip()
        last = (last_name or "").strip()
        if not first or not last:
            raise ValueError("NSOPW requires both first_name and last_name")
        if len(first) + len(last) < 3:
            raise ValueError("Combined first+last name must be at least 3 characters")

        jurs = list(jurisdictions) if jurisdictions else list(DEFAULT_JURISDICTIONS)
        # API rejects the literal "All" mixed into arrays in some cases — filter it
        jurs = [j for j in jurs if j and j.upper() != "ALL"]

        body = {
            "firstName": first,
            "lastName": last,
            "city": None,
            "county": None,
            "zips": None,
            "longitude": None,
            "latitude": None,
            "distance": None,
            "jurisdictions": jurs,
            "clientIp": "",
        }

        headers = {"token": self._token()}
        max_attempts = len(_CF_BACKOFF_SECONDS)
        resp: Any = None
        last_cf = False

        try:
            for attempt in range(max_attempts):
                self._ensure_warm()
                try:
                    resp = self.session.post(
                        NSOPW_SEARCH_URL,
                        json=body,
                        headers=headers,
                        timeout=self.timeout,
                    )
                except Exception as e:
                    if attempt + 1 >= max_attempts:
                        raise RuntimeError(f"NSOPW network error: {e}") from e
                    time.sleep(_CF_BACKOFF_SECONDS[min(attempt + 1, max_attempts - 1)])
                    continue

                if _is_cloudflare_block(resp):
                    last_cf = True
                    wait = _CF_BACKOFF_SECONDS[min(attempt + 1, max_attempts - 1)]
                    if attempt + 1 >= max_attempts:
                        break
                    # New TLS session sometimes clears a sticky challenge
                    if attempt >= 1:
                        try:
                            self.session.close()
                        except Exception:
                            pass
                        self.session, self.http_backend = _make_http_session()
                        self._warmed = False
                    time.sleep(wait)
                    continue

                last_cf = False
                break
        finally:
            # Polite spacing between completed search attempts (success or hard fail)
            if self.delay > 0:
                time.sleep(self.delay)

        if resp is None:
            raise RuntimeError("NSOPW search failed: no response")

        if last_cf or _is_cloudflare_block(resp):
            raise RuntimeError(
                f"NSOPW blocked by Cloudflare (HTTP {resp.status_code}). "
                "Wait a minute, increase Search delay to 3–5s, and retry. "
                f"HTTP backend={self.http_backend}. "
                "If this persists, install curl_cffi: pip install curl_cffi"
            )

        if resp.status_code == 422:
            # Structured validation errors
            try:
                err = resp.json()
                code = err.get("statusCode")
                raise RuntimeError(
                    f"NSOPW rejected query (statusCode={code}): {resp.text[:300]}"
                )
            except ValueError:
                resp.raise_for_status()

        if resp.status_code >= 400:
            preview = (resp.text or "")[:200].replace("\n", " ")
            raise RuntimeError(
                f"NSOPW search failed: HTTP {resp.status_code} for url: "
                f"{NSOPW_SEARCH_URL} — {preview}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError(
                f"NSOPW returned non-JSON (HTTP {resp.status_code}): "
                f"{(resp.text or '')[:200]!r}"
            ) from e

        raw_offenders = data.get("offenders") or []
        parsed = [
            self._parse_offender(o) for o in raw_offenders if isinstance(o, dict)
        ]
        if not strict_prefix:
            return parsed

        kept: List[NSOPWOffender] = []
        for off in parsed:
            alias_dicts = [
                a for a in (off.raw.get("aliases") or []) if isinstance(a, dict)
            ]
            if offender_matches_name_prefixes(
                first,
                last,
                first_name=off.first_name,
                middle_name=off.middle_name,
                last_name=off.last_name,
                alias_dicts=alias_dicts,
                aliases=off.aliases,
            ):
                kept.append(off)
        return kept


