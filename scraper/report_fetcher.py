"""
Fetch jurisdiction offender report pages linked from NSOPW, extract demographics,
and optionally archive the raw HTML next to the database for offline validation.
"""

from __future__ import annotations

import base64
import html as html_lib
import re
import time
from hashlib import sha1
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from .config import DEFAULT_DELAY, REQUEST_TIMEOUT

# Prefer a browser UA for state sites (many WAF on custom bots).
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_LABEL_MAP = {
    "race": "race",
    "racial": "race",
    "ethnicity": "ethnicity",
    "ethnic origin": "ethnicity",
    "sex": "gender",
    "gender": "gender",
    "height": "height",
    "weight": "weight",
    "eye color": "eye_color",
    "eyes": "eye_color",
    "hair color": "hair_color",
    "hair": "hair_color",
    "skin tone": "skin_tone",
    "complexion": "skin_tone",
    "build": "build",
    "age": "age",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "birth date": "date_of_birth",
    "county": "county",
    "city": "city",
    "address": "address",
    "risk level": "risk_level",
    "offense": "offense_type",
    "offense description": "offense_description",
    "conviction": "conviction_date",
}

_CAPTCHA_MARKERS = (
    "recaptcha",
    "hcaptcha",
    "cf-turnstile",
    "captcha",
    "just a moment",
    "datadome",
    "access denied",
    "bot detection",
)
_DISCLAIMER_MARKERS = (
    "conditions of use",
    "terms and conditions",
    "you must agree",
    "accept the terms",
    "disclaimer",
    "i agree",
    "by clicking accept",
)


def _normalize_label(raw: str) -> str:
    s = re.sub(r"\s+", " ", (raw or "").strip().lower())
    # iCrimeWatch / OffenderWatch: "• Race:", "&bull; Eyes:", etc.
    s = re.sub(r"^[\u2022\u00b7•·\-\*]+\s*", "", s)
    s = s.replace("&bull;", "").strip()
    return s.rstrip(":").strip()


def _clean_value(raw: str) -> str:
    """Collapse whitespace / newlines and decode HTML entities."""
    s = html_lib.unescape(raw or "")
    return re.sub(r"\s+", " ", s).strip()


def _normalize_url(url: str) -> str:
    """Fix scheme case, drop :80, and rewrite known gateway hosts."""
    url = html_lib.unescape((url or "").strip())
    m = re.match(r"^(https?)://(.*)$", url, flags=re.I)
    if m:
        url = m.group(1).lower() + "://" + m.group(2)
    # Drop default port 80 on http(s) hosts
    url = re.sub(r"^(https?://[^/:]+):80(?=/|$)", r"\1", url)
    # Colorado: public link → live apps host after agreement cookie
    url = url.replace(
        "www.colorado.gov/apps/cdps/sor",
        "apps.colorado.gov/apps/dps/sor",
    )
    url = url.replace(
        "colorado.gov/apps/cdps/sor",
        "apps.colorado.gov/apps/dps/sor",
    )
    return url

class ReportFetcher:
    """HTTP client that scrapes demographic fields from report URLs."""

    def __init__(self, delay: float = DEFAULT_DELAY, timeout: float = REQUEST_TIMEOUT):
        # delay=0 when the caller (builder) owns rate limiting — avoid double sleeps.
        self.delay = max(0.0, float(delay))
        self.timeout = timeout
        self.session = self._make_session()

    @staticmethod
    def _make_session() -> Any:
        try:
            from curl_cffi import requests as creq  # type: ignore

            session = creq.Session(impersonate="chrome")
        except Exception:
            session = requests.Session()
            session.headers["User-Agent"] = BROWSER_UA
        session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        return session

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    def fetch_demographics(
        self,
        report_url: str,
        save_html: bool = False,
        html_dir: Optional[Path] = None,
        jurisdiction: str = "UNK",
    ) -> Dict[str, Any]:
        """
        Fetch a report URL and return extracted fields.

        When save_html=True, writes the response body under html_dir and sets
        result['report_html_path'] to the relative/local path.
        """
        result: Dict[str, Any] = {
            "report_url": report_url,
            "report_fetch_ok": False,
            "report_fetch_status": None,
        }
        report_url = _normalize_url(str(report_url or ""))
        if not report_url.lower().startswith("http://") and not report_url.lower().startswith(
            "https://"
        ):
            result["report_fetch_status"] = "invalid_url"
            return result
        result["report_url"] = report_url
        original_url = report_url

        try:
            # Texas SOR: try JSON detail endpoint when rapsheet HTML is a JS shell
            tx_json = self._try_texas_json(report_url)
            if tx_json is not None and (
                tx_json.get("race") or tx_json.get("ethnicity") or tx_json.get("gender")
            ):
                if save_html and html_dir is not None:
                    try:
                        resp = self._get(report_url)
                        path = self._save_html(
                            resp.content, report_url, html_dir, jurisdiction, resp.url
                        )
                        if path:
                            result["report_html_path"] = path
                            result["report_final_url"] = resp.url
                    except Exception:
                        pass
                result.update(tx_json)
                result["report_fetch_ok"] = True
                result["report_fetch_status"] = result.get("report_fetch_status") or 200
                self._pace()
                return result

            # Do NOT strip disclaimer gateways early — land on agree page, POST, then detail.
            resp, used_url = self._get_with_https_fallback(report_url)
            result["report_fetch_status"] = resp.status_code
            result["report_final_url"] = getattr(resp, "url", used_url) or used_url

            if resp.status_code >= 400:
                result["report_block_reason"] = self._classify_block(resp)
                self._pace()
                return result

            # Click through Conditions / disclaimer forms
            passed = self._click_through_disclaimers(resp, max_hops=4)
            if passed is not None:
                resp = passed
                result["report_final_url"] = getattr(resp, "url", result["report_final_url"])
                result["report_fetch_status"] = resp.status_code
                result["disclaimer_passed"] = True
                if resp.status_code >= 400:
                    result["report_block_reason"] = self._classify_block(resp)
                    self._pace()
                    return result
                # After agreement, re-fetch original detail URL (CO JSF, WI terms, etc.)
                resp = self._refetch_detail_if_needed(resp, original_url)
                result["report_final_url"] = getattr(resp, "url", result["report_final_url"])
                result["report_fetch_status"] = getattr(resp, "status_code", 200)

            # Maine SOR: national step3 → step4 more-info
            me_resp = self._try_maine_step4(resp, original_url)
            if me_resp is not None:
                resp = me_resp
                result["report_final_url"] = getattr(resp, "url", result["report_final_url"])

            self._pace()

            content_type = (resp.headers.get("Content-Type") or "").lower()
            raw_bytes = resp.content

            if save_html and html_dir is not None:
                path = self._save_html(
                    raw_bytes,
                    report_url,
                    html_dir,
                    jurisdiction,
                    result["report_final_url"],
                )
                if path:
                    result["report_html_path"] = path

            if "json" in content_type:
                try:
                    data = resp.json()
                    result.update(self._from_json_blob(data))
                    result["report_fetch_ok"] = self._has_demographics(result)
                    return result
                except ValueError:
                    pass

            text = raw_bytes.decode("utf-8", errors="replace")
            block = self._page_block_reason(text)
            if block:
                result["report_block_reason"] = block
            extracted = self._from_html(text, base_url=result["report_final_url"])
            result.update(extracted)
            result["report_fetch_ok"] = self._has_demographics(result)
            if resp.status_code == 200 and len(text) > 500:
                result["report_page_fetched"] = True
            if not result["report_fetch_ok"] and block:
                result["report_fetch_status"] = f"blocked:{block}"
            return result
        except Exception as e:
            result["report_fetch_status"] = f"error:{type(e).__name__}"
            result["report_error"] = str(e)[:300]
            self._pace()
            return result

    def _pace(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    def _get(self, url: str, **kwargs: Any) -> Any:
        return self.session.get(
            url,
            timeout=self.timeout,
            allow_redirects=True,
            **kwargs,
        )

    def _post(self, url: str, data: Dict[str, str], referer: str = "") -> Any:
        headers: Dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if referer:
            headers["Referer"] = referer
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                headers["Origin"] = f"{parsed.scheme}://{parsed.netloc}"
        return self.session.post(
            url,
            data=data,
            timeout=self.timeout,
            allow_redirects=True,
            headers=headers,
        )

    def _get_with_https_fallback(self, url: str) -> Tuple[Any, str]:
        """Try URL as-is; on http timeout/SSL issues, retry https / www / verify=False."""
        url = _normalize_url(url)
        candidates = [url]
        if url.startswith("http://"):
            candidates.append("https://" + url[len("http://") :])
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if host and not host.startswith("www."):
            candidates.append(
                urlunparse(parsed._replace(netloc="www." + host, scheme="https"))
            )
        if parsed.scheme == "http":
            candidates.append(urlunparse(parsed._replace(scheme="https")))

        last_err: Optional[Exception] = None
        for cand in candidates:
            try:
                return self._get(cand), cand
            except Exception as e:
                last_err = e
                # TLS / cert failures common on some SOR hosts
                try:
                    resp = self.session.get(
                        cand,
                        timeout=self.timeout,
                        allow_redirects=True,
                        verify=False,
                    )
                    return resp, cand
                except Exception as e2:
                    last_err = e2
                    continue
        if last_err:
            raise last_err
        raise RuntimeError(f"Failed to fetch {url}")

    def _click_through_disclaimers(self, resp: Any, max_hops: int = 3) -> Optional[Any]:
        """
        If the response is a Conditions-of-Use / disclaimer gate, POST the agree
        form (checkbox + Continue) and follow redirects to the real report.

        Handles iCrimeWatch / OffenderWatch / sheriffalerts / communitynotification
        patterns like:
          <form method="post">
            <input type="hidden" name="fwd" value="...">
            <input type="checkbox" name="agree" value="1">
            <input type="submit" name="continue" value="Continue">
          </form>
        """
        current = resp
        any_passed = False
        for _ in range(max_hops):
            text = getattr(current, "text", None) or ""
            if not self._looks_like_disclaimer(text, getattr(current, "url", "") or ""):
                break
            next_resp = self._submit_disclaimer_form(current)
            if next_resp is None:
                break
            any_passed = True
            current = next_resp
            # Stop if we still look stuck on the same disclaimer
            if self._looks_like_disclaimer(
                getattr(current, "text", None) or "",
                getattr(current, "url", "") or "",
            ):
                # One more attempt only if form still present
                continue
            break
        return current if any_passed else None

    @staticmethod
    def _looks_like_disclaimer(text: str, url: str = "") -> bool:
        low = (text or "").lower()
        url_l = (url or "").lower()
        if "cap_office_disclaimer" in url_l or "disclaimer.php" in url_l:
            return True
        if "search-agreement" in url_l or "/terms" in url_l or "agreement.jsf" in url_l:
            return True
        if 'name="agree"' in low or "name='agree'" in low or 'id="agree"' in low:
            if re.search(r"continue|i agree|terms\s*&\s*conditions|disclaimer", low):
                return True
        if "you must agree to the terms" in low:
            return True
        if "you must click on the" in low and "continue" in low and "disclaimer" in low:
            return True
        if "before entering the web site" in low and "agree" in low:
            return True
        if "i agree" in low and "i do not agree" in low:
            return True
        if "acceptform" in low and "submit" in low and "agreement" in low:
            return True
        # Form present with agree checkbox + continue submit
        if re.search(
            r"<form[^>]*>[\s\S]{0,4000}agree[\s\S]{0,2000}continue[\s\S]{0,500}</form>",
            low,
        ):
            return True
        return False

    def _refetch_detail_if_needed(self, resp: Any, original_url: str) -> Any:
        """
        After accepting terms, some sites land on a search home. Re-request the
        original offender detail URL with the new session cookie.
        """
        text = getattr(resp, "text", None) or ""
        if self._has_demographics(self._from_html(text)):
            return resp
        orig = _normalize_url(original_url)
        if not orig:
            return resp
        try:
            again, _ = self._get_with_https_fallback(orig)
            if self._has_demographics(self._from_html(getattr(again, "text", "") or "")):
                return again
            # Prefer page that at least mentions race and is not still a terms form
            low = (getattr(again, "text", "") or "").lower()
            if "race" in low and not self._looks_like_disclaimer(low, getattr(again, "url", "")):
                return again
        except Exception:
            pass
        return resp

    def _try_maine_step4(self, resp: Any, original_url: str) -> Optional[Any]:
        """Maine SOR step3 page links to step4 for full detail."""
        page_url = getattr(resp, "url", "") or original_url or ""
        if "maine.gov" not in page_url.lower() and "maine.gov" not in (original_url or "").lower():
            return None
        html = getattr(resp, "text", None) or ""
        if "step3" not in page_url.lower() and "step3" not in html.lower():
            # still try if form posts to step4
            if "step4" not in html.lower():
                return None
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return None
        for form in soup.find_all("form"):
            action = (form.get("action") or "").lower()
            if "step4" not in action and not any(
                (i.get("value") or "").lower().startswith("request more")
                for i in form.find_all("input")
            ):
                continue
            post_url = urljoin(page_url, form.get("action") or page_url)
            data: Dict[str, str] = {}
            for inp in form.find_all("input"):
                name = inp.get("name")
                if not name:
                    continue
                typ = (inp.get("type") or "text").lower()
                val = inp.get("value") or ""
                if typ == "submit":
                    if "request" in val.lower() or "more" in val.lower():
                        data[name] = val
                elif typ != "checkbox":
                    data[name] = val
            if not data:
                continue
            try:
                return self._post(post_url, data=data, referer=page_url)
            except Exception:
                continue
        return None

    def _submit_disclaimer_form(self, resp: Any) -> Optional[Any]:
        """Find agree/accept form on page and POST it. Returns new response or None."""
        html = getattr(resp, "text", None) or ""
        page_url = getattr(resp, "url", "") or ""
        if not html or not page_url:
            return None
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return None

        form = self._find_disclaimer_form(soup)
        if form is None:
            return None

        action = urljoin(page_url, form.get("action") or page_url)
        data = self._build_disclaimer_post_data(form, page_url)
        if not data:
            return None

        try:
            return self._post(action, data=data, referer=page_url)
        except Exception:
            return None

    @staticmethod
    def _find_disclaimer_form(soup: BeautifulSoup) -> Any:
        """Prefer forms with agree/accept/continue controls."""
        candidates = []
        for form in soup.find_all("form"):
            inputs = form.find_all("input")
            blob = " ".join(
                f"{(i.get('name') or '')} {(i.get('id') or '')} {(i.get('value') or '')} "
                f"{(i.get('type') or '')}"
                for i in inputs
            ).lower()
            score = 0
            if re.search(r"\bagree\b|\baccept\b|\bterms\b", blob):
                score += 2
            if re.search(r"\bcontinue\b|\bsubmit\b|\bproceed\b|\benter\b", blob):
                score += 2
            if "checkbox" in blob:
                score += 1
            if "fwd" in blob or "disc" in blob:
                score += 1
            if "i agree" in blob:
                score += 3
            if "acceptform" in blob or "submitlogin" in blob.replace(":", ""):
                score += 2
            if score >= 2:
                candidates.append((score, form))
        if not candidates:
            # Fallback: any form containing an agree-named control
            for form in soup.find_all("form"):
                for inp in form.find_all("input"):
                    name = (inp.get("name") or inp.get("id") or "").lower()
                    val = (inp.get("value") or "").lower()
                    if name in ("agree", "accept", "iagree", "chkagree", "terms", "tos"):
                        return form
                    if "i agree" in val and "not" not in val:
                        return form
            return None
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    @staticmethod
    def _build_disclaimer_post_data(form: Any, page_url: str = "") -> Dict[str, str]:
        """Build POST body: hidden fields + checked agree + continue submit."""
        data: Dict[str, str] = {}
        submit_picked = False

        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            typ = (inp.get("type") or "text").lower()
            val = inp.get("value")
            if val is None:
                val = ""
            else:
                val = str(val)

            if typ == "hidden":
                data[name] = val
                continue

            if typ in ("checkbox", "radio"):
                blob = f"{name} {val} {inp.get('id') or ''}".lower()
                # Always check terms/agree boxes
                if re.search(r"agree|accept|terms|confirm|license|consent", blob):
                    data[name] = val or "1"
                continue

            if typ == "submit":
                blob = f"{name} {val}".lower()
                # Prefer affirmative agree; skip "I do not agree" / decline
                if re.search(r"do\s*not|don't|disagree|decline|cancel|no\b", blob):
                    continue
                if re.search(
                    r"continue|accept|i agree|agree|submit|enter|yes|proceed|ok",
                    blob,
                ):
                    if not submit_picked:
                        data[name] = val or "Continue"
                        submit_picked = True
                continue

            if typ in ("button", "image", "reset", "file"):
                continue

            # Rare text fields
            if name.lower() in ("agree", "accept"):
                data[name] = val or "1"

        # Ensure agree + continue exist (WatchSystems pattern)
        keys_l = {k.lower() for k in data}
        if "agree" not in keys_l and not any(
            re.search(r"agree|accept|terms", k, re.I) for k in data
        ):
            data["agree"] = "1"
        if not submit_picked and "continue" not in keys_l:
            data["continue"] = "Continue"

        # If form action is empty POST to page URL, keep query `fwd` when missing in body
        if page_url and "fwd" not in data:
            try:
                qs = parse_qs(urlparse(page_url).query)
                fwd = (qs.get("fwd") or [None])[0]
                if fwd:
                    data["fwd"] = fwd
            except Exception:
                pass

        return data

    @staticmethod
    def _resolve_gateway_url(url: str) -> str:
        """Decode sheriffalerts/icrimewatch `fwd=` base64 payloads when present."""
        try:
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            fwd = (qs.get("fwd") or [None])[0]
            if not fwd:
                return url
            pad = "=" * (-len(fwd) % 4)
            target = base64.b64decode(fwd + pad).decode("utf-8", errors="replace").strip()
            if target.startswith("http://") or target.startswith("https://"):
                return target
        except Exception:
            pass
        return url

    @staticmethod
    def _has_demographics(data: Dict[str, Any]) -> bool:
        race = (data.get("race") or "").strip()
        # "Unknown" still counts as extracted race field from some states (SC)
        if race:
            return True
        if data.get("ethnicity"):
            return True
        gender = (data.get("gender") or "").strip().lower()
        if gender and gender not in ("minor", "n/a", "unknown", "unk"):
            if data.get("height") or data.get("hair_color") or data.get("eye_color"):
                return True
            # gender alone is weak but useful if paired with DOB/age from report
            if data.get("date_of_birth") or data.get("age"):
                return True
        return bool(data.get("height") and data.get("hair_color"))

    @staticmethod
    def _classify_block(resp: Any) -> str:
        text = (getattr(resp, "text", None) or "")[:2000].lower()
        if resp.status_code in (403, 429):
            if any(m in text for m in _CAPTCHA_MARKERS):
                return "captcha_or_waf"
            return f"http_{resp.status_code}"
        return f"http_{resp.status_code}"

    @staticmethod
    def _page_block_reason(text: str) -> Optional[str]:
        low = text.lower()
        # Real demographic content? Then ignore passive captcha widgets in footers.
        has_demo_signal = bool(
            re.search(r"(?:^|>|\b)race\s*:", low)
            or re.search(r"<td[^>]*>\s*white\s*</td>", low)
            or ("height" in low and "weight" in low and "hair" in low)
        )
        if any(m in low for m in _CAPTCHA_MARKERS):
            # Interactive captcha wall (no offender fields yet)
            if not has_demo_signal:
                if "g-recaptcha" in low or "hcaptcha" in low or "cf-turnstile" in low:
                    return "captcha"
                if "sex offender recaptcha" in low or "complete the captcha" in low:
                    return "captcha"
                if "datadome" in low:
                    return "waf_datadome"
        if not has_demo_signal:
            if "you must agree" in low or "must agree to the terms" in low:
                return "disclaimer_gate"
            if "cap_office_disclaimer" in low:
                return "disclaimer_gate"
        return None
    def _save_html(
        self,
        content: bytes,
        report_url: str,
        html_dir: Path,
        jurisdiction: str,
        final_url: str = "",
    ) -> Optional[str]:
        """Write report HTML to disk; return path relative to cwd if possible."""
        try:
            jur = re.sub(r"[^A-Za-z0-9_-]", "", (jurisdiction or "UNK").upper())[:12] or "UNK"
            digest = sha1((final_url or report_url).encode("utf-8", errors="replace")).hexdigest()[:16]
            folder = Path(html_dir) / jur
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / f"{digest}.html"

            header = (
                f"<!-- archived_from: {html_lib.escape(final_url or report_url)} -->\n"
                f"<!-- archived_at_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} -->\n"
            ).encode("utf-8")
            if dest.exists() and dest.stat().st_size > 100:
                pass
            else:
                dest.write_bytes(header + content)

            try:
                return str(dest.relative_to(Path.cwd()))
            except ValueError:
                return str(dest)
        except OSError:
            return None

    def _from_html(self, html: str, base_url: str = "") -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        found: Dict[str, Any] = {}

        # Keep a raw copy for regex patterns before tag stripping
        raw_html = html

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # --- Header-row tables (OK Apex, many report grids) ---
        # Require multiple <th> headers (not label|value rows that use th/td pairs).
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            ths = rows[0].find_all("th")
            if len(ths) < 2:
                continue
            headers = [_normalize_label(c.get_text(" ", strip=True)) for c in ths]
            mapped_n = sum(1 for h in headers if h in _LABEL_MAP)
            if mapped_n < 2:
                continue
            for data_row in rows[1:]:
                tds = data_row.find_all("td")
                if not tds:
                    continue
                values = [_clean_value(td.get_text(" ", strip=True)) for td in tds]
                for h, v in zip(headers, values):
                    key = _LABEL_MAP.get(h)
                    if key and v and _normalize_label(v) not in _LABEL_MAP:
                        found.setdefault(key, v)
                if any(k in found for k in ("race", "gender", "height")):
                    break

        # PrimeFaces / FL style: alternating label/value cells
        cells = soup.select("div.borderPanelCell, div.ui-g-12.borderPanelCell")
        if len(cells) >= 2:
            i = 0
            while i < len(cells) - 1:
                lab = _normalize_label(cells[i].get_text(" ", strip=True))
                val = _clean_value(cells[i + 1].get_text(" ", strip=True))
                if lab in _LABEL_MAP and val and len(val) < 120 and lab != _normalize_label(val):
                    found.setdefault(_LABEL_MAP[lab], val)
                    i += 2
                else:
                    i += 1

        # Bootstrap / CA Megans Law: Label:</div><div class="col-…">VALUE</div>
        for m in re.finditer(
            r"(Race|Ethnicity|Sex|Gender|Height|Weight|Hair Color|Eye Color|Eyes|Hair|"
            r"Date of Birth|DOB|Age)\s*:?\s*</(?:div|span|label|strong|b|dt|th)>\s*"
            r"<(?:div|span|dd|td)[^>]*>\s*([^<]{1,80}?)\s*</(?:div|span|dd|td)>",
            raw_html,
            flags=re.I,
        ):
            key = _LABEL_MAP.get(m.group(1).lower())
            if key:
                found.setdefault(key, _clean_value(m.group(2)))

        # DE / label + sibling span (possibly empty if Knockout not rendered)
        for lab in soup.find_all("label"):
            label = _normalize_label(lab.get_text(" ", strip=True))
            if label not in _LABEL_MAP:
                continue
            val = ""
            fid = lab.get("for")
            if fid:
                target = soup.find(id=fid)
                if target is not None:
                    val = _clean_value(target.get_text(" ", strip=True))
            if not val:
                for sib in lab.find_next_siblings(["span", "div", "p", "td"]):
                    val = _clean_value(sib.get_text(" ", strip=True))
                    if val and _normalize_label(val) not in _LABEL_MAP:
                        break
                    val = ""
            if not val and lab.parent is not None:
                # parent row: "Race: | Black"
                ptext = lab.parent.get_text(" ", strip=True)
                rest = re.sub(
                    re.escape(lab.get_text(" ", strip=True)),
                    "",
                    ptext,
                    count=1,
                    flags=re.I,
                ).strip(" :-|")
                if rest and len(rest) < 80:
                    val = _clean_value(rest)
            if val and val not in ("(unknown)", "—", "-") and not val.startswith("("):
                found.setdefault(_LABEL_MAP[label], val)

        for dt in soup.find_all("dt"):
            label = _normalize_label(dt.get_text(" ", strip=True))
            dd = dt.find_next_sibling("dd")
            if dd and label in _LABEL_MAP:
                found.setdefault(_LABEL_MAP[label], _clean_value(dd.get_text(" ", strip=True)))

        for row in soup.find_all("tr"):
            cells = row.find_all(["th", "td"])
            # Pair adjacent cells: [label, value, label, value, ...]
            # (iCrimeWatch rows often pack two fields per <tr>)
            i = 0
            while i < len(cells) - 1:
                label = _normalize_label(cells[i].get_text(" ", strip=True))
                value = _clean_value(cells[i + 1].get_text(" ", strip=True))
                if label in _LABEL_MAP and value and _normalize_label(value) not in _LABEL_MAP:
                    found.setdefault(_LABEL_MAP[label], value)
                    i += 2
                else:
                    i += 1

        # Label-only node → next sibling element holds value (common grid layouts)
        for lab_el in soup.find_all(["span", "div", "label", "strong", "b", "th", "td", "p"]):
            raw = lab_el.get_text(" ", strip=True)
            if not raw or len(raw) > 60:
                continue
            label = _normalize_label(raw)
            if label not in _LABEL_MAP:
                # "Race: White" on same node
                m = re.match(
                    r"^(Race|Ethnicity|Sex|Gender|Height|Weight|Eye Color|Hair Color|"
                    r"Eyes|Hair|Age|DOB|Date of Birth)\s*[:\-]\s*(.+)$",
                    raw,
                    flags=re.I,
                )
                if m:
                    key = _LABEL_MAP.get(m.group(1).lower())
                    if key:
                        found.setdefault(key, m.group(2).strip()[:120])
                continue
            # empty value on label node → look next
            if ":" in raw and not re.search(r":\s*\S", raw):
                # parent then next sibling
                parent = lab_el.parent
                candidates = []
                if parent is not None:
                    candidates.append(parent.find_next_sibling())
                candidates.append(lab_el.find_next_sibling())
                for nxt in candidates:
                    if not nxt or not hasattr(nxt, "get_text"):
                        continue
                    val = nxt.get_text(" ", strip=True)
                    if val and len(val) < 80 and _normalize_label(val) not in _LABEL_MAP:
                        found.setdefault(_LABEL_MAP[label], val)
                        break

        for lab in soup.find_all(["label", "strong", "b", "span", "div", "p"]):
            raw = lab.get_text(" ", strip=True)
            if not raw or len(raw) > 80:
                continue
            m = re.match(
                r"^(Race|Ethnicity|Sex|Gender|Height|Weight|Eye Color|Hair Color|Age|DOB|Date of Birth)\s*[:\-]\s*(.+)$",
                raw,
                flags=re.I,
            )
            if m:
                key = _LABEL_MAP.get(m.group(1).lower())
                if key:
                    found.setdefault(key, m.group(2).strip())
                continue

            label = _normalize_label(raw)
            if label in _LABEL_MAP:
                nxt = lab.find_next_sibling(string=True)
                if nxt and str(nxt).strip():
                    found.setdefault(_LABEL_MAP[label], str(nxt).strip())
                    continue
                parent = lab.parent
                if parent:
                    ptext = parent.get_text(" ", strip=True)
                    rest = re.sub(re.escape(raw), "", ptext, count=1, flags=re.I).strip(" :-")
                    if rest and len(rest) < 80:
                        found.setdefault(_LABEL_MAP[label], rest)

        body_text = soup.get_text("\n", strip=True)
        for line in body_text.splitlines():
            m = re.match(
                r"^(Race|Ethnicity|Sex|Gender|Height|Weight|Eye Color|Hair Color|Age|Date of Birth|DOB)\s*[:\-]\s*(.+)$",
                line.strip(),
                flags=re.I,
            )
            if m:
                key = _LABEL_MAP.get(m.group(1).lower())
                if key:
                    found.setdefault(key, m.group(2).strip()[:120])

        # Re-parse scripts from original HTML for embedded JSON
        for script in BeautifulSoup(html, "html.parser").find_all("script"):
            content = script.string or ""
            if "race" in content.lower() and len(content) < 500_000:
                for m in re.finditer(
                    r'"(race|ethnicity|gender|sex|height|weight|eyeColor|hairColor)"\s*:\s*"([^"]{1,80})"',
                    content,
                    flags=re.I,
                ):
                    raw_key = m.group(1).lower()
                    key = {
                        "race": "race",
                        "ethnicity": "ethnicity",
                        "gender": "gender",
                        "sex": "gender",
                        "height": "height",
                        "weight": "weight",
                        "eyecolor": "eye_color",
                        "haircolor": "hair_color",
                    }.get(raw_key)
                    if key:
                        found.setdefault(key, m.group(2))

        if "age" in found:
            try:
                found["age"] = int(re.sub(r"[^\d]", "", str(found["age"])) or 0) or found["age"]
            except (TypeError, ValueError):
                pass

        # Drop bogus gender values
        g = str(found.get("gender") or "").strip().lower()
        if g in ("minor", "description", "status", "yes", "no"):
            found.pop("gender", None)

        # Clean all string fields
        for k, v in list(found.items()):
            if isinstance(v, str):
                found[k] = _clean_value(v)

        # CA and others often use Ethnicity where Race is expected
        if not found.get("race") and found.get("ethnicity"):
            eth = str(found["ethnicity"]).strip()
            if eth and eth.lower() not in ("unknown", "undetermined", "n/a", "none"):
                found["race"] = eth

        if base_url:
            found["report_final_url"] = base_url
        return found

    def _from_json_blob(self, data: Any, prefix: str = "") -> Dict[str, Any]:
        found: Dict[str, Any] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                kl = str(k).lower().replace("_", "")
                mapped = {
                    "race": "race",
                    "ethnicity": "ethnicity",
                    "gender": "gender",
                    "sex": "gender",
                    "height": "height",
                    "weight": "weight",
                    "eyecolor": "eye_color",
                    "haircolor": "hair_color",
                    "skintone": "skin_tone",
                    "build": "build",
                    "age": "age",
                    "dateofbirth": "date_of_birth",
                    "dob": "date_of_birth",
                    "county": "county",
                    "city": "city",
                    "address": "address",
                    "risklevel": "risk_level",
                }.get(kl)
                if mapped and isinstance(v, (str, int, float)) and str(v).strip():
                    found.setdefault(mapped, v)
                elif isinstance(v, (dict, list)) and len(str(v)) < 10000:
                    found.update(self._from_json_blob(v))
        elif isinstance(data, list):
            for item in data[:50]:
                found.update(self._from_json_blob(item))
        return found

    def _try_texas_json(self, report_url: str) -> Optional[Dict[str, Any]]:
        if "sor.dps.texas.gov" not in report_url.lower():
            return None
        m = re.search(r"[?&]sid=([^&]+)", report_url, flags=re.I)
        if not m:
            return None
        sid = m.group(1)
        candidates = [
            f"https://sor.dps.texas.gov/Search/Rapsheet/Index?sid={sid}&handler=GetRapsheet",
            f"https://publicsite.dps.texas.gov/SexOffenderRegistry/Search/Rapsheet?sid={sid}",
        ]
        for url in candidates:
            try:
                resp = self._get(
                    url,
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "X-Requested-With": "XMLHttpRequest",
                        "Referer": report_url,
                    },
                )
                if resp.status_code != 200:
                    continue
                ct = (resp.headers.get("Content-Type") or "").lower()
                if "json" in ct:
                    return self._from_json_blob(resp.json())
                # Sometimes returns JSON with wrong content-type
                text = resp.text.strip()
                if text.startswith("{") or text.startswith("["):
                    try:
                        import json as _json

                        return self._from_json_blob(_json.loads(text))
                    except ValueError:
                        pass
                if "race" in resp.text.lower():
                    return self._from_html(resp.text, base_url=resp.url)
            except Exception:
                continue
        return None
