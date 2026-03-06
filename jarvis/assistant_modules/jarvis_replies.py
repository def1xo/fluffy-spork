# jarvis_replies.py
REPLIES = {
    "greeting": [
        "Привет. Чем могу помочь?",
        "Я на связи.",
        "Слушаю команды."
    ],
    "listening": [
        "Слушаю.",
        "Говори."
    ],
    "done": [
        "Выполнено.",
        "Готово.",
        "Сделано."
    ],
    "not_understood": [
        "Не понял команду. Повтори, пожалуйста.",
        "Кажется, я не расслышал."
    ],
    "error": [
        "Что-то пошло не так.",
        "Ошибка при выполнении."
    ]
}

import random
def pick(kind="greeting"):
    return random.choice(REPLIES.get(kind, ["..."]))
