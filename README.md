# Video Splitter

Application de bureau multiplateforme pour découper une vidéo en segments de durée fixe.

## Fonctionnalités

- Sélection d'un fichier vidéo (`.mp4`, `.mkv`, `.mov`, `.webm`).
- Durée de segment configurable en minutes/secondes.
- Deux modes :
  - **Rapide (sans ré-encodage)** : découpe plus rapide, dépend des keyframes.
  - **Précis (ré-encodage)** : coupes exactes (H.264 + AAC par défaut).
- Choix du format de sortie (mp4 par défaut).
- Barre de progression, ETA approximatif via l'avancement, et log des commandes FFmpeg.
- Gestion d'erreurs (FFmpeg absent, format non supporté, permissions, etc.).

## Prérequis

- Python 3.10+
- FFmpeg + FFprobe installés et accessibles dans le `PATH`.

### Installer FFmpeg

- **Windows** : https://ffmpeg.org/download.html
- **macOS** : `brew install ffmpeg`
- **Linux (Debian/Ubuntu)** : `sudo apt install ffmpeg`

## Lancer l'application

```bash
python main.py
```

## Utilisation

1. Sélectionnez le fichier vidéo.
2. Choisissez la durée de segment.
3. Sélectionnez le mode (Rapide ou Précis) et le format de sortie.
4. Choisissez le dossier de sortie.
5. Cliquez sur **Analyser** pour obtenir la durée totale.
6. Cliquez sur **Lancer**.

Les segments sont nommés `video_title_part_001.mp4`, `video_title_part_002.mp4`, etc.

## Exemple

Découper une vidéo de 2h en segments de 6 minutes :

- Minutes : `6`
- Secondes : `0`
- Mode : Rapide ou Précis

L'application calcule automatiquement le nombre de segments : `ceil(7200 / 360) = 20`.

## Dépannage

- **FFmpeg introuvable** : vérifiez que `ffmpeg` et `ffprobe` sont accessibles dans votre `PATH`.
- **Coupes non exactes en mode rapide** : le mode rapide utilise `-c copy`, les coupes peuvent dépendre des keyframes.
- **Permissions** : assurez-vous que le dossier de sortie est accessible en écriture.

## Structure du projet

- `main.py` : point d'entrée de l'application.
- `video_splitter/app.py` : UI Tkinter + orchestration.
- `video_splitter/splitter.py` : logique de découpe (FFmpeg/FFprobe).
- `video_splitter/utils.py` : validation, formatage, nommage.
