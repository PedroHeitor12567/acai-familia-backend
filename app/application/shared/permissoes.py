from app.domain.exceptions import PermissaoNegada
from app.domain.usuarios.entities import Papel, Usuario


def exigir_gestor(ator: Usuario) -> None:
    """Escrita de cardápio e estoque: só admin e gerente. Atendente e caixa apenas leem."""
    if ator.papel not in (Papel.ADMIN, Papel.GERENTE):
        raise PermissaoNegada
