from dataclasses import dataclass
from typing import Protocol

from app.domain.usuarios.entities import Papel


@dataclass(frozen=True)
class TokenClaims:
    usuario_id: int
    tipo: str
    papel: Papel | None = None


class PasswordHasher(Protocol):
    def hash(self, senha: str) -> str: ...
    def verify(self, senha_hash: str, senha: str) -> bool: ...
    def verify_dummy(self) -> None: ...


class TokenService(Protocol):
    def criar_access(self, usuario_id: int, papel: Papel) -> str: ...
    def criar_refresh(self, usuario_id: int) -> str: ...
    def decodificar(self, token: str, tipo: str) -> TokenClaims:
        """Levanta `TokenInvalido` se o token for inválido, expirado ou de outro tipo."""
        ...


class LoginThrottle(Protocol):
    def verificar(self, chave: str) -> None:
        """Levanta `MuitasTentativas` se a chave estiver bloqueada."""
        ...

    def registrar_falha(self, chave: str) -> None: ...
    def zerar(self, chave: str) -> None: ...
