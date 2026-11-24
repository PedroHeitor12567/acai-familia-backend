from typing import Any

from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import (
    EmailJaCadastrado,
    OperacaoNaoPermitida,
    PermissaoNegada,
    UsuarioNaoEncontrado,
)
from app.domain.usuarios.entities import Papel, Usuario


class AtualizarUsuario:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def executar(
        self,
        ator: Usuario,
        usuario_id: int,
        nome: str | None = None,
        email: str | None = None,
        papel: Papel | None = None,
    ) -> Usuario:
        if ator.papel is not Papel.ADMIN:
            raise PermissaoNegada
        usuario = self._uow.usuarios.obter_por_id(usuario_id)
        if usuario is None:
            raise UsuarioNaoEncontrado

        if papel is not None and usuario.papel is Papel.ADMIN and papel is not Papel.ADMIN:
            if usuario.id == ator.id:
                raise OperacaoNaoPermitida("auto_rebaixamento")
            if usuario.ativo and self._uow.usuarios.contar_admins_ativos() <= 1:
                raise OperacaoNaoPermitida("ultimo_admin")

        email = email.lower() if email is not None else None
        if (
            email is not None
            and email != usuario.email
            and self._uow.usuarios.obter_por_email(email) is not None
        ):
            raise EmailJaCadastrado

        diff: dict[str, Any] = {}
        for campo, novo in (("nome", nome), ("email", email), ("papel", papel)):
            antes = getattr(usuario, campo)
            if novo is not None and novo != antes:
                diff[campo] = {"antes": str(antes), "depois": str(novo)}
                setattr(usuario, campo, novo)
        if not diff:
            return usuario

        atualizado = self._uow.usuarios.atualizar(usuario)
        self._uow.auditoria.registrar(
            ator.id_persistido, "atualizar", "usuario", str(usuario_id), diff
        )
        self._uow.commit()
        return atualizado
