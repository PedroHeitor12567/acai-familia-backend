from datetime import date

from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.fluxo import montar_fluxo
from app.domain.dashboard.modelos import FluxoCaixa
from app.domain.dashboard.periodo import Agrupamento, montar_periodo, validar_agrupamento
from app.domain.usuarios.entities import Usuario


class ObterFluxoCaixa:
    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(
        self,
        ator: Usuario,
        de: date | None,
        ate: date | None,
        hoje: date,
        agrupamento: Agrupamento,
        incluir_projecao: bool,
    ) -> FluxoCaixa:
        exigir_gestor(ator)
        # A projeção olha vencimentos futuros, então só ela aceita um período que passa de hoje.
        periodo = montar_periodo(de, ate, hoje, permite_futuro=incluir_projecao)
        validar_agrupamento(periodo, agrupamento)
        fatos = await self._q.fatos_fluxo_caixa(periodo, incluir_projecao)
        return montar_fluxo(periodo, agrupamento, fatos, incluir_projecao=incluir_projecao)
