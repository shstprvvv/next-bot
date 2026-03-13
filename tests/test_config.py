import os
import json
import unittest
from unittest.mock import patch
from app.config import load_config

class TestConfigMultiTenancy(unittest.TestCase):
    
    @patch.dict(os.environ, {
        "WB_API_KEY": "base_wb_key",
        "OZON_CLIENT_ID": "base_oz_id",
        "OZON_API_KEY": "base_oz_key",
        "TELETHON_API_ID": "123",
        "TELETHON_API_HASH": "hash"
    }, clear=True)
    def test_load_config_single_client(self):
        """Тест загрузки конфигурации только с базовым клиентом."""
        config = load_config()
        
        self.assertIn("CLIENTS", config)
        clients = config["CLIENTS"]
        
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["id"], "next")
        self.assertEqual(clients[0]["name"], "NEXT")
        self.assertEqual(clients[0]["wb_api_key"], "base_wb_key")
        self.assertEqual(clients[0]["telegram_enabled"], True)
        self.assertEqual(clients[0]["qdrant_collection"], "smart_bot_knowledge")

    @patch.dict(os.environ, {
        "WB_API_KEY": "base_wb_key",
        "EXTRA_CLIENTS_JSON": json.dumps([
            {
                "id": "client_2",
                "name": "Second Store",
                "wb_api_key": "wb_key_2",
                "qdrant_collection": "kb_client_2"
            },
            {
                "id": "client_3",
                "name": "Third Store",
                "ozon_client_id": "oz_id_3",
                "ozon_api_key": "oz_key_3"
            }
        ])
    }, clear=True)
    def test_load_config_multiple_clients(self):
        """Тест загрузки базового клиента + дополнительных из JSON."""
        config = load_config()
        clients = config["CLIENTS"]
        
        # Должно быть 3 клиента (базовый NEXT + 2 дополнительных)
        self.assertEqual(len(clients), 3)
        
        # Проверяем базового
        self.assertEqual(clients[0]["id"], "next")
        
        # Проверяем второго
        self.assertEqual(clients[1]["id"], "client_2")
        self.assertEqual(clients[1]["name"], "Second Store")
        self.assertEqual(clients[1]["wb_api_key"], "wb_key_2")
        self.assertEqual(clients[1]["qdrant_collection"], "kb_client_2")
        
        # Проверяем третьего
        self.assertEqual(clients[2]["id"], "client_3")
        self.assertEqual(clients[2]["ozon_client_id"], "oz_id_3")

    @patch.dict(os.environ, {
        "WB_API_KEY": "base",
        "EXTRA_CLIENTS_JSON": "invalid_json_format_123"
    }, clear=True)
    def test_invalid_json(self):
        """Тест: некорректный JSON не ломает загрузку (остается базовый клиент)."""
        config = load_config()
        clients = config["CLIENTS"]
        
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["id"], "next")

if __name__ == '__main__':
    unittest.main()
