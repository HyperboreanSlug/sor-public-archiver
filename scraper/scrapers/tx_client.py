"""Texas DPS SOR client — rapsheet XML by SID."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element

import requests

from scraper.config import DEFAULT_DELAY, MAX_RETRIES, REQUEST_TIMEOUT, USER_AGENT
from scraper.public_links_tx import tx_rapsheet_url, tx_rapsheet_xml_url

_NAME_SPLIT = re.compile(r"\s*,\s*")


class TxSorClient:
    """Fetch public rapsheet XML from sor.dps.texas.gov."""

    def __init__(self, delay: float = DEFAULT_DELAY, timeout: float = REQUEST_TIMEOUT):
        self.delay = max(0.0, float(delay))
        self.timeout = float(timeout)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/xml,text/xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass

    def _pace(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    def fetch_rapsheet_xml(self, sid: str) -> str:
        url = tx_rapsheet_xml_url(sid)
        if not url:
            return ""
        last_exc: Optional[BaseException] = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                self._pace()
                if resp.status_code == 404:
                    return ""
                resp.raise_for_status()
                return resp.text or ""
            except Exception as e:
                last_exc = e
                if attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(self.delay * (attempt + 1) or 0.5)
        if last_exc:
            raise last_exc
        return ""

    def fetch_record(self, sid: str) -> Dict[str, Any]:
        xml_text = self.fetch_rapsheet_xml(sid)
        if not xml_text.strip():
            return {}
        return parse_rapsheet_xml(xml_text, sid=sid)


def _text(el: Optional[Element], tag: str) -> str:
    if el is None:
        return ""
    child = el.find(tag)
    if child is None or child.text is None:
        return ""
    return str(child.text).strip()


def _split_name(nam_txt: str) -> Dict[str, Any]:
    """TX names are usually ``LAST,FIRST MIDDLE``."""
    raw = (nam_txt or "").strip()
    if not raw:
        return {}
    if "," in raw:
        last, rest = _NAME_SPLIT.split(raw, maxsplit=1)
        parts = rest.split()
        first = parts[0] if parts else ""
        middle = " ".join(parts[1:]) if len(parts) > 1 else ""
        full = " ".join(p for p in (first, middle, last) if p)
        return {
            "first_name": first or None,
            "middle_name": middle or None,
            "last_name": last or None,
            "full_name": full or None,
        }
    parts = raw.split()
    if len(parts) >= 2:
        return {
            "first_name": parts[0],
            "middle_name": " ".join(parts[1:-1]) or None,
            "last_name": parts[-1],
            "full_name": raw,
        }
    return {"full_name": raw, "last_name": raw}


def parse_rapsheet_xml(xml_text: str, *, sid: str = "") -> Dict[str, Any]:
    """Map GetRapsheetXml INDV payload → offender record dict."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}
    if root.tag.upper() != "INDV" and root.find("INDV") is not None:
        root = root.find("INDV")  # type: ignore[assignment]
    if root is None:
        return {}

    dps = _text(root, "DPS_NBR") or re.sub(r"\D", "", sid)
    rec: Dict[str, Any] = {
        "external_id": dps or None,
        "source_state": "TX",
        "state": "TX",
        "source_url": tx_rapsheet_url(dps) if dps else None,
        "risk_level": _text(root, "RSK_COD_LIT") or None,
        "gender": _text(root, "SEX_COD_LIT") or None,
        "race": _text(root, "RAC_COD_LIT") or None,
        "ethnicity": _text(root, "ETH_COD_LIT") or None,
        "height": _text(root, "HGT_QTY_formatted") or None,
        "weight": _text(root, "WGT_QTY") or None,
        "hair_color": _text(root, "HAI_COD_LIT") or None,
        "eye_color": _text(root, "EYE_COD_LIT") or None,
        "last_verified": _text(root, "ERD_DTE_formatted") or None,
    }

    # Primary name: TYP_COD B (birth) preferred, else first
    names = root.find("Names")
    chosen = ""
    if names is not None:
        for nm in names.findall("Name"):
            typ = (_text(nm, "TYP_COD") or "").upper()
            txt = _text(nm, "NAM_TXT")
            if not txt:
                continue
            if typ == "B" or not chosen:
                chosen = txt
            if typ == "B":
                break
    if chosen:
        rec.update({k: v for k, v in _split_name(chosen).items() if v})

    bds = root.find("Birthdates")
    if bds is not None:
        for bd in bds.findall("Birthdate"):
            dob = _text(bd, "DOB_DTE_formatted")
            if dob:
                rec["date_of_birth"] = dob
                break

    addrs = root.find("Addresses")
    if addrs is not None:
        for ad in addrs.findall("Address"):
            line1 = _text(ad, "AddressLine1")
            if line1:
                rec["address"] = line1
                break

    offenses = root.find("Offenses")
    crimes: List[str] = []
    if offenses is not None:
        for off in offenses.findall("Offense"):
            title = _text(off, "LEN_TXT")
            cite = _text(off, "CIT_TXT")
            bit = " — ".join(p for p in (title, cite) if p)
            if bit:
                crimes.append(bit)
    if crimes:
        rec["crime"] = "; ".join(crimes)[:800]

    # Drop empty
    return {k: v for k, v in rec.items() if v not in (None, "")}
