from app.application.seguranca.ports import PasswordHasher
from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import PermissaoNegada, UsuarioNaoEncontrado
from app.domain.usuarios.entities import Papel, Usuario


class RedefinirSenha:
    """Admin define nova senha de outro usuário, sem exigir a senha atual."""

    def __init__(self, uow: UnitOfWork, hasher: PasswordHasher) -> None:
        self._uow = uow
        self._hasher = hasher

    async def executar(self, ator: Usuario, usuario_id: int, nova_senha: str) -> None:
        if ator.papel is not Papel.ADMIN:
            raise PermissaoNegada
        usuario = await self._uow.usuarios.obter_por_id(usuario_id)
        if usuario is None:
            raise UsuarioNaoEncontrado
        usuario.senha_hash = await self._hasher.hash(nova_senha)
        await self._uow.usuarios.atualizar(usuario)
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "redefinir_senha",
            "usuario",
            str(usuario_id),
            {"campos": ["senha"]},
        )
        await self._uow.commit()
