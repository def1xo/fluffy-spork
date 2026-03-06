#!/usr/bin/env python3
# jarvis_agent.py — V10: GOD MODE (HYBRID + CONTEXT + STOP)
import os, subprocess, wave, numpy as np, sounddevice as sd, re, time, threading
from scipy.signal import resample_poly
from collections import deque
from llm_interface_stub import map_command_to_tool_json
from llm_interface import run_agent_loop
from tts_engine import speak, stop_speaking
from sounds import play_startup, play_success, play_error, play_listening, play_wake
import tools

# === КОНФИГ ===
DEVICE = 25
IN_SR = 48000
SR16 = 16000
TMPDIR = os.path.expanduser("~/jarvis/tmp")
os.makedirs(TMPDIR, exist_ok=True)

BUFFER_SEC = 5.0
MAX_SILENCE_SEC = 0.5
RMS_TH = 0.035

WAKE_WORDS = ["джарвис", "jarvis", "жарвис", "жарвец", "рарвис", "гейрвис", "javis", "джар"]
STOP_WORDS = ["хватит", "стоп", "прекрати", "молчи", "тихо", "замолчи"]

WHISPER_BIN = os.path.expanduser("~/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL = os.path.expanduser("~/whisper.cpp/models/ggml-small.bin")

# === RING BUFFER ===
class RingBuffer:
    def __init__(self, duration_sec, sr):
        self.max_samples = int(duration_sec * sr)
        self.buffer = np.zeros(self.max_samples, dtype=np.float32)
        self.idx = 0
        self.filled = False
    
    def add(self, chunk):
        for sample in chunk:
            self.buffer[self.idx] = sample
            self.idx = (self.idx + 1) % self.max_samples
            if self.idx == 0: self.filled = True
    
    def get_audio(self):
        if not self.filled:
            return self.buffer[:self.idx].copy()
        return np.concatenate([self.buffer[self.idx:], self.buffer[:self.idx]])
    
    def clear(self):
        self.buffer.fill(0)
        self.idx = 0
        self.filled = False

def to_16k_int16(x):
    if x.size == 0: return np.zeros(SR16, dtype=np.int16)
    x16 = resample_poly(np.asarray(x, dtype=np.float32), SR16, IN_SR).astype(np.float32)
    peak = float(np.max(np.abs(x16))) if x16.size else 0.0
    if peak > 1.0: x16 = x16 / peak
    return (np.clip(x16, -1.0, 1.0) * 32767.0).astype(np.int16)

def write_wav(path, arr_i16):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR16)
        wf.writeframes(arr_i16.tobytes())

def transcribe(wav_path):
    if not os.path.exists(WHISPER_BIN): return ""
    cmd = [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", wav_path, "--language", "ru", "--no-timestamps"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        text = re.sub(r'\[.*?\]', '', res.stdout)
        text = re.sub(r'\s+', ' ', text).strip().lower()
        return text
    except: return ""

def check_wake(text):
    text = text.lower()
    for w in WAKE_WORDS:
        if w in text: return w
    if "жар" in text or "рарв" in text or "гейр" in text: return "джарвис"
    return None

def check_stop(text):
    text = text.lower()
    for w in STOP_WORDS:
        if w in text: return True
    return False

def extract_command(text, wake_word):
    if not wake_word: return text
    parts = text.split(wake_word, 1)
    if len(parts) > 1:
        cmd = parts[1].strip().lstrip(" ,.!?-")
        return cmd
    return text

def execute_fast(spec):
    """Быстрое выполнение без LLM"""
    tool = spec.get("tool")
    args = spec.get("args", {})
    
    if tool == "stop":
        stop_speaking()
        print("[STOP] Speech interrupted")
        return True
    
    if tool and hasattr(tools, tool):
        try:
            result = getattr(tools, tool)(**args)
            msg = result.get("msg", str(result))
            print(f"[FAST] {tool}: {msg}")
            speak(msg, interrupt=False)
            play_success()
            return True
        except Exception as e:
            print(f"[ERROR] {e}")
            speak(f"Ошибка: {e}", interrupt=False)
            return False
    return False

def on_speak(text):
    speak(text, interrupt=True)

def main():
    print("="*60)
    print("JARVIS V10 — GOD MODE (HYBRID + CONTEXT + STOP)")
    print(f"Device: {DEVICE} | RMS: {RMS_TH} | Silence: {MAX_SILENCE_SEC}s")
    print("="*60)
    
    if not os.path.exists(WHISPER_MODEL):
        print(f"[ERROR] Модель не найдена: {WHISPER_MODEL}")
        return
    
    play_startup()
    speak("Джарвис онлайн.", interrupt=False)
    
    ring_buf = RingBuffer(BUFFER_SEC, IN_SR)
    
    def audio_callback(indata, frames, time, status):
        ring_buf.add(indata[:, 0])
    
    stream = sd.InputStream(device=DEVICE, channels=1, samplerate=IN_SR, dtype='float32', callback=audio_callback)
    stream.start()
    
    print("\n[OK] Listening...")
    print("Команды:")
    print("  'Джарвис + команда' → выполнить")
    print("  'Джарвис' → спросит 'Что нужно?'")
    print("  'Хватит/Стоп' → прервать")
    print("  После вопроса можно ответить без 'Джарвис'")
    print("="*60)
    
    speaking = False
    silence_start = None
    command_count = 0
    waiting_for_command = False  # Контекст: ждём продолжение
    
    try:
        while True:
            time.sleep(0.05)
            current = ring_buf.get_audio()
            if len(current) < int(0.2 * IN_SR): continue
            
            last_200ms = current[-int(0.2 * IN_SR):]
            rms = np.sqrt(np.mean(last_200ms ** 2))
            
            # Проверка СТОП слов в реальном времени
            if rms > RMS_TH and speaking:
                # Можно добавить детекцию стоп-слов
                pass
            
            if rms > RMS_TH:
                if not speaking:
                    speaking = True
                    silence_start = None
                    command_count += 1
                    print(f"\n[!] Voice #{command_count} (RMS: {rms:.3f})")
                silence_start = None
            else:
                if speaking:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start > MAX_SILENCE_SEC:
                        print(f"[...] Processing...")
                        speaking = False
                        
                        full_audio = ring_buf.get_audio()
                        arr16 = to_16k_int16(full_audio)
                        wav_path = os.path.join(TMPDIR, "cmd.wav")
                        write_wav(wav_path, arr16)
                        
                        text = transcribe(wav_path)
                        print(f"[USER] {text}")
                        
                        if text:
                            # Проверка СТОП
                            if check_stop(text):
                                print("[STOP] Stop word detected")
                                stop_speaking()
                                speak("Хорошо", interrupt=False)
                                waiting_for_command = False
                                ring_buf.clear()
                                continue
                            
                            wake = check_wake(text)
                            
                            if wake:
                                play_wake()
                                print(f"[+] Wake: '{wake}'")
                                cmd = extract_command(text, wake)
                                waiting_for_command = False  # Сброс контекста
                                
                                if cmd and len(cmd) > 3:
                                    print(f"[CMD] {cmd}")
                                    play_listening()
                                    
                                    spec = map_command_to_tool_json(cmd)
                                    speed = spec.get("speed", "none")
                                    
                                    if speed == "fast":
                                        execute_fast(spec)
                                    elif speed == "slow":
                                        run_agent_loop(cmd, tts_callback=on_speak)
                                        play_success()
                                    else:
                                        speak("Не поняла", interrupt=False)
                                else:
                                    # Только "Джарвис"
                                    waiting_for_command = True
                                    speak("Слушаю", interrupt=False)
                                    play_listening()
                            else:
                                if waiting_for_command:
                                    # КОНТЕКСТ: ответ без "Джарвис"
                                    print(f"[CMD] {text}")
                                    run_agent_loop(text, tts_callback=on_speak)
                                    play_success()
                                    waiting_for_command = False
                                else:
                                    print(f"[!] No wake word")
                        
                        ring_buf.clear()
                        
    except KeyboardInterrupt:
        print("\n[JARVIS] Stopped.")
        stop_speaking()
    finally:
        stream.stop()
        stream.close()

if __name__ == "__main__":
    main()
