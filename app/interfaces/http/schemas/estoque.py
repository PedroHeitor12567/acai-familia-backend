from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.domain.estoque.entities import (
    Insumo,
    ItemFichaTecnica,
    MovimentacaoEstoque,
    TipoMovimentacao,
    UnidadeMedida,
)
from app.interfaces.http.schemas.base import EntradaEstrita, QuantidadeOut

NomeInsumo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
# Quantidade: Decimal >= 0, até 3 casas, cabe em Numeric(12,3). "> 0" é checado no domínio.
Quantidade = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]


class InsumoCreateIn(EntradaEstrita):
    nome: NomeInsumo
    unidade: UnidadeMedida
    estoque_minimo: Quantidade = Decimal("0")


class InsumoUpdateIn(EntradaEstrita):
    nome: NomeInsumo | None = None
    estoque_minimo: Quantidade | None = None

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if self.nome is None and self.estoque_minimo is None:
            raise ValueError("Informe ao menos um campo: nome ou estoque_minimo")
        return self


class InsumoOut(BaseModel):
    id: int
    nome: str
    unidade: UnidadeMedida
    estoque_minimo: QuantidadeOut
    estoque_atual: QuantidadeOut
    abaixo_do_minimo: bool
    ativo: bool

    @classmethod
    def de_entidade(cls, i: Insumo) -> Self:
        return cls(
            id=i.id_persistido,
            nome=i.nome,
            unidade=i.unidade,
            estoque_minimo=i.estoque_minimo,
            estoque_atual=i.estoque_atual,
            abaixo_do_minimo=i.abaixo_do_minimo,
            ativo=i.ativo,
        )


class PaginaInsumosOut(BaseModel):
    itens: list[InsumoOut]
    total: int
    limit: int
    offset: int


class MovimentacaoIn(EntradaEstrita):
    tipo: TipoMovimentacao
    quantidade: Quantidade
    motivo: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ] = None


class MovimentacaoOut(BaseModel):
    id: int
    insumo_id: int
    tipo: TipoMovimentacao
    quantidade: QuantidadeOut
    saldo_antes: QuantidadeOut
    saldo_apos: QuantidadeOut
    motivo: str | None
    usuario_id: int | None
    criado_em: datetime | None

    @classmethod
    def de_entidade(cls, m: MovimentacaoEstoque) -> Self:
        return cls(
            id=m.id_persistido,
            insumo_id=m.insumo_id,
            tipo=m.tipo,
            quantidade=m.quantidade,
            saldo_antes=m.saldo_antes,
            saldo_apos=m.saldo_apos,
            motivo=m.motivo,
            usuario_id=m.usuario_id,
            criado_em=m.criado_em,
        )


class PaginaMovimentacoesOut(BaseModel):
    itens: list[MovimentacaoOut]
    total: int
    limit: int
    offset: int


class ItemFichaIn(EntradaEstrita):
    insumo_id: int
    quantidade: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]


class FichaTecnicaIn(EntradaEstrita):
    itens: list[ItemFichaIn] = Field(max_length=100)


class ItemFichaOut(BaseModel):
    insumo_id: int
    quantidade: QuantidadeOut


class FichaTecnicaOut(BaseModel):
    itens: list[ItemFichaOut]

    @classmethod
    def de_itens(cls, itens: list[ItemFichaTecnica]) -> Self:
        return cls(
            itens=[ItemFichaOut(insumo_id=i.insumo_id, quantidade=i.quantidade) for i in itens]
        )
