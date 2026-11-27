from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.shared import ComId

ZERO = Decimal("0.00")


class FormaPagamento(StrEnum):
    DINHEIRO = "dinheiro"
    PIX = "pix"
    CARTAO_DEBITO = "cartao_debito"
    CARTAO_CREDITO = "cartao_credito"


class StatusSessao(StrEnum):
    ABERTA = "aberta"
    FECHADA = "fechada"


class TipoMovimento(StrEnum):
    SANGRIA = "sangria"
    SUPRIMENTO = "suprimento"


@dataclass
class SessaoCaixa(ComId):
    valor_abertura: Decimal
    aberta_por_id: int
    aberta_em: datetime
    status: StatusSessao = StatusSessao.ABERTA
    fechada_por_id: int | None = None
    fechada_em: datetime | None = None
    valor_esperado: Decimal | None = None
    valor_contado: Decimal | None = None
    diferenca: Decimal | None = None
    observacao: str | None = None
    id: int | None = None


@dataclass
class MovimentoCaixa(ComId):
    sessao_id: int
    tipo: TipoMovimento
    valor: Decimal
    motivo: str
    criado_por_id: int
    criado_em: datetime
    id: int | None = None


@dataclass(frozen=True)
class PagamentoPedido:
    forma: FormaPagamento
    valor: Decimal
    valor_recebido: Decimal | None = None

    @property
    def troco(self) -> Decimal:
        if self.valor_recebido is None:
            return ZERO
        return self.valor_recebido - self.valor


@dataclass
class Pagamento(ComId):
    comanda_id: int
    sessao_id: int
    forma: FormaPagamento
    valor: Decimal
    criado_por_id: int
    criado_em: datetime
    valor_recebido: Decimal | None = None
    id: int | None = None

    @property
    def troco(self) -> Decimal:
        if self.valor_recebido is None:
            return ZERO
        return self.valor_recebido - self.valor
