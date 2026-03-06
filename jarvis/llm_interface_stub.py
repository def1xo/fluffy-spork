#!/usr/bin/env python3
import re

def map_command_to_tool_json(user_cmd: str) -> dict:
    """БЫСТРЫЙ маппинг без LLM (0.01 сек)"""
    cmd = user_cmd.lower()
    
    # СТОП СЛОВА
    if any(x in cmd for x in ["хватит", "стоп", "прекрати", "молчи", "тихо"]):
        return {"tool": "stop", "args": {}, "speed": "fast"}
    
    # ЗАКРЫТЬ ПРИЛОЖЕНИЕ
    if any(x in cmd for x in ["закрой", "close", "убей", "kill", "выключи"]):
        if any(x in cmd for x in ["спот", "spotify", "спорт"]):
            return {"tool": "close_app", "args": {"name": "spotify"}, "speed": "fast"}
        if any(x in cmd for x in ["код", "code", "vscode", "vs", "вис"]):
            return {"tool": "close_app", "args": {"name": "code"}, "speed": "fast"}
        if any(x in cmd for x in ["браузер", "firefox", "хром", "chrome"]):
            return {"tool": "close_app", "args": {"name": "firefox"}, "speed": "fast"}
    
    # SPOTIFY
    if any(x in cmd for x in ["спот", "спорт", "spotify", "спотифай", "музыка"]):
        return {"tool": "open_app", "args": {"name": "spotify"}, "speed": "fast"}
    
    # VS CODE
    if any(x in cmd for x in ["код", "code", "vscode", "vs", "вис", "редактор"]):
        return {"tool": "open_app", "args": {"name": "code"}, "speed": "fast"}
    
    # WORKSPACE: ПЕРЕМЕСТИТЬ приложение (например "перемести spotify на пятый стол")
    if any(x in cmd for x in ["перемест", "move", "перекинь", "тащи"]):
        if any(x in cmd for x in ["спот", "spotify"]):
            nums = re.findall(r"\d+", cmd)
            if nums:
                return {"tool": "move_app_to_workspace", "args": {"app": "spotify", "num": int(nums[0])}, "speed": "fast"}
        if any(x in cmd for x in ["код", "code", "vscode"]):
            nums = re.findall(r"\d+", cmd)
            if nums:
                return {"tool": "move_app_to_workspace", "args": {"app": "code", "num": int(nums[0])}, "speed": "fast"}
    
    # WORKSPACE: ПЕРЕКЛЮЧИТЬСЯ (например "перемести меня на третий" или "третий стол")
    if any(x in cmd for x in ["стол", "окно", "workspace", "рабоч", "экран"]):
        nums = re.findall(r"\d+", cmd)
        if nums:
            return {"tool": "workspace", "args": {"num": int(nums[0])}, "speed": "fast"}
        if any(x in cmd for x in ["перв", "один", "1"]):
            return {"tool": "workspace", "args": {"num": 1}, "speed": "fast"}
        if any(x in cmd for x in ["втор", "два", "2"]):
            return {"tool": "workspace", "args": {"num": 2}, "speed": "fast"}
        if any(x in cmd for x in ["трет", "три", "3"]):
            return {"tool": "workspace", "args": {"num": 3}, "speed": "fast"}
        if any(x in cmd for x in ["пят", "пять", "5"]):
            return {"tool": "workspace", "args": {"num": 5}, "speed": "fast"}
    
    # ГРОМКОСТЬ
    if any(x in cmd for x in ["громк", "volume", "звук", "тиш", "гром"]):
        if any(x in cmd for x in ["тиш", "меньш", "down", "-", "убавь"]):
            return {"tool": "set_volume", "args": {"delta_percent": "-10%"}, "speed": "fast"}
        return {"tool": "set_volume", "args": {"delta_percent": "+10%"}, "speed": "fast"}
    
    # МУЗЫКА
    if any(x in cmd for x in ["пауз", "pause", "стоп"]):
        return {"tool": "playerctl", "args": {"action": "pause"}, "speed": "fast"}
    if any(x in cmd for x in ["плей", "play", "игра", "включ"]):
        return {"tool": "playerctl", "args": {"action": "play"}, "speed": "fast"}
    if any(x in cmd for x in ["след", "next", "дальше"]):
        return {"tool": "playerctl", "args": {"action": "next"}, "speed": "fast"}
    
    # САЙТЫ
    if any(x in cmd for x in ["ютуб", "youtube", "видео"]):
        return {"tool": "open_website", "args": {"site": "youtube"}, "speed": "fast"}
    if any(x in cmd for x in ["гугл", "google", "поиск"]):
        return {"tool": "open_website", "args": {"site": "google"}, "speed": "fast"}
    
    # СЛОЖНЫЕ ЗАДАЧИ → LLM
    if any(x in cmd for x in ["анализ", "чекни", "посмотри", "файл", "папк", "картинк", "изображ", "цвет"]):
        return {"tool": "llm_agent", "args": {"cmd": user_cmd}, "speed": "slow"}
    
    return {"tool": None, "speed": "none"}
