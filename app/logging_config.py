import logging


def setup_logging():
    # Настройка основного логгера
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(filename)s] %(message)s',
        handlers=[
            logging.StreamHandler()  # Вывод в консоль
        ]
    )

    # Настройка логгера для неотвеченных вопросов
    unanswered_logger = logging.getLogger('unanswered')
    unanswered_logger.setLevel(logging.INFO)
    unanswered_handler = logging.FileHandler('unanswered_questions.log', mode='a', encoding='utf-8')
    unanswered_formatter = logging.Formatter('%(asctime)s - %(message)s')
    unanswered_handler.setFormatter(unanswered_formatter)
    unanswered_logger.addHandler(unanswered_handler)
    unanswered_logger.propagate = False  # Не передавать сообщения в основной логгер

    # Уменьшаем "шум" от сторонних библиотек
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telethon').setLevel(logging.WARNING)


