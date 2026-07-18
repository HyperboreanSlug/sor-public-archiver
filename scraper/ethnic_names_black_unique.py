"""Shared Anglo/Black surname rules — only *uniquely* Black names drive AA/African labels.

Common English/American surnames (Wade, Washington, Banks, …) appear in both
White and Black populations. They must not classify as African / African
American — and must not flag race=White as a Black misclassification — unless
the given name is a strong African-American signal (e.g. DeShawn Washington).
"""
from __future__ import annotations

from typing import Optional

# English/Irish/French surnames that collide with real African ethnics or are
# too short / multi-ethnic to treat as uniquely Black.
_AFRICAN_ENGLISH_COLLISIONS = frozenset({
    "wade",   # English; also Wolof (Abdoulaye Wade) — not unique
    "fall",   # English; also Wolof
    "kane",   # Irish; also Wolof
    "barry",  # Irish/English; also listed AA
    "ba",     # too short / multi-use
    "sy",     # too short
    "jean", "michel", "noel",  # Francophone shared
    "lee", "king", "brown", "smith", "jones", "williams",
})

# Common US English/American surnames that also appear on AA lists.
# Shared Black/White heritage — not uniquely Black.
_COMMON_US_ENGLISH_SURNAMES = frozenset({
    "adams", "alexander", "allen", "anderson", "bailey", "baker", "banks",
    "barnes", "bell", "bennett", "boyd", "brooks", "brown", "bryant",
    "butler", "campbell", "carter", "charles", "clark", "cole", "coleman",
    "collins", "cook", "cooper", "cotton", "cox", "davis", "diggs",
    "dorsey", "dunbar", "edwards", "ellis", "ellison", "epps", "evans",
    "fisher", "ford", "foster", "freeman", "gibson", "graham", "gray",
    "green", "griffin", "hall", "hamilton", "harris", "harrison", "hayes",
    "henderson", "hill", "howard", "hughes", "jackson", "james", "jefferson",
    "jenkins", "johnson", "jones", "jordan", "kelly", "kennedy", "king",
    "lee", "lewis", "long", "mack", "marshall", "martin", "mason", "miller",
    "mitchell", "montgomery", "moore", "morgan", "morris", "murphy",
    "murray", "myers", "nelson", "owens", "parker", "patterson", "perry",
    "peterson", "phillips", "powell", "price", "reed", "reynolds",
    "richardson", "roberts", "robinson", "rogers", "ross", "russell",
    "sanders", "scott", "simmons", "simpson", "smith", "stevens",
    "stewart", "sullivan", "taylor", "thomas", "thompson", "turner",
    "walker", "wallace", "ward", "washington", "watson", "webb", "wells",
    "west", "white", "williams", "wilson", "wood", "woods", "wright",
    "young", "ashford", "bolden", "bonner", "booker", "burrell", "cowans",
    "crump", "dabney", "dozier", "dupree", "ellison",
})


def is_shared_black_white_surname(surname: Optional[str]) -> bool:
    """True when the surname is common to White and Black populations."""
    s = (surname or "").strip().lower()
    if not s:
        return False
    if s in _AFRICAN_ENGLISH_COLLISIONS:
        return True
    if s in _COMMON_US_ENGLISH_SURNAMES:
        return True
    return False


def is_uniquely_black_surname(surname: Optional[str]) -> bool:
    """Inverse of shared — may still need list membership checked by caller."""
    return not is_shared_black_white_surname(surname)
