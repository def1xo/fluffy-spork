# Jarvis: Arch Linux setup and autostart

## What is implemented in code now

`jarvis_agent_integrated.py` now has anti-false-trigger protections:
- energy gate for near-silence (`JARVIS_ENERGY_THRESHOLD`)
- basic VAD call to faster-whisper (when supported)
- duplicate text suppression (`JARVIS_DEDUP_WINDOW`)
- low-quality/noise phrase filter (subtitle artifacts etc.)
- safer wake-word detection (exact wake word has priority over fuzzy)
- command session stays active after successful command for follow-up utterances during wake window

## Recommended env config

Create `~/.config/jarvis/env`:

```bash
JARVIS_ASR_MODEL=small
JARVIS_ASR_DEVICE=cpu
JARVIS_SAMPLE_RATE=16000
JARVIS_SEGMENT_SECONDS=1.2
JARVIS_WAKE_THRESHOLD=82
JARVIS_WAKE_WINDOW=12
JARVIS_ENERGY_THRESHOLD=0.010
JARVIS_ADAPTIVE_ENERGY_FACTOR=3.0
JARVIS_MIN_ENERGY_FLOOR=0.003
JARVIS_CALIBRATION_SECONDS=1.5
JARVIS_MIN_TEXT_LEN=4
JARVIS_DEDUP_WINDOW=4
# can be index (25) OR part of device name (e.g. USB, HyperX, Fifine)
JARVIS_MIC_DEVICE=USB
```

Tune values:
- increase `JARVIS_ENERGY_THRESHOLD` if silent-room false triggers continue
- increase `JARVIS_WAKE_THRESHOLD` if random wake events continue
- increase `JARVIS_WAKE_WINDOW` for multi-turn without repeating wake word

## systemd user autostart

Create `~/.config/systemd/user/jarvis.service`:

```ini
[Unit]
Description=Jarvis local voice agent
After=graphical-session.target pipewire.service
Wants=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/home/YOUR_USER/jarvis
EnvironmentFile=%h/.config/jarvis/env
ExecStart=/home/YOUR_USER/jarvis/.venv/bin/python /home/YOUR_USER/jarvis/jarvis_agent_integrated.py
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now jarvis.service
loginctl enable-linger "$USER"
```

Logs:

```bash
journalctl --user -u jarvis.service -f
```

## What still needs to be built for "full Jarvis"

1. Speaker verification (`only me` mode) so random audio from speakers/TV is ignored.
2. Explicit dialogue state machine (sleep/listen/execute/follow-up) with timeout + cancel intents.
3. NLU router with intent confidence and confirmations for risky actions.
4. Local coding agent pipeline:
   - safe shell executor
   - git-aware patching
   - test runner + summary
5. Fast command path for desktop control (wmctrl/hyprctl/i3-msg), bypassing LLM.
6. Better whisper handling for whisper speech:
   - larger model (`small`/`medium`),
   - optional Vosk fallback,
   - wake keyword model (Porcupine/OpenWakeWord).
7. Better TTS voice profile and response style templates (Jarvis persona).
8. Permission model for "full system access" (allow-list + confirmations for destructive ops).


## Mic troubleshooting (if Jarvis does not react)

1. Run `python -m sounddevice` and check that your microphone has input channels.
2. Put either the numeric device index or part of microphone name into `JARVIS_MIC_DEVICE`.
3. Restart service: `systemctl --user restart jarvis.service`.
4. Watch logs and confirm line `Using input device index=...` appears.

If `JARVIS_MIC_DEVICE` is not set, Jarvis now auto-picks default input device, then falls back to first available input device.
