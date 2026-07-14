from __future__ import annotations

from bs4 import BeautifulSoup

import re
import base64

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


from scraper.reports.fetcher_types import *  # noqa: F401,F403
from scraper.reports.util import (  # noqa: F401
    _CAPTCHA_MARKERS,
    _DISCLAIMER_MARKERS,
    _LABEL_MAP,
    _LONG_VALUE_KEYS,
    _MAX_CRIME_LEN,
    _PHOTO_HOST_STATE,
    _clean_value,
    _normalize_label,
    _normalize_url,
    photo_state_from_url,
    photo_url_variants,
    extract_dedicated_photo_urls,
)

class FetcherDisclaimerMixin:
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


