"""Montagem pura do fluxo de caixa (regime de caixa) a partir de fatos já agregados."""

from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal

from app.domain.dashboard.calculos import ZERO, acumular, percentual
from app.domain.dashboard.modelos import (
    FatoCaixa,
    FluxoCaixa,
    PontoFluxo,
    PontoProjecao,
    SaidaCategoria,
    TotaisFluxo,
)
from app.domain.dashboard.periodo import Agrupamento, Periodo, buckets, chave_bucket

TOP_CATEGORIAS = 10

FONTE_VENDA = "venda"
FONTE_RECEBER = "receber"
FONTE_PAGAR = "pagar"
FONTE_A_RECEBER = "a_receber"
FONTE_A_PAGAR = "a_pagar"


def _somar_por_chave(
    fatos: Iterable[FatoCaixa], fonte: str, periodo: Periodo, agrupamento: Agrupamento
) -> dict[date, Decimal]:
    soma: dict[date, Decimal] = {}
    for f in fatos:
        if f.fonte != fonte or not periodo.de <= f.dia <= periodo.ate:
            continue
        chave = chave_bucket(f.dia, agrupamento)
        soma[chave] = soma.get(chave, ZERO) + f.valor
    return soma


def montar_fluxo(
    periodo: Periodo,
    agrupamento: Agrupamento,
    fatos: Sequence[FatoCaixa],
    *,
    incluir_projecao: bool,
) -> FluxoCaixa:
    """Realizado (vendas + recebimentos pagos − pagamentos pagos) por bucket, com saldo
    acumulado desde o início do período; projeção (pendentes por vencimento) separada."""
    faixas = buckets(periodo, agrupamento)
    vendas = _somar_por_chave(fatos, FONTE_VENDA, periodo, agrupamento)
    outras = _somar_por_chave(fatos, FONTE_RECEBER, periodo, agrupamento)
    saidas = _somar_por_chave(fatos, FONTE_PAGAR, periodo, agrupamento)

    saldos = [
        vendas.get(b.chave, ZERO) + outras.get(b.chave, ZERO) - saidas.get(b.chave, ZERO)
        for b in faixas
    ]
    acumulados = acumular(saldos)
    realizado = [
        PontoFluxo(
            b.inicio,
            b.fim,
            vendas.get(b.chave, ZERO),
            outras.get(b.chave, ZERO),
            saidas.get(b.chave, ZERO),
            saldo,
            acumulado,
        )
        for b, saldo, acumulado in zip(faixas, saldos, acumulados, strict=True)
    ]

    total_vendas = sum(vendas.values(), start=ZERO)
    total_outras = sum(outras.values(), start=ZERO)
    total_saidas = sum(saidas.values(), start=ZERO)
    totais = TotaisFluxo(
        total_vendas, total_outras, total_saidas, total_vendas + total_outras - total_saidas
    )

    projecao: list[PontoProjecao] | None = None
    if incluir_projecao:
        a_receber = _somar_por_chave(fatos, FONTE_A_RECEBER, periodo, agrupamento)
        a_pagar = _somar_por_chave(fatos, FONTE_A_PAGAR, periodo, agrupamento)
        projecao = [
            PontoProjecao(b.inicio, b.fim, a_receber.get(b.chave, ZERO), a_pagar.get(b.chave, ZERO))
            for b in faixas
        ]

    return FluxoCaixa(
        periodo=periodo,
        agrupamento=agrupamento,
        realizado=realizado,
        totais=totais,
        saidas_por_categoria=saidas_por_categoria(fatos, periodo),
        projecao=projecao,
    )


def saidas_por_categoria(fatos: Iterable[FatoCaixa], periodo: Periodo) -> list[SaidaCategoria]:
    """Maiores categorias de despesa paga no período; participação sobre o total de saídas."""
    por_categoria: dict[str, Decimal] = {}
    for f in fatos:
        if f.fonte != FONTE_PAGAR or not periodo.de <= f.dia <= periodo.ate:
            continue
        nome = f.categoria or "Sem categoria"
        por_categoria[nome] = por_categoria.get(nome, ZERO) + f.valor
    total = sum(por_categoria.values(), start=ZERO)
    ordenadas = sorted(por_categoria.items(), key=lambda item: (-item[1], item[0].casefold()))
    return [
        SaidaCategoria(nome, valor, percentual(valor, total))
        for nome, valor in ordenadas[:TOP_CATEGORIAS]
    ]
