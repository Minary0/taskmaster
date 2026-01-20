from __future__ import annotations

import math
import os
import queue
import re
import shutil
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable, List, Optional, Tuple

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}


class FFMpegError(RuntimeError):
    pass


class DownloaderError(RuntimeError):
    pass


def ensure_ffmpeg_available() -> Tuple[str, str]:
    """Return ffmpeg/ffprobe paths from PATH or local ./bin."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")

    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe

    base_dir = Path(__file__).resolve().parent
    bin_dir = base_dir / "bin"

    if os.name == "nt":
        local_ffmpeg = bin_dir / "ffmpeg.exe"
        local_ffprobe = bin_dir / "ffprobe.exe"
    else:
        local_ffmpeg = bin_dir / "ffmpeg"
        local_ffprobe = bin_dir / "ffprobe"

    if local_ffmpeg.exists() and local_ffprobe.exists():
        return str(local_ffmpeg), str(local_ffprobe)

    raise FileNotFoundError(
        "FFmpeg/FFprobe introuvables. Installe FFmpeg et ajoute-le au PATH, "
        "ou place ffmpeg(.exe) et ffprobe(.exe) dans le dossier ./bin à côté de main.py."
    )


def ensure_downloader_available() -> str:
    downloader = shutil.which("yt-dlp") or shutil.which("youtube-dl")
    if not downloader:
        raise FileNotFoundError(
            "yt-dlp (recommandé) ou youtube-dl est introuvable dans le PATH."
        )
    return downloader


def download_video(url: str, output_dir: Path, logger: Callable[[str], None]) -> Path:
    downloader = ensure_downloader_available()
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(title)s.%(ext)s")
    command = [
        downloader,
        "--no-playlist",
        "--print",
        "after_move:filepath",
        "-o",
        template,
        url,
    ]
    logger("Téléchargement: " + " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise DownloaderError(result.stderr.strip() or "Erreur lors du téléchargement.")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise DownloaderError("Impossible de récupérer le chemin du fichier téléchargé.")
    downloaded_path = Path(lines[-1])
    if not downloaded_path.exists():
        raise DownloaderError("Le fichier téléchargé est introuvable.")
    return downloaded_path


def get_duration_seconds(input_path: Path) -> float:
    _, ffprobe_path = ensure_ffmpeg_available()
    command = [
        ffprobe_path,
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
    ffmpeg_path: str,
) -> List[str]:
    if mode == "fast":
        return [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_path),
            "-ss",
            f"{start}",
            "-t",
            f"{duration}",
            "-c",
            "copy",
            "-avoid_negative_ts",
            "1",
            "-fflags",
            "+genpts",
            str(output_path),
        ]
    return [
        ffmpeg_path,
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
    logger: Callable[[str], None],
    progress: Callable[[int, int], None],
) -> Iterable[Path]:
    ffmpeg_path, _ = ensure_ffmpeg_available()
    validate_paths(input_path, output_dir)
    total_duration = get_duration_seconds(input_path)
    total_segments = estimate_segments(total_duration, segment_duration)
    logger(
        f"Durée totale: {total_duration:.2f}s | Segments: {total_segments} | Mode: {mode}"
    )
    results: List[Path] = []
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
        command = build_ffmpeg_command(
            input_path, output_path, start, duration, mode, ffmpeg_path
        )
        logger("Commande: " + " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger(result.stderr.strip())
            raise FFMpegError("Erreur FFmpeg lors du découpage.")
        results.append(output_path)
        progress(index + 1, total_segments)
    return results


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


class VideoSplitterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Video Splitter")
        self.geometry("820x640")
        self.resizable(True, True)

        self.style = ttk.Style(self)
        self.dark_mode = tk.BooleanVar(value=False)

        self.event_queue: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.output_paths: List[Path] = []
        self.total_duration: Optional[float] = None
        self.source_path: Optional[Path] = None

        self._build_ui()
        self._configure_styles()
        self._apply_theme()
        self.after(150, self._process_queue)

    def _build_ui(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        file_frame = ttk.LabelFrame(main, text="Fichier vidéo ou URL")
        file_frame.pack(fill=tk.X, pady=6)
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="Fichier").grid(row=0, column=0, padx=6, pady=6)
        self.video_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.video_path_var, width=70).grid(
            row=0, column=1, padx=6, pady=6, sticky=tk.EW
        )
        ttk.Button(file_frame, text="Parcourir", command=self._browse_video).grid(
            row=0, column=2, padx=6, pady=6
        )

        ttk.Label(file_frame, text="Lien YouTube").grid(row=1, column=0, padx=6, pady=6)
        self.url_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.url_var, width=70).grid(
            row=1, column=1, padx=6, pady=6, sticky=tk.EW
        )

        duration_frame = ttk.LabelFrame(main, text="Durée du segment")
        duration_frame.pack(fill=tk.X, pady=6)
        ttk.Label(duration_frame, text="Minutes").grid(row=0, column=0, padx=6, pady=6)
        self.minutes_var = tk.StringVar(value="6")
        ttk.Entry(duration_frame, textvariable=self.minutes_var, width=6).grid(
            row=0, column=1, padx=6, pady=6
        )
        ttk.Label(duration_frame, text="Secondes").grid(row=0, column=2, padx=6, pady=6)
        self.seconds_var = tk.StringVar(value="0")
        ttk.Entry(duration_frame, textvariable=self.seconds_var, width=6).grid(
            row=0, column=3, padx=6, pady=6
        )
        self.minutes_var.trace_add("write", lambda *_: self._update_segments_label())
        self.seconds_var.trace_add("write", lambda *_: self._update_segments_label())

        options_frame = ttk.LabelFrame(main, text="Options")
        options_frame.pack(fill=tk.X, pady=6)

        ttk.Label(options_frame, text="Mode").grid(row=0, column=0, padx=6, pady=6)
        self.mode_var = tk.StringVar(value="fast")
        ttk.Radiobutton(
            options_frame,
            text="Rapide (sans ré-encodage)",
            variable=self.mode_var,
            value="fast",
        ).grid(row=0, column=1, padx=6, pady=6, sticky=tk.W)
        ttk.Radiobutton(
            options_frame,
            text="Précis (ré-encodage)",
            variable=self.mode_var,
            value="precise",
        ).grid(row=0, column=2, padx=6, pady=6, sticky=tk.W)

        ttk.Label(options_frame, text="Format de sortie").grid(
            row=1, column=0, padx=6, pady=6
        )
        self.format_var = tk.StringVar(value=".mp4")
        ttk.Combobox(
            options_frame,
            textvariable=self.format_var,
            values=[".mp4", ".mkv", ".mov", ".webm"],
            width=8,
            state="readonly",
        ).grid(row=1, column=1, padx=6, pady=6, sticky=tk.W)

        ttk.Checkbutton(
            options_frame,
            text="Mode sombre",
            variable=self.dark_mode,
            command=self._apply_theme,
        ).grid(row=1, column=2, padx=6, pady=6, sticky=tk.W)

        output_frame = ttk.LabelFrame(main, text="Dossier de sortie")
        output_frame.pack(fill=tk.X, pady=6)
        self.output_dir_var = tk.StringVar()
        ttk.Entry(output_frame, textvariable=self.output_dir_var, width=70).pack(
            side=tk.LEFT, padx=6, pady=6, fill=tk.X, expand=True
        )
        ttk.Button(output_frame, text="Parcourir", command=self._browse_output).pack(
            side=tk.RIGHT, padx=6, pady=6
        )

        action_frame = ttk.Frame(main)
        action_frame.pack(fill=tk.X, pady=6)
        ttk.Button(action_frame, text="Analyser", command=self._analyze).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(action_frame, text="Lancer", command=self._start_split).pack(
            side=tk.LEFT, padx=6
        )
        self.open_folder_button = ttk.Button(
            action_frame,
            text="Ouvrir le dossier de sortie",
            command=self._open_output_folder,
            state=tk.DISABLED,
        )
        self.open_folder_button.pack(side=tk.RIGHT, padx=6)

        info_frame = ttk.Frame(main)
        info_frame.pack(fill=tk.X, pady=6)
        self.duration_label = ttk.Label(info_frame, text="Durée totale: -")
        self.duration_label.pack(side=tk.LEFT, padx=6)
        self.segment_label = ttk.Label(info_frame, text="Segments estimés: -")
        self.segment_label.pack(side=tk.LEFT, padx=6)

        progress_frame = ttk.Frame(main)
        progress_frame.pack(fill=tk.X, pady=6)
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, variable=self.progress_var, maximum=100
        )
        self.progress_bar.pack(fill=tk.X, padx=6, pady=6)
        self.progress_text = ttk.Label(progress_frame, text="0 / 0")
        self.progress_text.pack(anchor=tk.W, padx=6)

        log_frame = ttk.LabelFrame(main, text="Logs")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _browse_video(self) -> None:
        path = filedialog.askopenfilename(
            title="Choisir une vidéo",
            filetypes=[
                ("Vidéo", "*.mp4 *.mkv *.mov *.webm"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if path:
            self.video_path_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Choisir le dossier de sortie")
        if path:
            self.output_dir_var.set(path)

    def _log(self, message: str) -> None:
        self.event_queue.put(("log", message))

    def _progress(self, current: int, total: int) -> None:
        self.event_queue.put(("progress", (current, total)))

    def _set_info(self, duration: float, segments: int) -> None:
        self.event_queue.put(("set_info", (duration, segments)))

    def _configure_styles(self) -> None:
        self.style.theme_use("default")
        self.style.configure("Light.TFrame", background="#f5f5f5")
        self.style.configure("Light.TLabelframe", background="#f5f5f5", foreground="#111111")
        self.style.configure(
            "Light.TLabelframe.Label", background="#f5f5f5", foreground="#111111"
        )
        self.style.configure("Light.TLabel", background="#f5f5f5", foreground="#111111")
        self.style.configure("Light.TButton", background="#f5f5f5", foreground="#111111")
        self.style.configure("Light.TCheckbutton", background="#f5f5f5", foreground="#111111")
        self.style.configure("Light.TRadiobutton", background="#f5f5f5", foreground="#111111")
        self.style.configure("Light.TEntry", fieldbackground="#ffffff", foreground="#111111")
        self.style.configure("Light.TCombobox", fieldbackground="#ffffff", foreground="#111111")
        self.style.configure("Light.TProgressbar", background="#4a90e2")

        self.style.configure("Dark.TFrame", background="#1f1f1f")
        self.style.configure("Dark.TLabelframe", background="#1f1f1f", foreground="#e6e6e6")
        self.style.configure(
            "Dark.TLabelframe.Label", background="#1f1f1f", foreground="#e6e6e6"
        )
        self.style.configure("Dark.TLabel", background="#1f1f1f", foreground="#e6e6e6")
        self.style.configure("Dark.TButton", background="#2b2b2b", foreground="#e6e6e6")
        self.style.configure("Dark.TCheckbutton", background="#1f1f1f", foreground="#e6e6e6")
        self.style.configure("Dark.TRadiobutton", background="#1f1f1f", foreground="#e6e6e6")
        self.style.configure("Dark.TEntry", fieldbackground="#2b2b2b", foreground="#e6e6e6")
        self.style.configure("Dark.TCombobox", fieldbackground="#2b2b2b", foreground="#e6e6e6")
        self.style.configure("Dark.TProgressbar", background="#6bb8ff")

        labelframe_layout = self.style.layout("TLabelframe")
        if labelframe_layout:
            self.style.layout("Light.TLabelframe", labelframe_layout)
            self.style.layout("Dark.TLabelframe", labelframe_layout)

    def _apply_theme(self) -> None:
        theme_prefix = "Dark" if self.dark_mode.get() else "Light"
        self.configure(background=self.style.lookup(f"{theme_prefix}.TFrame", "background"))
        self._apply_theme_to_widgets(self, theme_prefix)
        log_bg = "#2b2b2b" if self.dark_mode.get() else "#ffffff"
        log_fg = "#e6e6e6" if self.dark_mode.get() else "#111111"
        self.log_text.config(
            bg=log_bg,
            fg=log_fg,
            insertbackground=log_fg,
            selectbackground="#4a90e2",
        )

    def _apply_theme_to_widgets(self, parent: tk.Misc, theme_prefix: str) -> None:
        for child in parent.winfo_children():
            if isinstance(child, ttk.Frame):
                child.configure(style=f"{theme_prefix}.TFrame")
            elif isinstance(child, ttk.LabelFrame):
                child.configure(style=f"{theme_prefix}.TLabelframe")
            elif isinstance(child, ttk.Label):
                child.configure(style=f"{theme_prefix}.TLabel")
            elif isinstance(child, ttk.Button):
                child.configure(style=f"{theme_prefix}.TButton")
            elif isinstance(child, ttk.Checkbutton):
                child.configure(style=f"{theme_prefix}.TCheckbutton")
            elif isinstance(child, ttk.Radiobutton):
                child.configure(style=f"{theme_prefix}.TRadiobutton")
            elif isinstance(child, ttk.Entry):
                child.configure(style=f"{theme_prefix}.TEntry")
            elif isinstance(child, ttk.Combobox):
                child.configure(style=f"{theme_prefix}.TCombobox")
            elif isinstance(child, ttk.Progressbar):
                child.configure(style=f"{theme_prefix}.TProgressbar")
            self._apply_theme_to_widgets(child, theme_prefix)

    def _update_segments_label(self) -> None:
        if self.total_duration is None:
            return
        try:
            segment_duration = parse_duration(
                self.minutes_var.get().strip(),
                self.seconds_var.get().strip(),
            )
        except ValueError:
            self.segment_label.config(text="Segments estimés: -")
            return
        segments = estimate_segments(self.total_duration, segment_duration)
        self.segment_label.config(text=f"Segments estimés: {segments}")

    def _analyze(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Analyse", "Une opération est déjà en cours.")
            return

        video_path = self.video_path_var.get().strip()
        url = self.url_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        if not video_path:
            if not url:
                messagebox.showerror("Analyse", "Veuillez sélectionner une vidéo ou un lien.")
                return
            if not output_dir:
                messagebox.showerror(
                    "Analyse", "Veuillez choisir un dossier de sortie pour le téléchargement."
                )
                return

        def run() -> None:
            try:
                if url:
                    self.event_queue.put(("log", "Téléchargement en cours..."))
                    self.source_path = download_video(url, Path(output_dir), self._log)
                else:
                    self.source_path = Path(video_path)
                duration = get_duration_seconds(self.source_path)
                segment_duration = parse_duration(
                    self.minutes_var.get().strip(),
                    self.seconds_var.get().strip(),
                )
                segments = estimate_segments(duration, segment_duration)
                self._set_info(duration, segments)
            except (FFMpegError, DownloaderError, FileNotFoundError) as exc:
                self.event_queue.put(("error", str(exc)))
                return
            self.event_queue.put(("analysis", duration))

        self.worker_thread = threading.Thread(target=run, daemon=True)
        self.worker_thread.start()

    def _start_split(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Découpage", "Une opération est déjà en cours.")
            return

        video_path = self.video_path_var.get().strip()
        url = self.url_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            messagebox.showerror("Découpage", "Veuillez choisir un dossier de sortie.")
            return
        if not video_path and not url:
            messagebox.showerror(
                "Découpage", "Veuillez choisir un fichier ou fournir un lien."
            )
            return

        try:
            segment_duration = parse_duration(
                self.minutes_var.get().strip(),
                self.seconds_var.get().strip(),
            )
        except ValueError as exc:
            messagebox.showerror("Durée invalide", str(exc))
            return

        self._reset_progress()
        self.open_folder_button.config(state=tk.DISABLED)
        self._clear_logs()
        self._log("Démarrage du découpage...")

        def run() -> None:
            try:
                if url:
                    self.event_queue.put(("log", "Téléchargement en cours..."))
                    self.source_path = download_video(url, Path(output_dir), self._log)
                elif self.source_path is None:
                    self.source_path = Path(video_path)
                duration = get_duration_seconds(self.source_path)
                segment_duration = parse_duration(
                    self.minutes_var.get().strip(),
                    self.seconds_var.get().strip(),
                )
                segments = estimate_segments(duration, segment_duration)
                self._set_info(duration, segments)
                self.output_paths = list(
                    split_video(
                        self.source_path,
                        Path(output_dir),
                        segment_duration,
                        self.mode_var.get(),
                        self.format_var.get(),
                        logger=self._log,
                        progress=self._progress,
                    )
                )
            except (
                FFMpegError,
                DownloaderError,
                FileNotFoundError,
                PermissionError,
                ValueError,
            ) as exc:
                self.event_queue.put(("error", str(exc)))
                return
            self.event_queue.put(("done", None))

        self.worker_thread = threading.Thread(target=run, daemon=True)
        self.worker_thread.start()

    def _reset_progress(self) -> None:
        self.progress_var.set(0)
        self.progress_text.config(text="0 / 0")

    def _clear_logs(self) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _open_output_folder(self) -> None:
        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            return
        path = Path(output_dir)
        if not path.exists():
            return
        if tk.sys.platform.startswith("win"):
            path_str = str(path)
            threading.Thread(target=lambda: __import__("os").startfile(path_str)).start()
        elif tk.sys.platform == "darwin":
            threading.Thread(
                target=lambda: __import__("subprocess").run(["open", str(path)])
            ).start()
        else:
            threading.Thread(
                target=lambda: __import__("subprocess").run(["xdg-open", str(path)])
            ).start()

    def _process_queue(self) -> None:
        try:
            while True:
                event, payload = self.event_queue.get_nowait()
                if event == "log":
                    self._append_log(str(payload))
                elif event == "progress":
                    current, total = payload
                    percent = (current / total * 100) if total else 0
                    self.progress_var.set(percent)
                    self.progress_text.config(text=f"{current} / {total}")
                elif event == "analysis":
                    self.total_duration = float(payload)
                    self.duration_label.config(
                        text=f"Durée totale: {format_seconds(self.total_duration)}"
                    )
                    try:
                        segment_duration = parse_duration(
                            self.minutes_var.get().strip(),
                            self.seconds_var.get().strip(),
                        )
                        segments = estimate_segments(
                            self.total_duration, segment_duration
                        )
                        self.segment_label.config(text=f"Segments estimés: {segments}")
                    except ValueError:
                        self.segment_label.config(text="Segments estimés: -")
                elif event == "set_info":
                    duration, segments = payload
                    self.total_duration = float(duration)
                    self.duration_label.config(
                        text=f"Durée totale: {format_seconds(self.total_duration)}"
                    )
                    self.segment_label.config(text=f"Segments estimés: {segments}")
                elif event == "done":
                    self._log("Découpage terminé.")
                    self.open_folder_button.config(state=tk.NORMAL)
                elif event == "error":
                    self._log(f"Erreur: {payload}")
                    messagebox.showerror("Erreur", str(payload))
        except queue.Empty:
            pass
        self.after(150, self._process_queue)

    def _append_log(self, message: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)


if __name__ == "__main__":
    app = VideoSplitterApp()
    app.mainloop()
