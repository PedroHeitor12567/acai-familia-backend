from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Protocol

from app.domain.caixa.entities import (
    ZERO,
    FormaPagamento,
    PagamentoPedido,
    SessaoCaixa,
    StatusSessao,
)
from app.domain.exceptions import (
    CaixaInvalido,
    OperacaoNaoPermitida,
    PagamentoInvalido,
    ValorInvalido,
)
from app.domain.shared import decimal_valido, validar_valor_monetario

MAX_MOTIVO = 255
MAX_OBSERVACAO = 500


class _ComValores(Protocol):
    @property
    def forma(self) -> FormaPagamento: ...
    @property
    def valor(self) -> Decimal: ...
    @property
    def troco(self) -> Decimal: ...


def calcular_troco(pagamento: _ComValores) -> Decimal:
    return pagamento.troco


def validar_pagamentos(total: Decimal, pagamentos: Sequence[PagamentoPedido]) -> None:
    formas: set[FormaPagamento] = set()
    soma = Decimal("0.00")
    for p in pagamentos:
        validar_valor_monetario(p.valor, motivo="pagamento_valor_invalido")
        if p.forma in formas:
            raise PagamentoInvalido("forma_repetida")
        formas.add(p.forma)
        if p.valor_recebido is not None:
            if p.forma is not FormaPagamento.DINHEIRO:
                raise PagamentoInvalido("valor_recebido_invalido")
            if not isinstance(p.valor_recebido, Decimal) or not decimal_valido(p.valor_recebido, 2):
                raise PagamentoInvalido("valor_recebido_invalido")
            if p.valor_recebido < p.valor:
                raise PagamentoInvalido("valor_recebido_insuficiente")
        soma += p.valor
    if soma != total:
        raise PagamentoInvalido("pagamento_diferente_do_total")


def valor_esperado(
    abertura: Decimal,
    pagamentos_dinheiro: Iterable[Decimal],
    suprimentos: Iterable[Decimal],
    sangrias: Iterable[Decimal],
) -> Decimal:
    return (
        abertura
        + sum(pagamentos_dinheiro, start=ZERO)
        + sum(suprimentos, start=ZERO)
        - sum(sangrias, start=ZERO)
    )


def validar_sangria(saldo_atual: Decimal, valor: Decimal) -> None:
    if valor > saldo_atual:
        raise OperacaoNaoPermitida("saldo_caixa_insuficiente")


def resumo_por_forma(
    pagamentos: Iterable[_ComValores],
) -> dict[FormaPagamento, Decimal]:
    resumo = {forma: ZERO for forma in FormaPagamento}
    for p in pagamentos:
        resumo[p.forma] += p.valor
    return resumo


def exigir_aberta(sessao: SessaoCaixa) -> None:
    if sessao.status is not StatusSessao.ABERTA:
        raise OperacaoNaoPermitida("sessao_nao_aberta")


def validar_valor_abertura(valor: Decimal) -> Decimal:
    return validar_valor_monetario(valor, permite_zero=True)


def validar_valor_contado(valor: Decimal) -> Decimal:
    return validar_valor_monetario(valor, permite_zero=True)


def validar_motivo_movimento(motivo: str) -> str:
    limpo = motivo.strip() if isinstance(motivo, str) else ""
    if not limpo or len(limpo) > MAX_MOTIVO:
        raise ValorInvalido("motivo_movimento_invalido")
    return limpo


def validar_observacao(texto: str | None) -> str | None:
    if texto is None:
        return None
    limpo = texto.strip()
    if len(limpo) > MAX_OBSERVACAO:
        raise ValorInvalido("observacao_invalida")
    return limpo or None


def calcular_diferenca(contado: Decimal, esperado: Decimal) -> Decimal:
    return contado - esperado


def exigir_justificativa(diferenca: Decimal, observacao: str | None) -> None:
    if diferenca != 0 and not observacao:
        raise CaixaInvalido("justificativa_obrigatoria")
