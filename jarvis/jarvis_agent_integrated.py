# jarvis_agent_integrated.py — session-based command execution, cleanup on exit
import os, sys, threading, time, traceback, logging, atexit, signal, glob, subprocess, shlex, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "assistant_modules"))

# imports (best-effort)
try:
    import command_handler as ch
    handle_text = getattr(ch, "handle_text")
    spotify_open_fn = getattr(ch, "spotify_open", None)
    spotify_play_fn = getattr(ch, "spotify_playpause", None)
except Exception:
    ch = None
    handle_text = None
    spotify_open_fn = None
    spotify_play_fn = None

try:
    import tts as tts_mod
except Exception:
    tts_mod = None

# optional faster-whisper (ASR)
ASR_AVAILABLE = False
WHISPER_MODEL = None
try:
    from faster_whisper import WhisperModel
    ASR_AVAILABLE = True
except Exception:
    ASR_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jarvis")

# Session / wake settings
WAKE_WORDS = ["джарвис", "джарв", "джарвет", "жарвис", "jarvis"]
WAKE_FUZZY_THRESHOLD = int(os.getenv("JARVIS_WAKE_THRESHOLD", "70"))
WAKE_WINDOW_SECONDS = float(os.getenv("JARVIS_WAKE_WINDOW", "8.0"))

SAMPLE_RATE = int(os.getenv("JARVIS_SAMPLE_RATE", "16000"))
SEGMENT_SECONDS = float(os.getenv("JARVIS_SEGMENT_SECONDS", "1.4"))
ENERGY_THRESHOLD = float(os.getenv("JARVIS_ENERGY_THRESHOLD", "0.012"))
MIN_TEXT_LEN = int(os.getenv("JARVIS_MIN_TEXT_LEN", "5"))
DEDUP_WINDOW_SECONDS = float(os.getenv("JARVIS_DEDUP_WINDOW", "4.0"))

# runtime session state
session = {
    "active": False,
    "last_wake": 0.0,
    "last_text": "",
    "last_text_ts": 0.0,
}

transcribe_lock = threading.Lock()

NOISE_PATTERNS = (
    "редактор субтитров",
    "корректор",
)

def cleanup_tmp():
    try:
        for p in glob.glob("/tmp/jarvis_utter_*.wav"):
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass

def _signal_handler(sig, frame):
    logger.info("Signal received, cleaning and exiting...")
    cleanup_tmp()
    sys.exit(0)

# register handlers
atexit.register(cleanup_tmp)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

def say(text):
    if not text:
        return
    try:
        if tts_mod:
            tts_mod.speak(text)
        else:
            logger.info("[TTS] %s", text)
    except Exception as e:
        logger.exception("TTS error: %s", e)

# ASR init
def init_asr():
    global WHISPER_MODEL, ASR_AVAILABLE
    if not ASR_AVAILABLE:
        logger.info("ASR not available")
        return
    model = os.getenv("JARVIS_ASR_MODEL", "tiny")
    device = os.getenv("JARVIS_ASR_DEVICE", "cpu")
    try:
        WHISPER_MODEL = WhisperModel(model, device=device)
        logger.info("ASR loaded model=%s device=%s", model, device)
    except Exception as e:
        logger.exception("ASR init failed, disabling ASR: %s", e)
        WHISPER_MODEL = None
        ASR_AVAILABLE = False

def fuzzy_wake_detect(text):
    # lightweight fuzzy matching: returns True if any wake word similar enough
    from rapidfuzz import fuzz
    t = normalize_text(text)
    if not t:
        return False, 0
    if any(w in t for w in WAKE_WORDS):
        return True, 100
    best = 0
    for w in WAKE_WORDS:
        score = max(fuzz.partial_ratio(w, t), fuzz.token_set_ratio(w, t))
        if score > best:
            best = score
    return best >= WAKE_FUZZY_THRESHOLD, best


def normalize_text(text):
    t = (text or "").lower().strip()
    t = re.sub(r"[^\w\sа-яё-]", " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def is_duplicate_text(text):
    now = time.time()
    if text == session["last_text"] and (now - session["last_text_ts"] <= DEDUP_WINDOW_SECONDS):
        return True
    session["last_text"] = text
    session["last_text_ts"] = now
    return False


def is_low_quality_text(text):
    if len(text) < MIN_TEXT_LEN:
        return True
    if not re.search(r"[a-zа-яё]", text, flags=re.IGNORECASE):
        return True
    if any(pat in text for pat in NOISE_PATTERNS):
        return True
    return False


def has_voice_activity(audio_np):
    if audio_np is None or len(audio_np) == 0:
        return False
    # simple energy gating for silent room false positives
    energy = float((audio_np ** 2).mean())
    return energy >= ENERGY_THRESHOLD

def contains_dyn_music(text):
    if not text:
        return False
    t = text.lower()
    return "динамич" in t or "энерг" in t or "движ" in t or "треки" in t

def open_spotify_search_and_play():
    """
    Try to open Spotify and play a 'динамичная музыка' search:
    - try spotify client (flatpak/binary) or xdg-open search url
    - then try to trigger play via playerctl
    """
    logger.info("Attempting to open Spotify and play dynamic music")
    say("Открываю динамичную музыку в Spotify.")
    # 1) try spotify open via command handler if available
    try:
        if spotify_open_fn:
            ok = spotify_open_fn()
            if ok:
                # wait a bit then try toggle play
                time.sleep(1.2)
                if spotify_play_fn:
                    spotify_play_fn()
                return True
    except Exception as e:
        logger.exception("spotify_open_fn error: %s", e)
    # 2) fallback: open web search
    try:
        query = "динамичная%20музыка"
        url = f"https://open.spotify.com/search/{query}"
        if shutil_which := (lambda n: __import__("shutil").which(n)):
            if shutil_which("xdg-open"):
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # try to play
                if shutil_which("playerctl"):
                    try:
                        time.sleep(1.5)
                        subprocess.run(["playerctl", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass
                return True
    except Exception as e:
        logger.exception("open_spotify_search_and_play fallback error: %s", e)
    return False

def safe_handle_text_call(text):
    # if text matches dynamic music -> special flow
    if contains_dyn_music(text):
        ok = open_spotify_search_and_play()
        if ok:
            say("Окей, поставил динамичную музыку.")
            return True
        else:
            say("Не получилось открыть Spotify.")
            return False
    # default: call command_handler
    try:
        if handle_text:
            return handle_text(text)
    except Exception:
        logger.exception("handle_text failed")
    return False

# thread worker for transcriptions
def transcribe_and_process(audio_np):
    # audio_np - float32 [-1,1]
    if not has_voice_activity(audio_np):
        return
    if not transcribe_lock.acquire(blocking=False):
        return
    try:
        if not WHISPER_MODEL:
            return
        try:
            segments, info = WHISPER_MODEL.transcribe(
                audio_np,
                language="ru",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 250},
            )
        except TypeError:
            segments, info = WHISPER_MODEL.transcribe(audio_np, language="ru")
        text = " ".join([seg.text for seg in segments]).strip()
    except Exception as e:
        logger.exception("Transcribe failed: %s", e)
        return
    finally:
        transcribe_lock.release()

    text = normalize_text(text)
    if not text:
        return
    if is_low_quality_text(text):
        logger.debug("Ignored low quality text: %s", text)
        return
    if is_duplicate_text(text):
        logger.debug("Ignored duplicate text: %s", text)
        return
    logger.info("TRANSCRIBED: %s", text)
    # wake detection
    is_wake, score = fuzzy_wake_detect(text)
    if is_wake:
        # activate session
        session["active"] = True
        session["last_wake"] = time.time()
        logger.info("Wake detected (score=%s). Session active.", score)
        say("Слушаю команды.")
        return
    # if session active and within window -> handle
    if session.get("active") and (time.time() - session.get("last_wake", 0) <= WAKE_WINDOW_SECONDS):
        handled = safe_handle_text_call(text)
        if handled:
            say("Сделано.")
            session["last_wake"] = time.time()
        else:
            say("Не понял команду или не получилось выполнить.")
            session["active"] = False
    else:
        logger.info("Ignored utterance (no active session).")

# audio listener (uses sounddevice)
def audio_listener_loop():
    import sounddevice as sd, numpy as np, queue
    q = queue.Queue()
    mic_env = os.getenv("JARVIS_MIC_DEVICE")
    if mic_env:
        try:
            sd.default.device = int(mic_env)
            logger.info("Set sounddevice default device -> %s", mic_env)
        except Exception:
            logger.info("Invalid JARVIS_MIC_DEVICE")
    sd.default.samplerate = SAMPLE_RATE
    sd.default.channels = 1
    def callback(indata, frames, time_info, status):
        q.put(indata.copy())
    try:
        stream = sd.InputStream(callback=callback, channels=1, samplerate=SAMPLE_RATE, blocksize=int(SAMPLE_RATE*0.2))
        stream.start()
    except Exception as e:
        logger.exception("Failed to open input stream: %s", e)
        return
    logger.info("Listening (audio stream started)...")
    buffer = []
    samples_needed = int(SAMPLE_RATE * SEGMENT_SECONDS)
    try:
        while True:
            data = q.get()
            arr = (data.reshape(-1)).astype('float32')
            buffer.append(arr)
            total = sum(len(b) for b in buffer)
            if total >= samples_needed:
                audio_np = __import__("numpy").concatenate(buffer, axis=0)
                buffer = []
                # spawn thread to transcribe & process
                threading.Thread(target=transcribe_and_process, args=(audio_np,), daemon=True).start()
    except KeyboardInterrupt:
        logger.info("Audio listener interrupted")
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass

def main():
    say("Jarvis запущен.")
    init_asr()
    if WHISPER_MODEL:
        # start audio listener in background
        t = threading.Thread(target=audio_listener_loop, daemon=True)
        t.start()
        # keep alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interrupted")
            cleanup_tmp()
    else:
        # fallback: stdin control
        logger.info("ASR unavailable; using stdin control")
        try:
            while True:
                line = input().strip()
                if not line:
                    continue
                if any(w in line.lower() for w in WAKE_WORDS):
                    say("Слушаю команды.")
                    cmd = input().strip()
                    if cmd:
                        safe_handle_text_call(cmd)
        except KeyboardInterrupt:
            cleanup_tmp()
            logger.info("Exited.")

if __name__ == '__main__':
    main()
