#!/usr/bin/env python3
"""
generate_audio.py - Étape 2 : générer la voix off anglaise à partir des SRT.

Moteur : Kokoro (synthèse vocale, licence Apache 2.0) via kokoro-onnx (licence MIT).
Tout tourne sur ton PC, gratuitement, sans compte ni clé.
Les fichiers du modèle (~350 Mo) sont téléchargés une seule fois au premier lancement.

Chaque phrase est placée au temps exact de son sous-titre : la piste produite démarre
à 00:00 et se pose telle quelle sous la vidéo, sans recalage.

Prérequis (une fois) :
  pip install kokoro-onnx soundfile
  ffmpeg (déjà installé)

Usage :
  py generate_audio.py "C:\\Users\\DELL\\Videos\\srt_enhanced" --voice female
  py generate_audio.py "C:\\Users\\DELL\\Videos\\srt_enhanced" --voice male
  py generate_audio.py "...\\cli1\\cli 1 output.en.srt" --voice female --speed 0.95
  py generate_audio.py --list-voices

Sortie : C:\\Users\\DELL\\Videos\\audio\\<cliN>\\<nom>.<voix>.wav (et .mp3)
"""

import argparse
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_DIR = SCRIPT_DIR / "kokoro_models"
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]

DEFAULT_OUTPUT = Path.home() / "Videos" / "audio"

VOICES = {
    "female": "af_heart",    # américaine, la voix la mieux notée de Kokoro
    "male": "am_michael",    # américain
}

MAX_SPEED = 1.25         # au-delà, la voix devient pressée
GAP = 0.12               # silence minimal entre deux phrases (s)
TARGET_LUFS = -16        # niveau standard podcast / YouTube

# Prononciation : appliquée au texte avant la synthèse (le SRT n'est pas modifié).
# Ordre important : les règles les plus précises d'abord.
PRONUNCIATION = [
    (r"\bhdrctl\b", "H D R C T L"),
    (r"--no-studio\b", "dash dash no studio"),
    (r"--help\b", "dash dash help"),
    (r"--lang\b", "dash dash lang"),
    (r"--version\b", "dash dash version"),
    (r"(?<![\w-])-h\b", "dash h"),
    (r"\bhydraetl\.com\b", "hydra E T L dot com"),
    (r"(?<![\w/])\.hydra\b", "dot hydra"),
    (r"\bdata/output\.csv\b", "data slash output dot C S V"),
    (r"\b([\w-]+)\.(yaml|yml)\b", r"\1 dot yaml"),
    (r"\b([\w-]+)\.log\b", r"\1 dot log"),
    (r"\b([\w-]+)\.csv\b", r"\1 dot C S V"),
    (r"\./([\w-]+)", r"dot slash \1"),
    (r"\b([\w-]+)\.py\b", r"\1 dot P Y"),
    (r"\bmy_project\b", "my project"),
    (r"\bbrokenproject\b", "broken project"),
    (r"\bdbproject\b", "D B project"),
    (r"\bchainproject\b", "chain project"),
    (r"\bmyproject\b", "my project"),
    (r"\bupsret\b", "ups ret"),
    (r"\bMySQL\b", "My S Q L"),
    (r"\bPostgreSQL\b", "Postgres"),
    (r"\bHydra DSL\b", "Hydra D S L"),
    (r"\bport 5678\b", "port five six seven eight"),
    (r"\b(\d+)\.(\d+)\.(\d+)\b", r"\1 point \2 point \3"),
    (r"\b(\d+)\.(\d+)\b", r"\1 point \2"),
    (r"\b(job|workflow)(\d+)\b", r"\1 \2"),
    (r"\b([a-z]+)-([a-z]+)\b", r"\1 \2"),   # export-report, load-orders
]


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
        import kokoro_onnx  # noqa: F401
        import numpy  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        fail("Bibliothèques manquantes. Installez-les : pip install kokoro-onnx soundfile")


def download_models():
    MODEL_DIR.mkdir(exist_ok=True)
    for name in MODEL_FILES:
        target = MODEL_DIR / name
        if target.exists() and target.stat().st_size > 0:
            continue
        print(f"⬇️  Téléchargement de {name} (une seule fois)…")
        tmp = target.with_suffix(target.suffix + ".part")

        def progress(blocks, block_size, total):
            if total > 0:
                pct = min(100, blocks * block_size * 100 // total)
                print(f"\r   {pct:3d} %", end="", flush=True)

        urllib.request.urlretrieve(MODEL_URL + name, tmp, progress)
        tmp.replace(target)
        print()


def parse_time(text):
    h, m, rest = text.strip().split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(path):
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = (parse_time(t) for t in lines[1].split("-->"))
        cues.append({"start": start, "end": end, "text": " ".join(lines[2:]).strip()})
    return sorted(cues, key=lambda c: c["start"])


def speakable(text, rules):
    for pattern, replacement in rules:
        text = re.sub(pattern, replacement, text)
    return text.replace("_", " ")


def load_rules(extra_file):
    rules = list(PRONUNCIATION)
    if extra_file:
        # fichier texte : une règle par ligne, « mot = prononciation »
        for line in Path(extra_file).read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                word, said = (x.strip() for x in line.split("=", 1))
                rules.insert(0, (r"(?<!\w)" + re.escape(word) + r"(?!\w)", said))
    return rules


def collect_srts(inputs):
    files = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            files += sorted(path.rglob("*.srt"))
        elif path.is_file():
            files.append(path)
        else:
            print(f"⚠️  Ignoré (introuvable) : {item}")
    return files


# --------------------------------------------------------------------------- synthèse

def synthesize(kokoro, text, voice, speed):
    samples, rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
    return samples, rate


def build_track(srt_path, kokoro, voice, args, rules):
    import numpy as np

    cues = parse_srt(srt_path)
    if not cues:
        raise RuntimeError("aucun sous-titre lisible")

    rate = 24000
    clips, drift_warnings, sped_up = [], [], 0
    for i, cue in enumerate(cues):
        # Place disponible : jusqu'au début de la phrase suivante (le silence entre deux est utilisable).
        next_start = cues[i + 1]["start"] if i + 1 < len(cues) else cue["end"] + 2.0
        window = max(0.5, next_start - cue["start"] - GAP)
        text = speakable(cue["text"], rules)

        speed = args.speed
        samples, rate = synthesize(kokoro, text, voice, speed)
        duration = len(samples) / rate
        if duration > window:
            speed = min(MAX_SPEED, args.speed * duration / window * 1.03)
            samples, rate = synthesize(kokoro, text, voice, speed)
            sped_up += 1
        clips.append((cue, samples, speed))
        print(f"\r   🗣️  {i + 1}/{len(cues)}", end="", flush=True)
    print()

    # Assemblage : chaque phrase à son temps, sans jamais chevaucher la précédente.
    placed, previous_end = [], 0.0
    for cue, samples, speed in clips:
        start = max(cue["start"], previous_end + GAP)
        if start - cue["start"] > 0.5:
            drift_warnings.append(f"      ⚠️  « {cue['text'][:50]}… » décalée de {start - cue['start']:.1f} s")
        placed.append((start, samples))
        previous_end = start + len(samples) / rate

    total = max(previous_end, cues[-1]["end"]) + 0.5
    track = np.zeros(int(total * rate) + 1, dtype=np.float32)
    for start, samples in placed:
        a = int(start * rate)
        track[a:a + len(samples)] += samples
    return track, rate, len(cues), sped_up, drift_warnings


def finalize(raw_wav, out_wav, out_mp3):
    """Normalise le volume à -16 LUFS et produit WAV + MP3."""
    loudnorm = f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11"
    for target, codec in ((out_wav, ["-c:a", "pcm_s16le"]), (out_mp3, ["-c:a", "libmp3lame", "-b:a", "192k"])):
        if target is None:
            continue
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw_wav), "-af", loudnorm,
               "-ar", "48000", *codec, str(target)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg : {result.stderr[-500:]}")


def output_paths(srt_path, args, voice_label):
    root = Path(args.output)
    sub = root / srt_path.parent.name   # srt_enhanced\cli1\… → audio\cli1\…
    stem = srt_path.stem  # « cli 1 output.en »
    wav = sub / f"{stem}.{voice_label}.wav"
    mp3 = None if args.no_mp3 else sub / f"{stem}.{voice_label}.mp3"
    return sub, wav, mp3


def main():
    parser = argparse.ArgumentParser(description="Génère une voix off anglaise, calée sur les temps des SRT.")
    parser.add_argument("inputs", nargs="*", help="Dossier(s) de SRT ou fichier(s) .srt")
    parser.add_argument("--voice", choices=["female", "male"], default="female",
                        help="Voix féminine ou masculine (défaut : female)")
    parser.add_argument("--voice-name", help="Voix Kokoro précise, ex. af_bella, am_fenrir, bm_george")
    parser.add_argument("--speed", type=float, default=1.0, help="Débit de base (défaut : 1.0)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help=f"Dossier de sortie (défaut : {DEFAULT_OUTPUT})")
    parser.add_argument("--pronunciation", help="Fichier de prononciations : une ligne « mot = prononciation »")
    parser.add_argument("--no-mp3", action="store_true", help="Ne produire que le WAV")
    parser.add_argument("--force", action="store_true", help="Regénérer même si le fichier existe déjà")
    parser.add_argument("--list-voices", action="store_true", help="Lister les voix anglaises disponibles")
    args = parser.parse_args()

    check_prerequisites()
    download_models()
    from kokoro_onnx import Kokoro
    import soundfile as sf

    kokoro = Kokoro(str(MODEL_DIR / MODEL_FILES[0]), str(MODEL_DIR / MODEL_FILES[1]))

    if args.list_voices:
        names = [v for v in kokoro.get_voices() if v[:2] in ("af", "am", "bf", "bm")]
        print("Voix anglaises (a = américain, b = britannique ; f = femme, m = homme) :")
        print("  " + ", ".join(names))
        return
    if not args.inputs:
        fail("Indiquez un dossier ou un fichier .srt (ou --list-voices).")

    voice = args.voice_name or VOICES[args.voice]
    voice_label = args.voice_name or args.voice
    rules = load_rules(args.pronunciation)

    srts = collect_srts(args.inputs)
    if not srts:
        fail("Aucun fichier .srt trouvé.")
    print(f"🎙️  Voix : {voice} · débit {args.speed} · {len(srts)} fichier(s)")

    ok = 0
    for srt in srts:
        sub, wav, mp3 = output_paths(srt, args, voice_label)
        if wav.exists() and not args.force:
            print(f"⏭️  Déjà généré : {wav.name}  (--force pour refaire)")
            ok += 1
            continue
        print(f"\n📄 {srt.name}")
        try:
            sub.mkdir(parents=True, exist_ok=True)
            track, rate, count, sped_up, drifts = build_track(srt, kokoro, voice, args, rules)
            raw = sub / f".{wav.stem}.raw.wav"
            sf.write(raw, track, rate)
            finalize(raw, wav, mp3)
            raw.unlink(missing_ok=True)
            print(f"   ✅ {count} phrases, {len(track) / rate:.0f} s"
                  + (f", {sped_up} accélérée(s) pour tenir dans leur place" if sped_up else ""))
            for line in drifts:
                print(line)
            print(f"      {wav}" + (f"\n      {mp3}" if mp3 else ""))
            ok += 1
        except Exception as e:  # un fichier en échec n'arrête pas les autres
            print(f"   ❌ {srt.name} : {e}")
    print(f"\n🏁 Terminé : {ok}/{len(srts)} piste(s) audio")
    sys.exit(0 if ok == len(srts) else 1)


if __name__ == "__main__":
    main()
