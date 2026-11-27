from app.application.dashboard.ports import DashboardQueries
from app.application.shared.permissoes import exigir_gestor
from app.domain.dashboard.calculos import montar_estoque_critico
from app.domain.dashboard.modelos import EstoqueCritico, NivelEstoque, PaginaEstoqueCritico
from app.domain.usuarios.entities import Usuario


def contar_niveis(criticos: list[EstoqueCritico]) -> tuple[int, int]:
    zerados = sum(1 for c in criticos if c.nivel is NivelEstoque.ZERADO)
    return zerados, len(criticos) - zerados


class ObterEstoqueCritico:
    """O conjunto crítico é limitado pelos insumos cadastrados (poucas dezenas), então a
    ordenação e a paginação acontecem em memória sobre uma única consulta; assim os contadores
    valem para todos os críticos, mesmo com `nivel` ou página fora do alcance."""

    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(
        self, ator: Usuario, nivel: NivelEstoque | None, limit: int, offset: int
    ) -> PaginaEstoqueCritico:
        exigir_gestor(ator)
        criticos = montar_estoque_critico(await self._q.insumos_criticos())
        zerados, em_alerta = contar_niveis(criticos)
        filtrados = [c for c in criticos if nivel is None or c.nivel is nivel]
        return PaginaEstoqueCritico(
            total_zerados=zerados,
            total_criticos=em_alerta,
            itens=filtrados[offset : offset + limit],
            total=len(filtrados),
            limit=limit,
            offset=offset,
        )
