# Jarvis: Arch Linux setup and autostart (project-local config)

## TL;DR

Ты прав: у тебя сейчас **не создано ничего из обязательного**:
- нет `~/jarvis/.config/env`
- нет `~/.config/systemd/user/jarvis.service`

Сделай одной командой:

```bash
cd ~/jarvis
bash scripts/install_autostart.sh
```

После этого проверь:

```bash
systemctl --user status jarvis.service --no-pager
journalctl --user -u jarvis.service -n 80 --no-pager
```

---

## Что и где хранится

- Jarvis env: `~/jarvis/.config/env`  ✅ (внутри проекта)
- systemd unit: `~/.config/systemd/user/jarvis.service`  ✅ (это обязательный путь systemd)

---

## Если хочешь вручную (copy/paste через cat)

```bash
mkdir -p ~/jarvis/.config ~/.config/systemd/user

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
# index или имя: pipewire/pulse/USB/HyperX/...
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
```

---

## Диагностика (что скинуть мне, чтобы дотюнить под твой ПК)

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

## Быстрый debug wake word

```bash
cd ~/jarvis
. .venv/bin/activate
python jarvis_agent_integrated.py --doctor
JARVIS_DEBUG_AUDIO=1 python jarvis_agent_integrated.py
```

Если `AUDIO energy` стабильно ниже `threshold` — снизь `JARVIS_ENERGY_THRESHOLD` до `0.0025` и перезапусти сервис.
