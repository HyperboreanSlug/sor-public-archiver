"""Extract demographic fields from public report PDFs (PA Megan's Law, etc.)."""
from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import urljoin

# Label: value on same or next line (PA PDF layout).
_FIELD_RE = re.compile(
    r"(?im)^\s*(Ethnicity|Race|Gender|Sex|Height|Weight|Eyes|Eye Color|"
    r"Hair|Hair Color|Year of Birth|Date of Birth|DOB)\s*:\s*(.+?)\s*$"
)

# When label and value are on adjacent lines (common in PA public report)
_FIELD_NEXT_RE = re.compile(
    r"(?im)^\s*(Ethnicity|Race|Gender|Sex|Height|Weight|Eyes|Eye Color|"
    r"Hair|Hair Color|Year of Birth)\s*:\s*\n\s*(.+?)\s*$"
)

_LABEL_TO_KEY = {
    "ethnicity": "ethnicity",
    "race": "race",
    "gender": "gender",
    "sex": "gender",
    "height": "height",
    "weight": "weight",
    "eyes": "eye_color",
    "eye color": "eye_color",
    "hair": "hair_color",
    "hair color": "hair_color",
    "year of birth": "date_of_birth",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
}

_PA_REPORT_HREF_RE = re.compile(
    r"""(?ix)
    href\s*=\s*["']([^"']*MegansOffenderReports[^"']*)["']
    |
    href\s*=\s*["']([^"']*ReportName=OffenderPublicRpt[^"']*)["']
    """
)


def extract_pdf_text(data: bytes) -> str:
    """Return concatenated text from PDF bytes, or empty string."""
    if not data or not data.startswith(b"%PDF"):
        return ""
    try:
        from pypdf import PdfReader
        import io
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                parts.append(t)
        return "\n".join(parts)
    except Exception:
        return ""


def _clean_val(val: str) -> str:
    return " ".join((val or "").split()).strip(" :-")


def _is_plausible_demo_value(key: str, val: str) -> bool:
    v = (val or "").strip()
    if not v or len(v) > 80:
        return False
    low = v.lower()
    if low.startswith("pennsylvania") or low in (
        "gender", "race", "ethnicity", "height", "weight", "eyes", "hair",
        "residential address", "employment address", "physical description",
        "offender type", "primary", "address", "municipality", "county",
    ):
        return False
    if key == "date_of_birth":
        return bool(re.fullmatch(r"(?:19|20)\d{2}", v) or re.search(r"\d{1,2}[/\-]\d{1,2}", v))
    if key == "gender":
        return bool(re.fullmatch(r"(?i)male|female|m|f|man|woman", v))
    if key in ("race", "ethnicity"):
        return bool(re.search(r"[A-Za-z]{3,}", v)) and not re.fullmatch(
            r"(?i)gender|race|ethnicity", v
        )
    return True


def fields_from_pdf_text(text: str) -> Dict[str, str]:
    """Parse label/value demographic fields from extracted PDF text."""
    found: Dict[str, str] = {}
    if not (text or "").strip():
        return found

    # Normalize PA line breaks: "HISPANIC OR \nLATINO" → "HISPANIC OR LATINO"
    norm = re.sub(r"\r\n?", "\n", text)
    norm = re.sub(r"([A-Za-z])\n([a-z])", r"\1 \2", norm)
    norm = re.sub(r"(?m)(OR)\s*\n\s*([A-Z]{2,})", r"\1 \2", norm)

    # Same-line or next-line Label: value (skip label-like values)
    for rx in (_FIELD_RE, _FIELD_NEXT_RE):
        for m in rx.finditer(norm):
            lab = m.group(1).strip().lower()
            val = _clean_val(m.group(2))
            key = _LABEL_TO_KEY.get(lab)
            if not key or not _is_plausible_demo_value(key, val):
                continue
            found.setdefault(key, val)

    # PA public report: Ethnicity on following line(s)
    if "ethnicity" not in found:
        m = re.search(
            r"(?is)Ethnicity\s*:\s*\n\s*([A-Z][A-Z /]+(?:\n[A-Z][A-Z /]+)?)",
            norm,
        )
        if m:
            val = _clean_val(m.group(1))
            if _is_plausible_demo_value("ethnicity", val):
                found["ethnicity"] = val

    # PA: "Race:\nGender:\nWHITE\nMALE"
    if "race" not in found or not _is_plausible_demo_value("race", found.get("race", "")):
        m = re.search(
            r"(?is)Race\s*:\s*\n\s*Gender\s*:\s*\n\s*([A-Z][A-Z /]+)\s*\n\s*(MALE|FEMALE)",
            norm,
        )
        if m:
            found["race"] = m.group(1).strip()
            found.setdefault("gender", m.group(2).strip())

    # PA: year of birth printed above the label
    if "date_of_birth" not in found or not _is_plausible_demo_value(
        "date_of_birth", found.get("date_of_birth", "")
    ):
        m = re.search(r"(?m)^\s*((?:19|20)\d{2})\s*\n\s*Year of Birth\s*:", norm)
        if m:
            found["date_of_birth"] = m.group(1)

    # Drop any junk values that slipped through
    for k in list(found.keys()):
        if not _is_plausible_demo_value(k, str(found[k])):
            found.pop(k, None)

    return found


def find_pa_public_report_url(html: str, base_url: str = "") -> Optional[str]:
    """Return absolute URL for PA Megan's Law 'View Report' PDF, if present."""
    if not html:
        return None
    m = _PA_REPORT_HREF_RE.search(html)
    if not m:
        return None
    href = (m.group(1) or m.group(2) or "").strip()
    if not href:
        return None
    href = href.replace("&amp;", "&")
    if base_url:
        return urljoin(base_url, href)
    if href.startswith("http"):
        return href
    return "https://www.meganslaw.psp.pa.gov" + (
        href if href.startswith("/") else "/" + href
    )


def merge_pdf_fields(
    target: Dict[str, object],
    pdf_fields: Dict[str, str],
    *,
    overwrite: bool = False,
) -> None:
    """Copy PDF fields into *target* when missing (or always if overwrite)."""
    for k, v in pdf_fields.items():
        if not v:
            continue
        cur = str(target.get(k) or "").strip()
        if overwrite or not cur:
            target[k] = v


def should_try_pa_public_report(
    html: str,
    base_url: str = "",
    jurisdiction: str = "",
) -> bool:
    """True when this page/jurisdiction may need the PA View Report PDF."""
    jur = (jurisdiction or "").upper().replace(" ", "")
    parts = [p for p in re.split(r"[|,;/]+", jur) if p]
    if "PA" in parts:
        return True
    blob = f"{base_url} {html[:4000]}".lower()
    return "meganslaw.psp.pa.gov" in blob or "megansoffenderreports" in blob


def load_pa_public_report_fields(
    get_bytes_fn,
    html: str,
    base_url: str = "",
) -> Dict[str, str]:
    """
    Download PA 'View Report' PDF via *get_bytes_fn(url) -> bytes|None*
    and return parsed demographic fields.
    """
    url = find_pa_public_report_url(html, base_url)
    if not url:
        return {}
    try:
        data = get_bytes_fn(url)
    except Exception:
        return {}
    if not data or not isinstance(data, (bytes, bytearray)):
        return {}
    if bytes(data[:4]) != b"%PDF":
        return {}
    return fields_from_pdf_text(extract_pdf_text(bytes(data)))
