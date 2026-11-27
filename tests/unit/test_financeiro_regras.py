from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.caixa.entities import FormaPagamento
from app.domain.exceptions import LancamentoInvalido, OperacaoNaoPermitida, ValorInvalido
from app.domain.financeiro.entities import (
    CategoriaFinanceira,
    Lancamento,
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)
from app.domain.financeiro.regras import (
    data_local,
    esta_atrasado,
    exigir_pendente,
    tipo_categoria_exigido,
    validar_categoria,
    validar_descricao,
    validar_nome_categoria,
    validar_texto_opcional,
    validar_valor_lancamento,
)

D = Decimal
DESPESA = CategoriaFinanceira("Fornecedores", TipoCategoria.DESPESA, id=1)
RECEITA = CategoriaFinanceira("Eventos", TipoCategoria.RECEITA, id=2)


def _lancamento(status: StatusLancamento, vencimento: date) -> Lancamento:
    return Lancamento(
        tipo=TipoLancamento.PAGAR,
        descricao="Polpa",
        valor=D("10.00"),
        vencimento=vencimento,
        categoria_id=1,
        criado_por_id=1,
        status=status,
    )


def test_pagar_pede_despesa_e_receber_pede_receita() -> None:
    assert tipo_categoria_exigido(TipoLancamento.PAGAR) is TipoCategoria.DESPESA
    assert tipo_categoria_exigido(TipoLancamento.RECEBER) is TipoCategoria.RECEITA
    validar_categoria(TipoLancamento.PAGAR, DESPESA)
    validar_categoria(TipoLancamento.RECEBER, RECEITA)


@pytest.mark.parametrize(
    ("tipo", "categoria"),
    [(TipoLancamento.PAGAR, RECEITA), (TipoLancamento.RECEBER, DESPESA)],
)
def test_categoria_incompativel_com_o_tipo(
    tipo: TipoLancamento, categoria: CategoriaFinanceira
) -> None:
    with pytest.raises(LancamentoInvalido) as erro:
        validar_categoria(tipo, categoria)
    assert erro.value.motivo == "categoria_incompativel"


def test_categoria_inativa_e_recusada() -> None:
    inativa = CategoriaFinanceira("Velha", TipoCategoria.DESPESA, ativo=False, id=3)
    with pytest.raises(OperacaoNaoPermitida) as erro:
        validar_categoria(TipoLancamento.PAGAR, inativa)
    assert erro.value.motivo == "categoria_financeira_inativa"


def test_so_pendente_pode_ser_alterado() -> None:
    exigir_pendente(_lancamento(StatusLancamento.PENDENTE, date(2026, 1, 1)))
    for terminal in (StatusLancamento.PAGO, StatusLancamento.CANCELADO):
        with pytest.raises(OperacaoNaoPermitida) as erro:
            exigir_pendente(_lancamento(terminal, date(2026, 1, 1)))
        assert erro.value.motivo == "lancamento_nao_pendente"


def test_atrasado_e_derivado_de_pendente_e_vencimento() -> None:
    hoje = date(2026, 11, 27)
    ontem, amanha = date(2026, 11, 26), date(2026, 11, 28)
    assert esta_atrasado(_lancamento(StatusLancamento.PENDENTE, ontem), hoje)
    assert not esta_atrasado(_lancamento(StatusLancamento.PENDENTE, hoje), hoje)
    assert not esta_atrasado(_lancamento(StatusLancamento.PENDENTE, amanha), hoje)
    assert not esta_atrasado(_lancamento(StatusLancamento.PAGO, ontem), hoje)
    assert not esta_atrasado(_lancamento(StatusLancamento.CANCELADO, ontem), hoje)


def test_hoje_vira_a_meia_noite_do_fuso_da_loja_e_nao_a_do_utc() -> None:
    fuso = "America/Sao_Paulo"
    vencimento = date(2026, 11, 27)
    lancamento = _lancamento(StatusLancamento.PENDENTE, vencimento)

    antes = data_local(datetime(2026, 11, 27, 2, 59, tzinfo=UTC), fuso)
    assert antes == date(2026, 11, 26) and not esta_atrasado(lancamento, antes)
    assert data_local(datetime(2026, 11, 27, 3, 0, tzinfo=UTC), fuso) == vencimento
    depois = data_local(datetime(2026, 11, 28, 3, 0, tzinfo=UTC), fuso)
    assert depois == date(2026, 11, 28) and esta_atrasado(lancamento, depois)


def test_validacoes_de_texto_e_valor() -> None:
    assert validar_nome_categoria("  Aluguel ") == "Aluguel"
    assert validar_descricao(" Conta de luz ") == "Conta de luz"
    assert validar_texto_opcional("   ", 120, "x") is None
    assert validar_valor_lancamento(D("0.01")) == D("0.01")
    for invalido in ("", "  ", "x" * 81):
        with pytest.raises(ValorInvalido):
            validar_nome_categoria(invalido)
    for invalida in ("", "  ", "x" * 161):
        with pytest.raises(ValorInvalido):
            validar_descricao(invalida)
    with pytest.raises(ValorInvalido):
        validar_texto_opcional("x" * 121, 120, "contraparte_invalida")
    for valor in (D("0"), D("-1.00"), D("1.001"), D("NaN")):
        with pytest.raises(ValorInvalido):
            validar_valor_lancamento(valor)


def test_forma_de_pagamento_do_financeiro_reusa_a_do_caixa() -> None:
    assert {f.value for f in FormaPagamento} == {
        "dinheiro",
        "pix",
        "cartao_debito",
        "cartao_credito",
    }
