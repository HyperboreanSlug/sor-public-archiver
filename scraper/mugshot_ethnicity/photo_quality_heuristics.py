"""Image heuristics for non-mugshot detection (silhouette, QR, UI icons)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

# Silhouette heuristic thresholds (white bg + dark outline).
WHITE_FRAC_MIN = 0.70
BLACK_FRAC_MIN = 0.05
MID_FRAC_MAX = 0.10
STUB_SIZE_MIN = 2_000
STUB_SIZE_MAX = 25_000

# QR-code heuristic (square B/W modules, high transition density).
QR_SIDE_MIN = 80
QR_SIDE_MAX = 400
QR_MID_MAX = 0.08
QR_BLACK_MIN = 0.15
QR_WHITE_MIN = 0.35
QR_TRANS_MIN = 0.15


def gray_hist_fractions(gray) -> Optional[Tuple[float, float, float]]:
    """Return (white, black, mid) fractions for a PIL L-mode image."""
    try:
        import numpy as np

        arr = np.asarray(gray, dtype=np.uint8)
        n = float(arr.size) or 1.0
        white = float((arr > 240).sum()) / n
        black = float((arr < 40).sum()) / n
        return white, black, 1.0 - white - black
    except Exception:
        hist = gray.histogram()
        total = float(sum(hist)) or 1.0
        white = sum(hist[241:256]) / total
        black = sum(hist[0:40]) / total
        return white, black, 1.0 - white - black


def transition_density(gray) -> Optional[Tuple[float, float]]:
    """Horizontal / vertical binary-edge density (QR modules score high)."""
    try:
        import numpy as np

        arr = np.asarray(gray, dtype=np.uint8)
        thr = (arr > 128).astype(np.int16)
        h, w = thr.shape
        if h < 3 or w < 3:
            return None
        ht = float(np.abs(np.diff(thr, axis=1)).sum()) / (h * max(w - 1, 1))
        vt = float(np.abs(np.diff(thr, axis=0)).sum()) / (w * max(h - 1, 1))
        return ht, vt
    except Exception:
        return None


def dominant_color_icon(path: Path) -> bool:
    """True for small UI icons where one color covers a large fraction of pixels."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < 800 or size > 20_000:
        return False
    try:
        from PIL import Image
    except Exception:
        return False
    try:
        with Image.open(path) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            if max(w, h) > 160 or min(w, h) < 40:
                return False
            small = rgb.resize((64, 64))
            try:
                q = small.quantize(colors=32, method=Image.Quantize.MEDIANCUT)
            except AttributeError:
                q = small.quantize(colors=32, method=0)
            colors = q.getcolors() or []
            if not colors:
                return False
            top = max(c for c, _ in colors)
            return (top / float(64 * 64)) >= 0.38
    except Exception:
        return False


def heuristic_silhouette(path: Path) -> bool:
    """True if image looks like a white-bg black-outline silhouette stub."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size < STUB_SIZE_MIN or size > STUB_SIZE_MAX:
        return False
    try:
        from PIL import Image
    except Exception:
        return False
    try:
        with Image.open(path) as im:
            gray = im.convert("L")
            gray.thumbnail((160, 160))
            fr = gray_hist_fractions(gray)
            if fr is None:
                return False
            white, black, mid = fr
        return (
            white >= WHITE_FRAC_MIN
            and black >= BLACK_FRAC_MIN
            and mid <= MID_FRAC_MAX
        )
    except Exception:
        return False


def heuristic_qr_code(path: Path) -> bool:
    """True if image looks like a QR code (not a face mugshot)."""
    try:
        from PIL import Image
    except Exception:
        return False
    try:
        with Image.open(path) as im:
            w, h = im.size
            if min(w, h) < QR_SIDE_MIN or max(w, h) > QR_SIDE_MAX:
                return False
            if not (0.85 <= w / float(h) <= 1.15):
                return False
            gray = im.convert("L")
            if max(w, h) > 200:
                gray = gray.copy()
                gray.thumbnail((200, 200))
            fr = gray_hist_fractions(gray)
            if fr is None:
                return False
            white, black, mid = fr
            if mid >= QR_MID_MAX or black <= QR_BLACK_MIN or white <= QR_WHITE_MIN:
                return False
            td = transition_density(gray)
            if td is None:
                return False
            ht, vt = td
            return ht >= QR_TRANS_MIN and vt >= QR_TRANS_MIN
    except Exception:
        return False


def bytes_looks_like_qr(data: bytes) -> bool:
    """In-memory QR check for pre-write rejection."""
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if min(w, h) < QR_SIDE_MIN or max(w, h) > QR_SIDE_MAX:
                return False
            if not (0.85 <= w / float(h) <= 1.15):
                return False
            gray = im.convert("L")
            if max(w, h) > 200:
                gray = gray.copy()
                gray.thumbnail((200, 200))
            fr = gray_hist_fractions(gray)
            if fr is None:
                return False
            white, black, mid = fr
            if mid >= QR_MID_MAX or black <= QR_BLACK_MIN or white <= QR_WHITE_MIN:
                return False
            td = transition_density(gray)
            if td is None:
                return False
            ht, vt = td
            return ht >= QR_TRANS_MIN and vt >= QR_TRANS_MIN
    except Exception:
        return False


def bytes_looks_like_silhouette(data: bytes) -> bool:
    """In-memory silhouette stub check."""
    if not (STUB_SIZE_MIN <= len(data) <= STUB_SIZE_MAX):
        return False
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(data)) as im:
            gray = im.convert("L")
            gray.thumbnail((160, 160))
            fr = gray_hist_fractions(gray)
            if fr is None:
                return False
            white, black, mid = fr
            return (
                white >= WHITE_FRAC_MIN
                and black >= BLACK_FRAC_MIN
                and mid <= MID_FRAC_MAX
            )
    except Exception:
        return False
