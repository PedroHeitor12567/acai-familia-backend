from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.usuarios.ports import FiltrosUsuario
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.usuarios.models import UsuarioModel


def _escapar_like(texto: str) -> str:
    """Neutraliza os curingas do LIKE para que `%` e `_` digitados sejam literais."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def obter_por_email(self, email: str) -> Usuario | None:
        m = await self._s.scalar(select(UsuarioModel).where(UsuarioModel.email == email))
        return _to_entity(m) if m else None

    async def obter_por_id(self, usuario_id: int) -> Usuario | None:
        m = await self._s.get(UsuarioModel, usuario_id)
        return _to_entity(m) if m else None

    async def adicionar(self, usuario: Usuario) -> Usuario:
        m = UsuarioModel(
            nome=usuario.nome,
            email=usuario.email,
            senha_hash=usuario.senha_hash,
            papel=str(usuario.papel),
            ativo=usuario.ativo,
        )
        self._s.add(m)
        await self._s.flush()
        return _to_entity(m)

    async def listar(
        self, filtros: FiltrosUsuario, limit: int, offset: int
    ) -> tuple[list[Usuario], int]:
        condicoes: list[ColumnElement[bool]] = []
        if filtros.ativo is not None:
            condicoes.append(UsuarioModel.ativo.is_(filtros.ativo))
        if filtros.papel is not None:
            condicoes.append(UsuarioModel.papel == str(filtros.papel))
        if filtros.q:
            padrao = f"%{_escapar_like(filtros.q)}%"
            condicoes.append(
                or_(
                    UsuarioModel.nome.ilike(padrao, escape="\\"),
                    UsuarioModel.email.ilike(padrao, escape="\\"),
                )
            )
        total = await self._s.scalar(
            select(func.count()).select_from(UsuarioModel).where(*condicoes)
        )
        resultado = await self._s.scalars(
            select(UsuarioModel)
            .where(*condicoes)
            .order_by(UsuarioModel.id)
            .limit(limit)
            .offset(offset)
        )
        return [_to_entity(m) for m in resultado.all()], total or 0

    async def atualizar(self, usuario: Usuario) -> Usuario:
        m = await self._s.get(UsuarioModel, usuario.id_persistido)
        if m is None:
            raise ValueError("Usuário não existe")
        m.nome = usuario.nome
        m.email = usuario.email
        m.senha_hash = usuario.senha_hash
        m.papel = str(usuario.papel)
        m.ativo = usuario.ativo
        await self._s.flush()
        return _to_entity(m)

    async def contar_admins_ativos(self) -> int:
        total = await self._s.scalar(
            select(func.count())
            .select_from(UsuarioModel)
            .where(UsuarioModel.papel == str(Papel.ADMIN), UsuarioModel.ativo.is_(True))
        )
        return total or 0
