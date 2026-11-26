"""Regras puras de comandas: totais, consumo agregado de estoque e transições de status."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.comandas.entities import AdicionalItem, Comanda, ItemComanda, StatusComanda
from app.domain.comandas.regras import (
    consumo_da_comanda,
    itens_sem_ficha,
    subtotal_item,
    total_comanda,
    total_efetivo,
    validar_cancelamento,
    validar_cliente_nome,
    validar_fechamento,
    validar_observacao,
    validar_quantidade_item,
)
from app.domain.estoque.entities import ItemFichaTecnica
from app.domain.exceptions import OperacaoNaoPermitida, ValorInvalido

D = Decimal


def _item(
    preco: str = "10.00",
    quantidade: int = 1,
    adicionais: list[AdicionalItem] | None = None,
    produto_id: int = 1,
    tamanho_id: int = 1,
    id: int | None = None,
) -> ItemComanda:
    return ItemComanda(
        produto_id=produto_id,
        tamanho_id=tamanho_id,
        nome_produto="Açaí",
        nome_tamanho="500 ml",
        preco_unitario=D(preco),
        quantidade=quantidade,
        adicionais=adicionais or [],
        id=id,
    )


def _comanda(itens: list[ItemComanda], status: StatusComanda = StatusComanda.ABERTA) -> Comanda:
    return Comanda(
        cliente_nome="Ana", aberta_em=datetime.now(UTC), itens=itens, status=status, id=1
    )


# --- totais ---


def test_subtotal_com_adicionais_e_quantidade() -> None:
    item = _item(
        "18.90",
        quantidade=3,
        adicionais=[
            AdicionalItem(1, "Granola", D("2.50"), 2),
            AdicionalItem(2, "Leite ninho", D("3.00"), 1),
        ],
    )
    # (18,90 + 2,50*2 + 3,00) * 3 = 26,90 * 3
    assert subtotal_item(item) == D("80.70")


def test_total_soma_os_itens_e_nunca_vira_float() -> None:
    itens = [_item("0.10", 3), _item("0.20", 1, [AdicionalItem(1, "X", D("0.07"), 3)])]
    total = total_comanda(itens)
    assert total == D("0.71")  # 0,30 + (0,20 + 0,21), exato em Decimal
    assert isinstance(total, Decimal)
    assert total_comanda([]) == D("0")


def test_total_efetivo_usa_o_snapshot_da_comanda_fechada() -> None:
    comanda = _comanda([_item("10.00", 2)])
    assert total_efetivo(comanda) == D("20.00")
    comanda.total_fechado = D("15.00")  # snapshot gravado no fechamento
    assert total_efetivo(comanda) == D("15.00")


# --- consumo de estoque ---


def test_consumo_soma_o_mesmo_insumo_de_itens_e_adicionais_diferentes() -> None:
    polpa, granola = 1, 2
    itens = [
        _item(
            produto_id=1, tamanho_id=1, quantidade=2, adicionais=[AdicionalItem(7, "G", D("1"), 2)]
        ),
        _item(
            produto_id=2, tamanho_id=1, quantidade=1, adicionais=[AdicionalItem(7, "G", D("1"), 1)]
        ),
    ]
    fichas_produto = {
        (1, 1): [ItemFichaTecnica(polpa, D("0.300"))],
        (2, 1): [ItemFichaTecnica(polpa, D("0.200")), ItemFichaTecnica(granola, D("0.010"))],
    }
    fichas_adicional = {7: [ItemFichaTecnica(granola, D("0.020"))]}

    consumo = consumo_da_comanda(itens, fichas_produto, fichas_adicional)

    # polpa: 0,3*2 + 0,2*1 = 0,8 | granola: 0,01*1 + 0,02*(2*2) + 0,02*(1*1) = 0,11
    assert consumo == {polpa: D("0.800"), granola: D("0.110")}


def test_consumo_ignora_item_e_adicional_sem_ficha() -> None:
    itens = [_item(adicionais=[AdicionalItem(9, "Sem ficha", D("1"), 1)])]
    assert consumo_da_comanda(itens, {}, {}) == {}


def test_itens_sem_ficha_lista_so_os_que_nao_baixam_estoque() -> None:
    itens = [_item(produto_id=1, id=10), _item(produto_id=2, id=11)]
    fichas = {(1, 1): [ItemFichaTecnica(1, D("1"))], (2, 1): []}
    assert itens_sem_ficha(itens, fichas) == [11]


# --- transições ---


def test_so_comanda_aberta_com_itens_fecha() -> None:
    validar_fechamento(_comanda([_item()]))
    with pytest.raises(OperacaoNaoPermitida, match="comanda_vazia"):
        validar_fechamento(_comanda([]))
    for terminal in (StatusComanda.FECHADA, StatusComanda.CANCELADA):
        with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
            validar_fechamento(_comanda([_item()], terminal))


def test_cancelar_so_aberta() -> None:
    validar_cancelamento(_comanda([]))  # aberta e vazia pode ser cancelada
    for terminal in (StatusComanda.FECHADA, StatusComanda.CANCELADA):
        with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
            validar_cancelamento(_comanda([], terminal))


# --- validações ---


@pytest.mark.parametrize("quantidade", [0, -1, 100, True])
def test_quantidade_do_item_de_1_a_99(quantidade: int) -> None:
    with pytest.raises(ValorInvalido):
        validar_quantidade_item(quantidade)


@pytest.mark.parametrize("quantidade", [1, 50, 99])
def test_quantidade_valida(quantidade: int) -> None:
    assert validar_quantidade_item(quantidade) == quantidade


def test_nome_do_cliente() -> None:
    assert validar_cliente_nome("  Maria  ") == "Maria"
    for invalido in ("", "   ", "x" * 121):
        with pytest.raises(ValorInvalido):
            validar_cliente_nome(invalido)


def test_observacao() -> None:
    assert validar_observacao(None) is None
    assert validar_observacao("   ") is None
    assert validar_observacao(" sem granola ") == "sem granola"
    with pytest.raises(ValorInvalido):
        validar_observacao("x" * 501)
