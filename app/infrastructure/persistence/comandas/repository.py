from datetime import datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.comandas.ports import FiltrosComanda
from app.domain.comandas.entities import (
    AdicionalItem,
    Comanda,
    ItemComanda,
    OrigemComanda,
    StatusComanda,
)
from app.domain.exceptions import ComandaNaoEncontrada, ItemComandaNaoEncontrado
from app.infrastructure.persistence.comandas.models import (
    ComandaModel,
    ItemComandaAdicionalModel,
    ItemComandaModel,
)
from app.infrastructure.persistence.utils import escapar_like


def _item(m: ItemComandaModel) -> ItemComanda:
    return ItemComanda(
        id=m.id,
        produto_id=m.produto_id,
        tamanho_id=m.tamanho_id,
        nome_produto=m.nome_produto,
        nome_tamanho=m.nome_tamanho,
        preco_unitario=m.preco_unitario,
        quantidade=m.quantidade,
        observacao=m.observacao,
        adicionais=[
            AdicionalItem(a.adicional_id, a.nome, a.preco_unitario, a.quantidade)
            for a in m.adicionais
        ],
    )


def _comanda(m: ComandaModel) -> Comanda:
    return Comanda(
        id=m.id,
        cliente_nome=m.cliente_nome,
        origem=OrigemComanda(m.origem),
        cliente_contato=m.cliente_contato,
        observacao=m.observacao,
        status=StatusComanda(m.status),
        itens=[_item(i) for i in m.itens],
        aberta_por_id=m.aberta_por_id,
        fechada_por_id=m.fechada_por_id,
        aberta_em=m.aberta_em,
        fechada_em=m.fechada_em,
        total_fechado=m.total,
    )


class SqlAlchemyComandaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _modelo(self, comanda_id: int) -> ComandaModel:
        m = await self._s.get(ComandaModel, comanda_id)
        if m is None:
            raise ComandaNaoEncontrada
        return m

    async def adicionar(self, comanda: Comanda) -> Comanda:
        m = ComandaModel(
            cliente_nome=comanda.cliente_nome,
            origem=str(comanda.origem),
            cliente_contato=comanda.cliente_contato,
            observacao=comanda.observacao,
            status=str(comanda.status),
            aberta_por_id=comanda.aberta_por_id,
            aberta_em=comanda.aberta_em,
            itens=[],  # evita lazy load (proibido em async) ao mapear de volta
        )
        self._s.add(m)
        await self._s.flush()
        return _comanda(m)

    async def obter(self, comanda_id: int, *, para_atualizar: bool = False) -> Comanda | None:
        # `populate_existing`: se a comanda já está na sessão (lida antes de esperar o lock),
        # sem isso status e itens velhos seriam reaproveitados em vez dos recém-commitados.
        consulta = (
            select(ComandaModel)
            .where(ComandaModel.id == comanda_id)
            .execution_options(populate_existing=True)
        )
        if para_atualizar:
            consulta = consulta.with_for_update()
        m = await self._s.scalar(consulta)
        return _comanda(m) if m else None

    async def adicionar_item(self, comanda_id: int, item: ItemComanda) -> ItemComanda:
        m = ItemComandaModel(
            comanda_id=comanda_id,
            produto_id=item.produto_id,
            tamanho_id=item.tamanho_id,
            nome_produto=item.nome_produto,
            nome_tamanho=item.nome_tamanho,
            quantidade=item.quantidade,
            preco_unitario=item.preco_unitario,
            observacao=item.observacao,
            adicionais=[
                ItemComandaAdicionalModel(
                    adicional_id=a.adicional_id,
                    nome=a.nome,
                    quantidade=a.quantidade,
                    preco_unitario=a.preco_unitario,
                )
                for a in item.adicionais
            ],
        )
        self._s.add(m)
        await self._s.flush()
        return _item(m)

    async def _modelo_item(self, comanda_id: int, item_id: int) -> ItemComandaModel:
        m = await self._s.get(ItemComandaModel, item_id)
        if m is None or m.comanda_id != comanda_id:
            raise ItemComandaNaoEncontrado
        return m

    async def atualizar_item(
        self, comanda_id: int, item_id: int, quantidade: int, observacao: str | None
    ) -> None:
        m = await self._modelo_item(comanda_id, item_id)
        m.quantidade, m.observacao = quantidade, observacao
        await self._s.flush()

    async def remover_item(self, comanda_id: int, item_id: int) -> None:
        m = await self._modelo_item(comanda_id, item_id)
        await self._s.delete(m)
        await self._s.flush()

    async def marcar_fechada(
        self, comanda_id: int, fechada_por_id: int, fechada_em: datetime, total: Decimal
    ) -> None:
        m = await self._modelo(comanda_id)
        m.status = str(StatusComanda.FECHADA)
        m.fechada_por_id, m.fechada_em, m.total = fechada_por_id, fechada_em, total
        await self._s.flush()

    async def marcar_cancelada(self, comanda_id: int) -> None:
        m = await self._modelo(comanda_id)
        m.status = str(StatusComanda.CANCELADA)
        await self._s.flush()

    async def listar(
        self, filtros: FiltrosComanda, limit: int, offset: int
    ) -> tuple[list[Comanda], int]:
        condicoes: list[ColumnElement[bool]] = []
        if filtros.status is not None:
            condicoes.append(ComandaModel.status == str(filtros.status))
        if filtros.origem is not None:
            condicoes.append(ComandaModel.origem == str(filtros.origem))
        if filtros.cliente:
            condicoes.append(
                ComandaModel.cliente_nome.ilike(f"%{escapar_like(filtros.cliente)}%", escape="\\")
            )
        if filtros.aberta_por_id is not None:
            condicoes.append(ComandaModel.aberta_por_id == filtros.aberta_por_id)
        if filtros.de is not None:
            condicoes.append(ComandaModel.aberta_em >= filtros.de)
        if filtros.ate is not None:
            condicoes.append(ComandaModel.aberta_em <= filtros.ate)

        total = await self._s.scalar(
            select(func.count()).select_from(ComandaModel).where(*condicoes)
        )
        eh_aberta = ComandaModel.status == str(StatusComanda.ABERTA)
        resultado = await self._s.scalars(
            select(ComandaModel)
            .where(*condicoes)
            .order_by(
                # abertas primeiro, da mais antiga para a mais nova; as demais, do mais recente
                case((eh_aberta, 0), else_=1),
                case((eh_aberta, ComandaModel.aberta_em)).asc(),
                ComandaModel.aberta_em.desc(),
                ComandaModel.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return [_comanda(m) for m in resultado.all()], total or 0
