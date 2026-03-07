# assistant_modules/tts.py — prefer edge-tts (online) -> pyttsx3 (offline); non-blocking worker
import os, tempfile, threading, subprocess, shlex, time, queue, asyncio

_tts_queue = queue.Queue()
_tts_worker = None

def _play_wav_nonblocking(path):
    for cmd in (f"paplay {shlex.quote(path)}", f"aplay {shlex.quote(path)}", f"ffplay -nodisp -autoexit {shlex.quote(path)}"):
        try:
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.05)
            return p
        except Exception:
            continue
    return None

async def _edge_synth(text, voice=None, outpath=None):
    try:
        import edge_tts
        voice = voice or os.getenv("JARVIS_TTS_VOICE", "en-US-GuyNeural")
        outpath = outpath or tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        comm = edge_tts.Communicate(text, voice)
        await comm.save(outpath)
        return outpath
    except Exception as e:
        print("edge-tts synth error:", e)
        return None

def _worker_loop():
    # try edge-tts first, otherwise pyttsx3, otherwise system print
    edge_ok = False
    py_ok = False
    try:
        import importlib
        edge_ok = importlib.util.find_spec("edge_tts") is not None
    except Exception:
        edge_ok = False
    try:
        import importlib
        py_ok = importlib.util.find_spec("pyttsx3") is not None
    except Exception:
        py_ok = False

    py_engine = None
    if py_ok:
        try:
            import pyttsx3
            py_engine = pyttsx3.init()
            py_engine.setProperty("rate", 150)
            print("TTS: pyttsx3 ready in worker")
        except Exception as e:
            print("pyttsx3 init failed in worker:", e)
            py_engine = None
            py_ok = False

    while True:
        text, model_hint = _tts_queue.get()
        if text is None:
            break
        # 1) edge-tts (online)
        if edge_ok:
            try:
                out = asyncio.run(_edge_synth(text))
                if out:
                    _play_wav_nonblocking(out)
                    _tts_queue.task_done()
                    continue
            except Exception as e:
                print("edge-tts failed in worker:", e)
                edge_ok = False
        # 2) pyttsx3
        if py_ok and py_engine is not None:
            try:
                def run_py(t):
                    try:
                        py_engine.say(t)
                        py_engine.runAndWait()
                    except Exception as e:
                        print("pyttsx3 runtime error:", e)
                threading.Thread(target=run_py, args=(text,), daemon=True).start()
                _tts_queue.task_done()
                continue
            except Exception as e:
                print("pyttsx3 error in worker:", e)
                py_engine = None
                py_ok = False
        # 3) system fallback
        try:
            if os.system(f"spd-say {shlex.quote(text)} >/dev/null 2>&1") == 0:
                pass
            elif os.system(f"espeak {shlex.quote(text)} >/dev/null 2>&1") == 0:
                pass
            else:
                print("[TTS fallback print]", text)
        except Exception:
            print("[TTS fallback print]", text)
        _tts_queue.task_done()

def _ensure_worker():
    global _tts_worker
    if _tts_worker is None or not _tts_worker.is_alive():
        _tts_worker = threading.Thread(target=_worker_loop, daemon=True)
        _tts_worker.start()

def speak(text, model_name=None):
    if not text:
        return
    _ensure_worker()
    _tts_queue.put((text, model_name))
    # non-blocking
