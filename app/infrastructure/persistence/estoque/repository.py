from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.estoque.ports import FiltrosInsumo, FiltrosMovimentacao
from app.domain.estoque.entities import (
    Insumo,
    ItemFichaTecnica,
    MovimentacaoEstoque,
    TipoMovimentacao,
    UnidadeMedida,
)
from app.domain.estoque.regras import calcular_movimentacao
from app.domain.exceptions import InsumoNaoEncontrado
from app.infrastructure.persistence.estoque.models import (
    InsumoModel,
    ItemFichaAdicionalModel,
    ItemFichaTecnicaModel,
    MovimentacaoEstoqueModel,
)
from app.infrastructure.persistence.utils import escapar_like


def _insumo(m: InsumoModel) -> Insumo:
    return Insumo(
        id=m.id,
        nome=m.nome,
        unidade=UnidadeMedida(m.unidade),
        estoque_minimo=m.estoque_minimo,
        estoque_atual=m.estoque_atual,
        ativo=m.ativo,
    )


def _movimentacao(m: MovimentacaoEstoqueModel) -> MovimentacaoEstoque:
    return MovimentacaoEstoque(
        id=m.id,
        insumo_id=m.insumo_id,
        tipo=TipoMovimentacao(m.tipo),
        quantidade=m.quantidade,
        saldo_antes=m.saldo_antes,
        saldo_apos=m.saldo_apos,
        motivo=m.motivo,
        usuario_id=m.usuario_id,
        criado_em=m.criado_em,
    )


class SqlAlchemyEstoqueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def obter_insumo(self, insumo_id: int) -> Insumo | None:
        m = await self._s.get(InsumoModel, insumo_id)
        return _insumo(m) if m else None

    async def obter_insumo_por_nome(self, nome: str) -> Insumo | None:
        m = await self._s.scalar(
            select(InsumoModel).where(func.lower(InsumoModel.nome) == nome.lower())
        )
        return _insumo(m) if m else None

    async def adicionar_insumo(self, insumo: Insumo) -> Insumo:
        m = InsumoModel(
            nome=insumo.nome,
            unidade=str(insumo.unidade),
            estoque_minimo=insumo.estoque_minimo,
            estoque_atual=insumo.estoque_atual,
            ativo=insumo.ativo,
        )
        self._s.add(m)
        await self._s.flush()
        return _insumo(m)

    async def atualizar_insumo(self, insumo: Insumo) -> Insumo:
        # Saldo e unidade ficam de fora de propósito: o saldo só muda em `movimentar`.
        m = await self._s.get(InsumoModel, insumo.id_persistido)
        if m is None:
            raise ValueError("Insumo não existe")
        m.nome, m.estoque_minimo, m.ativo = insumo.nome, insumo.estoque_minimo, insumo.ativo
        await self._s.flush()
        return _insumo(m)

    async def listar_insumos(
        self, filtros: FiltrosInsumo, limit: int, offset: int
    ) -> tuple[list[Insumo], int]:
        condicoes: list[ColumnElement[bool]] = []
        if filtros.ativo is not None:
            condicoes.append(InsumoModel.ativo.is_(filtros.ativo))
        if filtros.abaixo_do_minimo is True:
            condicoes.append(InsumoModel.estoque_atual <= InsumoModel.estoque_minimo)
        elif filtros.abaixo_do_minimo is False:
            condicoes.append(InsumoModel.estoque_atual > InsumoModel.estoque_minimo)
        if filtros.q:
            condicoes.append(InsumoModel.nome.ilike(f"%{escapar_like(filtros.q)}%", escape="\\"))
        total = await self._s.scalar(
            select(func.count()).select_from(InsumoModel).where(*condicoes)
        )
        resultado = await self._s.scalars(
            select(InsumoModel)
            .where(*condicoes)
            .order_by(InsumoModel.nome, InsumoModel.id)
            .limit(limit)
            .offset(offset)
        )
        return [_insumo(m) for m in resultado.all()], total or 0

    async def movimentar(
        self,
        insumo_id: int,
        tipo: TipoMovimentacao,
        quantidade: Decimal,
        usuario_id: int | None,
        motivo: str | None = None,
    ) -> MovimentacaoEstoque:
        # FOR UPDATE serializa movimentações concorrentes do mesmo insumo: a segunda espera o
        # commit da primeira e lê o saldo já atualizado. `populate_existing` é essencial: se o
        # insumo já está na sessão (lido antes), sem isso o saldo velho seria reaproveitado.
        insumo = await self._s.scalar(
            select(InsumoModel)
            .where(InsumoModel.id == insumo_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if insumo is None:
            raise InsumoNaoEncontrado
        resultado = calcular_movimentacao(tipo, insumo.estoque_atual, quantidade)
        saldo_antes = insumo.estoque_atual
        insumo.estoque_atual = resultado.saldo_apos
        mov = MovimentacaoEstoqueModel(
            insumo_id=insumo_id,
            tipo=str(tipo),
            quantidade=resultado.quantidade_registrada,
            saldo_antes=saldo_antes,
            saldo_apos=resultado.saldo_apos,
            motivo=motivo,
            usuario_id=usuario_id,
        )
        self._s.add(mov)
        await self._s.flush()
        return _movimentacao(mov)

    async def aplicar_saida(
        self,
        insumo_id: int,
        quantidade: Decimal,
        usuario_id: int | None,
        motivo: str | None = None,
    ) -> MovimentacaoEstoque:
        return await self.movimentar(
            insumo_id, TipoMovimentacao.SAIDA, quantidade, usuario_id, motivo
        )

    async def listar_movimentacoes(
        self, insumo_id: int, filtros: FiltrosMovimentacao, limit: int, offset: int
    ) -> tuple[list[MovimentacaoEstoque], int]:
        condicoes: list[ColumnElement[bool]] = [MovimentacaoEstoqueModel.insumo_id == insumo_id]
        if filtros.tipo is not None:
            condicoes.append(MovimentacaoEstoqueModel.tipo == str(filtros.tipo))
        if filtros.de is not None:
            condicoes.append(MovimentacaoEstoqueModel.criado_em >= filtros.de)
        if filtros.ate is not None:
            condicoes.append(MovimentacaoEstoqueModel.criado_em <= filtros.ate)
        total = await self._s.scalar(
            select(func.count()).select_from(MovimentacaoEstoqueModel).where(*condicoes)
        )
        resultado = await self._s.scalars(
            select(MovimentacaoEstoqueModel)
            .where(*condicoes)
            .order_by(MovimentacaoEstoqueModel.criado_em.desc(), MovimentacaoEstoqueModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_movimentacao(m) for m in resultado.all()], total or 0


class SqlAlchemyFichaTecnicaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def obter_ficha_produto(self, produto_id: int, tamanho_id: int) -> list[ItemFichaTecnica]:
        resultado = await self._s.scalars(
            select(ItemFichaTecnicaModel)
            .where(
                ItemFichaTecnicaModel.produto_id == produto_id,
                ItemFichaTecnicaModel.tamanho_id == tamanho_id,
            )
            .order_by(ItemFichaTecnicaModel.insumo_id)
        )
        return [ItemFichaTecnica(m.insumo_id, m.quantidade) for m in resultado.all()]

    async def substituir_ficha_produto(
        self, produto_id: int, tamanho_id: int, itens: Sequence[ItemFichaTecnica]
    ) -> None:
        await self._s.execute(
            delete(ItemFichaTecnicaModel).where(
                ItemFichaTecnicaModel.produto_id == produto_id,
                ItemFichaTecnicaModel.tamanho_id == tamanho_id,
            )
        )
        self._s.add_all(
            ItemFichaTecnicaModel(
                produto_id=produto_id,
                tamanho_id=tamanho_id,
                insumo_id=i.insumo_id,
                quantidade=i.quantidade,
            )
            for i in itens
        )
        await self._s.flush()

    async def obter_ficha_adicional(self, adicional_id: int) -> list[ItemFichaTecnica]:
        resultado = await self._s.scalars(
            select(ItemFichaAdicionalModel)
            .where(ItemFichaAdicionalModel.adicional_id == adicional_id)
            .order_by(ItemFichaAdicionalModel.insumo_id)
        )
        return [ItemFichaTecnica(m.insumo_id, m.quantidade) for m in resultado.all()]

    async def substituir_ficha_adicional(
        self, adicional_id: int, itens: Sequence[ItemFichaTecnica]
    ) -> None:
        await self._s.execute(
            delete(ItemFichaAdicionalModel).where(
                ItemFichaAdicionalModel.adicional_id == adicional_id
            )
        )
        self._s.add_all(
            ItemFichaAdicionalModel(
                adicional_id=adicional_id, insumo_id=i.insumo_id, quantidade=i.quantidade
            )
            for i in itens
        )
        await self._s.flush()
