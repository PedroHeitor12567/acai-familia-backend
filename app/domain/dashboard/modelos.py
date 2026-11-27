"""Resultados do dashboard: dataclasses imutáveis, sem ORM nem framework."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.caixa.entities import FormaPagamento
from app.domain.dashboard.periodo import Agrupamento, Periodo
from app.domain.financeiro.entities import TipoLancamento


class OrdenarPor(StrEnum):
    QUANTIDADE = "quantidade"
    RECEITA = "receita"


class NivelEstoque(StrEnum):
    ZERADO = "zerado"
    CRITICO = "critico"


# --- vendas ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class TotaisVendas:
    faturamento: Decimal
    qtd_comandas: int
    itens_vendidos: int = 0
    comandas_canceladas: int = 0


@dataclass(frozen=True)
class Variacoes:
    faturamento: Decimal | None
    qtd_comandas: Decimal | None
    ticket_medio: Decimal | None


@dataclass(frozen=True)
class ResumoVendas:
    periodo: Periodo
    atual: TotaisVendas
    ticket_medio: Decimal
    periodo_anterior: Periodo
    anterior: TotaisVendas
    ticket_medio_anterior: Decimal
    variacao_pct: Variacoes


@dataclass(frozen=True)
class VendaDia:
    dia: date
    faturamento: Decimal
    qtd_comandas: int


@dataclass(frozen=True)
class PontoSerie:
    inicio: date
    fim: date
    faturamento: Decimal
    qtd_comandas: int


@dataclass(frozen=True)
class LinhaProduto:
    produto_id: int
    nome: str
    quantidade: int
    receita: Decimal


@dataclass(frozen=True)
class ProdutoVendido:
    produto_id: int
    nome: str
    quantidade: int
    receita: Decimal
    participacao_pct: Decimal


@dataclass(frozen=True)
class VendaForma:
    forma: FormaPagamento
    valor: Decimal
    qtd_pagamentos: int
    participacao_pct: Decimal = Decimal("0.0")


@dataclass(frozen=True)
class VendaHora:
    hora: int
    qtd_comandas: int
    faturamento: Decimal


# --- estoque ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class InsumoCritico:
    """Linha crua do banco: insumo ativo, com mínimo > 0, no mínimo ou abaixo."""

    insumo_id: int
    nome: str
    unidade: str
    estoque_atual: Decimal
    estoque_minimo: Decimal


@dataclass(frozen=True)
class EstoqueCritico:
    insumo_id: int
    nome: str
    unidade: str
    estoque_atual: Decimal
    estoque_minimo: Decimal
    deficit: Decimal
    cobertura_pct: Decimal
    nivel: NivelEstoque


@dataclass(frozen=True)
class PaginaEstoqueCritico:
    total_zerados: int
    total_criticos: int
    itens: list[EstoqueCritico]
    total: int
    limit: int
    offset: int


# --- financeiro ------------------------------------------------------------------------------


@dataclass(frozen=True)
class FatoCaixa:
    """Linha agregada do fluxo. `fonte`: venda | receber | pagar | a_receber | a_pagar."""

    fonte: str
    dia: date
    valor: Decimal
    categoria: str | None = None


@dataclass(frozen=True)
class PontoFluxo:
    inicio: date
    fim: date
    entradas_vendas: Decimal
    entradas_outras: Decimal
    saidas: Decimal
    saldo_periodo: Decimal
    saldo_acumulado: Decimal


@dataclass(frozen=True)
class PontoProjecao:
    inicio: date
    fim: date
    a_receber: Decimal
    a_pagar: Decimal


@dataclass(frozen=True)
class SaidaCategoria:
    categoria: str
    valor: Decimal
    participacao_pct: Decimal


@dataclass(frozen=True)
class TotaisFluxo:
    entradas_vendas: Decimal
    entradas_outras: Decimal
    saidas: Decimal
    resultado: Decimal


@dataclass(frozen=True)
class FluxoCaixa:
    periodo: Periodo
    agrupamento: Agrupamento
    realizado: list[PontoFluxo]
    totais: TotaisFluxo
    saidas_por_categoria: list[SaidaCategoria]
    projecao: list[PontoProjecao] | None


@dataclass(frozen=True)
class PosicaoConta:
    """Pendentes de um tipo (`pagar` ou `receber`) na data de hoje."""

    tipo: TipoLancamento
    total_pendente: Decimal
    qtd_pendente: int
    total_atrasado: Decimal
    qtd_atrasado: int
    vence_hoje_valor: Decimal
    vence_hoje_qtd: int
    vence_em_7_dias_valor: Decimal
    vence_em_7_dias_qtd: int


@dataclass(frozen=True)
class Vencimento:
    id: int
    tipo: TipoLancamento
    descricao: str
    valor: Decimal
    vencimento: date
    atrasado: bool


@dataclass(frozen=True)
class PosicaoContas:
    hoje: date
    pagar: PosicaoConta
    receber: PosicaoConta
    proximos_vencimentos: list[Vencimento]


# --- visão geral -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CaixaAberto:
    """Sessão aberta com as parcelas do saldo em dinheiro (a conta é a da Fase 3)."""

    sessao_id: int
    valor_abertura: Decimal
    pagamentos_dinheiro: Decimal
    suprimentos: Decimal
    sangrias: Decimal


@dataclass(frozen=True)
class VendasHoje:
    data: date
    comparado_com: date
    faturamento: Decimal
    qtd_comandas: int
    ticket_medio: Decimal
    anterior: TotaisVendas
    ticket_medio_anterior: Decimal
    variacao_pct: Variacoes


@dataclass(frozen=True)
class ResumoCaixa:
    aberto: bool
    sessao_id: int | None
    saldo_dinheiro: Decimal | None


@dataclass(frozen=True)
class ResumoEstoque:
    total_zerados: int
    total_criticos: int


@dataclass(frozen=True)
class ResumoContas:
    qtd_atrasadas_pagar: int
    valor_atrasado_pagar: Decimal
    qtd_atrasadas_receber: int
    valor_atrasado_receber: Decimal
    vence_hoje_pagar: Decimal


@dataclass(frozen=True)
class VisaoGeral:
    vendas_hoje: VendasHoje
    comandas_abertas: int
    caixa: ResumoCaixa
    estoque: ResumoEstoque
    contas: ResumoContas
