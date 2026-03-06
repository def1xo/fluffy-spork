# Release v1.2 — Full integration stubs for VAD/ASR/TTS/DIARIZATION

Сделано (v1.2):
- Интеграция модулей в единый скрипт jarvis_agent_integrated.py (v1.2).
- sr_pipeline.py: добавлена попытка загрузки silero-vad и faster-whisper (graceful fallback).
- tts.py: поддержка Coqui TTS, сохранение и проигрывание wav, fallback на печать.
- command_handler.py: расширен список команд для управления рабочими столами, code-oss, git, docker, сервисы и др.
- Добавлена поддержка опциональной диаризации через pyannote (если установлена) — placeholder.

Осталось (план):
- Прогнать реальные тесты на машине пользователя: проверить загрузку silero-vad, faster-whisper и coqui-tts.
- Подобрать и включить 2–3 голоса Coqui; добавить SSML реплики Джарвиса.
- Настроить pyannote pipeline с примером использования на аудио.
- Расширить command_handler и привязать макросы для code-oss.
