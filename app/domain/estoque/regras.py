"""Regras puras de estoque (sem I/O): saldo de movimentações e consumo da ficha técnica."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.domain.estoque.entities import ItemFichaTecnica, TipoMovimentacao, validar_quantidade
from app.domain.exceptions import EstoqueInsuficiente, FichaTecnicaInvalida, ValorInvalido


@dataclass(frozen=True)
class ResultadoMovimentacao:
    quantidade_registrada: Decimal
    saldo_apos: Decimal


def calcular_movimentacao(
    tipo: TipoMovimentacao, saldo_atual: Decimal, quantidade: Decimal
) -> ResultadoMovimentacao:
    """Entrada soma, saída subtrai (nunca deixa o saldo negativo) e ajuste define o saldo
    absoluto (`quantidade` = contagem física) registrando o módulo da diferença."""
    if tipo is TipoMovimentacao.AJUSTE:
        validar_quantidade(quantidade, permite_zero=True)
        diferenca = quantidade - saldo_atual
        if diferenca == 0:
            raise ValorInvalido("ajuste_sem_diferenca")
        return ResultadoMovimentacao(abs(diferenca), quantidade)

    validar_quantidade(quantidade)
    if tipo is TipoMovimentacao.ENTRADA:
        return ResultadoMovimentacao(quantidade, saldo_atual + quantidade)
    if quantidade > saldo_atual:
        raise EstoqueInsuficiente(saldo_atual, quantidade)
    return ResultadoMovimentacao(quantidade, saldo_atual - quantidade)


def validar_ficha(itens: Iterable[ItemFichaTecnica]) -> list[ItemFichaTecnica]:
    """Sem insumo repetido na mesma receita. (A quantidade > 0 já é garantida pelo item.)"""
    lista = list(itens)
    ids = [i.insumo_id for i in lista]
    if len(ids) != len(set(ids)):
        raise FichaTecnicaInvalida("insumo_repetido")
    return lista


def calcular_consumo(
    ficha: Iterable[ItemFichaTecnica], quantidade_vendida: int
) -> dict[int, Decimal]:
    """Insumos (id -> quantidade) a baixar do estoque ao vender `quantidade_vendida` unidades.

    É o que o fechamento de comanda (Fase 2) chama. Soma itens do mesmo insumo, caso a ficha
    venha de mais de uma fonte (produto + adicionais).
    """
    if isinstance(quantidade_vendida, bool) or quantidade_vendida <= 0:
        raise ValorInvalido("quantidade_invalida")
    consumo: dict[int, Decimal] = {}
    for item in ficha:
        consumo[item.insumo_id] = consumo.get(item.insumo_id, Decimal("0")) + (
            item.quantidade * quantidade_vendida
        )
    return consumo
