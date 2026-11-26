from decimal import Decimal

import pytest

from app.domain.cardapio.entities import Adicional, ProdutoTamanho, validar_preco
from app.domain.estoque.entities import (
    Insumo,
    ItemFichaTecnica,
    TipoMovimentacao,
    UnidadeMedida,
)
from app.domain.estoque.regras import calcular_consumo, calcular_movimentacao, validar_ficha
from app.domain.exceptions import EstoqueInsuficiente, FichaTecnicaInvalida, ValorInvalido

D = Decimal


# --- preço ---


@pytest.mark.parametrize("preco", [D("-0.01"), D("10.999"), D("NaN"), D("Infinity")])
def test_preco_invalido(preco: Decimal) -> None:
    with pytest.raises(ValorInvalido):
        validar_preco(preco)


def test_preco_nao_aceita_float() -> None:
    with pytest.raises(ValorInvalido):
        validar_preco(12.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("preco", [D("0"), D("0.1"), D("19.90")])
def test_preco_valido(preco: Decimal) -> None:
    assert validar_preco(preco) == preco
    assert ProdutoTamanho(1, 1, preco).preco == preco
    assert Adicional(nome="Granola", preco=preco).preco == preco


def test_adicional_e_produto_tamanho_rejeitam_preco_negativo() -> None:
    with pytest.raises(ValorInvalido):
        Adicional(nome="X", preco=D("-1"))
    with pytest.raises(ValorInvalido):
        ProdutoTamanho(1, 1, D("-1"))


# --- insumo ---


@pytest.mark.parametrize(
    ("atual", "minimo", "esperado"),
    [("5", "5", True), ("4.999", "5", True), ("5.001", "5", False), ("0", "0", True)],
)
def test_abaixo_do_minimo_inclui_igualdade(atual: str, minimo: str, esperado: bool) -> None:
    insumo = Insumo("Polpa", UnidadeMedida.KG, estoque_minimo=D(minimo), estoque_atual=D(atual))
    assert insumo.abaixo_do_minimo is esperado


def test_estoque_minimo_negativo_e_invalido() -> None:
    with pytest.raises(ValorInvalido):
        Insumo("Polpa", UnidadeMedida.KG, estoque_minimo=D("-1"))


# --- movimentações ---


def test_entrada_soma() -> None:
    r = calcular_movimentacao(TipoMovimentacao.ENTRADA, D("10"), D("2.5"))
    assert (r.saldo_apos, r.quantidade_registrada) == (D("12.5"), D("2.5"))


def test_saida_subtrai_e_permite_zerar() -> None:
    r = calcular_movimentacao(TipoMovimentacao.SAIDA, D("10"), D("10"))
    assert r.saldo_apos == D("0")


def test_saida_maior_que_saldo_e_bloqueada() -> None:
    with pytest.raises(EstoqueInsuficiente):
        calcular_movimentacao(TipoMovimentacao.SAIDA, D("1"), D("1.001"))


@pytest.mark.parametrize("tipo", [TipoMovimentacao.ENTRADA, TipoMovimentacao.SAIDA])
@pytest.mark.parametrize("quantidade", [D("0"), D("-1"), D("1.0001"), D("NaN")])
def test_quantidade_invalida_em_entrada_e_saida(
    tipo: TipoMovimentacao, quantidade: Decimal
) -> None:
    with pytest.raises(ValorInvalido):
        calcular_movimentacao(tipo, D("10"), quantidade)


def test_ajuste_define_saldo_absoluto_e_registra_diferenca() -> None:
    para_cima = calcular_movimentacao(TipoMovimentacao.AJUSTE, D("10"), D("13.5"))
    assert (para_cima.saldo_apos, para_cima.quantidade_registrada) == (D("13.5"), D("3.5"))
    para_baixo = calcular_movimentacao(TipoMovimentacao.AJUSTE, D("10"), D("4"))
    assert (para_baixo.saldo_apos, para_baixo.quantidade_registrada) == (D("4"), D("6"))


def test_ajuste_pode_zerar_o_saldo() -> None:
    r = calcular_movimentacao(TipoMovimentacao.AJUSTE, D("3"), D("0"))
    assert (r.saldo_apos, r.quantidade_registrada) == (D("0"), D("3"))


def test_ajuste_sem_diferenca_e_rejeitado() -> None:
    with pytest.raises(ValorInvalido) as exc:
        calcular_movimentacao(TipoMovimentacao.AJUSTE, D("10"), D("10.000"))
    assert exc.value.motivo == "ajuste_sem_diferenca"


# --- ficha técnica ---


def test_item_de_ficha_exige_quantidade_positiva() -> None:
    with pytest.raises(ValorInvalido):
        ItemFichaTecnica(1, D("0"))
    with pytest.raises(ValorInvalido):
        ItemFichaTecnica(1, D("-2"))


def test_ficha_nao_aceita_insumo_repetido() -> None:
    with pytest.raises(FichaTecnicaInvalida) as exc:
        validar_ficha([ItemFichaTecnica(1, D("1")), ItemFichaTecnica(1, D("2"))])
    assert exc.value.motivo == "insumo_repetido"


def test_ficha_vazia_e_valida() -> None:
    assert validar_ficha([]) == []


def test_calcular_consumo_multiplica_pela_quantidade() -> None:
    ficha = [ItemFichaTecnica(1, D("0.150")), ItemFichaTecnica(2, D("30"))]
    assert calcular_consumo(ficha, 3) == {1: D("0.450"), 2: D("90")}


def test_calcular_consumo_soma_o_mesmo_insumo_de_fontes_diferentes() -> None:
    produto = [ItemFichaTecnica(1, D("100"))]
    adicional = [ItemFichaTecnica(1, D("10")), ItemFichaTecnica(2, D("5"))]
    assert calcular_consumo([*produto, *adicional], 2) == {1: D("220"), 2: D("10")}


def test_calcular_consumo_de_ficha_vazia() -> None:
    assert calcular_consumo([], 5) == {}


@pytest.mark.parametrize("quantidade", [0, -1, True])
def test_calcular_consumo_rejeita_quantidade_vendida_invalida(quantidade: int) -> None:
    with pytest.raises(ValorInvalido):
        calcular_consumo([ItemFichaTecnica(1, D("1"))], quantidade)


def test_calcular_consumo_nao_perde_precisao() -> None:
    # 0,1 x 3 em float daria 0.30000000000000004
    assert calcular_consumo([ItemFichaTecnica(1, D("0.1"))], 3) == {1: D("0.3")}
