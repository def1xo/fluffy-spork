#!/usr/bin/env python3
import subprocess, os, shutil, pathlib, json, base64, urllib.request

def open_app(name: str):
    """Открывает приложение"""
    name = name.lower().strip()
    
    if any(x in name for x in ["spotify", "спот", "спорт", "музыка"]):
        if shutil.which("spotify"):
            subprocess.Popen(["spotify"])
            return {"ok": True, "msg": "Spotify запущен"}
        if shutil.which("flatpak"):
            try:
                subprocess.Popen(["flatpak", "run", "com.spotify.Client"])
                return {"ok": True, "msg": "Spotify (flatpak)"}
            except: pass
        return {"ok": False, "msg": "Spotify не установлен"}
    
    if any(x in name for x in ["code", "vscode", "vs", "код", "редактор", "вис"]):
        if shutil.which("code"):
            subprocess.Popen(["code"])
            return {"ok": True, "msg": "VS Code запущен"}
        return {"ok": False, "msg": "VS Code не найден"}
    
    if any(x in name for x in ["firefox", "браузер", "огонь", "chrome", "хром"]):
        for b in ["firefox", "google-chrome", "chromium"]:
            if shutil.which(b):
                subprocess.Popen([b])
                return {"ok": True, "msg": f"{b} запущен"}
        return {"ok": False, "msg": "Браузер не найден"}
    
    if shutil.which(name):
        subprocess.Popen([name])
        return {"ok": True, "msg": f"{name} запущен"}
    
    return {"ok": False, "msg": f"Приложение '{name}' не найдено"}

def close_app(name: str):
    """Закрывает приложение НАДЕЖНО (ИСПРАВЛЕНО)"""
    try:
        name = name.lower()
        # Варианты имен процессов
        targets = []
        if "spotify" in name:
            targets = ["spotify", "com.spotify.Client"]
        elif "code" in name or "vscode" in name:
            targets = ["code", "code-oss", "visual-studio-code"]
        elif "firefox" in name or "browser" in name:
            targets = ["firefox", "chrome", "chromium"]
        else:
            targets = [name]
        
        for t in targets:
            # pkill -9 (force)
            subprocess.run(["pkill", "-9", "-f", t], timeout=3, stderr=subprocess.DEVNULL)
            # killall backup
            subprocess.run(["killall", "-9", t], timeout=3, stderr=subprocess.DEVNULL)
        
        return {"ok": True, "msg": f"{name} закрыт"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}

def set_volume(delta_percent):
    """PipeWire wpctl"""
    try:
        if isinstance(delta_percent, str) and delta_percent.endswith("%"):
            val = float(delta_percent.strip("%")) / 100.0
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(val)], check=True)
        else:
            sign = "+" if delta_percent >= 0 else "-"
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", sign + str(abs(delta_percent)) + "%"], check=True)
        return {"ok": True, "msg": "Громкость изменена"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}

def workspace(num: int):
    """Hyprland: ПЕРЕКЛЮЧИТЬСЯ на рабочий стол"""
    try:
        subprocess.run(["hyprctl", "dispatch", "workspace", str(num)], check=True, timeout=5)
        return {"ok": True, "msg": f"Рабочий стол {num}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}

def move_app_to_workspace(app: str, num: int):
    """Hyprland: ПЕРЕМЕСТИТЬ окно приложения на рабочий стол"""
    try:
        # Ищем окно по названию приложения
        subprocess.run(["hyprctl", "dispatch", "movetoworkspacesilent", f"{num},title:{app}"], check=True, timeout=5)
        return {"ok": True, "msg": f"{app} перемещён на стол {num}"}
    except Exception as e:
        # Fallback без silent
        try:
            subprocess.run(["hyprctl", "dispatch", "movetoworkspace", f"{num},title:{app}"], check=True, timeout=5)
            return {"ok": True, "msg": f"{app} перемещён на стол {num}"}
        except:
            return {"ok": False, "msg": str(e)}

def playerctl(action: str):
    """Управление музыкой"""
    try:
        subprocess.run(["playerctl", action], check=True, timeout=5)
        return {"ok": True, "msg": f"Playerctl: {action}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}

def list_files(path: str):
    """Список файлов"""
    try:
        p = pathlib.Path(path).expanduser()
        if not p.exists():
            return {"ok": False, "error": "Папка не найдена"}
        files = [str(f) for f in p.iterdir() if f.is_file()]
        return {"ok": True, "files": files[:50], "msg": f"Найдено {len(files)} файлов"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def analyze_image(image_path: str, prompt: str = "Опиши изображение"):
    """Анализ через LLaVA"""
    try:
        p = pathlib.Path(image_path).expanduser()
        if not p.exists():
            return {"ok": False, "error": "Файл не найден"}
        with open(p, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')
        req_data = {"model": "llava", "prompt": prompt, "images": [img_b64], "stream": False}
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(req_data).encode(),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return {"ok": True, "description": result.get("response", "")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run_shell(cmd: str):
    """Выполнение shell команды"""
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {"ok": True, "stdout": res.stdout[:3000], "stderr": res.stderr[:1000]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def open_website(site: str):
    """Открывает сайт"""
    sites = {
        "youtube": "https://youtube.com", "ютуб": "https://youtube.com",
        "google": "https://google.com", "гугл": "https://google.com",
        "github": "https://github.com", "гитхаб": "https://github.com",
        "vk": "https://vk.com", "вк": "https://vk.com",
        "telegram": "https://web.telegram.org", "телеграм": "https://web.telegram.org",
    }
    url = sites.get(site.lower(), f"https://{site.lower()}.com")
    try:
        subprocess.Popen(["xdg-open", url])
        return {"ok": True, "msg": f"Открыл {url}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}
