from app.domain.exceptions import PermissaoNegada
from app.domain.usuarios.entities import Papel, Usuario


def exigir_gestor(ator: Usuario) -> None:
    """Escrita de cardápio e estoque: só admin e gerente. Atendente e caixa apenas leem."""
    if ator.papel not in (Papel.ADMIN, Papel.GERENTE):
        raise PermissaoNegada


def exigir_operador_comanda(ator: Usuario) -> None:
    """Abrir, lançar, alterar, remover e consultar comandas: todos os papéis operacionais."""
    if ator.papel not in (Papel.ADMIN, Papel.GERENTE, Papel.ATENDENTE, Papel.CAIXA):
        raise PermissaoNegada


def exigir_fechamento_comanda(ator: Usuario) -> None:
    """Fechar e cancelar: admin, gerente e caixa. O atendente lança, mas não fecha (o
    fechamento é o momento do pagamento)."""
    if ator.papel not in (Papel.ADMIN, Papel.GERENTE, Papel.CAIXA):
        raise PermissaoNegada
