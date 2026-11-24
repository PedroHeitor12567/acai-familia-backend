from sqlalchemy.orm import Session

from app.infrastructure.persistence.auditoria.repository import SqlAlchemyAuditoria
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository


class SqlAlchemyUnitOfWork:
    """Todos os repositórios compartilham a mesma sessão (= mesma transação)."""

    def __init__(self, session: Session) -> None:
        self._s = session
        self.usuarios = SqlAlchemyUsuarioRepository(session)
        self.auditoria = SqlAlchemyAuditoria(session)

    def commit(self) -> None:
        self._s.commit()

    def rollback(self) -> None:
        self._s.rollback()
