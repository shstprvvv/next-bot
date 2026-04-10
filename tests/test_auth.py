"""Tests for authentication endpoints and JWT logic."""


class TestRegister:
    def test_register_success(self, client):
        r = client.post("/api/auth/register", json={
            "email": "newuser@example.com",
            "password": "securepass123"
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client):
        payload = {"email": "dup@example.com", "password": "securepass123"}
        client.post("/api/auth/register", json=payload)
        r = client.post("/api/auth/register", json=payload)
        assert r.status_code == 400
        assert "already registered" in r.json()["detail"]

    def test_register_invalid_email(self, client):
        r = client.post("/api/auth/register", json={
            "email": "not-an-email",
            "password": "securepass123"
        })
        assert r.status_code == 422

    def test_register_short_password(self, client):
        r = client.post("/api/auth/register", json={
            "email": "short@example.com",
            "password": "abc"
        })
        assert r.status_code == 422

    def test_register_empty_body(self, client):
        r = client.post("/api/auth/register", json={})
        assert r.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        client.post("/api/auth/register", json={
            "email": "login@example.com",
            "password": "securepass123"
        })
        r = client.post("/api/auth/login", json={
            "email": "login@example.com",
            "password": "securepass123"
        })
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self, client):
        client.post("/api/auth/register", json={
            "email": "wrongpw@example.com",
            "password": "securepass123"
        })
        r = client.post("/api/auth/login", json={
            "email": "wrongpw@example.com",
            "password": "wrongpassword"
        })
        assert r.status_code == 401

    def test_login_nonexistent_user(self, client):
        r = client.post("/api/auth/login", json={
            "email": "nobody@example.com",
            "password": "securepass123"
        })
        assert r.status_code == 401


class TestJWT:
    def test_valid_token_accepted(self, client, auth_headers):
        r = client.post("/api/chat/init", json={
            "bot_id": "next_bot_main",
            "session_id": "test-session"
        }, headers=auth_headers)
        assert r.status_code == 200

    def test_missing_token_rejected(self, client):
        r = client.post("/api/chat/init", json={
            "bot_id": "next_bot_main",
            "session_id": "test-session"
        })
        assert r.status_code == 401

    def test_invalid_token_rejected(self, client):
        r = client.post("/api/chat/init", json={
            "bot_id": "next_bot_main",
            "session_id": "test-session"
        }, headers={"Authorization": "Bearer invalid.token.value"})
        assert r.status_code == 401
