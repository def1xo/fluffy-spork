# assistant_modules/ollama_agent.py — minimal Ollama wrapper via CLI
import subprocess, shlex, json, os

def query_ollama(prompt, model="llama2", timeout=30):
    """
    Query local Ollama via CLI: returns text or raises.
    Requires 'ollama' CLI installed and model available locally.
    Fallbacks: return None on error.
    """
    try:
        # Safe: pass prompt through stdin to avoid shell issues
        proc = subprocess.run(["ollama", "query", model, "--stdin"], input=prompt.encode("utf-8"),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")
            print("ollama query error:", err)
            return None
        out = proc.stdout.decode("utf-8", errors="ignore")
        return out.strip()
    except FileNotFoundError:
        print("ollama not found (install ollama to enable local LLM).")
        return None
    except Exception as e:
        print("ollama query exception:", e)
        return None
