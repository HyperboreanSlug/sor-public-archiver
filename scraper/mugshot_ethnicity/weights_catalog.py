"""Selectable DeepFace weight / detector options with human-readable explanations.

Race scoring for mugshots uses DeepFace's attribute ``Race`` model. Detector
backends find the face first; better detectors cost more download size and CPU.
Recognition models (VGG-Face, ArcFace, …) are optional — only needed if you
later use identity-match features; they are large.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Face detectors used by DeepFace.analyze(..., detector_backend=...)
# Order = recommended preference for mugshots.
DETECTOR_OPTIONS: List[Dict[str, Any]] = [
    {
        "id": "retinaface",
        "label": "RetinaFace (recommended)",
        "size": "~100 MB",
        "speed": "Medium",
        "summary": "Accurate face boxes on angled or low-quality mugshots.",
        "detail": (
            "Best default for registry photos. Downloads RetinaFace weights on "
            "first use. Slightly slower than OpenCV but fewer missed faces."
        ),
        "required_for_race": True,
        "build_model": None,  # detector, not build_model name
    },
    {
        "id": "opencv",
        "label": "OpenCV Haar (fast / small)",
        "size": "Built-in",
        "speed": "Fast",
        "summary": "No extra download; works offline immediately after package install.",
        "detail": (
            "Uses OpenCV's cascade classifier. Smallest footprint and fastest, but "
            "can miss rotated faces or tight crops. Good fallback."
        ),
        "required_for_race": False,
        "build_model": None,
    },
    {
        "id": "ssd",
        "label": "SSD (OpenCV DNN)",
        "size": "~10 MB",
        "speed": "Fast",
        "summary": "Lightweight neural detector; better than Haar, smaller than RetinaFace.",
        "detail": (
            "OpenCV DNN face detector. Balance of speed and accuracy for batch scans."
        ),
        "required_for_race": False,
        "build_model": None,
    },
    {
        "id": "mtcnn",
        "label": "MTCNN",
        "size": "~2 MB",
        "speed": "Medium-slow",
        "summary": "Multi-stage detector; solid on varied poses.",
        "detail": (
            "Three-stage cascaded CNN. More accurate than OpenCV Haar; slower on CPU."
        ),
        "required_for_race": False,
        "build_model": None,
    },
    {
        "id": "yunet",
        "label": "YuNet",
        "size": "~1 MB",
        "speed": "Fast",
        "summary": "Modern tiny detector in OpenCV zoo.",
        "detail": "Lightweight; good when disk/CPU is limited.",
        "required_for_race": False,
        "build_model": None,
    },
]

# Attribute + recognition models DeepFace.build_model can fetch.
# Race is required for mugshot ethnicity scoring.
WEIGHT_MODELS: List[Dict[str, Any]] = [
    {
        "id": "Race",
        "label": "Race / ethnicity (required)",
        "size": "~500 MB",
        "category": "attribute",
        "required": True,
        "summary": "Predicts White / Black / Asian / Indian / Middle Eastern / Latino Hispanic.",
        "detail": (
            "Core model for mugshot verify and gross misclass scan. Downloaded into "
            "~/.deepface/weights/ on first warm. Without this, face ethnicity scoring "
            "cannot run."
        ),
    },
    {
        "id": "Age",
        "label": "Age (optional)",
        "size": "~500 MB",
        "category": "attribute",
        "required": False,
        "summary": "Apparent age estimate from the face crop.",
        "detail": "Not used by default race pipeline; download only if you want age later.",
    },
    {
        "id": "Gender",
        "label": "Gender (optional)",
        "size": "~500 MB",
        "category": "attribute",
        "required": False,
        "summary": "Apparent gender classification.",
        "detail": "Optional attribute model; not required for race mismatch tools.",
    },
    {
        "id": "Emotion",
        "label": "Emotion (optional)",
        "size": "~50 MB",
        "category": "attribute",
        "required": False,
        "summary": "Expression categories (happy, sad, …).",
        "detail": "Smaller attribute model; unused by current mugshot race features.",
    },
    {
        "id": "VGG-Face",
        "label": "VGG-Face recognition (optional)",
        "size": "~500 MB",
        "category": "recognition",
        "required": False,
        "summary": "Default DeepFace identity embedding model.",
        "detail": (
            "Used for face verify/find (same person?), not race labels. Large download; "
            "skip unless you need identity matching."
        ),
    },
    {
        "id": "Facenet",
        "label": "FaceNet 128d (optional)",
        "size": "~90 MB",
        "category": "recognition",
        "required": False,
        "summary": "Google FaceNet embeddings (128-D).",
        "detail": "Smaller recognition model than VGG-Face; still unused for race scoring.",
    },
    {
        "id": "Facenet512",
        "label": "FaceNet 512d (optional)",
        "size": "~90 MB",
        "category": "recognition",
        "required": False,
        "summary": "FaceNet 512-D embeddings (higher detail).",
        "detail": "Optional recognition weights.",
    },
    {
        "id": "ArcFace",
        "label": "ArcFace (optional)",
        "size": "~130 MB",
        "category": "recognition",
        "required": False,
        "summary": "Strong modern recognition model.",
        "detail": "Good accuracy for identity match; not needed for race attributes.",
    },
    {
        "id": "OpenFace",
        "label": "OpenFace (optional)",
        "size": "~15 MB",
        "category": "recognition",
        "required": False,
        "summary": "Lightweight recognition model.",
        "detail": "Small download if experimenting with identity match.",
    },
    {
        "id": "SFace",
        "label": "SFace (optional)",
        "size": "~40 MB",
        "category": "recognition",
        "required": False,
        "summary": "OpenCV zoo recognition model.",
        "detail": "Optional; not used by race pipeline.",
    },
]


def detector_ids() -> List[str]:
    return [d["id"] for d in DETECTOR_OPTIONS]


def weight_model_ids() -> List[str]:
    return [m["id"] for m in WEIGHT_MODELS]


def get_detector(det_id: str) -> Optional[Dict[str, Any]]:
    for d in DETECTOR_OPTIONS:
        if d["id"] == det_id:
            return d
    return None


def get_weight_model(model_id: str) -> Optional[Dict[str, Any]]:
    for m in WEIGHT_MODELS:
        if m["id"] == model_id:
            return m
    return None


def default_selected_weights() -> List[str]:
    return ["Race"]


def explain_detector(det_id: str) -> str:
    d = get_detector(det_id)
    if not d:
        return ""
    return f"{d['summary']}\n\n{d['detail']}\nSize: {d['size']} · Speed: {d['speed']}"


def explain_weight(model_id: str) -> str:
    m = get_weight_model(model_id)
    if not m:
        return ""
    req = "Required" if m.get("required") else "Optional"
    return (
        f"{m['summary']}\n\n{m['detail']}\n"
        f"Category: {m['category']} · Download ≈ {m['size']} · {req}"
    )
