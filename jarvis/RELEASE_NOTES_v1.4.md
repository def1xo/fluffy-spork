# Release v1.4

Сделал:
- Добавлена опциональная диаризация (pyannote) и проверка доминирующего говорящего.
- sr_pipeline сохраняет utterances в .wav (для анализа) и безопасно игнорирует чужие голоса.
- Улучшен parsing команд (числа, пути, goto в code).
- tts: SSML-lite, неблокирующее воспроизведение, пресеты.
- jarvis_agent_integrated.py: логирование в logs/jarvis.log, поддержка PRIMARY_SPEAKER через env.

Осталось:
- Установить/проверить pyannote с токеном, адаптировать PRIMARY_SPEAKER и thresholds.
- Подобрать реальные TTS-модели и пресеты.
- Отладить макросы code-oss на твоём окружении.
