#!/usr/bin/env python3
import subprocess, os

def play_sound(name: str):
    paths = {
        "startup": "/usr/share/sounds/freedesktop/stereo/service-login.oga",
        "success": "/usr/share/sounds/freedesktop/stereo/complete.oga",
        "error": "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
        "listening": "/usr/share/sounds/freedesktop/stereo/message.oga",
        "wake": "/usr/share/sounds/freedesktop/stereo/bell.oga",
    }
    path = paths.get(name)
    if path and os.path.exists(path):
        try:
            subprocess.Popen(["paplay", path], stderr=subprocess.DEVNULL)
        except: pass

def play_startup(): play_sound("startup")
def play_success(): play_sound("success")
def play_error(): play_sound("error")
def play_listening(): play_sound("listening")
def play_wake(): play_sound("wake")
