from app.application.comandas.dto import DetalheComanda
from app.application.comandas.ports import FiltrosComanda
from app.application.shared.permissoes import exigir_operador_comanda
from app.application.unit_of_work import UnitOfWork
from app.domain.caixa.entities import Pagamento
from app.domain.comandas.entities import Comanda, StatusComanda
from app.domain.exceptions import ComandaNaoEncontrada
from app.domain.usuarios.entities import Usuario


class ObterComanda:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, comanda_id: int) -> DetalheComanda:
        exigir_operador_comanda(ator)
        comanda = await self._uow.comandas.obter(comanda_id)
        if comanda is None:
            raise ComandaNaoEncontrada
        pagamentos: list[Pagamento] = []
        if comanda.status is StatusComanda.FECHADA:
            pagamentos = await self._uow.caixa.listar_pagamentos_da_comanda(comanda_id)
        return DetalheComanda(comanda, pagamentos)


class ListarComandas:
    """Abertas por `aberta_em` crescente (as mais antigas primeiro, útil no balcão); as demais
    da mais recente para a mais antiga."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, filtros: FiltrosComanda, limit: int, offset: int
    ) -> tuple[list[Comanda], int]:
        exigir_operador_comanda(ator)
        return await self._uow.comandas.listar(filtros, limit, offset)
