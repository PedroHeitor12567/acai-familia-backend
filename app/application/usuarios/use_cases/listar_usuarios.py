from app.application.unit_of_work import UnitOfWork
from app.application.usuarios.ports import FiltrosUsuario
from app.domain.exceptions import PermissaoNegada
from app.domain.usuarios.entities import Papel, Usuario


class ListarUsuarios:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def executar(
        self, ator: Usuario, filtros: FiltrosUsuario, limit: int, offset: int
    ) -> tuple[list[Usuario], int]:
        if ator.papel not in (Papel.ADMIN, Papel.GERENTE):
            raise PermissaoNegada
        return self._uow.usuarios.listar(filtros, limit, offset)
