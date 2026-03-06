#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/jarvis/.config"
mkdir -p "$HOME/.config/systemd/user"

cat > "$HOME/jarvis/.config/env" <<'ENV'
JARVIS_ASR_MODEL=small
JARVIS_ASR_DEVICE=cpu
JARVIS_SAMPLE_RATE=16000
JARVIS_SEGMENT_SECONDS=1.2
JARVIS_WAKE_THRESHOLD=72
JARVIS_WAKE_WINDOW=12
JARVIS_ENERGY_THRESHOLD=0.0035
JARVIS_ADAPTIVE_ENERGY_FACTOR=3.0
JARVIS_MIN_ENERGY_FLOOR=0.003
JARVIS_CALIBRATION_SECONDS=1.5
JARVIS_MIN_TEXT_LEN=4
JARVIS_DEDUP_WINDOW=4
JARVIS_DEBUG_AUDIO=0
JARVIS_MIC_DEVICE=pipewire
ENV

cat > "$HOME/.config/systemd/user/jarvis.service" <<'UNIT'
[Unit]
Description=Jarvis local voice agent
After=graphical-session.target pipewire.service
Wants=graphical-session.target

[Service]
Type=simple
WorkingDirectory=%h/jarvis
EnvironmentFile=%h/jarvis/.config/env
ExecStart=%h/jarvis/.venv/bin/python %h/jarvis/jarvis_agent_integrated.py
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now jarvis.service
loginctl enable-linger "$USER"

echo "[OK] Done"
echo "[OK] env: $HOME/jarvis/.config/env"
echo "[OK] unit: $HOME/.config/systemd/user/jarvis.service"
echo "[OK] logs: journalctl --user -u jarvis.service -f"
