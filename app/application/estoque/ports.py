from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.estoque.entities import (
    Insumo,
    ItemFichaTecnica,
    MovimentacaoEstoque,
    TipoMovimentacao,
)


@dataclass(frozen=True)
class FiltrosInsumo:
    ativo: bool | None = None
    abaixo_do_minimo: bool | None = None
    q: str | None = None  # busca parcial no nome


@dataclass(frozen=True)
class FiltrosMovimentacao:
    tipo: TipoMovimentacao | None = None
    de: datetime | None = None  # inclusivo
    ate: datetime | None = None  # inclusivo


class EstoqueRepository(Protocol):
    async def obter_insumo(self, insumo_id: int) -> Insumo | None: ...
    async def obter_insumo_por_nome(self, nome: str) -> Insumo | None: ...
    async def adicionar_insumo(self, insumo: Insumo) -> Insumo: ...
    async def atualizar_insumo(self, insumo: Insumo) -> Insumo:
        """Persiste nome, estoque mínimo e `ativo`. O saldo só muda via `movimentar`."""
        ...

    async def listar_insumos(
        self, filtros: FiltrosInsumo, limit: int, offset: int
    ) -> tuple[list[Insumo], int]:
        """Página ordenada por nome e o total que bate com os filtros."""
        ...

    async def movimentar(
        self,
        insumo_id: int,
        tipo: TipoMovimentacao,
        quantidade: Decimal,
        usuario_id: int | None,
        motivo: str | None = None,
    ) -> MovimentacaoEstoque:
        """Aplica a movimentação na transação corrente (não faz commit): trava o insumo
        (`SELECT ... FOR UPDATE`), recalcula o saldo e grava movimentação e novo saldo juntos.
        Levanta `InsumoNaoEncontrado` ou `EstoqueInsuficiente`."""
        ...

    async def aplicar_saida(
        self,
        insumo_id: int,
        quantidade: Decimal,
        usuario_id: int | None,
        motivo: str | None = None,
    ) -> MovimentacaoEstoque:
        """Atalho de `movimentar` para saídas. É o ponto de reuso do fechamento de comanda
        (Fase 2): roda dentro da UoW da comanda, que decide o commit."""
        ...

    async def listar_movimentacoes(
        self, insumo_id: int, filtros: FiltrosMovimentacao, limit: int, offset: int
    ) -> tuple[list[MovimentacaoEstoque], int]:
        """Mais recentes primeiro. O histórico é imutável: não há update nem delete."""
        ...


class FichaTecnicaRepository(Protocol):
    async def obter_ficha_produto(
        self, produto_id: int, tamanho_id: int
    ) -> list[ItemFichaTecnica]: ...
    async def substituir_ficha_produto(
        self, produto_id: int, tamanho_id: int, itens: Sequence[ItemFichaTecnica]
    ) -> None:
        """Troca a receita inteira (apaga e regrava) na transação corrente."""
        ...

    async def obter_ficha_adicional(self, adicional_id: int) -> list[ItemFichaTecnica]: ...
    async def substituir_ficha_adicional(
        self, adicional_id: int, itens: Sequence[ItemFichaTecnica]
    ) -> None: ...
