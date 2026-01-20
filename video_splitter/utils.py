from __future__ import annotations

import math
import os
import re
from pathlib import Path

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}


def format_seconds(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


def parse_duration(minutes: str, seconds: str) -> int:
    minutes_val = int(minutes or 0)
    seconds_val = int(seconds or 0)
    if minutes_val < 0 or seconds_val < 0:
        raise ValueError("La durée doit être positive.")
    total = minutes_val * 60 + seconds_val
    if total <= 0:
        raise ValueError("La durée doit être supérieure à zéro.")
    return total


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "video"


def build_output_name(
    source_path: Path,
    output_dir: Path,
    index: int,
    total: int,
    extension: str,
) -> Path:
    stem = sanitize_filename(source_path.stem)
    digits = len(str(total))
    suffix = str(index).zfill(max(3, digits))
    return output_dir / f"{stem}_part_{suffix}{extension}"


def validate_paths(input_path: Path, output_dir: Path) -> None:
    if not input_path.exists():
        raise FileNotFoundError("Fichier vidéo introuvable.")
    if input_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError("Format vidéo non supporté.")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not os.access(output_dir, os.W_OK):
        raise PermissionError("Le dossier de sortie n'est pas accessible en écriture.")


def estimate_segments(total_duration: float, segment_duration: int) -> int:
    return int(math.ceil(total_duration / segment_duration))
