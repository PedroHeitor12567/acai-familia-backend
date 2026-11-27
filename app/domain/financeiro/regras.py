from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.exceptions import LancamentoInvalido, OperacaoNaoPermitida, ValorInvalido
from app.domain.financeiro.entities import (
    CategoriaFinanceira,
    Lancamento,
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)
from app.domain.shared import validar_valor_monetario

MAX_NOME_CATEGORIA = 80
MAX_DESCRICAO = 160
MAX_CONTRAPARTE = 120
MAX_OBSERVACAO = 500
MAX_MOTIVO = 255


def validar_nome_categoria(nome: str) -> str:
    limpo = nome.strip() if isinstance(nome, str) else ""
    if not limpo or len(limpo) > MAX_NOME_CATEGORIA:
        raise ValorInvalido("nome_categoria_financeira_invalido")
    return limpo


def validar_descricao(descricao: str) -> str:
    limpa = descricao.strip() if isinstance(descricao, str) else ""
    if not limpa or len(limpa) > MAX_DESCRICAO:
        raise ValorInvalido("descricao_invalida")
    return limpa


def validar_texto_opcional(texto: str | None, maximo: int, motivo: str) -> str | None:
    if texto is None:
        return None
    limpo = texto.strip()
    if len(limpo) > maximo:
        raise ValorInvalido(motivo)
    return limpo or None


def validar_valor_lancamento(valor: Decimal) -> Decimal:
    return validar_valor_monetario(valor)


def tipo_categoria_exigido(tipo: TipoLancamento) -> TipoCategoria:
    return TipoCategoria.DESPESA if tipo is TipoLancamento.PAGAR else TipoCategoria.RECEITA


def validar_categoria(tipo: TipoLancamento, categoria: CategoriaFinanceira) -> None:
    if not categoria.ativo:
        raise OperacaoNaoPermitida("categoria_financeira_inativa")
    if categoria.tipo is not tipo_categoria_exigido(tipo):
        raise LancamentoInvalido("categoria_incompativel")


def exigir_pendente(lancamento: Lancamento) -> None:
    if lancamento.status is not StatusLancamento.PENDENTE:
        raise OperacaoNaoPermitida("lancamento_nao_pendente")


def esta_atrasado(lancamento: Lancamento, hoje: date) -> bool:
    return lancamento.status is StatusLancamento.PENDENTE and lancamento.vencimento < hoje


def data_local(instante: datetime, fuso: str) -> date:
    return instante.astimezone(ZoneInfo(fuso)).date()
