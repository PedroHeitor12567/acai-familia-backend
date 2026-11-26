from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, StrictInt, StringConstraints, model_validator

from app.application.comandas.dto import ResultadoFechamento
from app.application.comandas.use_cases.itens import AdicionalPedido
from app.domain.comandas.entities import (
    AdicionalItem,
    Comanda,
    ItemComanda,
    OrigemComanda,
    StatusComanda,
)
from app.domain.comandas.regras import subtotal_item, total_efetivo
from app.interfaces.http.schemas.base import DinheiroOut, EntradaEstrita, QuantidadeOut

ClienteNome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ClienteContato = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]
Observacao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
QuantidadeItem = Annotated[StrictInt, Field(ge=1, le=99)]


class ComandaIn(EntradaEstrita):
    cliente_nome: ClienteNome
    origem: OrigemComanda = OrigemComanda.BALCAO
    cliente_contato: ClienteContato | None = None
    observacao: Observacao | None = None


class AdicionalPedidoIn(EntradaEstrita):
    adicional_id: int
    quantidade: QuantidadeItem = 1

    def para_pedido(self) -> AdicionalPedido:
        return AdicionalPedido(self.adicional_id, self.quantidade)


class ItemIn(EntradaEstrita):
    produto_id: int
    tamanho_id: int
    quantidade: QuantidadeItem = 1
    adicionais: list[AdicionalPedidoIn] = Field(default_factory=list, max_length=20)
    observacao: Observacao | None = None


class ItemUpdateIn(EntradaEstrita):
    quantidade: QuantidadeItem | None = None
    observacao: Observacao | None = Field(default=None, description='"" limpa a observação')

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if self.quantidade is None and self.observacao is None:
            raise ValueError("Informe ao menos um campo: quantidade ou observacao")
        return self


class CancelarIn(EntradaEstrita):
    motivo: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ] = None


class AdicionalItemOut(BaseModel):
    adicional_id: int
    nome: str
    quantidade: int
    preco_unitario: DinheiroOut

    @classmethod
    def de_entidade(cls, a: AdicionalItem) -> Self:
        return cls(
            adicional_id=a.adicional_id,
            nome=a.nome,
            quantidade=a.quantidade,
            preco_unitario=a.preco_unitario,
        )


class ItemComandaOut(BaseModel):
    id: int
    produto_id: int
    tamanho_id: int
    nome_produto: str
    nome_tamanho: str
    quantidade: int
    preco_unitario: DinheiroOut
    observacao: str | None
    adicionais: list[AdicionalItemOut]
    subtotal: DinheiroOut

    @classmethod
    def de_entidade(cls, i: ItemComanda) -> Self:
        return cls(
            id=i.id_persistido,
            produto_id=i.produto_id,
            tamanho_id=i.tamanho_id,
            nome_produto=i.nome_produto,
            nome_tamanho=i.nome_tamanho,
            quantidade=i.quantidade,
            preco_unitario=i.preco_unitario,
            observacao=i.observacao,
            adicionais=[AdicionalItemOut.de_entidade(a) for a in i.adicionais],
            subtotal=subtotal_item(i),
        )


class ComandaOut(BaseModel):
    id: int
    cliente_nome: str
    origem: OrigemComanda
    cliente_contato: str | None
    observacao: str | None
    status: StatusComanda
    aberta_por_id: int | None
    fechada_por_id: int | None
    aberta_em: datetime
    fechada_em: datetime | None
    total: DinheiroOut
    itens: list[ItemComandaOut]

    @classmethod
    def de_entidade(cls, c: Comanda) -> Self:
        return cls(
            id=c.id_persistido,
            cliente_nome=c.cliente_nome,
            origem=c.origem,
            cliente_contato=c.cliente_contato,
            observacao=c.observacao,
            status=c.status,
            aberta_por_id=c.aberta_por_id,
            fechada_por_id=c.fechada_por_id,
            aberta_em=c.aberta_em,
            fechada_em=c.fechada_em,
            total=total_efetivo(c),
            itens=[ItemComandaOut.de_entidade(i) for i in c.itens],
        )


class ConsumoInsumoOut(BaseModel):
    insumo_id: int
    quantidade: QuantidadeOut


class FechamentoOut(ComandaOut):
    """Comanda fechada + o que o fechamento baixou do estoque."""

    consumo: list[ConsumoInsumoOut]
    itens_sem_ficha: list[int]  # itens sem ficha técnica: fecharam sem baixar estoque

    @classmethod
    def de_resultado(cls, r: ResultadoFechamento) -> Self:
        base = ComandaOut.de_entidade(r.comanda)
        return cls(
            **base.model_dump(),
            consumo=[
                ConsumoInsumoOut(insumo_id=i, quantidade=q) for i, q in sorted(r.consumo.items())
            ],
            itens_sem_ficha=r.itens_sem_ficha,
        )


class ComandaResumoOut(BaseModel):
    """Linha da listagem: sem os itens (use o detalhe para eles)."""

    id: int
    cliente_nome: str
    origem: OrigemComanda
    status: StatusComanda
    aberta_por_id: int | None
    aberta_em: datetime
    fechada_em: datetime | None
    quantidade_itens: int
    total: DinheiroOut

    @classmethod
    def de_entidade(cls, c: Comanda) -> Self:
        return cls(
            id=c.id_persistido,
            cliente_nome=c.cliente_nome,
            origem=c.origem,
            status=c.status,
            aberta_por_id=c.aberta_por_id,
            aberta_em=c.aberta_em,
            fechada_em=c.fechada_em,
            quantidade_itens=len(c.itens),
            total=total_efetivo(c),
        )


class PaginaComandasOut(BaseModel):
    itens: list[ComandaResumoOut]
    total: int
    limit: int
    offset: int
