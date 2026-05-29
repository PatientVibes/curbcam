from pathlib import Path

from curbcam.web.auth import AuthStore


def test_no_password_until_set(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    assert store.has_password() is False


def test_set_and_verify_password(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    store.set_password("hunter2")
    assert store.has_password() is True
    assert store.verify_password("hunter2") is True
    assert store.verify_password("wrong") is False


def test_password_is_not_stored_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    AuthStore(path).set_password("hunter2")
    assert "hunter2" not in path.read_text(encoding="utf-8")


def test_secret_key_is_stable_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    s1 = AuthStore(path)
    s1.set_password("x")
    key1 = s1.secret_key()
    key2 = AuthStore(path).secret_key()
    assert key1 == key2 and len(key1) >= 32


def test_mint_verify_and_revoke_stream_token(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.json")
    store.set_password("x")
    token_id, raw = store.mint_stream_token("Home Assistant")
    assert store.verify_stream_token(raw) is True
    assert any(t["label"] == "Home Assistant" for t in store.list_stream_tokens())
    store.revoke_stream_token(token_id)
    assert store.verify_stream_token(raw) is False
