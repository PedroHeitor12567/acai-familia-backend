from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.auditoria.models import AuditLogModel


class SqlAlchemyAuditoria:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def registrar(
        self,
        usuario_id: int | None,
        acao: str,
        entidade: str,
        entidade_id: str | None = None,
        detalhes: dict[str, Any] | None = None,
    ) -> None:
        self._s.add(
            AuditLogModel(
                usuario_id=usuario_id,
                acao=acao,
                entidade=entidade,
                entidade_id=entidade_id,
                detalhes=detalhes,
            )
        )
