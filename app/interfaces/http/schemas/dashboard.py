"""Saídas do dashboard. Dinheiro sai como string com 2 casas (`DinheiroOut`); percentuais são
`Decimal` no cálculo e viram número JSON só na serialização."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, PlainSerializer

from app.domain.caixa.entities import FormaPagamento
from app.domain.dashboard import modelos as m
from app.domain.dashboard.periodo import Agrupamento, Periodo
from app.domain.financeiro.entities import TipoLancamento
from app.interfaces.http.schemas.base import DinheiroOut, QuantidadeOut

Percentual = Annotated[
    Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")
]
PercentualOpcional = Annotated[
    Decimal | None,
    PlainSerializer(
        lambda v: None if v is None else float(v), return_type=float | None, when_used="json"
    ),
]


class PeriodoOut(BaseModel):
    de: date
    ate: date
    dias: int

    @classmethod
    def de_periodo(cls, p: Periodo) -> Self:
        return cls(de=p.de, ate=p.ate, dias=p.dias)


class VariacoesOut(BaseModel):
    faturamento: PercentualOpcional
    qtd_comandas: PercentualOpcional
    ticket_medio: PercentualOpcional

    @classmethod
    def de_variacoes(cls, v: m.Variacoes) -> Self:
        return cls(
            faturamento=v.faturamento, qtd_comandas=v.qtd_comandas, ticket_medio=v.ticket_medio
        )


# --- vendas ----------------------------------------------------------------------------------


class TotaisAtualOut(BaseModel):
    faturamento: DinheiroOut
    qtd_comandas: int
    ticket_medio: DinheiroOut
    itens_vendidos: int
    comandas_canceladas: int


class TotaisAnteriorOut(BaseModel):
    periodo: PeriodoOut
    faturamento: DinheiroOut
    qtd_comandas: int
    ticket_medio: DinheiroOut


class ResumoVendasOut(BaseModel):
    periodo: PeriodoOut
    atual: TotaisAtualOut
    anterior: TotaisAnteriorOut
    variacao_pct: VariacoesOut

    @classmethod
    def de_resumo(cls, r: m.ResumoVendas) -> Self:
        return cls(
            periodo=PeriodoOut.de_periodo(r.periodo),
            atual=TotaisAtualOut(
                faturamento=r.atual.faturamento,
                qtd_comandas=r.atual.qtd_comandas,
                ticket_medio=r.ticket_medio,
                itens_vendidos=r.atual.itens_vendidos,
                comandas_canceladas=r.atual.comandas_canceladas,
            ),
            anterior=TotaisAnteriorOut(
                periodo=PeriodoOut.de_periodo(r.periodo_anterior),
                faturamento=r.anterior.faturamento,
                qtd_comandas=r.anterior.qtd_comandas,
                ticket_medio=r.ticket_medio_anterior,
            ),
            variacao_pct=VariacoesOut.de_variacoes(r.variacao_pct),
        )


class PontoSerieOut(BaseModel):
    inicio: date
    fim: date
    faturamento: DinheiroOut
    qtd_comandas: int


class SerieVendasOut(BaseModel):
    periodo: PeriodoOut
    agrupamento: Agrupamento
    pontos: list[PontoSerieOut]
    total_faturamento: DinheiroOut
    total_comandas: int


class ProdutoVendidoOut(BaseModel):
    produto_id: int
    nome: str
    quantidade: int
    receita: DinheiroOut
    participacao_pct: Percentual


class MaisVendidosOut(BaseModel):
    periodo: PeriodoOut
    itens: list[ProdutoVendidoOut]


class VendaFormaOut(BaseModel):
    forma: FormaPagamento
    valor: DinheiroOut
    qtd_pagamentos: int
    participacao_pct: Percentual


class VendasPorFormaOut(BaseModel):
    periodo: PeriodoOut
    total: DinheiroOut
    formas: list[VendaFormaOut]


class VendaHoraOut(BaseModel):
    hora: int
    qtd_comandas: int
    faturamento: DinheiroOut


class VendasPorHoraOut(BaseModel):
    periodo: PeriodoOut
    horas: list[VendaHoraOut]


# --- estoque ---------------------------------------------------------------------------------


class EstoqueCriticoOut(BaseModel):
    insumo_id: int
    nome: str
    unidade: str
    estoque_atual: QuantidadeOut
    estoque_minimo: QuantidadeOut
    deficit: QuantidadeOut
    cobertura_pct: Percentual
    nivel: m.NivelEstoque


class PaginaEstoqueCriticoOut(BaseModel):
    total_zerados: int
    total_criticos: int
    itens: list[EstoqueCriticoOut]
    total: int
    limit: int
    offset: int

    @classmethod
    def de_pagina(cls, p: m.PaginaEstoqueCritico) -> Self:
        return cls(
            total_zerados=p.total_zerados,
            total_criticos=p.total_criticos,
            itens=[EstoqueCriticoOut(**vars(i)) for i in p.itens],
            total=p.total,
            limit=p.limit,
            offset=p.offset,
        )


# --- financeiro ------------------------------------------------------------------------------


class PontoFluxoOut(BaseModel):
    inicio: date
    fim: date
    entradas_vendas: DinheiroOut
    entradas_outras: DinheiroOut
    saidas: DinheiroOut
    saldo_periodo: DinheiroOut
    saldo_acumulado: DinheiroOut


class PontoProjecaoOut(BaseModel):
    inicio: date
    fim: date
    a_receber: DinheiroOut
    a_pagar: DinheiroOut


class TotaisFluxoOut(BaseModel):
    entradas_vendas: DinheiroOut
    entradas_outras: DinheiroOut
    saidas: DinheiroOut
    resultado: DinheiroOut


class SaidaCategoriaOut(BaseModel):
    categoria: str
    valor: DinheiroOut
    participacao_pct: Percentual


class FluxoCaixaOut(BaseModel):
    periodo: PeriodoOut
    agrupamento: Agrupamento
    realizado: list[PontoFluxoOut]
    resultado: TotaisFluxoOut
    saidas_por_categoria: list[SaidaCategoriaOut]
    projecao: list[PontoProjecaoOut] | None

    @classmethod
    def de_fluxo(cls, f: m.FluxoCaixa) -> Self:
        return cls(
            periodo=PeriodoOut.de_periodo(f.periodo),
            agrupamento=f.agrupamento,
            realizado=[PontoFluxoOut(**vars(p)) for p in f.realizado],
            resultado=TotaisFluxoOut(**vars(f.totais)),
            saidas_por_categoria=[SaidaCategoriaOut(**vars(s)) for s in f.saidas_por_categoria],
            projecao=None
            if f.projecao is None
            else [PontoProjecaoOut(**vars(p)) for p in f.projecao],
        )


class JanelaContaOut(BaseModel):
    valor: DinheiroOut
    qtd: int


class PosicaoContaOut(BaseModel):
    total_pendente: DinheiroOut
    qtd_pendente: int
    total_atrasado: DinheiroOut
    qtd_atrasado: int
    vence_hoje: JanelaContaOut
    vence_em_7_dias: JanelaContaOut

    @classmethod
    def de_posicao(cls, p: m.PosicaoConta) -> Self:
        return cls(
            total_pendente=p.total_pendente,
            qtd_pendente=p.qtd_pendente,
            total_atrasado=p.total_atrasado,
            qtd_atrasado=p.qtd_atrasado,
            vence_hoje=JanelaContaOut(valor=p.vence_hoje_valor, qtd=p.vence_hoje_qtd),
            vence_em_7_dias=JanelaContaOut(
                valor=p.vence_em_7_dias_valor, qtd=p.vence_em_7_dias_qtd
            ),
        )


class VencimentoOut(BaseModel):
    id: int
    tipo: TipoLancamento
    descricao: str
    valor: DinheiroOut
    vencimento: date
    atrasado: bool


class ContasOut(BaseModel):
    hoje: date
    pagar: PosicaoContaOut
    receber: PosicaoContaOut
    proximos_vencimentos: list[VencimentoOut]

    @classmethod
    def de_contas(cls, c: m.PosicaoContas) -> Self:
        return cls(
            hoje=c.hoje,
            pagar=PosicaoContaOut.de_posicao(c.pagar),
            receber=PosicaoContaOut.de_posicao(c.receber),
            proximos_vencimentos=[VencimentoOut(**vars(v)) for v in c.proximos_vencimentos],
        )


# --- visão geral -----------------------------------------------------------------------------


class VendasHojeAnteriorOut(BaseModel):
    data: date
    faturamento: DinheiroOut
    qtd_comandas: int
    ticket_medio: DinheiroOut


class VendasHojeOut(BaseModel):
    data: date
    faturamento: DinheiroOut
    qtd_comandas: int
    ticket_medio: DinheiroOut
    mesmo_dia_semana_anterior: VendasHojeAnteriorOut
    variacao_pct: VariacoesOut


class CaixaVisaoOut(BaseModel):
    aberto: bool
    sessao_id: int | None
    saldo_dinheiro: DinheiroOut | None


class EstoqueVisaoOut(BaseModel):
    total_zerados: int
    total_criticos: int


class ContasVisaoOut(BaseModel):
    qtd_atrasadas_pagar: int
    valor_atrasado_pagar: DinheiroOut
    qtd_atrasadas_receber: int
    valor_atrasado_receber: DinheiroOut
    vence_hoje_pagar: DinheiroOut


class VisaoGeralOut(BaseModel):
    vendas_hoje: VendasHojeOut
    comandas_abertas: int
    caixa: CaixaVisaoOut
    estoque: EstoqueVisaoOut
    contas: ContasVisaoOut

    @classmethod
    def de_visao(cls, v: m.VisaoGeral) -> Self:
        h = v.vendas_hoje
        return cls(
            vendas_hoje=VendasHojeOut(
                data=h.data,
                faturamento=h.faturamento,
                qtd_comandas=h.qtd_comandas,
                ticket_medio=h.ticket_medio,
                mesmo_dia_semana_anterior=VendasHojeAnteriorOut(
                    data=h.comparado_com,
                    faturamento=h.anterior.faturamento,
                    qtd_comandas=h.anterior.qtd_comandas,
                    ticket_medio=h.ticket_medio_anterior,
                ),
                variacao_pct=VariacoesOut.de_variacoes(h.variacao_pct),
            ),
            comandas_abertas=v.comandas_abertas,
            caixa=CaixaVisaoOut(
                aberto=v.caixa.aberto,
                sessao_id=v.caixa.sessao_id,
                saldo_dinheiro=v.caixa.saldo_dinheiro,
            ),
            estoque=EstoqueVisaoOut(**vars(v.estoque)),
            contas=ContasVisaoOut(**vars(v.contas)),
        )
