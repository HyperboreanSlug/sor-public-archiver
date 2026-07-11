"""Ensure DeepFace (local race model) is installed and ready.

Called automatically when mugshot scoring starts with backend auto/deepface.
Installs from ``requirements-vision.txt`` into the current interpreter, then
optionally warms the race model (downloads weights to ``~/.deepface/weights/``).
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Package roots (repo root = parents[2] from this file)
_ROOT = Path(__file__).resolve().parents[2]
_VISION_REQ = _ROOT / "requirements-vision.txt"

# pip names if requirements-vision.txt is missing
_FALLBACK_PACKAGES = [
    "deepface>=0.0.93",
    "tensorflow>=2.13.0",
    "tf-keras>=2.15.0",
    "opencv-python-headless>=4.8.0",
    "pillow>=10.0.0",
]

_install_lock = threading.Lock()
_install_attempted = False
_install_ok: Optional[bool] = None
_warm_attempted = False


def _log(log: Optional[Callable[[str], None]], msg: str) -> None:
    if log:
        try:
            log(msg)
        except Exception:
            pass
    else:
        print(msg, flush=True)


def deepface_importable() -> bool:
    """True if ``import deepface`` would succeed."""
    return importlib.util.find_spec("deepface") is not None


def deepface_available() -> bool:
    """True if DeepFace can be imported (module present)."""
    if not deepface_importable():
        return False
    try:
        import deepface  # noqa: F401
        return True
    except Exception:
        return False


def _pip_install(packages_or_req: List[str], *, log: Optional[Callable[[str], None]]) -> bool:
    """Run pip install into *this* interpreter. Returns True on exit 0."""
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"]
    # Prefer --user when not in a venv (matches gui.py bootstrap)
    in_venv = getattr(sys, "base_prefix", sys.prefix) != sys.prefix or bool(
        os.environ.get("VIRTUAL_ENV")
    )
    if not in_venv:
        cmd.append("--user")
    cmd.extend(packages_or_req)
    _log(log, f"Installing DeepFace stack:\n  {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("SOR_DEEPFACE_PIP_TIMEOUT", "1200")),
        )
    except subprocess.TimeoutExpired:
        _log(log, "DeepFace pip install timed out")
        return False
    except Exception as e:
        _log(log, f"DeepFace pip install failed to start: {e}")
        return False
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        _log(log, f"DeepFace pip install failed (exit {proc.returncode}):\n{tail}")
        return False
    _log(log, "DeepFace packages installed OK")
    return True


def ensure_deepface(
    *,
    auto_install: bool = True,
    warm: bool = True,
    log: Optional[Callable[[str], None]] = None,
    force_reinstall: bool = False,
) -> bool:
    """
    Make DeepFace usable in this process.

    1. If already importable → optionally warm race model → True
    2. Else if auto_install → pip install requirements-vision.txt → re-check
    3. Else False

    Safe to call repeatedly (install attempted at most once per process unless
    *force_reinstall*).
    """
    global _install_attempted, _install_ok, _warm_attempted

    if deepface_available() and not force_reinstall:
        if warm:
            warm_deepface_models(log=log)
        return True

    if not auto_install:
        return False

    with _install_lock:
        if _install_attempted and not force_reinstall:
            ok = bool(_install_ok and deepface_available())
            if ok and warm:
                warm_deepface_models(log=log)
            return ok

        _install_attempted = True
        if deepface_available() and not force_reinstall:
            _install_ok = True
            if warm:
                warm_deepface_models(log=log)
            return True

        env_skip = os.environ.get("SOR_SKIP_DEEPFACE_INSTALL", "").strip() in (
            "1", "true", "yes",
        )
        if env_skip:
            _log(log, "SOR_SKIP_DEEPFACE_INSTALL set — not auto-installing DeepFace")
            _install_ok = False
            return False

        if _VISION_REQ.is_file():
            ok = _pip_install(["-r", str(_VISION_REQ)], log=log)
        else:
            ok = _pip_install(list(_FALLBACK_PACKAGES), log=log)

        # Invalidate import caches after install
        importlib.invalidate_caches()
        # Drop partial imports if any
        for mod in list(sys.modules):
            if mod == "deepface" or mod.startswith("deepface."):
                del sys.modules[mod]

        _install_ok = bool(ok and deepface_available())
        if not _install_ok:
            _log(
                log,
                "DeepFace still not importable after install. "
                f"Interpreter: {sys.executable}\n"
                "Try manually:\n"
                f"  {sys.executable} -m pip install -r requirements-vision.txt",
            )
            return False

        _log(log, "DeepFace import OK")
        if warm:
            warm_deepface_models(log=log)
        return True


def _build_one_model(DeepFace: Any, model_id: str, log: Optional[Callable[[str], None]]) -> bool:
    """Download/build a single DeepFace model by name."""
    _log(log, f"Downloading / building weights: {model_id} …")
    try:
        if hasattr(DeepFace, "build_model"):
            try:
                DeepFace.build_model(model_id)
                _log(log, f"  OK: {model_id}")
                return True
            except TypeError:
                DeepFace.build_model(model_name=model_id)
                _log(log, f"  OK: {model_id}")
                return True
        _log(log, f"  build_model unavailable for {model_id}")
        return False
    except Exception as e:
        _log(log, f"  FAIL {model_id}: {e}")
        return False


def download_selected_weights(
    model_ids: Optional[List[str]] = None,
    *,
    detector_backend: str = "retinaface",
    log: Optional[Callable[[str], None]] = None,
) -> Dict[str, bool]:
    """
    Download selected DeepFace model weights into ``~/.deepface/weights/``.

    Always attempts Race if list is empty. Detectors are exercised via a tiny
    analyze() call so their weights are also fetched when needed.
    """
    from scraper.mugshot_ethnicity.weights_catalog import default_selected_weights

    if not deepface_available():
        _log(log, "DeepFace not installed — cannot download weights")
        return {}

    models = list(model_ids or default_selected_weights())
    if "Race" not in models:
        models.insert(0, "Race")

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    from deepface import DeepFace

    results: Dict[str, bool] = {}
    for mid in models:
        results[mid] = _build_one_model(DeepFace, mid, log)

    # Trigger detector weight download (RetinaFace etc.) with a dummy image
    det = (detector_backend or "opencv").strip() or "opencv"
    if det != "opencv":
        _log(log, f"Warming detector backend: {det} …")
        try:
            import numpy as np
            from PIL import Image
            import tempfile

            arr = np.zeros((96, 96, 3), dtype=np.uint8)
            arr[:] = (180, 140, 120)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                Image.fromarray(arr).save(f.name, format="JPEG")
                path = f.name
            try:
                DeepFace.analyze(
                    img_path=path,
                    actions=["race"],
                    enforce_detection=False,
                    detector_backend=det,
                    silent=True,
                )
                results[f"detector:{det}"] = True
                _log(log, f"  OK detector: {det}")
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        except Exception as e:
            results[f"detector:{det}"] = False
            _log(log, f"  Detector warm note ({det}): {e}")

    ok_n = sum(1 for v in results.values() if v)
    _log(log, f"Weight download finished: {ok_n}/{len(results)} succeeded")
    return results


def warm_deepface_models(
    *,
    log: Optional[Callable[[str], None]] = None,
    model_ids: Optional[List[str]] = None,
    detector_backend: str = "retinaface",
) -> bool:
    """
    Download / load selected models into local cache (default: Race).

    First run may take a few minutes; later runs are fast.
    """
    global _warm_attempted
    if not deepface_available():
        return False
    # Allow re-warm when explicit model list provided
    if _warm_attempted and not model_ids:
        return True
    if not model_ids:
        _warm_attempted = True
    try:
        results = download_selected_weights(
            model_ids or ["Race"],
            detector_backend=detector_backend,
            log=log,
        )
        ok = bool(results.get("Race") or any(results.values()))
        if ok:
            _log(log, "DeepFace weights ready under ~/.deepface/weights/")
        return ok
    except Exception as e:
        _log(log, f"DeepFace warm-up failed: {e}")
        return False


def ensure_deepface_background(
    *,
    log: Optional[Callable[[str], None]] = None,
) -> threading.Thread:
    """Start ensure_deepface in a daemon thread (non-blocking GUI startup)."""
    def _run() -> None:
        try:
            ensure_deepface(auto_install=True, warm=True, log=log)
        except Exception as e:
            _log(log, f"Background DeepFace setup error: {e}")

    t = threading.Thread(target=_run, name="deepface-setup", daemon=True)
    t.start()
    return t
