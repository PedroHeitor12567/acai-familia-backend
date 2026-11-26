from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.comandas.entities import Comanda, ItemComanda, OrigemComanda, StatusComanda


@dataclass(frozen=True)
class FiltrosComanda:
    status: StatusComanda | None = None
    origem: OrigemComanda | None = None
    cliente: str | None = None  # busca parcial, sem diferenciar maiúsculas de minúsculas
    aberta_por_id: int | None = None
    de: datetime | None = None  # por `aberta_em`, inclusivo
    ate: datetime | None = None  # por `aberta_em`, inclusivo


class ComandaRepository(Protocol):
    """As escritas acontecem na transação corrente: quem decide o commit é o caso de uso."""

    async def adicionar(self, comanda: Comanda) -> Comanda: ...

    async def obter(self, comanda_id: int, *, para_atualizar: bool = False) -> Comanda | None:
        """Comanda com itens e adicionais, sempre relida do banco. `para_atualizar` trava a
        linha (`SELECT ... FOR UPDATE`): é o que serializa lançamento de itens e fechamento."""
        ...

    async def adicionar_item(self, comanda_id: int, item: ItemComanda) -> ItemComanda: ...
    async def atualizar_item(
        self, comanda_id: int, item_id: int, quantidade: int, observacao: str | None
    ) -> None: ...
    async def remover_item(self, comanda_id: int, item_id: int) -> None: ...

    async def marcar_fechada(
        self, comanda_id: int, fechada_por_id: int, fechada_em: datetime, total: Decimal
    ) -> None: ...
    async def marcar_cancelada(self, comanda_id: int) -> None: ...

    async def listar(
        self, filtros: FiltrosComanda, limit: int, offset: int
    ) -> tuple[list[Comanda], int]:
        """Abertas por `aberta_em` crescente (as mais antigas primeiro); as demais, da mais
        recente para a mais antiga."""
        ...
