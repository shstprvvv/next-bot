"""Tests for chat endpoints."""


class TestChatInit:
    def test_init_known_bot(self, client, auth_headers):
        r = client.post("/api/chat/init", json={
            "bot_id": "next_bot_main",
            "session_id": "sess-1"
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["reply"]

    def test_init_unknown_bot_returns_default_greeting(self, client, auth_headers):
        r = client.post("/api/chat/init", json={
            "bot_id": "unknown_bot_xyz",
            "session_id": "sess-2"
        }, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["reply"]

    def test_init_creator_bot(self, client, auth_headers):
        r = client.post("/api/chat/init", json={
            "bot_id": "creator_bot",
            "session_id": "sess-3"
        }, headers=auth_headers)
        assert r.status_code == 200
        assert "архитектор" in r.json()["reply"].lower() or "бот" in r.json()["reply"].lower()

    def test_init_requires_auth(self, client):
        r = client.post("/api/chat/init", json={
            "bot_id": "next_bot_main",
            "session_id": "sess-4"
        })
        assert r.status_code == 401


class TestChatMessage:
    def test_chat_requires_auth(self, client):
        r = client.post("/api/chat", json={
            "bot_id": "next_bot_main",
            "message": "Привет",
            "session_id": "sess-5"
        })
        assert r.status_code == 401

    def test_chat_unknown_bot_404(self, client, auth_headers):
        r = client.post("/api/chat", json={
            "bot_id": "nonexistent_bot",
            "message": "Привет",
            "session_id": "sess-6"
        }, headers=auth_headers)
        assert r.status_code == 404


class TestValidation:
    def test_empty_message_rejected(self, client, auth_headers):
        r = client.post("/api/chat", json={
            "bot_id": "next_bot_main",
            "message": "",
            "session_id": "sess-7"
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_empty_bot_id_rejected(self, client, auth_headers):
        r = client.post("/api/chat", json={
            "bot_id": "",
            "message": "hello",
            "session_id": "sess-8"
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_empty_session_id_rejected(self, client, auth_headers):
        r = client.post("/api/chat/init", json={
            "bot_id": "next_bot_main",
            "session_id": ""
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_missing_fields_rejected(self, client, auth_headers):
        r = client.post("/api/chat", json={}, headers=auth_headers)
        assert r.status_code == 422
