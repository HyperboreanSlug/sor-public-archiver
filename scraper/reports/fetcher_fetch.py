from __future__ import annotations

import re

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

class FetcherFetchMixin:
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
                        path, photo_path = self._save_html(
                            resp.content,
                            report_url,
                            html_dir,
                            jurisdiction,
                            resp.url,
                            download_images=True,
                        )
                        if path:
                            result["report_html_path"] = path
                            result["report_final_url"] = resp.url
                        if photo_path:
                            result["photo_path"] = photo_path
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
                br = result["report_block_reason"] or ""
                if "captcha" in br or "waf" in br:
                    self._note_captcha_block(
                        report_url, jurisdiction=jurisdiction, reason=br
                    )
                    result["needs_manual_captcha"] = True
                self._pace()
                return result

            # Re-apply domain cookies (in case store was updated mid-run)
            if self.use_saved_cookies:
                try:
                    self.cookie_store.apply_to_session(self.session, report_url)
                except Exception:
                    pass

            # Click through Conditions / disclaimer forms
            passed = self._click_through_disclaimers(resp, max_hops=4)
            if passed is not None:
                resp = passed
                result["report_final_url"] = getattr(resp, "url", result["report_final_url"])
                result["report_fetch_status"] = resp.status_code
                result["disclaimer_passed"] = True
                self._persist_cookies(result.get("report_final_url") or report_url)
                if resp.status_code >= 400:
                    result["report_block_reason"] = self._classify_block(resp)
                    br = result["report_block_reason"] or ""
                    if "captcha" in br or "waf" in br:
                        self._note_captcha_block(
                            report_url, jurisdiction=jurisdiction, reason=br
                        )
                        result["needs_manual_captcha"] = True
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
                path, photo_path = self._save_html(
                    raw_bytes,
                    report_url,
                    html_dir,
                    jurisdiction,
                    result["report_final_url"],
                    download_images=True,
                )
                if path:
                    result["report_html_path"] = path
                if photo_path:
                    result["photo_path"] = photo_path

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
            if block and ("captcha" in block or "waf" in block):
                self._note_captcha_block(
                    result.get("report_final_url") or report_url,
                    jurisdiction=jurisdiction,
                    reason=block,
                )
                result["needs_manual_captcha"] = True
                result["report_block_reason"] = block
                result["report_fetch_status"] = f"blocked:{block}"
                self._pace()
                return result
            if block:
                result["report_block_reason"] = block
            extracted = self._from_html(text, base_url=result["report_final_url"])
            result.update(extracted)
            # AL iCrimewatch / WatchSystems: pull dedicated /pictures/ mugshot URL
            # from the page so _ensure_photo can archive under …/photos/ even when
            # NSOPW imageUri is empty or points at a host alias.
            if not result.get("photo_url"):
                dedicated = extract_dedicated_photo_urls(
                    text, base_url=str(result.get("report_final_url") or report_url)
                )
                if dedicated:
                    result["photo_url"] = dedicated[0]
            result["report_fetch_ok"] = self._has_demographics(result)
            if resp.status_code == 200 and len(text) > 500:
                result["report_page_fetched"] = True
            if not result["report_fetch_ok"] and block:
                result["report_fetch_status"] = f"blocked:{block}"
            if result.get("report_fetch_ok"):
                final_u = result.get("report_final_url") or report_url
                self._persist_cookies(final_u)
                try:
                    self.captcha_queue.remove_url(report_url)
                    self.captcha_queue.remove_url(final_u)
                except Exception:
                    pass
            return result
        except Exception as e:
            result["report_fetch_status"] = f"error:{type(e).__name__}"
            result["report_error"] = str(e)[:300]
            self._pace()
            return result


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


