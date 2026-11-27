from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.financeiro.entities import (
    CategoriaFinanceira,
    Lancamento,
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)


@dataclass(frozen=True)
class FiltrosLancamento:
    tipo: TipoLancamento | None = None
    status: StatusLancamento | None = None
    categoria_id: int | None = None
    atrasados: bool = False
    hoje: date | None = None
    vencimento_de: date | None = None
    vencimento_ate: date | None = None
    contraparte: str | None = None


class FinanceiroRepository(Protocol):
    async def adicionar_categoria(self, categoria: CategoriaFinanceira) -> CategoriaFinanceira: ...
    async def obter_categoria(self, categoria_id: int) -> CategoriaFinanceira | None: ...
    async def obter_categoria_por_nome(
        self, nome: str, tipo: TipoCategoria
    ) -> CategoriaFinanceira | None: ...

    async def atualizar_categoria(self, categoria: CategoriaFinanceira) -> CategoriaFinanceira: ...
    async def listar_categorias(
        self, tipo: TipoCategoria | None, ativo: bool | None
    ) -> list[CategoriaFinanceira]: ...

    async def adicionar_lancamento(self, lancamento: Lancamento) -> Lancamento: ...
    async def obter_lancamento(
        self, lancamento_id: int, *, para_atualizar: bool = False
    ) -> Lancamento | None: ...
    async def atualizar_lancamento(self, lancamento: Lancamento) -> Lancamento: ...
    async def listar_lancamentos(
        self, filtros: FiltrosLancamento, limit: int, offset: int
    ) -> tuple[list[Lancamento], int]: ...
