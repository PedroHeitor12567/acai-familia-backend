from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.application.cardapio.dto import ProdutoComPrecos
from app.domain.cardapio.entities import Adicional, Categoria, Tamanho
from app.interfaces.http.schemas.base import DinheiroOut, EntradaEstrita

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
NomeCurto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
# Dinheiro: Decimal (nunca float), >= 0, 2 casas, cabe em Numeric(12,2)
Preco = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class CategoriaIn(EntradaEstrita):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class CategoriaUpdateIn(EntradaEstrita):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]


class CategoriaOut(BaseModel):
    id: int
    nome: str
    ativo: bool

    @classmethod
    def de_entidade(cls, c: Categoria) -> Self:
        return cls(id=c.id_persistido, nome=c.nome, ativo=c.ativo)


class PaginaCategoriasOut(BaseModel):
    itens: list[CategoriaOut]
    total: int
    limit: int
    offset: int


class TamanhoIn(EntradaEstrita):
    nome: NomeCurto


class TamanhoOut(BaseModel):
    id: int
    nome: str
    ativo: bool

    @classmethod
    def de_entidade(cls, t: Tamanho) -> Self:
        return cls(id=t.id_persistido, nome=t.nome, ativo=t.ativo)


class PaginaTamanhosOut(BaseModel):
    itens: list[TamanhoOut]
    total: int
    limit: int
    offset: int


class AdicionalCreateIn(EntradaEstrita):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    preco: Preco


class AdicionalUpdateIn(EntradaEstrita):
    nome: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)
    ] = None
    preco: Preco | None = None

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if self.nome is None and self.preco is None:
            raise ValueError("Informe ao menos um campo: nome ou preco")
        return self


class AdicionalOut(BaseModel):
    id: int
    nome: str
    preco: DinheiroOut
    ativo: bool

    @classmethod
    def de_entidade(cls, a: Adicional) -> Self:
        return cls(id=a.id_persistido, nome=a.nome, preco=a.preco, ativo=a.ativo)


class PaginaAdicionaisOut(BaseModel):
    itens: list[AdicionalOut]
    total: int
    limit: int
    offset: int


class ProdutoCreateIn(EntradaEstrita):
    nome: Nome
    categoria_id: int


class ProdutoUpdateIn(EntradaEstrita):
    nome: Nome | None = None
    categoria_id: int | None = None

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if self.nome is None and self.categoria_id is None:
            raise ValueError("Informe ao menos um campo: nome ou categoria_id")
        return self


class PrecoIn(EntradaEstrita):
    preco: Preco


class PrecoTamanhoOut(BaseModel):
    tamanho_id: int
    preco: DinheiroOut


class ProdutoOut(BaseModel):
    id: int
    nome: str
    categoria_id: int
    ativo: bool
    precos: list[PrecoTamanhoOut]

    @classmethod
    def de_dto(cls, p: ProdutoComPrecos) -> Self:
        return cls(
            id=p.produto.id_persistido,
            nome=p.produto.nome,
            categoria_id=p.produto.categoria_id,
            ativo=p.produto.ativo,
            precos=[PrecoTamanhoOut(tamanho_id=x.tamanho_id, preco=x.preco) for x in p.precos],
        )


class PaginaProdutosOut(BaseModel):
    itens: list[ProdutoOut]
    total: int
    limit: int
    offset: int
