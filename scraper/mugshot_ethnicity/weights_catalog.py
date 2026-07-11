"""Selectable DeepFace weight / detector options with accurate guidance.

**What this app needs for mugshot race tools**
  - Package: ``deepface`` (+ TensorFlow)
  - Weights: **Race** only (required)
  - Detector: any one (RetinaFace recommended)

**One vs multiple weights**
  - Download **only Race** for ethnicity / misclass features.
  - Attribute models (Age, Gender, Emotion) are separate networks — downloading
    them does **not** improve race accuracy; they add disk + RAM/VRAM load.
  - Recognition models (VGG-Face, ArcFace, …) embed identity (“same person?”).
    They are unrelated to race labels; skip unless you use face-verify later.
  - You pick **one** face detector at a time (not multiple).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Approximate VRAM when the model is loaded on GPU (TensorFlow/CUDA).
# CPU-only runs use system RAM instead (often 1.5–3× the weight file size).
DETECTOR_OPTIONS: List[Dict[str, Any]] = [
    {
        "id": "retinaface",
        "label": "RetinaFace (recommended)",
        "size": "~100 MB disk",
        "vram": "~0.5–1.0 GB GPU (or ~1–2 GB RAM on CPU)",
        "speed": "Medium",
        "summary": "Best face boxes for mugshots and low-quality registry photos.",
        "detail": (
            "Neural face detector. Finds the face crop before race is predicted. "
            "Slightly slower than OpenCV Haar but misses fewer faces on angled or "
            "compressed images. Use this for quality; only one detector is active."
        ),
    },
    {
        "id": "opencv",
        "label": "OpenCV Haar (fast / no download)",
        "size": "Built-in (no extra file)",
        "vram": "~0 GB dedicated (CPU; negligible GPU)",
        "speed": "Fastest",
        "summary": "Classic cascade detector; no weight download.",
        "detail": (
            "Runs on CPU with OpenCV. Lowest VRAM/RAM cost. Can miss rotated faces "
            "or tight crops. Good if you want zero detector download or weak GPU."
        ),
    },
    {
        "id": "ssd",
        "label": "SSD (OpenCV DNN)",
        "size": "~10 MB disk",
        "vram": "~0.2–0.4 GB GPU (or ~0.5 GB RAM on CPU)",
        "speed": "Fast",
        "summary": "Small neural detector; better than Haar, lighter than RetinaFace.",
        "detail": (
            "OpenCV DNN face detector. Reasonable accuracy for batch scans with "
            "lower VRAM than RetinaFace."
        ),
    },
    {
        "id": "mtcnn",
        "label": "MTCNN",
        "size": "~2 MB disk",
        "vram": "~0.3–0.6 GB GPU (or ~1 GB RAM on CPU)",
        "speed": "Medium–slow",
        "summary": "Multi-stage CNN; handles pose variation better than Haar.",
        "detail": (
            "Three cascaded networks. More accurate than Haar; slower on CPU. "
            "VRAM is moderate when GPU-accelerated."
        ),
    },
    {
        "id": "yunet",
        "label": "YuNet",
        "size": "~1 MB disk",
        "vram": "~0.1–0.3 GB GPU (or ~0.3 GB RAM on CPU)",
        "speed": "Fast",
        "summary": "Tiny modern detector (OpenCV zoo).",
        "detail": (
            "Very small model; low VRAM. Prefer when disk/GPU is limited and "
            "photos are mostly frontal."
        ),
    },
]

# Attribute + recognition models DeepFace.build_model can fetch.
WEIGHT_MODELS: List[Dict[str, Any]] = [
    {
        "id": "Race",
        "label": "Race / ethnicity (required)",
        "size": "~500 MB disk",
        "vram": "~1.0–1.5 GB GPU when loaded (or ~2–3 GB RAM on CPU)",
        "category": "attribute",
        "required": True,
        "summary": "Only model required for mugshot race / ethnicity scoring.",
        "detail": (
            "Outputs probabilities for White, Black, Asian, Indian, Middle Eastern, "
            "and Latino Hispanic. This is what mugshot-verify and mugshot-scan use. "
            "Download this one model to use the app’s face ethnicity features. "
            "Other weights do not improve these race predictions."
        ),
    },
    {
        "id": "Age",
        "label": "Age (optional — not for race)",
        "size": "~500 MB disk",
        "vram": "~1.0–1.5 GB GPU if loaded",
        "category": "attribute",
        "required": False,
        "summary": "Separate network that estimates apparent age only.",
        "detail": (
            "Does not affect race accuracy. Only download if you plan to use age "
            "attributes later. Loads another large model into memory if used."
        ),
    },
    {
        "id": "Gender",
        "label": "Gender (optional — not for race)",
        "size": "~500 MB disk",
        "vram": "~1.0–1.5 GB GPU if loaded",
        "category": "attribute",
        "required": False,
        "summary": "Separate network for apparent gender only.",
        "detail": (
            "Independent of the Race model. Skip for misclass tools; download only "
            "for optional gender analysis."
        ),
    },
    {
        "id": "Emotion",
        "label": "Emotion (optional — not for race)",
        "size": "~50 MB disk",
        "vram": "~0.3–0.5 GB GPU if loaded",
        "category": "attribute",
        "required": False,
        "summary": "Expression classes (happy, sad, angry, …).",
        "detail": (
            "Smaller attribute model. Unused by current race mismatch pipeline. "
            "Safe to skip."
        ),
    },
    {
        "id": "VGG-Face",
        "label": "VGG-Face identity (optional)",
        "size": "~500 MB disk",
        "vram": "~1.0–1.5 GB GPU if loaded",
        "category": "recognition",
        "required": False,
        "summary": "Identity embeddings (“is this the same person?”) — not race.",
        "detail": (
            "Recognition model: compares faces for identity match. It does not "
            "predict race/ethnicity. Large download; skip unless you use face "
            "verify/find features."
        ),
    },
    {
        "id": "Facenet",
        "label": "FaceNet 128d identity (optional)",
        "size": "~90 MB disk",
        "vram": "~0.5–0.8 GB GPU if loaded",
        "category": "recognition",
        "required": False,
        "summary": "Google FaceNet 128-D identity embeddings.",
        "detail": (
            "Smaller identity model than VGG-Face. Still not used for race labels. "
            "Download at most one recognition model if you need identity match."
        ),
    },
    {
        "id": "Facenet512",
        "label": "FaceNet 512d identity (optional)",
        "size": "~90 MB disk",
        "vram": "~0.6–1.0 GB GPU if loaded",
        "category": "recognition",
        "required": False,
        "summary": "FaceNet 512-D (richer identity vector than 128d).",
        "detail": (
            "Higher-dimension FaceNet. Prefer over Facenet 128d for identity match "
            "if you download any recognition model — do not need both."
        ),
    },
    {
        "id": "ArcFace",
        "label": "ArcFace identity (optional)",
        "size": "~130 MB disk",
        "vram": "~0.6–1.0 GB GPU if loaded",
        "category": "recognition",
        "required": False,
        "summary": "Strong modern identity model; alternative to VGG-Face/FaceNet.",
        "detail": (
            "Often best accuracy for same-person matching. Mutually alternative to "
            "VGG-Face/FaceNet — pick one recognition stack, not all."
        ),
    },
    {
        "id": "OpenFace",
        "label": "OpenFace identity (optional)",
        "size": "~15 MB disk",
        "vram": "~0.2–0.4 GB GPU if loaded",
        "category": "recognition",
        "required": False,
        "summary": "Lightweight identity embeddings.",
        "detail": "Smallest recognition option; lower accuracy than ArcFace/VGG-Face.",
    },
    {
        "id": "SFace",
        "label": "SFace identity (optional)",
        "size": "~40 MB disk",
        "vram": "~0.3–0.5 GB GPU if loaded",
        "category": "recognition",
        "required": False,
        "summary": "OpenCV zoo identity model.",
        "detail": "Optional recognition weights; not used for race scoring.",
    },
]

DOWNLOAD_GUIDANCE = (
    "What to download: For mugshot race / misclass tools, select only "
    "“Race / ethnicity” (required) plus one face detector (RetinaFace recommended). "
    "Do not download Age, Gender, Emotion, or recognition models unless you need "
    "those features — they are separate networks, increase disk and VRAM, and do "
    "not improve race accuracy. You never need multiple recognition models at once."
)


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
    return (
        f"{d['summary']}\n\n{d['detail']}\n\n"
        f"Disk: {d['size']}  ·  Speed: {d['speed']}\n"
        f"VRAM / memory: {d['vram']}\n"
        f"Only one detector is used at a time."
    )


def explain_weight(model_id: str) -> str:
    m = get_weight_model(model_id)
    if not m:
        return DOWNLOAD_GUIDANCE
    req = "Required for race tools" if m.get("required") else "Optional — not needed for race tools"
    return (
        f"{m['summary']}\n\n{m['detail']}\n\n"
        f"Category: {m['category']}  ·  {req}\n"
        f"Disk: {m['size']}\n"
        f"VRAM / memory when loaded: {m['vram']}\n\n"
        f"{DOWNLOAD_GUIDANCE}"
    )
