from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from utils import build_output_name, estimate_segments, validate_paths


class FFMpegError(RuntimeError):
    pass


def ensure_ffmpeg_available() -> None:
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError("FFmpeg est introuvable dans le PATH.")
    if not shutil.which("ffprobe"):
        raise FileNotFoundError("FFprobe est introuvable dans le PATH.")


def get_duration_seconds(input_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(input_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFMpegError(result.stderr.strip() or "Erreur lors de l'analyse de la vidéo.")
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise FFMpegError("Durée vidéo invalide.") from exc


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    start: float,
    duration: float,
    mode: str,
) -> list[str]:
    if mode == "fast":
        return [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start}",
            "-t",
            f"{duration}",
            "-i",
            str(input_path),
            "-c",
            "copy",
            str(output_path),
        ]
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ss",
        f"{start}",
        "-t",
        f"{duration}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]


def split_video(
    input_path: Path,
    output_dir: Path,
    segment_duration: int,
    mode: str,
    output_ext: str,
    logger: callable,
    progress: callable,
) -> Iterable[Path]:
    ensure_ffmpeg_available()
    validate_paths(input_path, output_dir)
    total_duration = get_duration_seconds(input_path)
    total_segments = estimate_segments(total_duration, segment_duration)
    logger(
        f"Durée totale: {total_duration:.2f}s | Segments: {total_segments} | Mode: {mode}"
    )
    results: list[Path] = []
    for index in range(total_segments):
        start = index * segment_duration
        duration = min(segment_duration, total_duration - start)
        output_path = build_output_name(
            input_path,
            output_dir,
            index + 1,
            total_segments,
            output_ext,
        )
        command = build_ffmpeg_command(input_path, output_path, start, duration, mode)
        logger("Commande: " + " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger(result.stderr.strip())
            raise FFMpegError("Erreur FFmpeg lors du découpage.")
        results.append(output_path)
        progress(index + 1, total_segments)
    return results
