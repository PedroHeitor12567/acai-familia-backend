from dataclasses import dataclass
from decimal import Decimal

from app.domain.exceptions import ValorInvalido
from app.domain.shared import ComId, decimal_valido


def validar_preco(preco: Decimal) -> Decimal:
    """Dinheiro é sempre `Decimal` >= 0 com no máximo 2 casas; nunca `float`."""
    if not isinstance(preco, Decimal) or not decimal_valido(preco, 2) or preco < 0:
        raise ValorInvalido("preco_invalido")
    return preco


@dataclass
class Categoria(ComId):
    nome: str
    ativo: bool = True
    id: int | None = None


@dataclass
class Tamanho(ComId):
    """Variação de venda (300 ml, 500 ml...). Produtos sem variação usam um tamanho "Único"."""

    nome: str
    ativo: bool = True
    id: int | None = None


@dataclass
class Produto(ComId):
    nome: str
    categoria_id: int
    ativo: bool = True
    id: int | None = None


@dataclass(frozen=True)
class ProdutoTamanho:
    produto_id: int
    tamanho_id: int
    preco: Decimal

    def __post_init__(self) -> None:
        validar_preco(self.preco)


@dataclass
class Adicional(ComId):
    nome: str
    preco: Decimal
    ativo: bool = True
    id: int | None = None

    def __post_init__(self) -> None:
        validar_preco(self.preco)
