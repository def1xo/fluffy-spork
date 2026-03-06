#!/usr/bin/env python3
# test_whisper.py - ДИАГНОСТИКА
import os, subprocess, wave, numpy as np, sounddevice as sd
from scipy.signal import resample_poly

DEVICE = 25  # <-- ЗАМЕНИТЕ НА СВОЙ НОМЕР
IN_SR = 48000
SR16 = 16000
TMPDIR = os.path.expanduser("~/jarvis/tmp")
os.makedirs(TMPDIR, exist_ok=True)

def find_whisper_bin():
    for p in [
        os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli"),
        os.path.expanduser("~/whisper.cpp/build/bin/main"),
        os.path.expanduser("~/whisper.cpp/main"),
    ]:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return None

WHISPER_BIN = find_whisper_bin()
print(f"[+] Whisper binary: {WHISPER_BIN}")
print(f"[+] Model: ~/whisper.cpp/models/ggml-tiny.bin")

def record_seconds(sec: float):
    frames = int(sec * IN_SR)
    audio = sd.rec(frames, samplerate=IN_SR, channels=1, dtype="float32", device=DEVICE)
    sd.wait()
    return audio[:, 0].copy()

def to_16k_int16(x):
    x = np.asarray(x, dtype=np.float32)
    x16 = resample_poly(x, SR16, IN_SR).astype(np.float32)
    x16 = np.clip(x16, -1.0, 1.0)
    return (x16 * 32767.0).astype(np.int16)

def write_wav(path, arr_i16):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR16)
        wf.writeframes(arr_i16.tobytes())

print("\n[!] Говорите сейчас (3 секунды)...")
audio = record_seconds(3.0)
arr16 = to_16k_int16(audio)
wav_path = os.path.join(TMPDIR, "test.wav")
write_wav(wav_path, arr16)
print(f"[+] WAV saved: {wav_path}")
print(f"[+] WAV size: {os.path.getsize(wav_path)} bytes")

# Пробуем разные варианты запуска whisper
out_path = os.path.join(TMPDIR, "out")
model_path = os.path.expanduser("~/whisper.cpp/models/ggml-tiny.bin")

print("\n[!] Запускаем whisper.cpp...")
for flags in [
    ["-m", model_path, "-f", wav_path, "-l", "ru", "-nt", "-of", out_path],
    ["-m", model_path, "-f", wav_path, "-l", "ru", "-of", out_path],
    ["-m", model_path, "-f", wav_path, "-l", "ru"],
]:
    print(f"\n[!] Флаги: {' '.join(flags)}")
    try:
        res = subprocess.run([WHISPER_BIN] + flags, capture_output=True, text=True, timeout=60)
        print(f"[stdout] {res.stdout[:500]}")
        print(f"[stderr] {res.stderr[:500]}")
        
        txt_file = out_path + ".txt"
        if os.path.exists(txt_file):
            print(f"[+] Файл {txt_file} создан!")
            with open(txt_file, "r", encoding="utf-8") as f:
                content = f.read()
                print(f"[content] {content}")
        else:
            print(f"[-] Файл {txt_file} НЕ создан")
    except Exception as e:
        print(f"[error] {e}")

print("\n[!] Диагностика завершена")
