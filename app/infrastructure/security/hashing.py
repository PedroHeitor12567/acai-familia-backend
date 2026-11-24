from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2Hasher:
    def __init__(self) -> None:
        self._ph = _Argon2()
        self._dummy = self._ph.hash("senha-dummy-para-tempo-constante")

    def hash(self, senha: str) -> str:
        return self._ph.hash(senha)

    def verify(self, senha_hash: str, senha: str) -> bool:
        try:
            return self._ph.verify(senha_hash, senha)
        except (VerificationError, InvalidHashError):
            return False

    def verify_dummy(self) -> None:
        self.verify(self._dummy, "outra-senha")
