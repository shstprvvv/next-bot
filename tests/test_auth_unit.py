"""Unit tests for auth module (no HTTP, direct function calls)."""

from datetime import timedelta
from app.core.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "MySecret123!"
        hashed = get_password_hash(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password_fails(self):
        hashed = get_password_hash("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_for_same_password(self):
        pw = "same_password"
        h1 = get_password_hash(pw)
        h2 = get_password_hash(pw)
        assert h1 != h2  # bcrypt salt makes them different


class TestJWTTokens:
    def test_create_and_decode(self):
        token = create_access_token(data={"sub": "user@test.com"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user@test.com"
        assert "exp" in payload

    def test_custom_expiry(self):
        token = create_access_token(
            data={"sub": "user@test.com"},
            expires_delta=timedelta(hours=1)
        )
        payload = decode_access_token(token)
        assert payload is not None

    def test_invalid_token_returns_none(self):
        assert decode_access_token("not.a.real.token") is None
        assert decode_access_token("") is None

    def test_tampered_token_returns_none(self):
        token = create_access_token(data={"sub": "user@test.com"})
        tampered = token[:-5] + "XXXXX"
        assert decode_access_token(tampered) is None
