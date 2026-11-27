from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.auditoria.repository import SqlAlchemyAuditoria
from app.infrastructure.persistence.caixa.repository import SqlAlchemyCaixaRepository
from app.infrastructure.persistence.cardapio.repository import SqlAlchemyCardapioRepository
from app.infrastructure.persistence.comandas.repository import SqlAlchemyComandaRepository
from app.infrastructure.persistence.estoque.repository import (
    SqlAlchemyEstoqueRepository,
    SqlAlchemyFichaTecnicaRepository,
)
from app.infrastructure.persistence.financeiro.repository import SqlAlchemyFinanceiroRepository
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository


class SqlAlchemyUnitOfWork:
    """Todos os repositórios compartilham a mesma sessão (= mesma transação)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self.usuarios = SqlAlchemyUsuarioRepository(session)
        self.cardapio = SqlAlchemyCardapioRepository(session)
        self.comandas = SqlAlchemyComandaRepository(session)
        self.estoque = SqlAlchemyEstoqueRepository(session)
        self.ficha_tecnica = SqlAlchemyFichaTecnicaRepository(session)
        self.caixa = SqlAlchemyCaixaRepository(session)
        self.financeiro = SqlAlchemyFinanceiroRepository(session)
        self.auditoria = SqlAlchemyAuditoria(session)

    async def commit(self) -> None:
        await self._s.commit()

    async def rollback(self) -> None:
        await self._s.rollback()
