from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.usuarios.models import UsuarioModel


def _to_entity(m: UsuarioModel) -> Usuario:
    return Usuario(
        id=m.id,
        nome=m.nome,
        email=m.email,
        senha_hash=m.senha_hash,
        papel=Papel(m.papel),
        ativo=m.ativo,
    )


class SqlAlchemyUsuarioRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def obter_por_email(self, email: str) -> Usuario | None:
        m = self._s.scalar(select(UsuarioModel).where(UsuarioModel.email == email))
        return _to_entity(m) if m else None

    def obter_por_id(self, usuario_id: int) -> Usuario | None:
        m = self._s.get(UsuarioModel, usuario_id)
        return _to_entity(m) if m else None

    def adicionar(self, usuario: Usuario) -> Usuario:
        m = UsuarioModel(
            nome=usuario.nome,
            email=usuario.email,
            senha_hash=usuario.senha_hash,
            papel=str(usuario.papel),
            ativo=usuario.ativo,
        )
        self._s.add(m)
        self._s.flush()
        return _to_entity(m)
