"""Cálculos puros do dashboard (sem I/O): tudo em `Decimal`, nunca `float`."""

from collections.abc import Iterable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domain.caixa.entities import FormaPagamento
from app.domain.dashboard.modelos import (
    EstoqueCritico,
    InsumoCritico,
    NivelEstoque,
    PontoSerie,
    Variacoes,
    VendaDia,
    VendaForma,
    VendaHora,
)
from app.domain.dashboard.periodo import Agrupamento, Periodo, buckets, chave_bucket

ZERO = Decimal("0.00")
CEM = Decimal("100")
_CENTAVOS = Decimal("0.01")
_DECIMO = Decimal("0.1")


def arredondar_dinheiro(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)


def ticket_medio(faturamento: Decimal, qtd_comandas: int) -> Decimal:
    if qtd_comandas <= 0:
        return ZERO
    return arredondar_dinheiro(faturamento / qtd_comandas)


def variacao_pct(atual: Decimal | int, anterior: Decimal | int) -> Decimal | None:
    """`(atual - anterior) / anterior * 100` com 1 casa; `None` quando o anterior é zero."""
    base = Decimal(anterior)
    if base == 0:
        return None
    return ((Decimal(atual) - base) / base * CEM).quantize(_DECIMO, rounding=ROUND_HALF_UP)


def calcular_variacoes(
    faturamento: tuple[Decimal, Decimal],
    qtd_comandas: tuple[int, int],
    ticket: tuple[Decimal, Decimal],
) -> Variacoes:
    """Cada par é `(atual, anterior)`."""
    return Variacoes(
        faturamento=variacao_pct(*faturamento),
        qtd_comandas=variacao_pct(*qtd_comandas),
        ticket_medio=variacao_pct(*ticket),
    )


def percentual(parte: Decimal, total: Decimal) -> Decimal:
    """Participação de `parte` em `total`, 1 casa. Cada linha é arredondada sozinha, então a
    soma das participações pode diferir de 100 por até 0,1 por linha (tolerância documentada)."""
    if total <= 0:
        return Decimal("0.0")
    return (parte / total * CEM).quantize(_DECIMO, rounding=ROUND_HALF_UP)


def cobertura_pct(estoque_atual: Decimal, estoque_minimo: Decimal) -> Decimal:
    """`estoque_atual / estoque_minimo * 100`, limitado a 0–100 (para barra de progresso)."""
    if estoque_minimo <= 0:
        return Decimal("100.0")
    bruto = estoque_atual / estoque_minimo * CEM
    return min(max(bruto, Decimal(0)), CEM).quantize(_DECIMO, rounding=ROUND_HALF_UP)


def classificar_nivel_estoque(
    estoque_atual: Decimal, estoque_minimo: Decimal
) -> NivelEstoque | None:
    """`None` = não é crítico (sem mínimo definido ou acima do mínimo). Exatamente no mínimo
    já conta como crítico."""
    if estoque_minimo <= 0 or estoque_atual > estoque_minimo:
        return None
    return NivelEstoque.ZERADO if estoque_atual <= 0 else NivelEstoque.CRITICO


def montar_estoque_critico(insumos: Iterable[InsumoCritico]) -> list[EstoqueCritico]:
    """Classifica, descarta o que não é crítico e ordena: zerados primeiro, depois menor
    cobertura, depois nome."""
    criticos: list[EstoqueCritico] = []
    for i in insumos:
        nivel = classificar_nivel_estoque(i.estoque_atual, i.estoque_minimo)
        if nivel is None:
            continue
        criticos.append(
            EstoqueCritico(
                insumo_id=i.insumo_id,
                nome=i.nome,
                unidade=i.unidade,
                estoque_atual=i.estoque_atual,
                estoque_minimo=i.estoque_minimo,
                deficit=max(i.estoque_minimo - i.estoque_atual, Decimal(0)),
                cobertura_pct=cobertura_pct(i.estoque_atual, i.estoque_minimo),
                nivel=nivel,
            )
        )
    criticos.sort(
        key=lambda c: (
            0 if c.nivel is NivelEstoque.ZERADO else 1,
            c.cobertura_pct,
            c.nome.casefold(),
            c.insumo_id,
        )
    )
    return criticos


def preencher_serie(
    periodo: Periodo, agrupamento: Agrupamento, vendas: Iterable[VendaDia]
) -> list[PontoSerie]:
    """Uma posição por bucket do período (zeros onde não houve venda). Vendas fora do período
    são ignoradas."""
    por_chave: dict[date, tuple[Decimal, int]] = {}
    for v in vendas:
        if not periodo.de <= v.dia <= periodo.ate:
            continue
        chave = chave_bucket(v.dia, agrupamento)
        faturamento, qtd = por_chave.get(chave, (ZERO, 0))
        por_chave[chave] = (faturamento + v.faturamento, qtd + v.qtd_comandas)
    return [
        PontoSerie(b.inicio, b.fim, *por_chave.get(b.chave, (ZERO, 0)))
        for b in buckets(periodo, agrupamento)
    ]


def acumular(valores: Iterable[Decimal]) -> list[Decimal]:
    """Soma corrida a partir do início do período (sem saldo anterior)."""
    total = ZERO
    corrido: list[Decimal] = []
    for v in valores:
        total += v
        corrido.append(total)
    return corrido


def completar_formas(linhas: Iterable[VendaForma]) -> list[VendaForma]:
    """Sempre as quatro formas (na ordem do enum), inclusive com 0,00, com participação."""
    por_forma = {linha.forma: linha for linha in linhas}
    total = sum((linha.valor for linha in por_forma.values()), start=ZERO)
    resultado: list[VendaForma] = []
    for forma in FormaPagamento:
        linha = por_forma.get(forma, VendaForma(forma, ZERO, 0))
        resultado.append(
            VendaForma(forma, linha.valor, linha.qtd_pagamentos, percentual(linha.valor, total))
        )
    return resultado


def completar_horas(linhas: Iterable[VendaHora]) -> list[VendaHora]:
    """Sempre 24 posições (0–23)."""
    por_hora = {linha.hora: linha for linha in linhas}
    return [por_hora.get(h, VendaHora(h, 0, ZERO)) for h in range(24)]
