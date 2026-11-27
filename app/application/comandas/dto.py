from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.caixa.entities import Pagamento
from app.domain.comandas.entities import Comanda


@dataclass(frozen=True)
class ResultadoFechamento:
    comanda: Comanda
    consumo: dict[int, Decimal] = field(default_factory=dict)  # insumo_id -> quantidade baixada
    itens_sem_ficha: list[int] = field(default_factory=list)  # itens que não baixaram nada
    pagamentos: list[Pagamento] = field(default_factory=list)
    troco_total: Decimal = Decimal("0.00")
    sessao_id: int | None = None


@dataclass(frozen=True)
class DetalheComanda:
    comanda: Comanda
    pagamentos: list[Pagamento] = field(default_factory=list)

    @property
    def troco(self) -> Decimal:
        return sum((p.troco for p in self.pagamentos), start=Decimal("0.00"))
