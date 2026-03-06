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
WAKE_FUZZY_THRESHOLD = int(os.getenv("JARVIS_WAKE_THRESHOLD", "62"))
WAKE_WINDOW_SECONDS = float(os.getenv("JARVIS_WAKE_WINDOW", "8.0"))

SAMPLE_RATE = int(os.getenv("JARVIS_SAMPLE_RATE", "16000"))
ASR_TARGET_SAMPLE_RATE = 16000
SEGMENT_SECONDS = float(os.getenv("JARVIS_SEGMENT_SECONDS", "1.8"))
ENERGY_THRESHOLD = float(os.getenv("JARVIS_ENERGY_THRESHOLD", "0.0035"))
MIN_TEXT_LEN = int(os.getenv("JARVIS_MIN_TEXT_LEN", "5"))
DEDUP_WINDOW_SECONDS = float(os.getenv("JARVIS_DEDUP_WINDOW", "4.0"))
ADAPTIVE_ENERGY_FACTOR = float(os.getenv("JARVIS_ADAPTIVE_ENERGY_FACTOR", "3.0"))
MIN_ENERGY_FLOOR = float(os.getenv("JARVIS_MIN_ENERGY_FLOOR", "0.003"))
CALIBRATION_SECONDS = float(os.getenv("JARVIS_CALIBRATION_SECONDS", "1.5"))
DEBUG_AUDIO = os.getenv("JARVIS_DEBUG_AUDIO", "0") == "1"

# runtime session state
session = {
    "active": False,
    "last_wake": 0.0,
    "last_text": "",
    "last_text_ts": 0.0,
    "noise_floor": 0.0,
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
    energy = float((audio_np ** 2).mean())
    dynamic_threshold = max(
        ENERGY_THRESHOLD,
        MIN_ENERGY_FLOOR,
        session.get("noise_floor", 0.0) * ADAPTIVE_ENERGY_FACTOR,
    )
    return energy >= dynamic_threshold




def resample_audio(audio_np, input_sr, target_sr=ASR_TARGET_SAMPLE_RATE):
    if audio_np is None or len(audio_np) == 0:
        return audio_np
    if input_sr == target_sr:
        return audio_np
    import numpy as np
    duration = len(audio_np) / float(input_sr)
    target_len = max(1, int(duration * target_sr))
    src_x = np.linspace(0.0, 1.0, num=len(audio_np), endpoint=False)
    dst_x = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
    return np.interp(dst_x, src_x, audio_np).astype("float32")


def open_input_stream_with_fallback(sd, selected_input):
    default_sr = float(sd.query_devices(selected_input).get("default_samplerate") or 0)
    sr_candidates = []
    for sr in (SAMPLE_RATE, default_sr, 48000, 44100, 32000, 16000):
        if sr and sr > 0:
            sr_int = int(sr)
            if sr_int not in sr_candidates:
                sr_candidates.append(sr_int)

    last_error = None
    for sr in sr_candidates:
        try:
            stream = sd.InputStream(
                device=selected_input,
                callback=None,
                channels=1,
                samplerate=sr,
                blocksize=int(sr * 0.2),
            )
            stream.close()
            return sr, None
        except Exception as e:
            last_error = e

    return None, last_error



def split_wake_and_command(text):
    t = normalize_text(text)
    if not t:
        return None, ""
    for w in WAKE_WORDS:
        idx = t.find(w)
        if idx >= 0:
            after = t[idx + len(w):].strip(" ,.!?-:")
            return w, after
    return None, ""

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




def wants_spotify_open(text):
    from rapidfuzz import fuzz
    t = normalize_text(text)
    if not t:
        return False

    # direct easy hits
    if ("споти" in t or "spotify" in t) and ("включ" in t or "отк" in t or "запуст" in t):
        return True

    # robust fuzzy fallback for broken ASR like "включить чисп"
    command_score = max(
        fuzz.partial_ratio(t, "включить спотифай"),
        fuzz.partial_ratio(t, "открой спотифай"),
        fuzz.partial_ratio(t, "запусти spotify"),
    )

    token_score = 0
    for token in t.split():
        token_score = max(
            token_score,
            fuzz.ratio(token, "спотифай"),
            fuzz.ratio(token, "spotify"),
            fuzz.ratio(token, "споти"),
        )

    has_action = any(k in t for k in ("включ", "отк", "запуст", "постав"))

    # allow slightly lower token score when action verb is present
    if has_action and command_score >= 55:
        return True
    if has_action and token_score >= 52:
        return True
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
    if wants_spotify_open(text):
        ok = open_spotify_search_and_play()
        if ok:
            say("Окей, включаю Spotify.")
            return True

    # default: call command_handler
    try:
        if handle_text:
            return handle_text(text)
    except Exception:
        logger.exception("handle_text failed")
    return False


# thread worker for transcriptions
def transcribe_and_process(audio_np, input_sr):
    # audio_np - float32 [-1,1]
    energy = float((audio_np ** 2).mean()) if audio_np is not None and len(audio_np) else 0.0
    if DEBUG_AUDIO:
        dyn_thr = max(ENERGY_THRESHOLD, MIN_ENERGY_FLOOR, session.get("noise_floor", 0.0) * ADAPTIVE_ENERGY_FACTOR)
        logger.info("AUDIO energy=%.6f threshold=%.6f", energy, dyn_thr)
    if not has_voice_activity(audio_np):
        return
    if not transcribe_lock.acquire(blocking=False):
        return
    try:
        if not WHISPER_MODEL:
            return
        audio_for_asr = resample_audio(audio_np, input_sr, ASR_TARGET_SAMPLE_RATE)
        try:
            segments, info = WHISPER_MODEL.transcribe(
                audio_for_asr,
                language="ru",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 250},
            )
        except TypeError:
            segments, info = WHISPER_MODEL.transcribe(audio_for_asr, language="ru")
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
    wake_word, inline_cmd = split_wake_and_command(text)
    is_wake, score = fuzzy_wake_detect(text)
    if wake_word or is_wake:
        # activate/update session
        session["active"] = True
        session["last_wake"] = time.time()
        logger.info("Wake detected (score=%s, wake=%s). Session active.", score, wake_word or "fuzzy")

        # if command is in same utterance: execute immediately
        if inline_cmd and len(inline_cmd) >= 2:
            logger.info("Inline command after wake: %s", inline_cmd)
            handled = safe_handle_text_call(inline_cmd)
            if handled:
                say("Сделано.")
                session["last_wake"] = time.time()
            else:
                say("Не понял команду или не получилось выполнить.")
            return

        say("Слушаю команды.")
        return
    # if session active and within window -> handle
    if session.get("active") and (time.time() - session.get("last_wake", 0) <= WAKE_WINDOW_SECONDS):
        handled = safe_handle_text_call(text)
        if handled:
            say("Сделано.")
            session["last_wake"] = time.time()
        else:
            say("Не понял команду или не получилось выполнить. Повтори команду.")
            session["last_wake"] = time.time()
    else:
        logger.info("Ignored utterance (no active session).")


def select_input_device(sd, mic_env):
    devices = sd.query_devices()

    def is_input(idx):
        try:
            return int(devices[idx].get("max_input_channels", 0)) > 0
        except Exception:
            return False

    def preferred_score(name):
        n = str(name or "").lower()
        score = 0
        # prefer stable virtual backends over raw hw:* to avoid ALSA quirks/overflows
        if "pipewire" in n:
            score += 120
        if "pulse" in n:
            score += 110
        if n == "default" or n.startswith("default"):
            score += 100
        if "sysdefault" in n:
            score += 90
        if "hw:" in n:
            score -= 40
        return score
    if mic_env:
        mic_env = str(mic_env).strip()
        # direct index
        if mic_env.isdigit():
            idx = int(mic_env)
            try:
                dev = sd.query_devices(idx)
                if int(dev.get("max_input_channels", 0)) > 0:
                    return idx
                logger.warning("JARVIS_MIC_DEVICE=%s has no input channels", mic_env)
            except Exception:
                logger.warning("Invalid JARVIS_MIC_DEVICE index=%s", mic_env)
        # substring by device name
        lowered = mic_env.lower()
        for idx, dev in enumerate(devices):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            name = str(dev.get("name", "")).lower()
            if lowered in name:
                return idx
        logger.warning("JARVIS_MIC_DEVICE='%s' not found by name", mic_env)

    # default input from sounddevice
    try:
        default_dev = sd.default.device
        if isinstance(default_dev, (tuple, list)):
            default_input = default_dev[0]
        else:
            default_input = default_dev
        if isinstance(default_input, int) and default_input >= 0 and is_input(default_input):
            return default_input
    except Exception:
        pass

    # choose best non-hw backend first (pipewire/pulse/default/sysdefault)
    candidates = []
    for idx, dev in enumerate(devices):
        if not is_input(idx):
            continue
        candidates.append((preferred_score(dev.get("name")), idx))

    if candidates:
        candidates.sort(reverse=True)
        return candidates[0][1]

    return None


def log_input_devices(sd):
    try:
        devices = sd.query_devices()
        logger.info("Detected audio input devices:")
        for idx, dev in enumerate(devices):
            max_in = int(dev.get("max_input_channels", 0))
            if max_in > 0:
                logger.info("  [%s] %s (in=%s, default_sr=%s)", idx, dev.get("name"), max_in, dev.get("default_samplerate"))
    except Exception as e:
        logger.warning("Failed to list input devices: %s", e)


# audio listener (uses sounddevice)
def audio_listener_loop():
    import sounddevice as sd, numpy as np, queue
    q = queue.Queue(maxsize=24)
    overflow_counter = 0

    mic_env = os.getenv("JARVIS_MIC_DEVICE")
    selected_input = select_input_device(sd, mic_env)
    if selected_input is None:
        logger.error("No audio input device available. Check your mic / PipeWire / PulseAudio setup.")
        log_input_devices(sd)
        return

    logger.info("Using input device index=%s name=%s", selected_input, sd.query_devices(selected_input).get("name"))
    sd.default.device = (selected_input, None)
    sd.default.channels = 1

    selected_rate, probe_error = open_input_stream_with_fallback(sd, selected_input)
    if selected_rate is None:
        logger.exception("Failed to find working sample rate for input device: %s", probe_error)
        log_input_devices(sd)
        return

    logger.info("Selected input sample rate=%s", selected_rate)
    sd.default.samplerate = selected_rate

    def callback(indata, frames, time_info, status):
        nonlocal overflow_counter
        if status:
            overflow_counter += 1
            if overflow_counter % 10 == 1:
                logger.warning("Audio callback status: %s (count=%s)", status, overflow_counter)
        try:
            q.put_nowait(indata.copy())
        except queue.Full:
            try:
                q.get_nowait()  # drop oldest chunk to keep stream realtime
            except queue.Empty:
                pass
            try:
                q.put_nowait(indata.copy())
            except queue.Full:
                pass

    try:
        stream = sd.InputStream(
            device=selected_input,
            callback=callback,
            channels=1,
            samplerate=selected_rate,
            blocksize=0,
            latency="high",
        )
        stream.start()
    except Exception as e:
        logger.exception("Failed to open input stream: %s", e)
        log_input_devices(sd)
        return

    logger.info("Listening (audio stream started)...")

    # short startup calibration for ambient noise floor
    calib_buf = []
    calibrate_until = time.time() + max(0.0, CALIBRATION_SECONDS)
    buffer = []
    buffered_samples = 0
    samples_needed = int(selected_rate * SEGMENT_SECONDS)

    try:
        while True:
            data = q.get()
            arr = (data.reshape(-1)).astype("float32")
            if time.time() < calibrate_until:
                calib_buf.append(arr)
                continue
            if calib_buf:
                noise_audio = np.concatenate(calib_buf, axis=0)
                session["noise_floor"] = float((noise_audio ** 2).mean())
                logger.info("Noise floor calibrated=%.6f dynamic_threshold=%.6f", session["noise_floor"], max(ENERGY_THRESHOLD, MIN_ENERGY_FLOOR, session["noise_floor"] * ADAPTIVE_ENERGY_FACTOR))
                calib_buf = []

            buffer.append(arr)
            buffered_samples += len(arr)
            if buffered_samples >= samples_needed:
                audio_np = np.concatenate(buffer, axis=0)
                buffer = []
                buffered_samples = 0
                # spawn thread to transcribe & process
                threading.Thread(target=transcribe_and_process, args=(audio_np, selected_rate), daemon=True).start()
    except KeyboardInterrupt:
        logger.info("Audio listener interrupted")
    finally:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass




def run_doctor():
    from pathlib import Path

    print("[doctor] Jarvis environment diagnostics")
    print(f"[doctor] Python: {sys.version.split()[0]}")
    print(f"[doctor] ASR_AVAILABLE: {ASR_AVAILABLE}")

    project_dir = Path.home() / "jarvis"
    env_path = project_dir / ".config" / "env"
    service_path = Path.home() / ".config" / "systemd" / "user" / "jarvis.service"

    if env_path.exists():
        print(f"[doctor] OK env file: {env_path}")
    else:
        print(f"[doctor][ERROR] Missing env file: {env_path}")

    if service_path.exists():
        print(f"[doctor] OK systemd unit: {service_path}")
    else:
        print(f"[doctor][ERROR] Missing systemd unit: {service_path}")

    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print(f"[doctor] Audio devices found: {len(devices)}")
        in_count = 0
        for i, d in enumerate(devices):
            if int(d.get("max_input_channels", 0)) > 0:
                in_count += 1
                print(f"  in[{i}] {d.get('name')} sr={int(d.get('default_samplerate', 0))}")
        if in_count == 0:
            print("[doctor][ERROR] No input devices with capture channels.")
        else:
            print(f"[doctor] Input devices: {in_count}")
        selected = select_input_device(sd, os.getenv("JARVIS_MIC_DEVICE"))
        print(f"[doctor] Selected input by current env: {selected}")
        if selected is not None:
            sr, err = open_input_stream_with_fallback(sd, selected)
            if sr is None:
                print(f"[doctor][ERROR] No working sample rate for selected device: {err}")
            else:
                print(f"[doctor] Working input sample rate: {sr}")
    except Exception as e:
        print(f"[doctor][ERROR] sounddevice check failed: {e}")

    env_hint = [
        "JARVIS_ASR_MODEL=small",
        "JARVIS_ASR_DEVICE=cpu",
        "JARVIS_MIC_DEVICE=pipewire",
        "JARVIS_SAMPLE_RATE=16000",
        "JARVIS_ENERGY_THRESHOLD=0.0035",
        "JARVIS_MIN_ENERGY_FLOOR=0.0025",
        "JARVIS_WAKE_THRESHOLD=62",
    ]
    print("[doctor] Suggested env baseline:")
    for line in env_hint:
        print("  " + line)

    print("[doctor] Quick fix command (copy/paste):")
    print("  bash ~/jarvis/scripts/install_autostart.sh")


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
    if '--doctor' in sys.argv:
        run_doctor()
    else:
        main()
