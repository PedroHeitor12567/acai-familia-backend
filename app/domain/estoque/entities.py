from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.exceptions import ValorInvalido
from app.domain.shared import ComId, decimal_valido

CASAS_QUANTIDADE = 3


class UnidadeMedida(StrEnum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    UN = "un"


class TipoMovimentacao(StrEnum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    AJUSTE = "ajuste"


def validar_quantidade(quantidade: Decimal, *, permite_zero: bool = False) -> Decimal:
    """Quantidade `Decimal` finita, com até 3 casas, > 0 (>= 0 só no ajuste de contagem)."""
    if not isinstance(quantidade, Decimal) or not decimal_valido(quantidade, CASAS_QUANTIDADE):
        raise ValorInvalido("quantidade_invalida")
    if quantidade < 0 or (quantidade == 0 and not permite_zero):
        raise ValorInvalido("quantidade_invalida")
    return quantidade


@dataclass
class Insumo(ComId):
    nome: str
    unidade: UnidadeMedida
    estoque_minimo: Decimal = Decimal("0")
    estoque_atual: Decimal = Decimal("0")
    ativo: bool = True
    id: int | None = None

    def __post_init__(self) -> None:
        validar_quantidade(self.estoque_minimo, permite_zero=True)

    @property
    def abaixo_do_minimo(self) -> bool:
        return self.estoque_atual <= self.estoque_minimo


@dataclass(frozen=True)
class MovimentacaoEstoque(ComId):
    """Registro imutável do histórico. `quantidade` é sempre positiva; no ajuste é o módulo da
    diferença (o sentido sai de `saldo_antes` x `saldo_apos`)."""

    insumo_id: int
    tipo: TipoMovimentacao
    quantidade: Decimal
    saldo_antes: Decimal
    saldo_apos: Decimal
    usuario_id: int | None
    motivo: str | None = None
    criado_em: datetime | None = None
    id: int | None = None


@dataclass(frozen=True)
class ItemFichaTecnica:
    """Quanto de um insumo é consumido por unidade vendida."""

    insumo_id: int
    quantidade: Decimal

    def __post_init__(self) -> None:
        validar_quantidade(self.quantidade)
