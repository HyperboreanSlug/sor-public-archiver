"""
Persistent cookie store for state SOR hosts.

After you complete a CAPTCHA or login wall in a normal browser, export cookies
for that site and import them here. The scraper reuses those cookies so later
report/HTML fetches can succeed without automated CAPTCHA solving.

Supported import formats:
  - JSON list: [{"name","value","domain","path"?,"secure"?}, ...]
  - Netscape cookies.txt (name/value/domain columns)
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

DEFAULT_COOKIE_PATH = Path("data/session_cookies.json")
DEFAULT_CAPTCHA_QUEUE = Path("data/captcha_queue.json")


def _host_key(url_or_host: str) -> str:
    s = (url_or_host or "").strip().lower()
    if "://" in s:
        s = urlparse(s).netloc or s
    s = s.split(":")[0].lstrip(".")
    if s.startswith("www."):
        s = s[4:]
    return s


class CookieJarStore:
    """Load/save domain-keyed cookie dicts for requests/curl_cffi sessions."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_COOKIE_PATH
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self.load()

    def load(self) -> None:
        self._data = {}
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, list):
                        self._data[_host_key(k)] = [c for c in v if isinstance(c, dict)]
        except (OSError, json.JSONDecodeError, TypeError):
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def cookies_for_url(self, url: str) -> List[Dict[str, Any]]:
        host = _host_key(url)
        out: List[Dict[str, Any]] = []
        for domain, cookies in self._data.items():
            if host == domain or host.endswith("." + domain) or domain.endswith("." + host):
                out.extend(cookies)
        return out

    def apply_to_session(self, session: Any, url: str = "") -> int:
        """Copy stored cookies into a requests/curl_cffi session. Returns count."""
        n = 0
        if url:
            targets = [(_host_key(url), self.cookies_for_url(url))]
        else:
            targets = list(self._data.items())
        for domain, cookies in targets:
            for c in cookies:
                name = c.get("name")
                value = c.get("value")
                if not name or value is None:
                    continue
                try:
                    # requests-compatible
                    session.cookies.set(
                        str(name),
                        str(value),
                        domain=c.get("domain") or domain,
                        path=c.get("path") or "/",
                    )
                    n += 1
                except Exception:
                    try:
                        session.cookies.set(str(name), str(value))
                        n += 1
                    except Exception:
                        pass
        return n

    def capture_from_session(self, session: Any, url: str) -> int:
        """Persist cookies currently on the session for this URL's host."""
        host = _host_key(url)
        if not host:
            return 0
        captured: List[Dict[str, Any]] = []
        try:
            jar = getattr(session, "cookies", None)
            if jar is None:
                return 0
            # requests CookieJar or dict-like
            if hasattr(jar, "items") and not hasattr(jar, "__iter__"):
                for name, value in jar.items():
                    captured.append({"name": name, "value": value, "domain": host, "path": "/"})
            else:
                for c in jar:
                    try:
                        name = getattr(c, "name", None) or c.get("name")
                        value = getattr(c, "value", None) if hasattr(c, "value") else c.get("value")
                        domain = getattr(c, "domain", None) or (c.get("domain") if isinstance(c, dict) else None) or host
                        path = getattr(c, "path", None) or (c.get("path") if isinstance(c, dict) else None) or "/"
                        if name and value is not None:
                            captured.append(
                                {
                                    "name": str(name),
                                    "value": str(value),
                                    "domain": str(domain).lstrip("."),
                                    "path": str(path) or "/",
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            return 0
        if not captured:
            return 0
        # merge by name
        existing = {c["name"]: c for c in self._data.get(host, []) if c.get("name")}
        for c in captured:
            existing[c["name"]] = c
        self._data[host] = list(existing.values())
        self.save()
        return len(captured)

    def import_cookies(self, raw: str, default_domain: str = "") -> int:
        """
        Import cookies from JSON or Netscape text. Returns number imported.
        """
        text = (raw or "").strip()
        if not text:
            return 0
        imported = 0
        # JSON array or object
        if text.startswith("[") or text.startswith("{"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict) and "cookies" in data:
                data = data["cookies"]
            if isinstance(data, list):
                for c in data:
                    if not isinstance(c, dict):
                        continue
                    name = c.get("name") or c.get("Name")
                    value = c.get("value") if "value" in c else c.get("Value")
                    domain = (
                        c.get("domain")
                        or c.get("Domain")
                        or default_domain
                        or ""
                    )
                    domain = _host_key(str(domain))
                    if not name or value is None or not domain:
                        continue
                    host = domain
                    bucket = {x["name"]: x for x in self._data.get(host, []) if x.get("name")}
                    bucket[str(name)] = {
                        "name": str(name),
                        "value": str(value),
                        "domain": host,
                        "path": str(c.get("path") or c.get("Path") or "/"),
                        "secure": bool(c.get("secure") or c.get("Secure")),
                    }
                    self._data[host] = list(bucket.values())
                    imported += 1
            elif isinstance(data, dict):
                # host -> list
                for host, cookies in data.items():
                    if not isinstance(cookies, list):
                        continue
                    for c in cookies:
                        if isinstance(c, dict) and c.get("name"):
                            h = _host_key(host)
                            bucket = {x["name"]: x for x in self._data.get(h, []) if x.get("name")}
                            bucket[c["name"]] = {
                                "name": c["name"],
                                "value": str(c.get("value", "")),
                                "domain": h,
                                "path": c.get("path") or "/",
                            }
                            self._data[h] = list(bucket.values())
                            imported += 1
        else:
            # Netscape / cookie header lines
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Cookie: a=b; c=d
                if line.lower().startswith("cookie:"):
                    line = line.split(":", 1)[1].strip()
                    domain = _host_key(default_domain) or "unknown"
                    for part in line.split(";"):
                        if "=" not in part:
                            continue
                        name, value = part.split("=", 1)
                        name, value = name.strip(), value.strip()
                        if not name:
                            continue
                        bucket = {x["name"]: x for x in self._data.get(domain, []) if x.get("name")}
                        bucket[name] = {"name": name, "value": value, "domain": domain, "path": "/"}
                        self._data[domain] = list(bucket.values())
                        imported += 1
                    continue
                # Netscape: domain flag path secure expiry name value
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain, _flag, path, _secure, _exp, name, value = parts[:7]
                    domain = _host_key(domain)
                    if not domain or not name:
                        continue
                    bucket = {x["name"]: x for x in self._data.get(domain, []) if x.get("name")}
                    bucket[name] = {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": path or "/",
                    }
                    self._data[domain] = list(bucket.values())
                    imported += 1
                    continue
                # name=value
                if "=" in line and "\t" not in line:
                    domain = _host_key(default_domain)
                    if not domain:
                        continue
                    name, value = line.split("=", 1)
                    name, value = name.strip(), value.strip()
                    bucket = {x["name"]: x for x in self._data.get(domain, []) if x.get("name")}
                    bucket[name] = {"name": name, "value": value, "domain": domain, "path": "/"}
                    self._data[domain] = list(bucket.values())
                    imported += 1
        if imported:
            self.save()
        return imported

    def clear(self, domain: Optional[str] = None) -> None:
        if domain:
            self._data.pop(_host_key(domain), None)
        else:
            self._data = {}
        self.save()

    def summary(self) -> Dict[str, int]:
        return {k: len(v) for k, v in sorted(self._data.items())}


class CaptchaQueue:
    """URLs that hit CAPTCHA/WAF — for manual browser completion + retry."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_CAPTCHA_QUEUE
        self._items: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        self._items = []
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self._items = [x for x in raw if isinstance(x, dict) and x.get("url")]
        except (OSError, json.JSONDecodeError, TypeError):
            self._items = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep last 500
        self._items = self._items[-500:]
        self.path.write_text(
            json.dumps(self._items, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def add(
        self,
        url: str,
        *,
        jurisdiction: str = "",
        reason: str = "captcha",
        name: str = "",
    ) -> None:
        url = (url or "").strip()
        if not url:
            return
        # de-dupe by url
        self._items = [x for x in self._items if x.get("url") != url]
        self._items.append(
            {
                "url": url,
                "jurisdiction": (jurisdiction or "").upper()[:8],
                "reason": reason or "captcha",
                "name": name or "",
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
        self.save()

    def list_items(self) -> List[Dict[str, Any]]:
        return list(self._items)

    def clear(self) -> None:
        self._items = []
        self.save()

    def remove_url(self, url: str) -> bool:
        before = len(self._items)
        self._items = [x for x in self._items if x.get("url") != url]
        if len(self._items) < before:
            self.save()
            return True
        return False

    def peek_next(self) -> Optional[Dict[str, Any]]:
        """Most recently queued item (or None)."""
        return dict(self._items[-1]) if self._items else None

    def mark_opened(self, url: str) -> None:
        """Stamp an item after the user opens it in a browser."""
        url = (url or "").strip()
        if not url:
            return
        for item in self._items:
            if item.get("url") == url:
                item["opened_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                item["opened"] = True
                self.save()
                return

    def mark_cookies_pulled(self, url: str, count: int = 0) -> None:
        url = (url or "").strip()
        if not url:
            return
        for item in self._items:
            if item.get("url") == url:
                item["cookies_pulled_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                item["cookies_pulled"] = int(count or 0)
                self.save()
                return
