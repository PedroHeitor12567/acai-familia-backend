from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.caixa.entities import SessaoCaixa, StatusSessao
from app.domain.caixa.regras import (
    calcular_diferenca,
    exigir_aberta,
    exigir_justificativa,
    validar_motivo_movimento,
    validar_observacao,
    validar_sangria,
    validar_valor_abertura,
    validar_valor_contado,
    valor_esperado,
)
from app.domain.exceptions import CaixaInvalido, OperacaoNaoPermitida, ValorInvalido

D = Decimal


def test_valor_esperado_soma_abertura_dinheiro_e_suprimentos_e_tira_sangrias() -> None:
    esperado = valor_esperado(
        D("100.00"), [D("20.00"), D("30.00")], [D("30.00")], [D("20.00"), D("10.00")]
    )
    assert esperado == D("150.00")


def test_valor_esperado_so_com_a_abertura() -> None:
    assert valor_esperado(D("80.00"), [], [], []) == D("80.00")


def test_pix_e_cartao_nao_entram_na_gaveta() -> None:
    assert valor_esperado(D("0.00"), [D("10.00")], [], []) == D("10.00")


def test_sangria_ate_o_saldo_e_permitida() -> None:
    validar_sangria(D("40.00"), D("40.00"))


def test_sangria_acima_do_saldo_e_recusada() -> None:
    with pytest.raises(OperacaoNaoPermitida) as erro:
        validar_sangria(D("40.00"), D("40.01"))
    assert erro.value.motivo == "saldo_caixa_insuficiente"


def test_diferenca_de_sobra_falta_e_exatidao() -> None:
    assert calcular_diferenca(D("105.00"), D("100.00")) == D("5.00")
    assert calcular_diferenca(D("95.00"), D("100.00")) == D("-5.00")
    assert calcular_diferenca(D("100.00"), D("100.00")) == D("0.00")


def test_justificativa_obrigatoria_so_quando_ha_diferenca() -> None:
    exigir_justificativa(D("0.00"), None)
    exigir_justificativa(D("-5.00"), "troco dado errado")
    for diferenca in (D("5.00"), D("-5.00")):
        with pytest.raises(CaixaInvalido) as erro:
            exigir_justificativa(diferenca, None)
        assert erro.value.motivo == "justificativa_obrigatoria"


def _sessao(status: StatusSessao) -> SessaoCaixa:
    return SessaoCaixa(
        valor_abertura=D("0.00"), aberta_por_id=1, aberta_em=datetime.now(UTC), status=status
    )


def test_so_sessao_aberta_aceita_operacoes() -> None:
    exigir_aberta(_sessao(StatusSessao.ABERTA))
    with pytest.raises(OperacaoNaoPermitida) as erro:
        exigir_aberta(_sessao(StatusSessao.FECHADA))
    assert erro.value.motivo == "sessao_nao_aberta"


@pytest.mark.parametrize("valor", [D("-0.01"), D("1.001"), D("NaN")])
def test_abertura_e_contagem_nao_aceitam_valor_invalido(valor: Decimal) -> None:
    with pytest.raises(ValorInvalido):
        validar_valor_abertura(valor)
    with pytest.raises(ValorInvalido):
        validar_valor_contado(valor)


def test_abertura_e_contagem_aceitam_zero() -> None:
    assert validar_valor_abertura(D("0.00")) == 0
    assert validar_valor_contado(D("0")) == 0


def test_motivo_do_movimento_e_obrigatorio_e_limitado() -> None:
    assert validar_motivo_movimento("  troco  ") == "troco"
    for invalido in ("", "   ", "x" * 256):
        with pytest.raises(ValorInvalido):
            validar_motivo_movimento(invalido)


def test_observacao_vazia_vira_none_e_limite_de_500() -> None:
    assert validar_observacao("  ") is None
    assert validar_observacao(None) is None
    assert validar_observacao(" ok ") == "ok"
    with pytest.raises(ValorInvalido):
        validar_observacao("x" * 501)
