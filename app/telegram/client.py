from telethon import TelegramClient

def create_telegram_client(session_name: str, api_id: str, api_hash: str, bot_token: str) -> TelegramClient:
    """
    Создает и настраивает клиент Telegram.
    Для аутентификации бота, bot_token будет использован в методе .start().
    """
    return TelegramClient(session_name, api_id, api_hash)


