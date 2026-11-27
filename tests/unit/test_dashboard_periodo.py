from datetime import UTC, date, datetime

import pytest

from app.domain.dashboard.periodo import (
    Agrupamento,
    Periodo,
    buckets,
    chave_bucket,
    limites_utc,
    montar_periodo,
    validar_agrupamento,
)
from app.domain.exceptions import PeriodoInvalido

HOJE = date(2026, 11, 27)  # sexta-feira


def test_padrao_sao_os_ultimos_30_dias_ate_hoje() -> None:
    p = montar_periodo(None, None, HOJE)
    assert (p.de, p.ate, p.dias) == (date(2026, 10, 29), HOJE, 30)


def test_so_ate_informado_conta_30_dias_para_tras() -> None:
    p = montar_periodo(None, date(2026, 11, 10), HOJE)
    assert (p.de, p.dias) == (date(2026, 10, 12), 30)


def test_um_dia_so_e_valido() -> None:
    assert montar_periodo(HOJE, HOJE, HOJE).dias == 1


@pytest.mark.parametrize(
    ("de", "ate", "motivo"),
    [
        (date(2026, 11, 20), date(2026, 11, 19), "periodo_invertido"),
        (date(2026, 11, 20), date(2026, 11, 28), "periodo_no_futuro"),
        (date(2025, 1, 1), HOJE, "periodo_longo_demais"),
    ],
)
def test_periodos_invalidos(de: date, ate: date, motivo: str) -> None:
    with pytest.raises(PeriodoInvalido) as erro:
        montar_periodo(de, ate, HOJE)
    assert erro.value.motivo == motivo


def test_366_dias_ainda_vale_e_367_nao() -> None:
    assert montar_periodo(date(2025, 11, 27), HOJE, HOJE).dias == 366
    with pytest.raises(PeriodoInvalido):
        montar_periodo(date(2025, 11, 26), HOJE, HOJE)


def test_futuro_so_com_permissao_da_projecao() -> None:
    assert montar_periodo(HOJE, date(2026, 12, 31), HOJE, permite_futuro=True).dias == 35


def test_agrupar_por_dia_vai_ate_92_dias() -> None:
    validar_agrupamento(Periodo(date(2026, 8, 28), HOJE), Agrupamento.DIA)  # 92 dias
    longo = Periodo(date(2026, 8, 27), HOJE)  # 93 dias
    with pytest.raises(PeriodoInvalido) as erro:
        validar_agrupamento(longo, Agrupamento.DIA)
    assert erro.value.motivo == "agrupamento_dia_longo_demais"
    validar_agrupamento(longo, Agrupamento.SEMANA)
    validar_agrupamento(longo, Agrupamento.MES)


def test_periodo_anterior_tem_a_mesma_duracao_e_vem_logo_antes() -> None:
    p = Periodo(date(2026, 11, 1), date(2026, 11, 27))
    anterior = p.anterior()
    assert anterior == Periodo(date(2026, 10, 5), date(2026, 10, 31))
    assert anterior.dias == p.dias == 27


def test_limites_utc_sao_semiabertos_e_seguem_o_fuso() -> None:
    inicio, fim = limites_utc(Periodo(date(2026, 11, 10), date(2026, 11, 10)), "America/Sao_Paulo")
    assert inicio == datetime(2026, 11, 10, 3, 0, tzinfo=UTC)  # 00:00 local = 03:00 UTC
    assert fim == datetime(2026, 11, 11, 3, 0, tzinfo=UTC)


def test_venda_das_23h30_locais_pertence_ao_dia_local() -> None:
    # 23:30 em São Paulo = 02:30 UTC do dia seguinte, mas ainda é dia 10 na loja.
    venda = datetime(2026, 11, 11, 2, 30, tzinfo=UTC)
    inicio, fim = limites_utc(Periodo(date(2026, 11, 10), date(2026, 11, 10)), "America/Sao_Paulo")
    assert inicio <= venda < fim
    inicio_11, _ = limites_utc(Periodo(date(2026, 11, 11), date(2026, 11, 11)), "America/Sao_Paulo")
    assert venda < inicio_11


def test_semana_comeca_na_segunda_e_mes_no_dia_1() -> None:
    assert chave_bucket(date(2026, 11, 27), Agrupamento.SEMANA) == date(2026, 11, 23)  # sexta
    assert chave_bucket(date(2026, 11, 22), Agrupamento.SEMANA) == date(2026, 11, 16)  # domingo
    assert chave_bucket(date(2026, 11, 27), Agrupamento.MES) == date(2026, 11, 1)
    assert chave_bucket(date(2026, 11, 27), Agrupamento.DIA) == date(2026, 11, 27)


def test_buckets_das_pontas_vem_recortados() -> None:
    faixas = buckets(Periodo(date(2026, 11, 25), date(2026, 12, 8)), Agrupamento.SEMANA)
    assert [(b.inicio, b.fim) for b in faixas] == [
        (date(2026, 11, 25), date(2026, 11, 29)),  # quarta a domingo (semana parcial)
        (date(2026, 11, 30), date(2026, 12, 6)),
        (date(2026, 12, 7), date(2026, 12, 8)),  # semana parcial
    ]
    assert faixas[0].chave == date(2026, 11, 23)  # início natural da semana


def test_buckets_mensais_cobrem_meses_sem_movimento() -> None:
    faixas = buckets(Periodo(date(2026, 1, 15), date(2026, 3, 10)), Agrupamento.MES)
    assert [(b.inicio, b.fim) for b in faixas] == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 10)),
    ]


def test_buckets_por_dia_tem_um_por_dia() -> None:
    assert len(buckets(Periodo(date(2026, 11, 1), date(2026, 11, 30)), Agrupamento.DIA)) == 30
