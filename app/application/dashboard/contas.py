from datetime import date

from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.modelos import PosicaoContas
from app.domain.financeiro.entities import TipoLancamento
from app.domain.usuarios.entities import Usuario

LIMITE_PROXIMOS_VENCIMENTOS = 10


class ObterPosicaoContas:
    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(self, ator: Usuario, hoje: date) -> PosicaoContas:
        exigir_gestor(ator)
        posicao = await self._q.posicao_contas(hoje)
        proximos = await self._q.proximos_vencimentos(hoje, LIMITE_PROXIMOS_VENCIMENTOS)
        return PosicaoContas(
            hoje=hoje,
            pagar=posicao[TipoLancamento.PAGAR],
            receber=posicao[TipoLancamento.RECEBER],
            proximos_vencimentos=proximos,
        )
