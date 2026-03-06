# Jarvis: Arch Linux setup and autostart (project-local config)

## Goal

Store **all Jarvis config inside project folder** (not in `~/.config`):
- env file: `~/jarvis/.config/env`
- systemd unit: `~/.config/systemd/user/jarvis.service` (systemd requirement)
- runtime paths point to `~/jarvis/...`

---

## 1) One-shot setup (copy/paste everything)

```bash
cat <<'SCRIPT' > ~/jarvis/setup_jarvis_autostart.sh
#!/usr/bin/env bash
set -euo pipefail

mkdir -p ~/jarvis/.config
mkdir -p ~/.config/systemd/user

cat > ~/jarvis/.config/env <<'ENV'
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
# can be index (25) OR part of device name (e.g. pipewire, pulse, USB, HyperX)
JARVIS_MIC_DEVICE=pipewire
ENV

cat > ~/.config/systemd/user/jarvis.service <<'UNIT'
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

echo "[OK] Jarvis autostart configured"
echo "[OK] Env file: ~/jarvis/.config/env"
echo "[OK] Service:  ~/.config/systemd/user/jarvis.service"
echo "[OK] Logs: journalctl --user -u jarvis.service -f"
SCRIPT

chmod +x ~/jarvis/setup_jarvis_autostart.sh
~/jarvis/setup_jarvis_autostart.sh
```

---

## 2) Quick checks (copy/paste)

```bash
systemctl --user status jarvis.service --no-pager
journalctl --user -u jarvis.service -n 80 --no-pager
```

Run doctor manually from project:

```bash
cd ~/jarvis
. .venv/bin/activate
python jarvis_agent_integrated.py --doctor
```

---

## 3) Mic troubleshooting (if Jarvis does not react)

```bash
cd ~/jarvis
. .venv/bin/activate
python -m sounddevice
python jarvis_agent_integrated.py --doctor
```

If wake word still not detected, run with debug energy logs:

```bash
cd ~/jarvis
. .venv/bin/activate
JARVIS_DEBUG_AUDIO=1 python jarvis_agent_integrated.py
```

You should see `AUDIO energy=... threshold=...` in logs.
If energy is always below threshold, lower `JARVIS_ENERGY_THRESHOLD` to `0.0025` in `~/jarvis/.config/env` and restart:

```bash
systemctl --user restart jarvis.service
journalctl --user -u jarvis.service -f
```

---

## 4) If you want me to tune exactly for your PC

Run this command and send output:

```bash
cat <<'CMD' > ~/jarvis/collect_jarvis_debug.sh
#!/usr/bin/env bash
set -euo pipefail

echo "===== USER/OS ====="
id
uname -a

echo "===== AUDIO DEVICES (sounddevice) ====="
python -m sounddevice || true

echo "===== PIPEWIRE/PULSE ====="
pactl info || true
pactl list short sources || true

echo "===== JARVIS ENV ====="
cat ~/jarvis/.config/env || true

echo "===== JARVIS SERVICE ====="
systemctl --user cat jarvis.service || true
systemctl --user status jarvis.service --no-pager || true

echo "===== JARVIS LOGS ====="
journalctl --user -u jarvis.service -n 120 --no-pager || true
CMD

chmod +x ~/jarvis/collect_jarvis_debug.sh
~/jarvis/collect_jarvis_debug.sh
```

---

## Notes

- `jarvis.service` file location must stay in `~/.config/systemd/user/` (systemd rule).
- But all **Jarvis-specific config/data** in this setup is under `~/jarvis/.config/`.
- Model `small` is strongly recommended for Russian wake word quality; `tiny` is faster but much less stable for short utterances.
