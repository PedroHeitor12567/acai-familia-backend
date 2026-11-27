from datetime import date, timedelta

from app.application.dashboard.estoque_critico import contar_niveis
from app.application.dashboard.ports import DashboardQueries
from app.application.dashboard.resumo_vendas import comparar
from app.application.shared.permissoes import exigir_gestor
from app.domain.caixa.regras import valor_esperado
from app.domain.dashboard.calculos import montar_estoque_critico
from app.domain.dashboard.modelos import (
    ResumoCaixa,
    ResumoContas,
    ResumoEstoque,
    VendasHoje,
    VisaoGeral,
)
from app.domain.dashboard.periodo import Periodo
from app.domain.financeiro.entities import TipoLancamento
from app.domain.usuarios.entities import Usuario


class ObterVisaoGeral:
    """Números de "hoje" da tela inicial, reaproveitando as consultas dos demais endpoints.
    Qualquer falha vira erro da resposta inteira: nunca devolve número faltando ou zerado."""

    def __init__(self, queries: DashboardQueries) -> None:
        self._q = queries

    async def executar(self, ator: Usuario, hoje: date) -> VisaoGeral:
        exigir_gestor(ator)
        mesmo_dia_semana_anterior = hoje - timedelta(days=7)
        atual, anterior = await self._q.comparativo_vendas(
            Periodo(hoje, hoje), Periodo(mesmo_dia_semana_anterior, mesmo_dia_semana_anterior)
        )
        ticket_atual, ticket_anterior, variacoes = comparar(atual, anterior)
        vendas_hoje = VendasHoje(
            data=hoje,
            comparado_com=mesmo_dia_semana_anterior,
            faturamento=atual.faturamento,
            qtd_comandas=atual.qtd_comandas,
            ticket_medio=ticket_atual,
            anterior=anterior,
            ticket_medio_anterior=ticket_anterior,
            variacao_pct=variacoes,
        )

        aberta = await self._q.caixa_aberto()
        caixa = (
            ResumoCaixa(aberto=False, sessao_id=None, saldo_dinheiro=None)
            if aberta is None
            else ResumoCaixa(
                aberto=True,
                sessao_id=aberta.sessao_id,
                saldo_dinheiro=valor_esperado(
                    aberta.valor_abertura,
                    [aberta.pagamentos_dinheiro],
                    [aberta.suprimentos],
                    [aberta.sangrias],
                ),
            )
        )

        zerados, em_alerta = contar_niveis(montar_estoque_critico(await self._q.insumos_criticos()))
        contas = await self._q.posicao_contas(hoje)
        pagar, receber = contas[TipoLancamento.PAGAR], contas[TipoLancamento.RECEBER]

        return VisaoGeral(
            vendas_hoje=vendas_hoje,
            comandas_abertas=await self._q.comandas_abertas(),
            caixa=caixa,
            estoque=ResumoEstoque(total_zerados=zerados, total_criticos=em_alerta),
            contas=ResumoContas(
                qtd_atrasadas_pagar=pagar.qtd_atrasado,
                valor_atrasado_pagar=pagar.total_atrasado,
                qtd_atrasadas_receber=receber.qtd_atrasado,
                valor_atrasado_receber=receber.total_atrasado,
                vence_hoje_pagar=pagar.vence_hoje_valor,
            ),
        )
