"""Parse one semicolon-separated offense clause into a short label."""
from __future__ import annotations

import re
from typing import Optional

from scraper.crime_summary_junk import (
    is_junk_label,
    is_statute_or_docket,
    strip_statute_cites,
)
from scraper.crime_summary_maps import CODE_MAP, DROP_CLAUSE, OFFENSE_MAP

_DATE = re.compile(
    r"(?ix)\b(?:"
    r"\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}"
    r"|\d{4}-\d{1,2}-\d{1,2}"
    r"|(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\.?\s+\d{1,2},?\s+\d{2,4}"
    r")\b"
)

_COURT_JUNK = re.compile(
    r"(?ix)\b(?:"
    r"(?:county|judicial\s+district|superior\s+court|circuit\s+court|"
    r"district\s+court|dept\.?\s+of\s+corrections|ndoc|doc)\b.*"
    r")$"
)

_LOCATION_TRAIL = re.compile(
    r"(?ix)"
    r"(?:"
    r",?\s*(?:in\s+)?(?:the\s+)?(?:city|county|state)\s+of\s+.+$"
    r"|,?\s*(?:resides?|residence|address|located)\s*(?:at|in|:)\s*.+$"
    r"|,?\s*\d{1,6}\s+[A-Za-z0-9.\- ]{2,40}\s+"
    r"(?:st|street|ave|avenue|blvd|rd|road|dr|drive|ln|lane|ct|court|way|hwy)\b.+$"
    r")$"
)
CITY_STATE = re.compile(
    r"(?ix)\b[A-Za-z][A-Za-z.\-']+(?:\s+[A-Za-z][A-Za-z.\-']+){0,3}"
    r",\s*[A-Z]{2}\b(?:\s+\d{5}(?:-\d{4})?)?"
)
COUNTY_LOC = re.compile(
    r"(?ix)\b[A-Za-z][A-Za-z.\-']+(?:\s+[A-Za-z][A-Za-z.\-']+)?\s+"
    r"County(?:,\s*[A-Z]{2})?\b"
)

_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)"
)


def norm(s: str) -> str:
    return " ".join((s or "").split()).strip(" ;,|")


def strip_dates(s: str) -> str:
    t = _DATE.sub(" ", s)
    t = re.sub(rf"(?i)\b{_MONTHS}\.?\s+\d{{1,2}},?\s+\d{{2,4}}\b", " ", t)
    t = re.sub(r"\(\s*(?:19|20)\d{2}\s*\)", " ", t)
    t = re.sub(r"\b(?:19|20)\d{2}\b", " ", t)
    return norm(t)


def strip_location_junk(s: str) -> str:
    t = s or ""
    t = _LOCATION_TRAIL.sub(" ", t)
    t = CITY_STATE.sub(" ", t)
    t = COUNTY_LOC.sub(" ", t)
    t = re.sub(r"(?i)\b(?:guilty/?convict(?:ed)?|adjudication\s+withheld)\b", " ", t)
    t = re.sub(r"(?i)\b(?:at\s+)?(?:last\s+)?known\s+(?:address|location)\b.*$", " ", t)
    t = re.sub(r"\s*[|;]\s*", " · ", t)
    t = re.sub(r"(?:\s*·\s*)+", " · ", t)
    return norm(t.strip(" ·;,"))


def title_offense(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if s.isupper() and len(s) < 40:
        return s.title()
    low = s.lower()
    if low.startswith("sexual battery"):
        rest = s[len("sexual battery") :].strip(" -:")
        return ("Sexual battery " + rest).strip() if rest else "Sexual battery"
    return s[0].upper() + s[1:] if len(s) > 1 else s.upper()


def extract_from_clause(clause: str) -> Optional[str]:
    c = norm(clause)
    if not c or len(c) < 3 or DROP_CLAUSE.match(c) or is_statute_or_docket(c):
        return None

    c = strip_dates(c)
    c = strip_statute_cites(c)
    if not c or DROP_CLAUSE.match(c) or is_statute_or_docket(c) or is_junk_label(c):
        return None

    src = clause + " " + c
    for rx, label in CODE_MAP:
        if rx.search(src):
            return label
    m = re.search(r"CHILD\s+MOLESTATION[- ]?(\d)", src, re.I)
    if m:
        return f"Child molestation {m.group(1)}"
    if re.search(r"\blewd\b|\blascivious\b", src, re.I):
        return None

    m = re.search(r"—\s*(.+)$", c)
    if m and len(m.group(1)) > 8:
        c = norm(m.group(1))
    m = re.search(r"§\s*[\d\-.]+\s*[—-]\s*(.+)$", c)
    if m and len(m.group(1)) > 8:
        c = norm(m.group(1))

    if re.search(r"\blewd\b|\blascivious\b", c, re.I):
        return None
    if is_statute_or_docket(c) or is_junk_label(c):
        return None

    if re.search(r"sexual\s+battery", c, re.I):
        extra = []
        if re.search(r"weapon|force|wpn", c, re.I):
            extra.append("weapon/force")
        if re.search(r"under\s*12", c, re.I):
            extra.append("victim under 12")
        if re.search(r"injury\s+not\s+likely", c, re.I):
            extra.append("injury not likely")
        base = "Sexual battery"
        return f"{base} — {', '.join(extra)}" if extra else base

    for pat, lab in OFFENSE_MAP:
        if re.search(pat, c, re.I):
            if "porn" in lab.lower():
                m_c = re.search(r"\(\s*(\d+)\s*counts?\s*\)", src, re.I)
                if m_c:
                    return f"{lab} — {m_c.group(1)} counts"
            return lab

    c2 = _COURT_JUNK.sub("", c).strip(" ;,")
    c2 = strip_statute_cites(strip_location_junk(c2))
    if not c2 or len(c2) < 4:
        return None
    if DROP_CLAUSE.match(c2) or is_statute_or_docket(c2) or is_junk_label(c2):
        return None
    if len(c2) > 90:
        c2 = re.split(r"\s+where\s+|\s+by\s+offender\s+", c2, maxsplit=1)[0]
        c2 = strip_location_junk(norm(c2))
        if len(c2) > 80:
            return None
    if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}$", c2) and not re.search(
        r"sexual|lewd|rape|child|assault|battery", c2, re.I
    ):
        return None
    if CITY_STATE.fullmatch(c2) or COUNTY_LOC.fullmatch(c2) or is_junk_label(c2):
        return None
    return title_offense(c2)
