# jarvis_agent_integrated.py — session-based command execution, cleanup on exit
import os, sys, threading, time, traceback, logging, atexit, signal, glob, subprocess, shlex
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

# runtime session state
session = {
    "active": False,
    "last_wake": 0.0
}

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
    t = (text or "").lower()
    best = 0
    for w in WAKE_WORDS:
        score = fuzz.partial_ratio(w, t)
        if score > best:
            best = score
    return best >= WAKE_FUZZY_THRESHOLD, best

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
    try:
        if not WHISPER_MODEL:
            return
        segments, info = WHISPER_MODEL.transcribe(audio_np, language="ru")
        text = " ".join([seg.text for seg in segments]).strip()
    except Exception as e:
        logger.exception("Transcribe failed: %s", e)
        return
    if not text:
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
        else:
            say("Не понял команду или не получилось выполнить.")
        # keep session active for short time if you want multi-turn; here we close
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
