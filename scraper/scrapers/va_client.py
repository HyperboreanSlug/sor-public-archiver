"""Virginia vspsor.com HTTP client (CSRF + DataTables search API)."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urljoin

import requests

from ..config import DEFAULT_DELAY, MAX_RETRIES, REQUEST_TIMEOUT, USER_AGENT

BASE = "https://www.vspsor.com"
SEARCH_PATH = "/search/searchRegistry"
RESULTS_PATH = "/Search/Results"
DETAILS_PATH = "/Offender/Details"
TOKEN_RE = re.compile(
    r'name=["\']vsppsorpdaccunhza["\'][^>]*value=["\']([^"\']+)["\']',
    re.I,
)
TOKEN_RE_ALT = re.compile(
    r'value=["\'](CfDJ[^"\']+)["\'][^>]*name=["\']vsppsorpdaccunhza["\']',
    re.I,
)

# DataTables column order must match the live SearchResults grid.
DT_COLUMNS = (
    "imageUrl",
    "fullName",
    "age",
    "addressType",
    "location",
    "city",
    "postalCode",
    "county",
    "id",
)


def _make_session() -> Any:
    try:
        from curl_cffi import requests as creq  # type: ignore

        session = creq.Session(impersonate="chrome")
    except Exception:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
    session.headers.update(
        {
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


class VaVspsorClient:
    """Session-backed client for vspsor.com list + detail endpoints."""

    def __init__(
        self,
        delay: float = DEFAULT_DELAY,
        timeout: float = REQUEST_TIMEOUT,
        *,
        verify_ssl: bool = False,
    ):
        self.delay = max(0.0, float(delay))
        self.timeout = float(timeout)
        # Windows often lacks the intermediate CA for vspsor.com.
        self.verify_ssl = bool(verify_ssl)
        self.session = _make_session()
        self._token: str = ""
        self._token_query: str = ""

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    def _pace(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)
        last_exc: Optional[BaseException] = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.request(method, url, **kwargs)
                self._pace()
                return resp
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                if kwargs.get("verify", True) is not False and any(
                    t in msg for t in ("ssl", "certificate", "cert")
                ):
                    kwargs = {**kwargs, "verify": False}
                    continue
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(self.delay * (attempt + 1) or 0.5)
        raise last_exc  # pragma: no cover

    def _extract_token(self, html: str) -> str:
        m = TOKEN_RE.search(html or "") or TOKEN_RE_ALT.search(html or "")
        return (m.group(1) if m else "").strip()

    def refresh_token(self, query: str = "Filter=None") -> str:
        """GET results shell so cookies + antiforgery token are fresh."""
        url = f"{BASE}{RESULTS_PATH}?{query}" if query else f"{BASE}{RESULTS_PATH}"
        resp = self._request("GET", url)
        resp.raise_for_status()
        token = self._extract_token(resp.text)
        if not token:
            raise RuntimeError("vspsor.com: antiforgery token not found")
        self._token = token
        self._token_query = query
        return token

    def _dt_payload(self, *, start: int, length: int, draw: int = 1) -> Dict[str, Any]:
        skip_order = {"imageUrl", "addressType", "location", "id"}
        cols = [
            {
                "data": name,
                "name": "",
                "searchable": True,
                "orderable": name not in skip_order,
                "search": {"value": "", "regex": False},
            }
            for name in DT_COLUMNS
        ]
        return {
            "draw": int(draw),
            "columns": cols,
            "order": [{"column": 1, "dir": "asc"}],
            "start": int(start),
            "length": int(length),
            "search": {"value": "", "regex": False},
        }

    def search_page(
        self,
        *,
        start: int = 0,
        length: int = 100,
        filter_name: str = "None",
        county: str = "",
        draw: int = 1,
    ) -> Dict[str, Any]:
        """POST /search/searchRegistry — returns JSON with offenders + totals."""
        params: Dict[str, str] = {"Filter": filter_name or "None"}
        if county:
            params["County"] = county
        query = urlencode(params)
        if not self._token or self._token_query != query:
            self.refresh_token(query)

        url = f"{BASE}{SEARCH_PATH}?{query}"
        headers = {
            "Content-Type": "application/json",
            "RequestVerificationToken": self._token,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": BASE,
            "Referer": f"{BASE}{RESULTS_PATH}?{query}",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        body = json.dumps(self._dt_payload(start=start, length=length, draw=draw))
        resp = self._request("POST", url, data=body, headers=headers)
        if resp.status_code in (400, 401, 403):
            # Token may have rotated — refresh once and retry.
            self.refresh_token(query)
            headers["RequestVerificationToken"] = self._token
            resp = self._request("POST", url, data=body, headers=headers)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as e:
            raise RuntimeError(
                f"vspsor.com: non-JSON search response ({resp.status_code})"
            ) from e
        if not isinstance(data, dict):
            raise RuntimeError("vspsor.com: unexpected search payload type")
        return data

    def fetch_detail_html(self, offender_id: str) -> Tuple[str, str]:
        """GET offender detail page. Returns (html, final_url)."""
        oid = (offender_id or "").strip()
        if not oid:
            return "", ""
        url = f"{BASE}{DETAILS_PATH}/{oid}"
        resp = self._request("GET", url)
        resp.raise_for_status()
        final = str(getattr(resp, "url", None) or url)
        return resp.text or "", final

    def list_counties(self) -> List[str]:
        """County option values from the public search form."""
        resp = self._request("GET", f"{BASE}/Search")
        resp.raise_for_status()
        html = resp.text or ""
        # Prefer the County select block.
        m = re.search(
            r'<select[^>]+id=["\']County["\'][^>]*>(.*?)</select>',
            html,
            re.I | re.S,
        )
        block = m.group(1) if m else html
        values = re.findall(r'<option[^>]+value=["\']([^"\']+)["\']', block, re.I)
        out: List[str] = []
        seen = set()
        for v in values:
            name = (v or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
        return out

    @staticmethod
    def absolute_url(path_or_url: str) -> str:
        if not path_or_url:
            return ""
        return urljoin(BASE + "/", path_or_url)
