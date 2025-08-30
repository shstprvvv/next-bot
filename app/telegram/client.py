from telethon import TelegramClient

def create_telegram_client(session_name: str, api_id: str, api_hash: str) -> TelegramClient:
    return TelegramClient(session_name, api_id, api_hash)


