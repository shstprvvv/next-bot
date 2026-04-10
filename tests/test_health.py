"""Tests for health check and static file serving."""


class TestHealth:
    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "active_bots" in data
        assert "redis_status" in data

    def test_health_lists_bots(self, client):
        r = client.get("/health")
        bots = r.json()["active_bots"]
        assert isinstance(bots, list)


class TestStaticFiles:
    def test_root_redirects_to_landing(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert "/static/index.html" in r.headers.get("location", "")

    def test_static_config_js(self, client):
        r = client.get("/static/js/config.js")
        assert r.status_code == 200
        assert "NEXTBOT_CONFIG" in r.text

    def test_static_landing(self, client):
        r = client.get("/static/index.html")
        assert r.status_code == 200
        assert "Next AI" in r.text

    def test_static_login(self, client):
        r = client.get("/static/login.html")
        assert r.status_code == 200
        assert "NextBot" in r.text

    def test_static_dashboard(self, client):
        r = client.get("/static/dashboard.html")
        assert r.status_code == 200
        assert "chat-form" in r.text
