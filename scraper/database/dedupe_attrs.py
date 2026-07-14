"""Shared class attributes for dedupe mixins."""
from __future__ import annotations


class DedupeAttrsMixin:
    _GENERIC_URL_MARKERS = (
        "captcha",
        "login",
        "signin",
        "sign-in",
        "challenge",
        "cloudflare",
        "just a moment",
        "cf-browser",
        "accessdenied",
        "access-denied",
        "botdetect",
        "search-public",
        "publicregistrantsearch",
        "sor_public",
        "sort_public",
        "coveredoffender",  # Hawaii landing (often non-unique)
    )
