#!/usr/bin/env python3
import subprocess, threading

class TTSEngine:
    def __init__(self):
        self.process = None
        self.lock = threading.Lock()
    
    def speak(self, text: str, interrupt: bool = True):
        if not text: return
        with self.lock:
            if interrupt and self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=1)
                except: pass
            self.process = subprocess.Popen(
                ["espeak-ng", "-v", "ru", "-s", "150", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    
    def stop(self):
        with self.lock:
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=1)
                except: pass
                self.process = None

tts = TTSEngine()
def speak(text: str, interrupt: bool = True): tts.speak(text, interrupt)
def stop_speaking(): tts.stop()
