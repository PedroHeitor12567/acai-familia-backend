from typing import Any, Protocol


class Auditoria(Protocol):
    """Registro de ações sensíveis (quem fez o quê, quando)."""

    def registrar(
        self,
        usuario_id: int | None,
        acao: str,
        entidade: str,
        entidade_id: str | None = None,
        detalhes: dict[str, Any] | None = None,
    ) -> None: ...
