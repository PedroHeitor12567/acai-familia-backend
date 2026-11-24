from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import PermissaoNegada, UsuarioNaoEncontrado
from app.domain.usuarios.entities import Papel, Usuario


class ObterUsuario:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, usuario_id: int) -> Usuario:
        if ator.papel not in (Papel.ADMIN, Papel.GERENTE):
            raise PermissaoNegada
        usuario = await self._uow.usuarios.obter_por_id(usuario_id)
        if usuario is None:
            raise UsuarioNaoEncontrado
        return usuario
