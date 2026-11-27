from decimal import Decimal

import pytest

from app.domain.caixa.entities import FormaPagamento, PagamentoPedido
from app.domain.caixa.regras import calcular_troco, resumo_por_forma, validar_pagamentos
from app.domain.exceptions import PagamentoInvalido, ValorInvalido

D = Decimal
DIN, PIX = FormaPagamento.DINHEIRO, FormaPagamento.PIX
DEB, CRED = FormaPagamento.CARTAO_DEBITO, FormaPagamento.CARTAO_CREDITO


def _motivo(total: str, pagamentos: list[PagamentoPedido]) -> str:
    with pytest.raises(PagamentoInvalido) as erro:
        validar_pagamentos(D(total), pagamentos)
    return erro.value.motivo


def test_soma_exata_com_uma_ou_varias_formas() -> None:
    validar_pagamentos(D("66.70"), [PagamentoPedido(PIX, D("66.70"))])
    validar_pagamentos(
        D("66.70"),
        [
            PagamentoPedido(DIN, D("20.00"), D("50.00")),
            PagamentoPedido(PIX, D("26.70")),
            PagamentoPedido(CRED, D("20.00")),
        ],
    )


def test_soma_a_menos_e_a_mais_sao_recusadas() -> None:
    assert _motivo("66.70", [PagamentoPedido(PIX, D("66.69"))]) == "pagamento_diferente_do_total"
    assert _motivo("66.70", [PagamentoPedido(PIX, D("66.71"))]) == "pagamento_diferente_do_total"
    assert _motivo("0.01", []) == "pagamento_diferente_do_total"


def test_lista_vazia_so_vale_para_total_zero() -> None:
    validar_pagamentos(D("0.00"), [])
    assert _motivo("0.00", [PagamentoPedido(PIX, D("1.00"))]) == "pagamento_diferente_do_total"


def test_forma_repetida() -> None:
    pagamentos = [PagamentoPedido(PIX, D("10.00")), PagamentoPedido(PIX, D("20.00"))]
    assert _motivo("30.00", pagamentos) == "forma_repetida"


def test_valor_recebido_so_em_dinheiro() -> None:
    assert _motivo("10.00", [PagamentoPedido(PIX, D("10.00"), D("10.00"))]) == (
        "valor_recebido_invalido"
    )
    assert _motivo("10.00", [PagamentoPedido(DEB, D("10.00"), D("20.00"))]) == (
        "valor_recebido_invalido"
    )


def test_valor_recebido_com_casas_demais_e_invalido() -> None:
    assert _motivo("10.00", [PagamentoPedido(DIN, D("10.00"), D("10.001"))]) == (
        "valor_recebido_invalido"
    )


def test_valor_recebido_menor_que_o_valor() -> None:
    assert _motivo("10.00", [PagamentoPedido(DIN, D("10.00"), D("9.99"))]) == (
        "valor_recebido_insuficiente"
    )


@pytest.mark.parametrize("valor", [D("0"), D("-1.00"), D("1.005"), D("NaN"), D("Infinity")])
def test_valor_do_pagamento_precisa_ser_positivo_com_duas_casas(valor: Decimal) -> None:
    with pytest.raises(ValorInvalido):
        validar_pagamentos(D("10.00"), [PagamentoPedido(PIX, valor)])


def test_troco_so_existe_em_dinheiro_com_valor_recebido() -> None:
    assert calcular_troco(PagamentoPedido(DIN, D("26.70"), D("50.00"))) == D("23.30")
    assert calcular_troco(PagamentoPedido(DIN, D("26.70"), D("26.70"))) == D("0.00")
    assert calcular_troco(PagamentoPedido(DIN, D("26.70"))) == D("0.00")
    assert calcular_troco(PagamentoPedido(PIX, D("26.70"))) == D("0.00")


def test_resumo_por_forma_traz_as_quatro_formas() -> None:
    resumo = resumo_por_forma(
        [PagamentoPedido(DIN, D("10.00"), D("20.00")), PagamentoPedido(PIX, D("5.50"))]
    )
    assert resumo == {DIN: D("10.00"), PIX: D("5.50"), DEB: D("0.00"), CRED: D("0.00")}
    assert all(isinstance(v, Decimal) for v in resumo.values())
