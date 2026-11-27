from dataclasses import dataclass
from decimal import Decimal

from app.domain.caixa.entities import FormaPagamento, MovimentoCaixa, SessaoCaixa


@dataclass(frozen=True)
class DetalheSessao:
    sessao: SessaoCaixa
    movimentos: list[MovimentoCaixa]
    resumo_por_forma: dict[FormaPagamento, Decimal]
    saldo_dinheiro: Decimal
    total_suprimentos: Decimal
    total_sangrias: Decimal
