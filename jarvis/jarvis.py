#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jarvis (improved) — local offline voice assistant.
Fixes: robust cleaning of whisper output, spotify handler, fallback small model.
"""
import os
import time
import subprocess
import wave
import re
import shutil
from typing import Optional
import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

# ========== Настройки ==========
DEVICE = 25                # твой working device (default was 25)
IN_SR = 48000
SR16 = 16000

# whisper-cli binary and models
WHISPER_BIN = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")
WAKE_MODEL_TINY = os.path.expanduser("~/whisper.cpp/models/ggml-tiny.bin")
WAKE_MODEL_SMALL = os.path.expanduser("~/whisper.cpp/models/ggml-small.bin")
CMD_MODEL = WAKE_MODEL_SMALL

# recording params
WAKE_CHUNK_SEC = 0.6
WAKE_LISTEN_SEC = 2.0
CMD_LISTEN_SEC = 6.0

# vad threshold (RMS on normalized int16 16k)
RMS_TH = 0.02

TMPDIR = os.path.expanduser("~/jarvis/tmp")
os.makedirs(TMPDIR, exist_ok=True)

# wake keywords and synonyms
WAKE_WORDS = [
    "джарвис", "jarvis", "эй джарвис", "hey jarvis",
    "spotify", "спотифай", "спортифай", "спортай", "споти"
]

WAKE_FALLBACK_TO_SMALL = True

# ======= Helpers =======
def find_whisper_bin():
    candidates = [
        os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli"),
        os.path.expanduser("~/whisper.cpp/build/bin/main"),
        os.path.expanduser("~/whisper.cpp/main"),
        os.path.expanduser("~/whisper.cpp/whisper-cli"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None

def which_or_raise(path):
    if path and os.path.exists(path) and os.access(path, os.X_OK):
        return path
    found = find_whisper_bin()
    if found:
        return found
    raise RuntimeError("Не найден whisper-cli бинарь. Собери whisper.cpp и укажи путь в WHISPER_BIN.")

WHISPER_BIN = which_or_raise(WHISPER_BIN)

def record_seconds(sec: float, sr: int, device: Optional[int]=DEVICE) -> np.ndarray:
    frames = int(sec * sr)
    audio = sd.rec(frames, samplerate=sr, channels=1, dtype="float32", device=device)
    sd.wait()
    return audio[:,0].copy()

def to_16k_int16(x_48k: np.ndarray) -> np.ndarray:
    if x_48k.size == 0:
        return np.zeros(SR16, dtype=np.int16)
    x = np.asarray(x_48k, dtype=np.float32)
    x16 = resample_poly(x, SR16, IN_SR).astype(np.float32)
    peak = float(np.max(np.abs(x16))) if x16.size else 0.0
    if peak > 1.0:
        x16 = x16 / peak
    x16 = np.clip(x16, -1.0, 1.0)
    if x16.shape[0] < SR16:
        x16 = np.pad(x16, (0, SR16 - x16.shape[0]))
    else:
        x16 = x16[:SR16]
    return (x16 * 32767.0).astype(np.int16)

def write_wav_int16(path: str, arr_i16: np.ndarray):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR16)
        wf.writeframes(arr_i16.tobytes())

# Improved cleaning: extract sequences of letters (Cyrillic+Latin+digits+spaces) and join them.
# This aggressively strips model logs and timings.
_regex_letters = re.compile(r"[A-Za-zА-Яа-яёЁ0-9\s\-]+")

def clean_whisper_text(raw: str) -> str:
    if not raw:
        return ""
    # Some versions output a lot to stdout/stderr. Keep only sequences with letters/digits/spaces.
    parts = _regex_letters.findall(raw)
    # join and collapse multiple spaces
    candidate = " ".join(parts)
    candidate = " ".join(candidate.split()).lower()
    # remove common non-words leftover
    # remove isolated single letters and spurious short tokens if too noisy
    tokens = [t for t in candidate.split() if len(t) > 1 or t in ("я","я.", "ok")]
    return " ".join(tokens).strip()

def transcribe_with_whisper_try(wav_path: str, model_path: str, lang: str="ru") -> str:
    """
    Attempt multiple command forms; then aggressively clean the combined stdout/stderr.
    We try to prefer whisper-cli writing output file (if supported), otherwise fallback to parsing stdout.
    """
    # attempt variants that write output file (silence logs by redirecting stderr)
    outtxt = os.path.join(TMPDIR, "out.txt")
    for cmd in [
        [WHISPER_BIN, "-m", model_path, "-f", wav_path, "-l", lang, "-nt", "-of", os.path.join(TMPDIR, "out")],
        [WHISPER_BIN, "-m", model_path, "-f", wav_path, "-l", lang, "-of", os.path.join(TMPDIR, "out")],
        [WHISPER_BIN, "-m", model_path, "-f", wav_path, "-of", os.path.join(TMPDIR, "out")],
    ]:
        try:
            # redirect stderr to /dev/null to hide internal logs; if whisper-cli writes out.txt, read it
            with open(os.devnull, "wb") as devnull:
                subprocess.run(cmd, stdout=devnull, stderr=devnull, check=True)
            if os.path.exists(outtxt):
                with open(outtxt, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                    return clean_whisper_text(raw)
        except Exception:
            continue

    # fallback: capture stdout+stderr and clean (aggressively)
    try:
        proc = subprocess.run([WHISPER_BIN, "-m", model_path, "-f", wav_path, "-l", lang],
                              capture_output=True, text=True, timeout=120)
        raw = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return clean_whisper_text(raw)
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""

def contains_wake_word(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    for w in WAKE_WORDS:
        if w in t:
            return True
    # additional pattern: verb + app (включи spotify)
    verbs = ["включи", "открой", "запусти", "воспроизведи"]
    for v in verbs:
        for app in ["spotify", "спотифай", "спортифай", "спортай", "споти"]:
            if v + " " + app in t:
                return True
    return False

def speak(text: str):
    try:
        subprocess.Popen(["notify-send", "Jarvis", text])
    except Exception:
        pass
    print("[jarvis speak]", text)

# Simple command handler (extendable). Handles spotify specially.
def handle_command(cmd_text: str) -> bool:
    t = cmd_text.lower()
    # spotify family
    if any(x in t for x in ["spotify", "спотифай", "спортифай", "спортай", "споти"]):
        speak("Открываю Spotify...")
        # try system spotify binary
        if shutil.which("spotify"):
            try:
                subprocess.Popen(["spotify"])
                return True
            except Exception:
                pass
        # try flatpak (common on many distros)
        if shutil.which("flatpak"):
            # check installed flatpak app id
            try:
                # try to run flatpak spotify runtime name
                subprocess.Popen(["flatpak", "run", "com.spotify.Client"])
                return True
            except Exception:
                pass
        # fallback: open web player
        try:
            subprocess.Popen(["xdg-open", "https://open.spotify.com"])
            return True
        except Exception:
            pass
        return False
    # add more handlers here: code editor, hyprctl, playerctl etc.
    # example: open code-oss
    if "code" in t or "editor" in t or "vscode" in t or "code-oss" in t:
        speak("Открываю VS Code...")
        if shutil.which("code"):
            subprocess.Popen(["code"])
        elif shutil.which("code-oss"):
            subprocess.Popen(["code-oss"])
        else:
            subprocess.Popen(["xdg-open", os.path.expanduser("~")])
        return True
    return False

# ===== Main wake logic =====
def has_voice_from_int16(arr_i16: np.ndarray) -> bool:
    if arr_i16.size == 0:
        return False
    x = arr_i16.astype(np.float32) / 32767.0
    rms = float(np.sqrt(np.mean(x * x)))
    return rms >= RMS_TH

def listen_for_wake():
    while True:
        x = record_seconds(WAKE_CHUNK_SEC, IN_SR)
        x16 = to_16k_int16(x)
        rms_dbg = float(np.sqrt(np.mean((x16.astype(np.float32) / 32767.0) ** 2)))
        print(f"[debug] chunk rms={rms_dbg:.4f}")
        if not has_voice_from_int16(x16):
            continue

        # record larger chunk and transcribe with tiny, fallback to small if tiny unusable
        x = record_seconds(WAKE_LISTEN_SEC, IN_SR)
        x16 = to_16k_int16(x)
        wav = os.path.join(TMPDIR, "wake.wav")
        write_wav_int16(wav, x16)

        txt = transcribe_with_whisper_try(wav, WAKE_MODEL_TINY, lang="ru")
        print("[wake raw tiny] ", repr(txt))
        if ((not txt) or len(txt.split()) <= 1) and WAKE_FALLBACK_TO_SMALL and os.path.exists(WAKE_MODEL_SMALL):
            print("[wake] tiny insufficient, trying small...")
            txt = transcribe_with_whisper_try(wav, WAKE_MODEL_SMALL, lang="ru")
            print("[wake raw small] ", repr(txt))

        print("[wake text cleaned] ", repr(txt))
        if contains_wake_word(txt):
            return
        time.sleep(0.15)

def listen_command() -> str:
    speak("Слушаю команду...")
    x = record_seconds(CMD_LISTEN_SEC, IN_SR)
    x16 = to_16k_int16(x)
    wav = os.path.join(TMPDIR, "cmd.wav")
    write_wav_int16(wav, x16)
    txt = transcribe_with_whisper_try(wav, CMD_MODEL, lang="ru")
    print("[command text cleaned] ", repr(txt))
    return txt.strip().lower() if txt else ""

def main():
    speak("Запущен. Скажи 'джарвис'.")
    try:
        while True:
            listen_for_wake()
            speak("Да?")
            cmd = listen_command()
            if not cmd:
                speak("Не расслышал.")
                continue
            print("== COMMAND ==\n", cmd)
            # handle known commands first (spotify, open editor, etc.)
            handled = handle_command(cmd)
            if not handled:
                speak(f"Понял: {cmd[:140]}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Stopped by user")

if __name__ == "__main__":
    main()
