"""Casos de uso de comandas sobre SQLite (permissões, preço congelado, estados, auditoria)."""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.comandas.use_cases.abrir import AbrirComanda
from app.application.comandas.use_cases.itens import (
    AdicionalPedido,
    AdicionarItem,
    AtualizarItem,
    RemoverItem,
)
from app.bootstrap.container import build_uow
from app.domain.cardapio.entities import ProdutoTamanho
from app.domain.comandas.entities import StatusComanda
from app.domain.comandas.regras import total_efetivo
from app.domain.exceptions import (
    AdicionalNaoEncontrado,
    ComandaNaoEncontrada,
    ItemComandaInvalido,
    ItemComandaNaoEncontrado,
    OperacaoNaoPermitida,
    ProdutoNaoEncontrado,
    TamanhoNaoEncontrado,
    ValorInvalido,
)
from app.domain.usuarios.entities import Papel
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from tests.comandas_helpers import Semente, semear_cardapio, semear_usuario

D = Decimal


@pytest.fixture
async def s(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


async def _acoes(s: AsyncSession) -> list[tuple[str, str]]:
    linhas = await s.execute(
        select(AuditLogModel.acao, AuditLogModel.entidade).order_by(AuditLogModel.id)
    )
    return [(a, e) for a, e in linhas.all()]


@pytest.mark.parametrize("papel", list(Papel))
async def test_todo_papel_operacional_abre_e_lanca_itens(s: AsyncSession, papel: Papel) -> None:
    ator = await semear_usuario(s, papel)
    sem = await semear_cardapio(s)
    comanda = await AbrirComanda(build_uow(s)).executar(ator, "  Ana  ")
    assert comanda.cliente_nome == "Ana"
    assert comanda.status is StatusComanda.ABERTA and comanda.aberta_por_id == ator.id
    com_item = await AdicionarItem(build_uow(s)).executar(
        ator, comanda.id_persistido, sem.produto_id, sem.tamanho_id
    )
    assert len(com_item.itens) == 1


async def test_abrir_valida_o_nome_e_audita(s: AsyncSession) -> None:
    ator = await semear_usuario(s, Papel.ATENDENTE)
    uow = build_uow(s)
    for nome in ("", "   ", "x" * 121):
        with pytest.raises(ValorInvalido):
            await AbrirComanda(uow).executar(ator, nome)
    assert await _acoes(s) == []
    await AbrirComanda(uow).executar(ator, "Ana", cliente_contato=" 11999 ", observacao="mesa 3")
    assert await _acoes(s) == [("abrir", "comanda")]


async def test_item_congela_preco_e_nomes_mesmo_se_o_cardapio_mudar(s: AsyncSession) -> None:
    ator = await semear_usuario(s, Papel.ATENDENTE)
    sem = await semear_cardapio(s)
    uow = build_uow(s)
    comanda = await AbrirComanda(uow).executar(ator, "Ana")
    await AdicionarItem(uow).executar(
        ator,
        comanda.id_persistido,
        sem.produto_id,
        sem.tamanho_id,
        quantidade=2,
        adicionais=[AdicionalPedido(sem.adicional_id, 1)],
    )

    # o cardápio muda depois: preço do produto, do adicional e nome do produto
    await uow.cardapio.definir_preco(ProdutoTamanho(sem.produto_id, sem.tamanho_id, D("99.00")))
    adicional = await uow.cardapio.obter_adicional(sem.adicional_id)
    produto = await uow.cardapio.obter_produto(sem.produto_id)
    assert adicional is not None and produto is not None
    adicional.preco, produto.nome = D("9.00"), "Renomeado"
    await uow.cardapio.atualizar_adicional(adicional)
    await uow.cardapio.atualizar_produto(produto)
    await s.commit()

    relida = await uow.comandas.obter(comanda.id_persistido)
    assert relida is not None
    item = relida.itens[0]
    assert (item.nome_produto, item.nome_tamanho) == ("Tradicional", "500 ml")
    assert item.preco_unitario == D("18.90")
    assert item.adicionais[0].preco_unitario == D("2.50") and item.adicionais[0].nome == "Granola"
    assert total_efetivo(relida) == D("42.80")  # (18,90 + 2,50) * 2

    # um item novo, lançado agora, já usa o preço novo
    depois = await AdicionarItem(uow).executar(
        ator, comanda.id_persistido, sem.produto_id, sem.tamanho_id
    )
    assert depois.itens[1].preco_unitario == D("99.00")


async def test_valida_produto_tamanho_e_adicionais(s: AsyncSession) -> None:
    ator = await semear_usuario(s, Papel.ATENDENTE)
    sem = await semear_cardapio(s)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(ator, "Ana")).id_persistido
    lancar = AdicionarItem(uow).executar

    with pytest.raises(ProdutoNaoEncontrado):
        await lancar(ator, cid, 999, sem.tamanho_id)
    with pytest.raises(TamanhoNaoEncontrado):
        await lancar(ator, cid, sem.produto_id, 999)
    with pytest.raises(AdicionalNaoEncontrado):
        await lancar(ator, cid, sem.produto_id, sem.tamanho_id, adicionais=[AdicionalPedido(999)])
    with pytest.raises(ComandaNaoEncontrada):
        await lancar(ator, 999, sem.produto_id, sem.tamanho_id)
    for ruim in (0, 100, -1):
        with pytest.raises(ValorInvalido):
            await lancar(ator, cid, sem.produto_id, sem.tamanho_id, quantidade=ruim)
    with pytest.raises(ValorInvalido):
        await lancar(
            ator,
            cid,
            sem.produto_id,
            sem.tamanho_id,
            adicionais=[AdicionalPedido(sem.adicional_id, 0)],
        )
    with pytest.raises(ItemComandaInvalido, match="adicional_repetido"):
        await lancar(
            ator,
            cid,
            sem.produto_id,
            sem.tamanho_id,
            adicionais=[AdicionalPedido(sem.adicional_id), AdicionalPedido(sem.adicional_id)],
        )
    assert (await uow.comandas.obter(cid)).itens == []  # type: ignore[union-attr]


async def test_inativos_e_produto_sem_preco_sao_recusados(s: AsyncSession) -> None:
    ator = await semear_usuario(s, Papel.ATENDENTE)
    sem = await semear_cardapio(s)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(ator, "Ana")).id_persistido
    produto = await uow.cardapio.obter_produto(sem.produto_id)
    tamanho = await uow.cardapio.obter_tamanho(sem.tamanho_id)
    adicional = await uow.cardapio.obter_adicional(sem.adicional_id)
    assert produto and tamanho and adicional

    outro_tamanho = await uow.cardapio.adicionar_tamanho(type(tamanho)("300 ml"))
    with pytest.raises(ItemComandaInvalido, match="produto_sem_preco"):
        await AdicionarItem(uow).executar(ator, cid, sem.produto_id, outro_tamanho.id_persistido)

    adicional.ativo = False
    await uow.cardapio.atualizar_adicional(adicional)
    with pytest.raises(ItemComandaInvalido, match="adicional_inativo"):
        await AdicionarItem(uow).executar(
            ator,
            cid,
            sem.produto_id,
            sem.tamanho_id,
            adicionais=[AdicionalPedido(sem.adicional_id)],
        )
    tamanho.ativo = False
    await uow.cardapio.atualizar_tamanho(tamanho)
    with pytest.raises(ItemComandaInvalido, match="tamanho_inativo"):
        await AdicionarItem(uow).executar(ator, cid, sem.produto_id, sem.tamanho_id)
    produto.ativo = False
    await uow.cardapio.atualizar_produto(produto)
    with pytest.raises(ItemComandaInvalido, match="produto_inativo"):
        await AdicionarItem(uow).executar(ator, cid, sem.produto_id, sem.tamanho_id)


async def _comanda_com_item(s: AsyncSession, sem: Semente, papel: Papel = Papel.ATENDENTE):  # type: ignore[no-untyped-def]
    ator = await semear_usuario(s, papel)
    uow = build_uow(s)
    comanda = await AbrirComanda(uow).executar(ator, "Ana")
    com_item = await AdicionarItem(uow).executar(
        ator,
        comanda.id_persistido,
        sem.produto_id,
        sem.tamanho_id,
        quantidade=2,
        observacao="sem granola",
    )
    return ator, comanda.id_persistido, com_item.itens[0].id_persistido


async def test_atualizar_e_remover_item(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    ator, cid, item_id = await _comanda_com_item(s, sem)
    uow = build_uow(s)

    atualizada = await AtualizarItem(uow).executar(ator, cid, item_id, quantidade=5)
    assert atualizada.itens[0].quantidade == 5
    assert atualizada.itens[0].observacao == "sem granola"  # None mantém
    atualizada = await AtualizarItem(uow).executar(ator, cid, item_id, observacao="")
    assert atualizada.itens[0].observacao is None and atualizada.itens[0].quantidade == 5
    with pytest.raises(ValorInvalido):
        await AtualizarItem(uow).executar(ator, cid, item_id, quantidade=100)
    with pytest.raises(ItemComandaNaoEncontrado):
        await AtualizarItem(uow).executar(ator, cid, 999, quantidade=1)

    await RemoverItem(uow).executar(ator, cid, item_id)
    assert (await uow.comandas.obter(cid)).itens == []  # type: ignore[union-attr]
    with pytest.raises(ItemComandaNaoEncontrado):
        await RemoverItem(uow).executar(ator, cid, item_id)
    assert [a for a, _ in await _acoes(s)][-2:] == ["atualizar_item", "remover_item"]


async def test_item_de_outra_comanda_nao_e_encontrado(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    ator, _, item_id = await _comanda_com_item(s, sem)
    uow = build_uow(s)
    outra = await AbrirComanda(uow).executar(ator, "Bia")
    with pytest.raises(ItemComandaNaoEncontrado):
        await RemoverItem(uow).executar(ator, outra.id_persistido, item_id)
    with pytest.raises(ItemComandaNaoEncontrado):
        await AtualizarItem(uow).executar(ator, outra.id_persistido, item_id, quantidade=1)


@pytest.mark.parametrize("status", [StatusComanda.CANCELADA, StatusComanda.FECHADA])
async def test_comanda_nao_aberta_nao_aceita_alteracao_de_itens(
    s: AsyncSession, status: StatusComanda
) -> None:
    sem = await semear_cardapio(s)
    ator, cid, item_id = await _comanda_com_item(s, sem)
    uow = build_uow(s)
    if status is StatusComanda.CANCELADA:
        await uow.comandas.marcar_cancelada(cid)
    else:
        from datetime import UTC, datetime

        await uow.comandas.marcar_fechada(cid, ator.id_persistido, datetime.now(UTC), D("37.80"))
    await s.commit()

    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await AdicionarItem(uow).executar(ator, cid, sem.produto_id, sem.tamanho_id)
    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await AtualizarItem(uow).executar(ator, cid, item_id, quantidade=1)
    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await RemoverItem(uow).executar(ator, cid, item_id)
