from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints

from app.application.caixa.dto import DetalheSessao
from app.domain.caixa.entities import (
    FormaPagamento,
    MovimentoCaixa,
    Pagamento,
    PagamentoPedido,
    SessaoCaixa,
    StatusSessao,
    TipoMovimento,
)
from app.interfaces.http.schemas.base import DinheiroOut, EntradaEstrita

Valor = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Observacao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class AbrirCaixaIn(EntradaEstrita):
    valor_abertura: Valor
    observacao: Observacao | None = None


class FecharCaixaIn(EntradaEstrita):
    valor_contado: Valor
    observacao: Observacao | None = None


class MovimentoIn(EntradaEstrita):
    tipo: TipoMovimento
    valor: ValorPositivo
    motivo: Motivo


class PagamentoIn(EntradaEstrita):
    forma: FormaPagamento
    valor: ValorPositivo
    valor_recebido: Valor | None = Field(
        default=None, description="Só dinheiro: o que o cliente entregou (o excedente é o troco)"
    )

    def para_pedido(self) -> PagamentoPedido:
        return PagamentoPedido(self.forma, self.valor, self.valor_recebido)


class PagamentoOut(BaseModel):
    id: int
    forma: FormaPagamento
    valor: DinheiroOut
    valor_recebido: DinheiroOut | None
    troco: DinheiroOut
    sessao_id: int
    criado_em: datetime

    @classmethod
    def de_entidade(cls, p: Pagamento) -> Self:
        return cls(
            id=p.id_persistido,
            forma=p.forma,
            valor=p.valor,
            valor_recebido=p.valor_recebido,
            troco=p.troco,
            sessao_id=p.sessao_id,
            criado_em=p.criado_em,
        )


class MovimentoOut(BaseModel):
    id: int
    sessao_id: int
    tipo: TipoMovimento
    valor: DinheiroOut
    motivo: str
    criado_por_id: int
    criado_em: datetime

    @classmethod
    def de_entidade(cls, m: MovimentoCaixa) -> Self:
        return cls(
            id=m.id_persistido,
            sessao_id=m.sessao_id,
            tipo=m.tipo,
            valor=m.valor,
            motivo=m.motivo,
            criado_por_id=m.criado_por_id,
            criado_em=m.criado_em,
        )


class SessaoResumoOut(BaseModel):
    id: int
    status: StatusSessao
    valor_abertura: DinheiroOut
    aberta_por_id: int
    fechada_por_id: int | None
    aberta_em: datetime
    fechada_em: datetime | None
    valor_esperado: DinheiroOut | None
    valor_contado: DinheiroOut | None
    diferenca: DinheiroOut | None
    observacao: str | None

    @classmethod
    def de_entidade(cls, s: SessaoCaixa) -> Self:
        return cls(
            id=s.id_persistido,
            status=s.status,
            valor_abertura=s.valor_abertura,
            aberta_por_id=s.aberta_por_id,
            fechada_por_id=s.fechada_por_id,
            aberta_em=s.aberta_em,
            fechada_em=s.fechada_em,
            valor_esperado=s.valor_esperado,
            valor_contado=s.valor_contado,
            diferenca=s.diferenca,
            observacao=s.observacao,
        )


class SessaoDetalheOut(SessaoResumoOut):
    saldo_dinheiro: DinheiroOut
    total_suprimentos: DinheiroOut
    total_sangrias: DinheiroOut
    resumo_por_forma: dict[FormaPagamento, DinheiroOut]
    movimentos: list[MovimentoOut]

    @classmethod
    def de_detalhe(cls, d: DetalheSessao) -> Self:
        base = SessaoResumoOut.de_entidade(d.sessao)
        return cls(
            **base.model_dump(),
            saldo_dinheiro=d.saldo_dinheiro,
            total_suprimentos=d.total_suprimentos,
            total_sangrias=d.total_sangrias,
            resumo_por_forma=d.resumo_por_forma,
            movimentos=[MovimentoOut.de_entidade(m) for m in d.movimentos],
        )


class PaginaSessoesOut(BaseModel):
    itens: list[SessaoResumoOut]
    total: int
    limit: int
    offset: int
