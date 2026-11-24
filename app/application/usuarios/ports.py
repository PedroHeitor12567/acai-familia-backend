from dataclasses import dataclass
from typing import Protocol

from app.domain.usuarios.entities import Papel, Usuario


@dataclass(frozen=True)
class FiltrosUsuario:
    ativo: bool | None = None
    papel: Papel | None = None
    q: str | None = None  # busca parcial em nome ou e-mail


class UsuarioRepository(Protocol):
    async def obter_por_email(self, email: str) -> Usuario | None: ...
    async def obter_por_id(self, usuario_id: int) -> Usuario | None: ...
    async def adicionar(self, usuario: Usuario) -> Usuario: ...
    async def listar(
        self, filtros: FiltrosUsuario, limit: int, offset: int
    ) -> tuple[list[Usuario], int]:
        """Página ordenada por id e o total de registros que batem com os filtros."""
        ...

    async def atualizar(self, usuario: Usuario) -> Usuario: ...
    async def contar_admins_ativos(self) -> int: ...
