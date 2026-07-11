"""Pull cookies from installed browsers (Chrome / Edge / Firefox) for a host.

Used by Settings → Access assistance after the user opens a blocked URL and
completes the CAPTCHA/WAF challenge in a normal browser.

Windows Chromium browsers store cookies encrypted (DPAPI + AES-GCM). This
module copies the SQLite DB (so Chrome can stay open), decrypts values, and
returns cookie dicts compatible with ``CookieJarStore.import_cookies``.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse


def host_from_url(url_or_host: str) -> str:
    s = (url_or_host or "").strip().lower()
    if "://" in s:
        s = urlparse(s).netloc or s
    s = s.split(":")[0].lstrip(".")
    if s.startswith("www."):
        s = s[4:]
    return s


def _domain_matches(cookie_domain: str, target_host: str) -> bool:
    d = (cookie_domain or "").strip().lower().lstrip(".")
    h = (target_host or "").strip().lower().lstrip(".")
    if not d or not h:
        return False
    if h == d or h.endswith("." + d) or d.endswith("." + h):
        return True
    # parent e.g. cookie .state.fl.us for host offender.fdle.state.fl.us
    parts = h.split(".")
    for i in range(len(parts) - 1):
        parent = ".".join(parts[i:])
        if parent == d or d.endswith("." + parent):
            return True
    return False


def _dpapi_decrypt(data: bytes) -> Optional[bytes]:
    """Windows DPAPI decrypt (CryptUnprotectData)."""
    if sys.platform != "win32" or not data:
        return None
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        blob_in = DATA_BLOB(
            len(data),
            ctypes.create_string_buffer(data, len(data)),
        )
        blob_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(blob_out),
        ):
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return None


def _aes_gcm_decrypt(key: bytes, encrypted: bytes) -> Optional[bytes]:
    """Decrypt Chrome v10/v20 cookie payload (nonce + ciphertext+tag)."""
    if not encrypted or len(encrypted) < 3 + 12 + 16:
        return None
    # prefix v10 / v11 / v20
    payload = encrypted[3:]
    nonce, rest = payload[:12], payload[12:]
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        return AESGCM(key).decrypt(nonce, rest, None)
    except Exception:
        pass
    # Soft fallback: pycryptodome
    try:
        from Crypto.Cipher import AES  # type: ignore

        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(rest[:-16], rest[-16:])
    except Exception:
        return None


def _chrome_master_key(user_data_dir: Path) -> Optional[bytes]:
    local_state = user_data_dir / "Local State"
    if not local_state.is_file():
        return None
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        enc = data.get("os_crypt", {}).get("encrypted_key")
        if not enc:
            return None
        raw = base64.b64decode(enc)
        # Windows: b'DPAPI' prefix
        if raw.startswith(b"DPAPI"):
            raw = raw[5:]
        return _dpapi_decrypt(raw)
    except Exception:
        return None


def _decrypt_chrome_value(value: bytes, master_key: Optional[bytes]) -> str:
    if not value:
        return ""
    # Chromium: v10/v11/v20 + AES-GCM
    if value[:3] in (b"v10", b"v11", b"v20") and master_key:
        plain = _aes_gcm_decrypt(master_key, value)
        if plain is not None:
            try:
                return plain.decode("utf-8", errors="replace")
            except Exception:
                return plain.decode("latin-1", errors="replace")
    # Older pure DPAPI
    plain = _dpapi_decrypt(value)
    if plain is not None:
        try:
            return plain.decode("utf-8", errors="replace")
        except Exception:
            return plain.decode("latin-1", errors="replace")
    # Sometimes stored as plain text in odd profiles
    try:
        return value.decode("utf-8")
    except Exception:
        return ""


def _chromium_cookie_db_paths(user_data_dir: Path) -> List[Path]:
    """Likely Cookies SQLite paths for Default + Profile *."""
    out: List[Path] = []
    if not user_data_dir.is_dir():
        return out
    profiles = ["Default"]
    try:
        profiles.extend(
            sorted(
                p.name
                for p in user_data_dir.iterdir()
                if p.is_dir() and p.name.startswith("Profile")
            )
        )
    except OSError:
        pass
    for prof in profiles:
        base = user_data_dir / prof
        for rel in ("Network/Cookies", "Cookies"):
            p = base / rel
            if p.is_file():
                out.append(p)
    return out


def _pull_chromium(
    user_data_dir: Path,
    target_host: str,
    *,
    browser_label: str,
) -> Tuple[List[Dict[str, Any]], str]:
    """Return (cookies, note)."""
    dbs = _chromium_cookie_db_paths(user_data_dir)
    if not dbs:
        return [], f"{browser_label}: no cookie DB under {user_data_dir}"
    master = _chrome_master_key(user_data_dir)
    if master is None and sys.platform == "win32":
        # May still work for plain/DPAPI-only values
        pass
    found: List[Dict[str, Any]] = []
    errors: List[str] = []
    for db_path in dbs:
        tmp = None
        try:
            fd, tmp_name = tempfile.mkstemp(suffix=".cookies.db")
            os.close(fd)
            tmp = Path(tmp_name)
            # Chrome locks the live DB — copy
            shutil.copy2(db_path, tmp)
            # Also try -wal/-shm if present (best-effort)
            for suffix in ("-wal", "-shm"):
                side = Path(str(db_path) + suffix)
                if side.is_file():
                    try:
                        shutil.copy2(side, Path(str(tmp) + suffix))
                    except OSError:
                        pass
            conn = sqlite3.connect(str(tmp))
            try:
                conn.row_factory = sqlite3.Row
                # host_key is eTLD+1 style; also filter host_key LIKE
                rows = conn.execute(
                    "SELECT host_key, name, value, encrypted_value, path, is_secure "
                    "FROM cookies"
                ).fetchall()
            finally:
                conn.close()
            for row in rows:
                host_key = (row["host_key"] or "").lstrip(".")
                if not _domain_matches(host_key, target_host):
                    continue
                name = row["name"]
                if not name:
                    continue
                raw_val = row["value"] or ""
                if not raw_val and row["encrypted_value"]:
                    enc = row["encrypted_value"]
                    if isinstance(enc, memoryview):
                        enc = enc.tobytes()
                    elif not isinstance(enc, (bytes, bytearray)):
                        enc = bytes(enc)
                    raw_val = _decrypt_chrome_value(bytes(enc), master)
                if raw_val is None or raw_val == "":
                    # keep empty values rarely useful — skip
                    if not row["encrypted_value"]:
                        continue
                    if not raw_val:
                        continue
                found.append(
                    {
                        "name": str(name),
                        "value": str(raw_val),
                        "domain": host_key,
                        "path": str(row["path"] or "/"),
                        "secure": bool(row["is_secure"]),
                        "source": browser_label,
                    }
                )
        except Exception as e:
            errors.append(f"{db_path.name}: {e}")
        finally:
            if tmp is not None:
                for p in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
                    try:
                        if p.exists():
                            p.unlink()
                    except OSError:
                        pass
    note = f"{browser_label}: {len(found)} cookie(s)"
    if errors and not found:
        note += " · " + "; ".join(errors[:2])
    return found, note


def _pull_firefox(target_host: str) -> Tuple[List[Dict[str, Any]], str]:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox" / "Profiles"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    else:
        base = Path.home() / ".mozilla" / "firefox"
    if not base.is_dir():
        return [], "Firefox: profile dir not found"
    found: List[Dict[str, Any]] = []
    try:
        profiles = [p for p in base.iterdir() if p.is_dir()]
    except OSError:
        return [], "Firefox: cannot list profiles"
    for prof in profiles:
        db = prof / "cookies.sqlite"
        if not db.is_file():
            continue
        tmp = None
        try:
            fd, tmp_name = tempfile.mkstemp(suffix=".ff.cookies.db")
            os.close(fd)
            tmp = Path(tmp_name)
            shutil.copy2(db, tmp)
            conn = sqlite3.connect(str(tmp))
            try:
                rows = conn.execute(
                    "SELECT host, name, value, path, isSecure FROM moz_cookies"
                ).fetchall()
            finally:
                conn.close()
            for host, name, value, path, secure in rows:
                host_s = (host or "").lstrip(".")
                if not _domain_matches(host_s, target_host):
                    continue
                if not name:
                    continue
                found.append(
                    {
                        "name": str(name),
                        "value": str(value or ""),
                        "domain": host_s,
                        "path": str(path or "/"),
                        "secure": bool(secure),
                        "source": "Firefox",
                    }
                )
        except Exception:
            continue
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass
    return found, f"Firefox: {len(found)} cookie(s)"


def _pull_browser_cookie3(target_host: str) -> Tuple[List[Dict[str, Any]], str]:
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        return [], "browser_cookie3 not installed"
    found: List[Dict[str, Any]] = []
    loaders = []
    for name in ("chrome", "edge", "chromium", "firefox", "brave"):
        fn = getattr(browser_cookie3, name, None)
        if callable(fn):
            loaders.append((name, fn))
    notes = []
    for name, fn in loaders:
        try:
            jar = fn(domain_name=target_host)
            n0 = len(found)
            for c in jar:
                domain = (getattr(c, "domain", None) or target_host).lstrip(".")
                if not _domain_matches(domain, target_host):
                    continue
                found.append(
                    {
                        "name": c.name,
                        "value": c.value,
                        "domain": domain,
                        "path": getattr(c, "path", None) or "/",
                        "secure": bool(getattr(c, "secure", False)),
                        "source": f"browser_cookie3:{name}",
                    }
                )
            notes.append(f"{name}+{len(found) - n0}")
        except Exception as e:
            notes.append(f"{name}:err")
            continue
    return found, "browser_cookie3: " + ",".join(notes) if notes else "browser_cookie3: none"


def chromium_user_data_dirs() -> List[Tuple[str, Path]]:
    """Return (label, User Data path) for common Chromium browsers."""
    out: List[Tuple[str, Path]] = []
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if sys.platform == "win32" and local:
        candidates = [
            ("Chrome", local / "Google" / "Chrome" / "User Data"),
            ("Edge", local / "Microsoft" / "Edge" / "User Data"),
            ("Brave", local / "BraveSoftware" / "Brave-Browser" / "User Data"),
            ("Chromium", local / "Chromium" / "User Data"),
        ]
    elif sys.platform == "darwin":
        supp = Path.home() / "Library" / "Application Support"
        candidates = [
            ("Chrome", supp / "Google" / "Chrome"),
            ("Edge", supp / "Microsoft Edge"),
            ("Brave", supp / "BraveSoftware" / "Brave-Browser"),
        ]
    else:
        config = Path.home() / ".config"
        candidates = [
            ("Chrome", config / "google-chrome"),
            ("Edge", config / "microsoft-edge"),
            ("Brave", config / "BraveSoftware" / "Brave-Browser"),
            ("Chromium", config / "chromium"),
        ]
    for label, path in candidates:
        if path.is_dir():
            out.append((label, path))
    return out


def pull_cookies_for_host(
    url_or_host: str,
    *,
    browsers: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Pull cookies matching *url_or_host* from local browsers.

    Returns dict:
      cookies: list[dict]
      host: str
      notes: list[str]
      count: int
    """
    host = host_from_url(url_or_host)
    if not host:
        return {"cookies": [], "host": "", "notes": ["No host in URL"], "count": 0}

    want = {b.lower() for b in browsers} if browsers else None
    all_cookies: List[Dict[str, Any]] = []
    notes: List[str] = []

    # 1) Native Chromium (Chrome/Edge/…)
    for label, udata in chromium_user_data_dirs():
        if want is not None and label.lower() not in want:
            continue
        cookies, note = _pull_chromium(udata, host, browser_label=label)
        notes.append(note)
        all_cookies.extend(cookies)

    # 2) Firefox
    if want is None or "firefox" in want:
        cookies, note = _pull_firefox(host)
        notes.append(note)
        all_cookies.extend(cookies)

    # 3) browser_cookie3 optional boost
    cookies, note = _pull_browser_cookie3(host)
    if cookies or "not installed" not in note:
        notes.append(note)
        all_cookies.extend(cookies)

    # Dedupe by (domain, name) — last wins
    bucket: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for c in all_cookies:
        key = (str(c.get("domain") or host).lower(), str(c.get("name") or ""))
        if key[1]:
            bucket[key] = c
    merged = list(bucket.values())
    return {
        "cookies": merged,
        "host": host,
        "notes": notes,
        "count": len(merged),
    }


def pull_and_store(
    url_or_host: str,
    *,
    store: Any = None,
) -> Dict[str, Any]:
    """
    Pull browser cookies for host and merge into CookieJarStore.
    Returns pull result plus imported count.
    """
    from scraper.cookie_jar import CookieJarStore

    jar = store if store is not None else CookieJarStore()
    result = pull_cookies_for_host(url_or_host)
    cookies = result.get("cookies") or []
    imported = 0
    if cookies:
        # Use JSON import path for consistent merge
        imported = jar.import_cookies(json.dumps(cookies))
    result["imported"] = imported
    result["summary"] = jar.summary()
    return result
