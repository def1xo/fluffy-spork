# assistant_modules/sr_pipeline.py — safer: force CPU by default + tiny model; async transcribe
import time, queue, os, tempfile, wave, threading
from rapidfuzz import fuzz
import numpy as np
import sounddevice as sd

try:
    from silero_vad import VoiceActivityDetector
    VAD_AVAILABLE = True
except Exception:
    VAD_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    ASR_AVAILABLE = True
except Exception:
    ASR_AVAILABLE = False

WAKE_WORDS = ["джарвис", "джарв", "джарвет", "жарвис", "jarvis"]
WAKE_THRESHOLD = int(os.getenv("JARVIS_WAKE_THRESHOLD", "70"))
SAMPLE_RATE = 16000
CHUNK = 1600

q = queue.Queue()
def callback(indata, frames, time_info, status):
    q.put(indata.copy())

def normalize_text(s):
    if not s:
        return ""
    s = s.lower()
    s = s.replace("ё", "е").replace("ъ", "").replace("ь", "")
    return s

def detect_wake(text):
    text = normalize_text(text)
    best = ("", 0)
    for w in WAKE_WORDS:
        score = fuzz.partial_ratio(w, text)
        if score > best[1]:
            best = (w, score)
    return best

class SR:
    # Single init per thread; force device via env JARVIS_ASR_DEVICE (cpu/gpu) default cpu
    def __init__(self, vad_model_path=None, asr_model=None):
        self.vad = None
        self.asr = None
        model = asr_model or os.getenv("JARVIS_ASR_MODEL", "tiny")
        device = os.getenv("JARVIS_ASR_DEVICE", "cpu")
        if VAD_AVAILABLE:
            try:
                self.vad = VoiceActivityDetector(vad_model_path) if vad_model_path else VoiceActivityDetector("silero_vad.jit")
            except Exception as e:
                print("silero init failed:", e)
                self.vad = None
        if ASR_AVAILABLE:
            try:
                # force device param; faster-whisper accepts device arg
                self.asr = WhisperModel(model, device=device)
            except Exception as e:
                print("faster-whisper init failed (fallback to CPU):", e)
                try:
                    self.asr = WhisperModel(model, device="cpu")
                except Exception as e2:
                    print("faster-whisper init failed completely:", e2)
                    self.asr = None

    def is_speech(self, audio_np):
        if self.vad is None:
            return float(np.mean(np.abs(audio_np))) > 0.0025
        return self.vad.is_speech(audio_np, SAMPLE_RATE)

    def transcribe(self, audio_np):
        if self.asr is None:
            return "<ASR_MISSING>"
        try:
            segments, info = self.asr.transcribe(audio_np, language="ru")
            text = " ".join([seg.text for seg in segments])
            return text.strip()
        except Exception as e:
            print("ASR transcribe failed:", e)
            return "<ASR_ERROR>"

def write_wav(path, frames, samplerate=SAMPLE_RATE):
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(frames)

def _async_transcribe_and_dispatch(on_command, audio_bytes):
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        write_wav(tmp, audio_bytes, SAMPLE_RATE)
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)/32768.0
        engine = SR()
        text = engine.transcribe(audio_np)
        matched, score = detect_wake(text)
        if score >= WAKE_THRESHOLD:
            on_command("WAKE_DETECTED", text)
        else:
            on_command("UTTERANCE", text)
    except Exception as e:
        print("async_transcribe error:", e)
    finally:
        try:
            os.remove(tmp)
        except:
            pass

def listen_loop(on_command, vad_model_path=None, asr_model=None, primary_speaker=None):
    sd.default.samplerate = SAMPLE_RATE
    sd.default.channels = 1
    stream = sd.InputStream(callback=callback, channels=1, samplerate=SAMPLE_RATE, blocksize=CHUNK)
    stream.start()
    buffer = bytearray()
    last_speech = 0
    try:
        while True:
            chunk = q.get()
            audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32)/32768.0
            # cheap vad: use per-chunk energy if no VAD
            is_s = False
            try:
                if VAD_AVAILABLE:
                    is_s = SR().is_speech(audio)
                else:
                    is_s = float(np.mean(np.abs(audio))) > 0.0025
            except Exception:
                is_s = float(np.mean(np.abs(audio))) > 0.0025
            if is_s:
                last_speech = time.time()
                buffer.extend(chunk.tobytes())
            if not is_s and buffer:
                if time.time() - last_speech > 0.5:
                    audio_bytes = bytes(buffer)
                    threading.Thread(target=_async_transcribe_and_dispatch, args=(on_command, audio_bytes), daemon=True).start()
                    buffer = bytearray()
    except KeyboardInterrupt:
        stream.stop()
    except Exception as e:
        print("listen_loop main error:", e)
        stream.stop()
