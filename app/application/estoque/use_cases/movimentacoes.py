from decimal import Decimal

from app.application.estoque.ports import FiltrosMovimentacao
from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.estoque.entities import MovimentacaoEstoque, TipoMovimentacao
from app.domain.exceptions import InsumoNaoEncontrado, OperacaoNaoPermitida
from app.domain.usuarios.entities import Usuario


class MovimentarEstoque:
    """Movimentação manual (entrada, saída ou ajuste de contagem) de um insumo.

    Saída que deixaria o saldo negativo levanta `EstoqueInsuficiente`; nada é gravado.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        insumo_id: int,
        tipo: TipoMovimentacao,
        quantidade: Decimal,
        motivo: str | None = None,
    ) -> MovimentacaoEstoque:
        exigir_gestor(ator)
        insumo = await self._uow.estoque.obter_insumo(insumo_id)
        if insumo is None:
            raise InsumoNaoEncontrado
        if not insumo.ativo:
            raise OperacaoNaoPermitida("insumo_inativo")
        try:
            movimentacao = await self._uow.estoque.movimentar(
                insumo_id, tipo, quantidade, ator.id_persistido, motivo
            )
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "movimentar",
                "insumo",
                str(insumo_id),
                {
                    "tipo": str(tipo),
                    "quantidade": str(movimentacao.quantidade),
                    "saldo_antes": str(movimentacao.saldo_antes),
                    "saldo_apos": str(movimentacao.saldo_apos),
                    "motivo": motivo,
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()  # solta o lock da linha do insumo
            raise
        return movimentacao


class ListarMovimentacoes:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, insumo_id: int, filtros: FiltrosMovimentacao, limit: int, offset: int
    ) -> tuple[list[MovimentacaoEstoque], int]:
        exigir_gestor(ator)
        if await self._uow.estoque.obter_insumo(insumo_id) is None:
            raise InsumoNaoEncontrado
        return await self._uow.estoque.listar_movimentacoes(insumo_id, filtros, limit, offset)
