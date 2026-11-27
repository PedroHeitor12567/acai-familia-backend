from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.domain.caixa.entities import MovimentoCaixa, Pagamento, SessaoCaixa, StatusSessao


@dataclass(frozen=True)
class FiltrosSessao:
    status: StatusSessao | None = None
    de: datetime | None = None
    ate: datetime | None = None


class CaixaRepository(Protocol):
    async def adicionar_sessao(self, sessao: SessaoCaixa) -> SessaoCaixa: ...

    async def obter_sessao(
        self, sessao_id: int, *, para_atualizar: bool = False
    ) -> SessaoCaixa | None: ...

    async def obter_sessao_aberta(self, *, para_atualizar: bool = False) -> SessaoCaixa | None: ...

    async def listar_sessoes(
        self, filtros: FiltrosSessao, limit: int, offset: int
    ) -> tuple[list[SessaoCaixa], int]: ...

    async def marcar_sessao_fechada(self, sessao: SessaoCaixa) -> None: ...

    async def adicionar_movimento(self, movimento: MovimentoCaixa) -> MovimentoCaixa: ...
    async def listar_movimentos(self, sessao_id: int) -> list[MovimentoCaixa]: ...

    async def adicionar_pagamento(self, pagamento: Pagamento) -> Pagamento: ...
    async def listar_pagamentos_da_sessao(self, sessao_id: int) -> list[Pagamento]: ...
    async def listar_pagamentos_da_comanda(self, comanda_id: int) -> list[Pagamento]: ...
