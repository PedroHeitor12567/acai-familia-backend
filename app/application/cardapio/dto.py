from dataclasses import dataclass

from app.domain.cardapio.entities import Produto, ProdutoTamanho


@dataclass(frozen=True)
class ProdutoComPrecos:
    produto: Produto
    precos: list[ProdutoTamanho]
