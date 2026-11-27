from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain.caixa.entities import FormaPagamento
from app.domain.shared import ComId


class TipoCategoria(StrEnum):
    RECEITA = "receita"
    DESPESA = "despesa"


class TipoLancamento(StrEnum):
    PAGAR = "pagar"
    RECEBER = "receber"


class StatusLancamento(StrEnum):
    PENDENTE = "pendente"
    PAGO = "pago"
    CANCELADO = "cancelado"


@dataclass
class CategoriaFinanceira(ComId):
    nome: str
    tipo: TipoCategoria
    ativo: bool = True
    id: int | None = None


@dataclass(frozen=True)
class Baixa:
    data_pagamento: date
    forma: FormaPagamento


@dataclass
class Lancamento(ComId):
    tipo: TipoLancamento
    descricao: str
    valor: Decimal
    vencimento: date
    categoria_id: int
    criado_por_id: int
    contraparte: str | None = None
    observacao: str | None = None
    status: StatusLancamento = StatusLancamento.PENDENTE
    data_pagamento: date | None = None
    forma_pagamento: FormaPagamento | None = None
    baixado_por_id: int | None = None
    id: int | None = None
