import asyncio

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2Hasher:
    """Argon2 é CPU-bound e propositalmente lento: roda em thread para não travar o event loop."""

    def __init__(self) -> None:
        self._ph = _Argon2()
        self._dummy = self._ph.hash("senha-dummy-para-tempo-constante")

    def _verify(self, senha_hash: str, senha: str) -> bool:
        try:
            return self._ph.verify(senha_hash, senha)
        except (VerificationError, InvalidHashError):
            return False

    async def hash(self, senha: str) -> str:
        return await asyncio.to_thread(self._ph.hash, senha)

    async def verify(self, senha_hash: str, senha: str) -> bool:
        return await asyncio.to_thread(self._verify, senha_hash, senha)

    async def verify_dummy(self) -> None:
        await self.verify(self._dummy, "outra-senha")
