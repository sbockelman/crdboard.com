from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer


class AccessTokenCodec:
    def __init__(self, secret: str) -> None:
        self._serializer = URLSafeSerializer(secret_key=secret, salt="table-access")

    def encode(self, payload: dict[str, Any], ttl_seconds: int = 3600) -> str:
        claims = dict(payload)
        claims["expires_at"] = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        return self._serializer.dumps(claims)

    def decode(self, token: str) -> dict[str, Any]:
        try:
            claims = self._serializer.loads(token)
        except BadSignature as exc:
            raise ValueError("Invalid token") from exc
        expires_at = datetime.fromisoformat(claims["expires_at"])
        if datetime.now(UTC) > expires_at:
            raise ValueError("Token expired")
        return claims
