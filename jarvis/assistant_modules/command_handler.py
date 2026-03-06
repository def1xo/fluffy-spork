# command_handler.py — spotify helpers + fuzzy commands
from rapidfuzz import process, fuzz
import subprocess, os, shlex, re

def run(cmd_list, check=False):
    try:
        return subprocess.run(cmd_list, check=check)
    except Exception as e:
        print("Error running", cmd_list, e)
        return None

def shutil_which(name):
    from shutil import which
    return which(name) is not None

def spotify_close():
    print("[command_handler] spotify_close called")
    try:
        if shutil_which("playerctl"):
            run(["playerctl", "stop"])
        run(["pkill", "-f", "spotify"], check=False)
        return True
    except Exception as e:
        print("spotify_close error:", e)
        return False

def spotify_playpause():
    print("[command_handler] spotify_playpause called")
    try:
        if shutil_which("playerctl"):
            run(["playerctl", "play-pause"])
            return True
        return False
    except Exception as e:
        print("spotify_playpause error:", e)
        return False

def spotify_open():
    print("[command_handler] spotify_open called")
    try:
        if shutil_which("flatpak"):
            run(["flatpak", "run", "com.spotify.Client"], check=False)
            return True
        if shutil_which("spotify"):
            run(["spotify"], check=False)
            return True
        if shutil_which("xdg-open"):
            run(["xdg-open", "https://open.spotify.com"], check=False)
            return True
    except Exception as e:
        print("spotify_open error:", e)
    return False

# Main handle_text (simple fuzzy + patterns)
def handle_text(text):
    if not text:
        return False
    txt = text.lower()
    # direct patterns
    if re.search(r"закр.*споти", txt) or "выключи музыку" in txt or "останови" in txt:
        return spotify_close()
    if re.search(r"пауз", txt) or "пауза" in txt:
        return spotify_playpause()
    if re.search(r"откр.*споти", txt) or "запусти spotify" in txt or "открой музыку" in txt:
        return spotify_open()
    # fuzzy fallback to known commands
    choices = ["закрой spotify", "открой spotify", "пауза", "открыть vscode", "закрой файл"]
    match, score, idx = process.extractOne(txt, choices, scorer=fuzz.token_sort_ratio)
    if score and score > 65:
        cmd = match
        if "закрой" in cmd:
            return spotify_close()
        if "открой" in cmd:
            return spotify_open()
        if "пауза" in cmd:
            return spotify_playpause()
    return False
