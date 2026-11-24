from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import OperacaoNaoPermitida, PermissaoNegada, UsuarioNaoEncontrado
from app.domain.usuarios.entities import Papel, Usuario


class AlterarStatusUsuario:
    """Desativa ou reativa um usuário. O `ativo` é checado a cada requisição, então
    desativar corta o acesso na hora (access e refresh)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, usuario_id: int, ativo: bool) -> Usuario:
        if ator.papel is not Papel.ADMIN:
            raise PermissaoNegada
        usuario = await self._uow.usuarios.obter_por_id(usuario_id)
        if usuario is None:
            raise UsuarioNaoEncontrado
        if usuario.ativo == ativo:
            return usuario

        if not ativo:
            if usuario.id == ator.id:
                raise OperacaoNaoPermitida("auto_desativacao")
            if (
                usuario.papel is Papel.ADMIN
                and await self._uow.usuarios.contar_admins_ativos() <= 1
            ):
                raise OperacaoNaoPermitida("ultimo_admin")

        usuario.ativo = ativo
        atualizado = await self._uow.usuarios.atualizar(usuario)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "reativar" if ativo else "desativar",
            "usuario",
            str(usuario_id),
            {"ativo": {"antes": not ativo, "depois": ativo}},
        )
        await self._uow.commit()
        return atualizado
