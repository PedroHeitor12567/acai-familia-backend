import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.application.seguranca.ports import TokenClaims
from app.config import Settings
from app.domain.exceptions import TokenInvalido
from app.domain.usuarios.entities import Papel

_ALG = "HS256"


class JwtService:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _encode(self, sub: int, tipo: str, ttl: timedelta, extra: dict[str, Any]) -> str:
        agora = datetime.now(UTC)
        payload = {
            "sub": str(sub),
            "type": tipo,
            "iat": agora,
            "exp": agora + ttl,
            "jti": uuid.uuid4().hex,
            **extra,
        }
        return jwt.encode(payload, self._s.secret_key, algorithm=_ALG)

    def criar_access(self, usuario_id: int, papel: Papel) -> str:
        ttl = timedelta(minutes=self._s.access_token_expire_minutes)
        return self._encode(usuario_id, "access", ttl, {"role": str(papel)})

    def criar_refresh(self, usuario_id: int) -> str:
        return self._encode(
            usuario_id, "refresh", timedelta(days=self._s.refresh_token_expire_days), {}
        )

    def decodificar(self, token: str, tipo: str) -> TokenClaims:
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._s.secret_key,
                algorithms=[_ALG],
                options={"require": ["exp", "sub", "type"]},
            )
            if claims["type"] != tipo:
                raise TokenInvalido
            papel = Papel(claims["role"]) if "role" in claims else None
            return TokenClaims(usuario_id=int(claims["sub"]), tipo=claims["type"], papel=papel)
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise TokenInvalido from exc
