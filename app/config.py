import os


def load_config():
    # В Docker-окружении load_dotenv() не нужен, 
    # переменные передаются напрямую через docker run --env-file
    return {
        "TELETHON_API_ID": os.getenv("TELETHON_API_ID"),
        "TELETHON_API_HASH": os.getenv("TELETHON_API_HASH"),
        "TELETHON_PHONE": os.getenv("TELETHON_PHONE"),
        "TELEGRAM_PASSWORD": os.getenv("TELEGRAM_PASSWORD"), # Добавляем загрузку пароля
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "OPENAI_API_BASE": os.getenv("OPENAI_API_BASE"),
        "WB_API_KEY": os.getenv("WB_API_KEY"),
        "WB_CHAT_POLLING_INTERVAL_SECONDS": int(os.getenv("WB_CHAT_POLLING_INTERVAL_SECONDS", 300)),
        "WB_CHECK_INTERVAL_SECONDS": int(os.getenv("WB_CHECK_INTERVAL_SECONDS", 300)),
        "WB_CHAT_DEBUG": os.getenv("WB_CHAT_DEBUG", "false").lower() in ('true', '1', 't'),
        "TELEGRAM_MESSAGE_DELAY_SECONDS": int(os.getenv("TELEGRAM_MESSAGE_DELAY_SECONDS", 2)),
    }


