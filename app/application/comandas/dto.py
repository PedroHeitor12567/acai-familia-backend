from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.comandas.entities import Comanda


@dataclass(frozen=True)
class ResultadoFechamento:
    comanda: Comanda
    consumo: dict[int, Decimal] = field(default_factory=dict)  # insumo_id -> quantidade baixada
    itens_sem_ficha: list[int] = field(default_factory=list)  # itens que não baixaram nada
