"""Single-admin auth state persisted to auth.json (spec §6).

Stores: an Argon2 password hash, a stable random secret_key (used by
itsdangerous to sign session cookies and stream tokens), and a list of
revocable stream tokens stored only as Argon2 hashes. Raw tokens are
shown to the user once at mint time.
"""
from __future__ import annotations

import json
import secrets
import uuid
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher()


class AuthStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # -- password --
    def has_password(self) -> bool:
        return bool(self._read().get("password_hash"))

    def set_password(self, password: str) -> None:
        data = self._read()
        data["password_hash"] = _ph.hash(password)
        if not data.get("secret_key"):
            data["secret_key"] = secrets.token_urlsafe(32)
        data.setdefault("stream_tokens", [])
        self._write(data)

    def verify_password(self, password: str) -> bool:
        h = self._read().get("password_hash")
        if not h:
            return False
        try:
            return _ph.verify(h, password)
        except VerifyMismatchError:
            return False

    def secret_key(self) -> str:
        data = self._read()
        key = data.get("secret_key")
        if not key:
            key = secrets.token_urlsafe(32)
            data["secret_key"] = key
            self._write(data)
        return key  # type: ignore[no-any-return]

    # -- stream tokens --
    def mint_stream_token(self, label: str) -> tuple[str, str]:
        raw = secrets.token_urlsafe(24)
        token_id = uuid.uuid4().hex[:8]
        data = self._read()
        tokens = data.setdefault("stream_tokens", [])
        tokens.append({"id": token_id, "label": label, "token_hash": _ph.hash(raw)})
        self._write(data)
        return token_id, raw

    def verify_stream_token(self, raw: str) -> bool:
        for t in self._read().get("stream_tokens", []):
            try:
                if _ph.verify(t["token_hash"], raw):
                    return True
            except VerifyMismatchError:
                continue
        return False

    def list_stream_tokens(self) -> list[dict[str, Any]]:
        return [
            {"id": t["id"], "label": t["label"]}
            for t in self._read().get("stream_tokens", [])
        ]

    def revoke_stream_token(self, token_id: str) -> None:
        data = self._read()
        data["stream_tokens"] = [
            t for t in data.get("stream_tokens", []) if t["id"] != token_id
        ]
        self._write(data)
