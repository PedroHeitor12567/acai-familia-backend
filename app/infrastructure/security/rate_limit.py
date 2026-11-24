import time
from collections import defaultdict

from app.domain.exceptions import MuitasTentativas


class InMemoryLoginThrottle:
    """Limitador em memória (1 instância). Em produção com várias réplicas, usar Redis."""

    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._fails: dict[str, list[float]] = defaultdict(list)

    def _prune(self, chave: str) -> None:
        limite = time.monotonic() - self._window
        self._fails[chave] = [t for t in self._fails[chave] if t > limite]

    def verificar(self, chave: str) -> None:
        self._prune(chave)
        if len(self._fails[chave]) >= self._max:
            retry = int(self._window - (time.monotonic() - self._fails[chave][0])) + 1
            raise MuitasTentativas(retry)

    def registrar_falha(self, chave: str) -> None:
        self._fails[chave].append(time.monotonic())

    def zerar(self, chave: str) -> None:
        self._fails.pop(chave, None)

    def zerar_tudo(self) -> None:
        self._fails.clear()
