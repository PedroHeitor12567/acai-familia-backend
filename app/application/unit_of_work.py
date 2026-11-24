from typing import Protocol

from app.application.shared.ports import Auditoria
from app.application.usuarios.ports import UsuarioRepository


class UnitOfWork(Protocol):
    """Uma transação. Todos os repositórios expostos compartilham a mesma sessão,
    então `commit()` confirma (ou o descarte desfaz) tudo de uma vez.

    Novos módulos (comandas, caixa, financeiro...) entram aqui como atributos, e é isso
    que permite ao fechamento de comanda alterar vários módulos numa única transação.
    """

    @property
    def usuarios(self) -> UsuarioRepository: ...

    @property
    def auditoria(self) -> Auditoria: ...

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
