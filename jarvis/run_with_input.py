#!/usr/bin/env python3
# run_with_input.py — запускает jarvis_agent_integrated.py и параллельно читает stdin
import sys, os, threading, time

# ensure local modules are importable
sys.path.insert(0, os.path.dirname(__file__))

import jarvis_agent_integrated as agent

def stdin_reader():
    """
    Простая эмуляция голосового ввода через клавиатуру:
    - строка содержащая 'джарв' -> триггер WAKE_DETECTED
    - любая другая строка -> UTTERANCE
    """
    print("[runner] stdin reader started. Пиши 'джарвис' на активацию, затем текст команды.")
    wake_seen = False
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            if not line:
                continue
            low = line.lower()
            if "джарв" in low or "jarv" in low:
                # emulate wake
                print("[runner] emulating WAKE_DETECTED")
                try:
                    agent.on_command("WAKE_DETECTED", line)
                except Exception as e:
                    print("[runner] error calling on_command WAKE_DETECTED:", e)
                wake_seen = True
                continue
            # if we saw wake recently, send utterance; else still send UTTERANCE (some agents accept that)
            try:
                agent.on_command("UTTERANCE", line)
            except Exception as e:
                print("[runner] error calling on_command UTTERANCE:", e)
    except KeyboardInterrupt:
        print("[runner] stdin reader exiting")

if __name__ == "__main__":
    # start stdin reader thread
    t = threading.Thread(target=stdin_reader, daemon=True)
    t.start()
    # run normal main loop of agent (this blocks)
    try:
        agent.main()
    except KeyboardInterrupt:
        print("run_with_input: interrupted by user")
