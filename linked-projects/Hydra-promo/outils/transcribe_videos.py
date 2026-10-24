#!/usr/bin/env python3
"""
transcribe_videos.py - Étape 1 : transcrire des vidéos, en local et gratuitement.

Moteur : Whisper (OpenAI, licence MIT) via faster-whisper (licence MIT).
Aucun compte, aucune clé, aucun coût : tout tourne sur ton PC.
Le modèle est téléchargé une seule fois au premier lancement, puis tout fonctionne hors ligne.

Pour chaque vidéo, écrit à côté d'elle :
  <nom>.fr.srt         sous-titres horodatés (base du doublage)
  <nom>.fr.txt         texte lisible, un paragraphe par pause
  <nom>.fr.review.txt  même texte, mots incertains entre ⟦ ⟧ (à vérifier à l'étape 2)
  <nom>.fr.json        mots, temps et confiance (pour la traduction)

Prérequis (une fois) :
  pip install faster-whisper
  winget install ffmpeg            (déjà fait pour audio_enhancer.py)

Usage :
  py transcribe_videos.py "cli 1 output.mp4"
  py transcribe_videos.py "C:\\Videos"                  tout un dossier
  py transcribe_videos.py "C:\\Videos" --model small    plus rapide, un peu moins précis
  py transcribe_videos.py "C:\\Videos" --force          refaire même si déjà transcrit
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
SAMPLE_RATE = 16000

# Phrase donnée au modèle avant l'écoute : elle l'oriente vers le vocabulaire de Hydra ETL.
DEFAULT_PROMPT = (
    "Démonstration de Hydra ETL. Commandes : hdrctl init, hdrctl validate, hdrctl test, "
    "hdrctl run, hdrctl list, hdrctl workflow run, hdrctl serve. Fichiers YAML : "
    "sources.yaml, destinations.yaml, pipeline.yaml, transformations.yaml, workflow.yaml. "
    "Un projet contient des jobs et des workflows. Connecteurs : CSV, JSON, Parquet, "
    "PostgreSQL, MySQL, SQL Server, MongoDB, API REST. Moteurs : pandas, DuckDB. "
    "Studio, Killercoda, Codespaces, VS Code, GitHub."
)

# Un mot dont la probabilité est sous ce seuil est marqué ⟦incertain⟧.
LOW_CONFIDENCE = 0.5

# Découpage des sous-titres
MAX_CUE_SECONDS = 6.0
MAX_CUE_CHARS = 84              # ~2 lignes de 42 caractères
PAUSE_SPLIT_SECONDS = 0.7       # une pause plus longue démarre un nouveau sous-titre
PARAGRAPH_PAUSE_SECONDS = 1.5   # une pause plus longue démarre un nouveau paragraphe


# --------------------------------------------------------------------------- utilitaires

def fail(message):
    print(f"❌ {message}")
    sys.exit(1)


def check_prerequisites():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        fail("ffmpeg introuvable. Installez-le : winget install ffmpeg (puis rouvrez le terminal).")
    try:
        import faster_whisper  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        fail("Bibliothèque manquante. Installez-la : pip install faster-whisper")


def collect_videos(inputs):
    videos = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            videos += sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS)
        elif path.is_file():
            videos.append(path)
        else:
            print(f"⚠️  Ignoré (introuvable) : {item}")
    return videos


def load_audio(video):
    """Décode la piste son avec ffmpeg : mono, 16 kHz, nombres flottants (format attendu par Whisper)."""
    import numpy as np
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video),
           "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg n'a pas pu lire le son :\n{result.stderr.decode(errors='replace')[-800:]}")
    return np.frombuffer(result.stdout, np.float32)


def timestamp(seconds):
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --------------------------------------------------------------------------- mise en forme

def build_cues(words):
    """Regroupe les mots en sous-titres : coupe sur pause, ponctuation finale, durée ou longueur."""
    cues, current = [], []
    for w in words:
        if current:
            text_len = len(" ".join(x["text"] for x in current)) + 1 + len(w["text"])
            pause = w["start"] - current[-1]["end"]
            too_long = (w["end"] - current[0]["start"] > MAX_CUE_SECONDS) or text_len > MAX_CUE_CHARS
            sentence_end = current[-1]["text"].endswith((".", "?", "!"))
            if pause > PAUSE_SPLIT_SECONDS or too_long or (sentence_end and len(current) >= 3):
                cues.append(current)
                current = []
        current.append(w)
    if current:
        cues.append(current)
    return cues


def join_words(words, mark_uncertain=False):
    parts = []
    for w in words:
        text = w["text"]
        if mark_uncertain and w["probability"] < LOW_CONFIDENCE:
            text = f"⟦{text}⟧"
        parts.append(text)
    # pas d'espace avant , et . (le français la garde avant ? ! : ;)
    return " ".join(parts).replace(" ,", ",").replace(" .", ".")


def to_srt(cues):
    blocks = []
    for i, cue in enumerate(cues, 1):
        blocks.append(f"{i}\n{timestamp(cue[0]['start'])} --> {timestamp(cue[-1]['end'])}\n"
                      f"{join_words(cue)}\n")
    return "\n".join(blocks)


def to_paragraphs(words, mark_uncertain=False):
    paragraphs, current = [], []
    for w in words:
        if current and w["start"] - current[-1]["end"] > PARAGRAPH_PAUSE_SECONDS:
            paragraphs.append(current)
            current = []
        current.append(w)
    if current:
        paragraphs.append(current)
    return "\n\n".join(join_words(p, mark_uncertain) for p in paragraphs) + "\n"


# --------------------------------------------------------------------------- transcription

def transcribe(model, audio, args, prompt):
    segments, info = model.transcribe(
        audio,
        language=args.language,
        initial_prompt=prompt or None,
        word_timestamps=True,
        vad_filter=True,                  # ignore les silences : moins de phrases inventées
        beam_size=5,
        condition_on_previous_text=False, # évite qu'une erreur se répète sur toute la vidéo
    )
    words = []
    for segment in segments:              # la transcription se fait ici, au fil de la lecture
        for w in segment.words or []:
            text = w.word.strip()
            if text:
                words.append({"text": text, "start": round(w.start, 3),
                              "end": round(w.end, 3), "probability": round(w.probability, 3)})
        print(f"\r   📝 {timestamp(segment.end)[:8]} / {timestamp(info.duration)[:8]}", end="", flush=True)
    print()
    return words, info.duration


def process(video, model, args, prompt):
    base = video.with_suffix("")
    out_srt = Path(f"{base}.{args.language}.srt")
    out_txt = Path(f"{base}.{args.language}.txt")
    out_review = Path(f"{base}.{args.language}.review.txt")
    out_json = Path(f"{base}.{args.language}.json")

    if out_srt.exists() and not args.force:
        print(f"⏭️  Déjà transcrit : {video.name}  (--force pour refaire)")
        return True

    print(f"\n🎬 {video.name}")
    started = time.monotonic()
    print("   🔊 Lecture du son…")
    audio = load_audio(video)
    words, duration = transcribe(model, audio, args, prompt)
    if not words:
        print("   ⚠️  Aucun mot reconnu.")
        return False

    cues = build_cues(words)
    uncertain = sum(1 for w in words if w["probability"] < LOW_CONFIDENCE)

    out_json.write_text(json.dumps({"source": video.name, "language": args.language,
                                    "model": args.model, "duration": round(duration, 3),
                                    "words": words}, ensure_ascii=False, indent=2), encoding="utf-8")
    out_srt.write_text(to_srt(cues), encoding="utf-8")
    out_txt.write_text(to_paragraphs(words), encoding="utf-8")
    out_review.write_text(to_paragraphs(words, mark_uncertain=True), encoding="utf-8")

    print(f"   ✅ {len(words)} mots, {len(cues)} sous-titres, {uncertain} mots incertains "
          f"— vidéo de {duration:.0f} s traitée en {time.monotonic() - started:.0f} s")
    print(f"      {out_srt.name} · {out_txt.name} · {out_review.name} · {out_json.name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Transcrit des vidéos en local avec Whisper (SRT + TXT à côté de chaque vidéo).")
    parser.add_argument("inputs", nargs="+", help="Dossier(s) ou fichier(s) vidéo")
    parser.add_argument("--language", default="fr", help="Langue parlée, code à 2 lettres (défaut : fr)")
    parser.add_argument("--model", default="large-v3-turbo",
                        help="Modèle Whisper : large-v3-turbo (défaut), large-v3 (plus précis, plus lent), "
                             "medium, small (rapide)")
    parser.add_argument("--prompt-file", help="Fichier texte remplaçant la phrase de vocabulaire par défaut")
    parser.add_argument("--no-prompt", action="store_true", help="Ne pas orienter le vocabulaire")
    parser.add_argument("--force", action="store_true", help="Retranscrire même si le .srt existe déjà")
    args = parser.parse_args()

    check_prerequisites()

    videos = collect_videos(args.inputs)
    if not videos:
        fail("Aucune vidéo trouvée.")

    if args.no_prompt:
        prompt = ""
    elif args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    else:
        prompt = DEFAULT_PROMPT

    from faster_whisper import WhisperModel
    print(f"🧠 Chargement du modèle {args.model} (téléchargé au premier lancement, puis hors ligne)…")
    model = WhisperModel(args.model, device="auto", compute_type="int8")
    print(f"📂 {len(videos)} vidéo(s) à traiter")

    ok = 0
    for video in videos:
        try:
            ok += bool(process(video, model, args, prompt))
        except Exception as e:  # une vidéo en échec n'arrête pas les autres
            print(f"   ❌ {video.name} : {e}")
    print(f"\n🏁 Terminé : {ok}/{len(videos)} vidéo(s) transcrite(s)")
    sys.exit(0 if ok == len(videos) else 1)


if __name__ == "__main__":
    main()
