from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.auditoria.repository import SqlAlchemyAuditoria
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository


class SqlAlchemyUnitOfWork:
    """Todos os repositórios compartilham a mesma sessão (= mesma transação)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session
        self.usuarios = SqlAlchemyUsuarioRepository(session)
        self.auditoria = SqlAlchemyAuditoria(session)

    async def commit(self) -> None:
        await self._s.commit()

    async def rollback(self) -> None:
        await self._s.rollback()
