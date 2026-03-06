#!/usr/bin/env python3
import subprocess, json, re, tools

OLLAMA_MODEL = "qwen2.5:7b"

SYSTEM_PROMPT = """
Ты — Jarvis для Arch Linux + Hyprland.
Инструменты: open_app, close_app, workspace, move_app_to_workspace, set_volume, playerctl, list_files, read_file, analyze_image, run_shell, open_website.

Отвечай ТОЛЬКО JSON:
{"thought": "что думаю", "action": "инструмент", "args": {"arg": "val"}, "final_answer": "ответ"}
"""

def call_ollama(prompt: str, timeout=60) -> str:
    cmd = ["ollama", "run", OLLAMA_MODEL, prompt]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"

def run_agent_loop(user_command: str, tts_callback=None) -> str:
    """LLM только для сложных задач"""
    print("[AGENT] LLM reasoning...")
    history = [{"role": "system", "content": SYSTEM_PROMPT}]
    history.append({"role": "user", "content": f"Command: {user_command}"})
    
    for step in range(4):
        ctx = "\n".join([f"{m['role']}: {m['content']}" for m in history[-6:]])
        prompt = f"{ctx}\nAssistant JSON:"
        
        raw = call_ollama(prompt, timeout=60)
        print(f"[LLM Step {step}] {raw[:100]}...")
        
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if not match:
                continue
            
            decision = json.loads(match.group(0))
            
            if decision.get("final_answer"):
                final_answer = decision["final_answer"]
                print(f"[JARVIS] {final_answer}")
                if tts_callback:
                    tts_callback(final_answer)
                return final_answer
            
            action = decision.get("action")
            args = decision.get("args", {})
            
            if action and hasattr(tools, action):
                print(f"[ACTION] {action}({args})")
                result = getattr(tools, action)(**args)
                history.append({"role": "assistant", "content": f"Called {action}: {result}"})
        except Exception as e:
            print(f"[Error] {e}")
            break
    
    return "Задача выполнена"
