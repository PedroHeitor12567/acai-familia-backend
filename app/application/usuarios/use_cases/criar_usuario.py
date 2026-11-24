from app.application.seguranca.ports import PasswordHasher
from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import EmailJaCadastrado, PermissaoNegada
from app.domain.usuarios.entities import Papel, Usuario


class CriarUsuario:
    def __init__(self, uow: UnitOfWork, hasher: PasswordHasher) -> None:
        self._uow = uow
        self._hasher = hasher

    def executar(
        self, ator: Usuario | None, nome: str, email: str, senha: str, papel: Papel
    ) -> Usuario:
        """`ator=None` representa o bootstrap do sistema (script do primeiro admin)."""
        if ator is not None and ator.papel is not Papel.ADMIN:
            raise PermissaoNegada
        email = email.lower()
        if self._uow.usuarios.obter_por_email(email) is not None:
            raise EmailJaCadastrado
        usuario = self._uow.usuarios.adicionar(
            Usuario(nome=nome, email=email, senha_hash=self._hasher.hash(senha), papel=papel)
        )
        self._uow.auditoria.registrar(
            ator.id_persistido if ator else None,
            "criar",
            "usuario",
            str(usuario.id),
            {"email": email, "papel": str(papel)},
        )
        self._uow.commit()
        return usuario
