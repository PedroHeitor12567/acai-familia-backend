from datetime import date
from decimal import Decimal

import pytest

from app.domain.caixa.entities import FormaPagamento
from app.domain.dashboard.calculos import (
    acumular,
    classificar_nivel_estoque,
    cobertura_pct,
    completar_formas,
    completar_horas,
    montar_estoque_critico,
    percentual,
    preencher_serie,
    ticket_medio,
    variacao_pct,
)
from app.domain.dashboard.fluxo import montar_fluxo
from app.domain.dashboard.modelos import (
    FatoCaixa,
    InsumoCritico,
    NivelEstoque,
    VendaDia,
    VendaForma,
    VendaHora,
)
from app.domain.dashboard.periodo import Agrupamento, Periodo

D = Decimal


def test_ticket_medio_sem_comandas_e_zero() -> None:
    assert ticket_medio(D("0.00"), 0) == D("0.00")
    assert str(ticket_medio(D("0.00"), 0)) == "0.00"


@pytest.mark.parametrize(
    ("total", "qtd", "esperado"),
    [("10.00", 3, "3.33"), ("10.00", 8, "1.25"), ("0.05", 2, "0.03"), ("100.00", 3, "33.33")],
)
def test_ticket_medio_arredonda_meio_para_cima(total: str, qtd: int, esperado: str) -> None:
    assert ticket_medio(D(total), qtd) == D(esperado)


def test_variacao_com_anterior_zero_e_nula() -> None:
    assert variacao_pct(D("100.00"), D("0.00")) is None
    assert variacao_pct(5, 0) is None
    assert variacao_pct(D("0.00"), D("0.00")) is None


def test_variacao_positiva_negativa_e_zero() -> None:
    assert variacao_pct(D("18450.00"), D("16900.00")) == D("9.2")
    assert variacao_pct(612, 574) == D("6.6")
    assert variacao_pct(D("50.00"), D("100.00")) == D("-50.0")
    assert variacao_pct(D("100.00"), D("100.00")) == D("0.0")
    assert variacao_pct(D("0.00"), D("100.00")) == D("-100.0")


def test_percentual_e_decimal_com_uma_casa() -> None:
    assert percentual(D("1.00"), D("3.00")) == D("33.3")
    assert percentual(D("0.00"), D("0.00")) == D("0.0")
    assert isinstance(percentual(D("1"), D("2")), Decimal)


def test_participacoes_somam_cem_dentro_da_tolerancia() -> None:
    partes = [D("1.00"), D("1.00"), D("1.00")]
    soma = sum(percentual(p, D("3.00")) for p in partes)
    assert abs(soma - D("100")) <= D("0.1") * len(partes)


def test_cobertura_fica_entre_0_e_100() -> None:
    assert cobertura_pct(D("0"), D("2")) == D("0.0")
    assert cobertura_pct(D("1"), D("2")) == D("50.0")
    assert cobertura_pct(D("2"), D("2")) == D("100.0")
    assert cobertura_pct(D("-1"), D("2")) == D("0.0")
    assert cobertura_pct(D("1"), D("3")) == D("33.3")


@pytest.mark.parametrize(
    ("atual", "minimo", "nivel"),
    [
        ("0", "2", NivelEstoque.ZERADO),
        ("-1", "2", NivelEstoque.ZERADO),
        ("0.001", "2", NivelEstoque.CRITICO),
        ("2", "2", NivelEstoque.CRITICO),  # exatamente no mínimo entra
        ("2.001", "2", None),  # acima do mínimo não entra
        ("0", "0", None),  # sem mínimo definido não é crítico
        ("5", "0", None),
    ],
)
def test_classificar_nivel_estoque(atual: str, minimo: str, nivel: NivelEstoque | None) -> None:
    assert classificar_nivel_estoque(D(atual), D(minimo)) is nivel


def test_estoque_critico_ordena_zerado_primeiro_depois_cobertura_e_nome() -> None:
    insumos = [
        InsumoCritico(1, "Leite", "l", D("1.000"), D("2.000")),  # 50%
        InsumoCritico(2, "Granola", "kg", D("0.000"), D("2.000")),  # zerado
        InsumoCritico(3, "Banana", "kg", D("0.500"), D("2.000")),  # 25%
        InsumoCritico(4, "Abacaxi", "kg", D("1.000"), D("2.000")),  # 50%, nome antes de Leite
        InsumoCritico(5, "Sobra", "kg", D("9.000"), D("2.000")),  # fora
        InsumoCritico(6, "Sem mínimo", "kg", D("0.000"), D("0.000")),  # fora
    ]
    resultado = montar_estoque_critico(insumos)
    assert [i.nome for i in resultado] == ["Granola", "Banana", "Abacaxi", "Leite"]
    granola = resultado[0]
    assert (granola.deficit, granola.cobertura_pct, granola.nivel) == (
        D("2.000"),
        D("0.0"),
        NivelEstoque.ZERADO,
    )
    assert resultado[3].deficit == D("1.000")


def test_deficit_nunca_e_negativo() -> None:
    [item] = montar_estoque_critico([InsumoCritico(1, "X", "kg", D("-3.000"), D("2.000"))])
    assert item.deficit == D("5.000")  # negativo no saldo aumenta o déficit, nunca o inverte
    [exato] = montar_estoque_critico([InsumoCritico(1, "X", "kg", D("2.000"), D("2.000"))])
    assert exato.deficit == D("0.000")


def test_serie_diaria_preenche_zeros() -> None:
    periodo = Periodo(date(2026, 11, 1), date(2026, 11, 5))
    serie = preencher_serie(
        periodo,
        Agrupamento.DIA,
        [VendaDia(date(2026, 11, 2), D("30.00"), 2), VendaDia(date(2026, 11, 5), D("10.00"), 1)],
    )
    assert [p.faturamento for p in serie] == [
        D("0.00"),
        D("30.00"),
        D("0.00"),
        D("0.00"),
        D("10.00"),
    ]
    assert sum(p.faturamento for p in serie) == D("40.00")
    assert sum(p.qtd_comandas for p in serie) == 3


def test_serie_semanal_soma_por_semana_iniciada_na_segunda() -> None:
    periodo = Periodo(date(2026, 11, 25), date(2026, 12, 8))
    vendas = [
        VendaDia(date(2026, 11, 25), D("10.00"), 1),  # quarta
        VendaDia(date(2026, 11, 29), D("5.00"), 1),  # domingo, mesma semana
        VendaDia(date(2026, 11, 30), D("7.00"), 1),  # segunda: semana nova
    ]
    serie = preencher_serie(periodo, Agrupamento.SEMANA, vendas)
    assert [(p.inicio, p.fim, p.faturamento) for p in serie] == [
        (date(2026, 11, 25), date(2026, 11, 29), D("15.00")),
        (date(2026, 11, 30), date(2026, 12, 6), D("7.00")),
        (date(2026, 12, 7), date(2026, 12, 8), D("0.00")),
    ]


def test_serie_mensal_com_mes_sem_venda() -> None:
    periodo = Periodo(date(2026, 1, 15), date(2026, 3, 10))
    serie = preencher_serie(periodo, Agrupamento.MES, [VendaDia(date(2026, 3, 1), D("9.00"), 1)])
    assert [p.faturamento for p in serie] == [D("0.00"), D("0.00"), D("9.00")]


def test_serie_ignora_vendas_fora_do_periodo() -> None:
    periodo = Periodo(date(2026, 11, 1), date(2026, 11, 2))
    serie = preencher_serie(periodo, Agrupamento.DIA, [VendaDia(date(2026, 10, 31), D("9.00"), 1)])
    assert sum(p.faturamento for p in serie) == D("0.00")


def test_acumular_corre_desde_o_inicio() -> None:
    assert acumular([D("10.00"), D("-4.00"), D("0.00"), D("1.50")]) == [
        D("10.00"),
        D("6.00"),
        D("6.00"),
        D("7.50"),
    ]
    assert acumular([]) == []


def test_formas_sempre_as_quatro_e_na_ordem_do_enum() -> None:
    formas = completar_formas([VendaForma(FormaPagamento.PIX, D("75.00"), 3)])
    assert [f.forma for f in formas] == list(FormaPagamento)
    por_forma = {f.forma: f for f in formas}
    assert por_forma[FormaPagamento.PIX].participacao_pct == D("100.0")
    assert por_forma[FormaPagamento.DINHEIRO].valor == D("0.00")
    assert por_forma[FormaPagamento.DINHEIRO].qtd_pagamentos == 0


def test_horas_sempre_24_posicoes() -> None:
    horas = completar_horas([VendaHora(14, 2, D("40.00"))])
    assert [h.hora for h in horas] == list(range(24))
    assert horas[14].qtd_comandas == 2 and horas[3].qtd_comandas == 0


# --- fluxo de caixa ----------------------------------------------------------------------------


def _fatos() -> list[FatoCaixa]:
    return [
        FatoCaixa("venda", date(2026, 11, 2), D("100.00")),
        FatoCaixa("venda", date(2026, 11, 3), D("50.00")),
        FatoCaixa("receber", date(2026, 11, 3), D("20.00")),
        FatoCaixa("pagar", date(2026, 11, 3), D("70.00"), "Insumos"),
        FatoCaixa("pagar", date(2026, 11, 4), D("30.00"), "Aluguel"),
        FatoCaixa("a_receber", date(2026, 11, 5), D("200.00")),
        FatoCaixa("a_pagar", date(2026, 11, 5), D("80.00"), None),
    ]


def test_fluxo_realizado_soma_entradas_menos_saidas_e_acumula() -> None:
    periodo = Periodo(date(2026, 11, 1), date(2026, 11, 5))
    fluxo = montar_fluxo(periodo, Agrupamento.DIA, _fatos(), incluir_projecao=False)
    assert [p.saldo_periodo for p in fluxo.realizado] == [
        D("0.00"),
        D("100.00"),
        D("0.00"),  # 50 + 20 - 70
        D("-30.00"),
        D("0.00"),
    ]
    assert [p.saldo_acumulado for p in fluxo.realizado] == [
        D("0.00"),
        D("100.00"),
        D("100.00"),
        D("70.00"),
        D("70.00"),
    ]
    assert fluxo.totais.entradas_vendas == D("150.00")
    assert fluxo.totais.entradas_outras == D("20.00")
    assert fluxo.totais.saidas == D("100.00")
    assert fluxo.totais.resultado == D("70.00")
    assert fluxo.realizado[-1].saldo_acumulado == fluxo.totais.resultado


def test_projecao_fica_separada_do_realizado() -> None:
    periodo = Periodo(date(2026, 11, 1), date(2026, 11, 5))
    sem = montar_fluxo(periodo, Agrupamento.DIA, _fatos(), incluir_projecao=False)
    com = montar_fluxo(periodo, Agrupamento.DIA, _fatos(), incluir_projecao=True)
    assert sem.projecao is None
    assert com.projecao is not None
    assert (com.projecao[4].a_receber, com.projecao[4].a_pagar) == (D("200.00"), D("80.00"))
    assert com.realizado == sem.realizado  # a projeção nunca é somada ao realizado
    assert com.totais == sem.totais


def test_saidas_por_categoria_ordenadas_com_participacao() -> None:
    periodo = Periodo(date(2026, 11, 1), date(2026, 11, 5))
    fluxo = montar_fluxo(periodo, Agrupamento.DIA, _fatos(), incluir_projecao=False)
    assert [(s.categoria, s.valor, s.participacao_pct) for s in fluxo.saidas_por_categoria] == [
        ("Insumos", D("70.00"), D("70.0")),
        ("Aluguel", D("30.00"), D("30.0")),
    ]


def test_fluxo_semanal_agrupa_os_dias() -> None:
    periodo = Periodo(date(2026, 11, 1), date(2026, 11, 8))
    fluxo = montar_fluxo(periodo, Agrupamento.SEMANA, _fatos(), incluir_projecao=False)
    assert [(p.inicio, p.fim) for p in fluxo.realizado] == [
        (date(2026, 11, 1), date(2026, 11, 1)),
        (date(2026, 11, 2), date(2026, 11, 8)),
    ]
    assert fluxo.realizado[1].entradas_vendas == D("150.00")
