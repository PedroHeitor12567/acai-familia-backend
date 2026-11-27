import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.caixa.use_cases.sessoes import AbrirCaixa
from app.application.comandas.use_cases.abrir import AbrirComanda
from app.application.comandas.use_cases.itens import AdicionarItem
from app.bootstrap.container import build_uow
from app.domain.cardapio.entities import Categoria, Produto, ProdutoTamanho, Tamanho
from app.domain.comandas.entities import StatusComanda
from app.domain.estoque.entities import (
    Insumo,
    ItemFichaTecnica,
    TipoMovimentacao,
    UnidadeMedida,
)
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.caixa.models import (
    MovimentoCaixaModel,
    PagamentoModel,
    SessaoCaixaModel,
)
from app.infrastructure.persistence.cardapio.models import (
    CategoriaModel,
    ProdutoModel,
    ProdutoTamanhoModel,
    TamanhoModel,
)
from app.infrastructure.persistence.comandas.models import ComandaModel
from app.infrastructure.persistence.estoque.models import (
    InsumoModel,
    ItemFichaTecnicaModel,
    MovimentacaoEstoqueModel,
)
from app.infrastructure.persistence.usuarios.models import UsuarioModel
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository
from tests.comandas_helpers import fechar_com_pix

D = Decimal
T = TypeVar("T")
Factory = async_sessionmaker[AsyncSession]


@dataclass
class Cenario:
    factory: Factory
    ator: Usuario
    tamanho_id: int
    insumos: list[int]
    produtos: dict[str, int] = field(default_factory=dict)
    sessao_id: int = 0

    async def saldo(self, insumo_id: int) -> Decimal:
        async with self.factory() as s:
            saldo = await s.scalar(
                select(InsumoModel.estoque_atual).where(InsumoModel.id == insumo_id)
            )
        assert saldo is not None
        return saldo

    async def saidas(self, insumo_id: int) -> int:
        async with self.factory() as s:
            total = await s.scalar(
                select(func.count())
                .select_from(MovimentacaoEstoqueModel)
                .where(
                    MovimentacaoEstoqueModel.insumo_id == insumo_id,
                    MovimentacaoEstoqueModel.tipo == "saida",
                )
            )
        return total or 0

    async def comanda_com_item(self, produto: str = "todos", quantidade: int = 1) -> int:
        async with self.factory() as s:
            uow = build_uow(s)
            cid = (await AbrirComanda(uow).executar(self.ator, "Concorrência")).id_persistido
            await AdicionarItem(uow).executar(
                self.ator, cid, self.produtos[produto], self.tamanho_id, quantidade
            )
        return cid

    async def fechar(self, comanda_id: int) -> None:
        async with self.factory() as s:
            await fechar_com_pix(build_uow(s), self.ator, comanda_id)

    async def pagamentos(self, comanda_id: int) -> int:
        async with self.factory() as s:
            total = await s.scalar(
                select(func.count())
                .select_from(PagamentoModel)
                .where(PagamentoModel.comanda_id == comanda_id)
            )
        return total or 0

    async def status(self, comanda_id: int) -> StatusComanda:
        async with self.factory() as s:
            comanda = await build_uow(s).comandas.obter(comanda_id)
        assert comanda is not None
        return comanda.status


async def _semear(
    factory: Factory, saldos: list[str], fichas: dict[str, list[int]]
) -> tuple[Cenario, Callable[[], Awaitable[None]]]:
    sufixo = uuid.uuid4().hex[:8]
    async with factory() as s:
        uow = build_uow(s)
        ator = await SqlAlchemyUsuarioRepository(s).adicionar(
            Usuario("Caixa PG", f"caixa-{sufixo}@acai.com", "x", Papel.CAIXA)
        )
        categoria = await uow.cardapio.adicionar_categoria(Categoria(f"Cat-{sufixo}"))
        tamanho = await uow.cardapio.adicionar_tamanho(Tamanho(f"Tam-{sufixo}"))
        insumos: list[int] = []
        for i, saldo in enumerate(saldos):
            insumo = await uow.estoque.adicionar_insumo(
                Insumo(f"Insumo{i}-{sufixo}", UnidadeMedida.UN)
            )
            insumos.append(insumo.id_persistido)
            if D(saldo) > 0:
                await uow.estoque.movimentar(
                    insumo.id_persistido, TipoMovimentacao.ENTRADA, D(saldo), None
                )
        cenario = Cenario(factory, ator, tamanho.id_persistido, insumos)
        sessao = await AbrirCaixa(uow).executar(ator, D("0.00"))
        cenario.sessao_id = sessao.id_persistido
        for nome, posicoes in fichas.items():
            produto = await uow.cardapio.adicionar_produto(
                Produto(f"{nome}-{sufixo}", categoria.id_persistido)
            )
            await uow.cardapio.definir_preco(
                ProdutoTamanho(produto.id_persistido, tamanho.id_persistido, D("10.00"))
            )
            await uow.ficha_tecnica.substituir_ficha_produto(
                produto.id_persistido,
                tamanho.id_persistido,
                [ItemFichaTecnica(insumos[p], D("1")) for p in posicoes],
            )
            cenario.produtos[nome] = produto.id_persistido
        await s.commit()

    async def limpar() -> None:
        async with factory() as s:
            comandas = select(ComandaModel.id).where(ComandaModel.aberta_por_id == ator.id)
            await s.execute(delete(PagamentoModel).where(PagamentoModel.comanda_id.in_(comandas)))
            await s.execute(delete(PagamentoModel).where(PagamentoModel.criado_por_id == ator.id))
            await s.execute(
                delete(MovimentoCaixaModel).where(MovimentoCaixaModel.criado_por_id == ator.id)
            )
            await s.execute(
                delete(SessaoCaixaModel).where(SessaoCaixaModel.aberta_por_id == ator.id)
            )
            await s.execute(delete(ComandaModel).where(ComandaModel.aberta_por_id == ator.id))
            await s.execute(
                delete(MovimentacaoEstoqueModel).where(
                    MovimentacaoEstoqueModel.insumo_id.in_(insumos)
                )
            )
            await s.execute(
                delete(ItemFichaTecnicaModel).where(ItemFichaTecnicaModel.insumo_id.in_(insumos))
            )
            ids_produtos = list(cenario.produtos.values())
            await s.execute(
                delete(ProdutoTamanhoModel).where(ProdutoTamanhoModel.produto_id.in_(ids_produtos))
            )
            await s.execute(delete(ProdutoModel).where(ProdutoModel.id.in_(ids_produtos)))
            await s.execute(delete(TamanhoModel).where(TamanhoModel.id == cenario.tamanho_id))
            await s.execute(delete(CategoriaModel).where(CategoriaModel.id == categoria.id))
            await s.execute(delete(InsumoModel).where(InsumoModel.id.in_(insumos)))
            await s.execute(delete(AuditLogModel).where(AuditLogModel.usuario_id == ator.id))
            await s.execute(delete(UsuarioModel).where(UsuarioModel.id == ator.id))
            await s.commit()

    return cenario, limpar


async def _cenario(
    factory: Factory, saldos: list[str], fichas: dict[str, list[int]] | None = None
) -> AsyncIterator[Cenario]:
    cenario, limpar = await _semear(factory, saldos, fichas or {"todos": [0, 1, 2]})
    try:
        yield cenario
    finally:
        await limpar()


async def _resultado(coro: Awaitable[T]) -> T | Exception:
    try:
        return await coro
    except Exception as erro:
        return erro
