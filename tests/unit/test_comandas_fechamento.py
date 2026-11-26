"""Fechar e cancelar comandas sobre SQLite: baixa de estoque, rollback total, estados terminais."""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.comandas.use_cases.abrir import AbrirComanda
from app.application.comandas.use_cases.fechamento import CancelarComanda, FecharComanda
from app.application.comandas.use_cases.itens import AdicionalPedido, AdicionarItem
from app.application.estoque.ports import FiltrosMovimentacao
from app.bootstrap.container import build_uow
from app.domain.cardapio.entities import ProdutoTamanho
from app.domain.comandas.entities import StatusComanda
from app.domain.comandas.regras import total_efetivo
from app.domain.estoque.entities import Insumo, ItemFichaTecnica, TipoMovimentacao, UnidadeMedida
from app.domain.exceptions import (
    ComandaNaoEncontrada,
    EstoqueInsuficienteNoFechamento,
    OperacaoNaoPermitida,
    PermissaoNegada,
    ValorInvalido,
)
from app.domain.usuarios.entities import Papel
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from tests.comandas_helpers import semear_cardapio, semear_usuario

D = Decimal


@pytest.fixture
async def s(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


async def _acoes(s: AsyncSession) -> list[str]:
    linhas = await s.scalars(select(AuditLogModel.acao).order_by(AuditLogModel.id))
    return list(linhas.all())


async def _saldo(s: AsyncSession, insumo_id: int) -> Decimal:
    s.expire_all()
    insumo = await build_uow(s).estoque.obter_insumo(insumo_id)
    assert insumo is not None
    return insumo.estoque_atual


async def _movimentacoes(s: AsyncSession, insumo_id: int) -> list[tuple[str, str | None]]:
    mov, _ = await build_uow(s).estoque.listar_movimentacoes(
        insumo_id, FiltrosMovimentacao(), 100, 0
    )
    return [(str(m.tipo), m.motivo) for m in reversed(mov)]


async def test_fechar_baixa_exatamente_o_consumo_da_ficha(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    await AdicionarItem(uow).executar(
        caixa, cid, sem.produto_id, sem.tamanho_id, 2, [AdicionalPedido(sem.adicional_id, 2)]
    )
    await AdicionarItem(uow).executar(caixa, cid, sem.produto_id, sem.tamanho_id, 1)

    r = await FecharComanda(uow).executar(caixa, cid)

    # polpa: 0,3*2 + 0,3*1 = 0,9 | granola: 0,02 * (2*2) = 0,08
    assert r.consumo == {sem.polpa_id: D("0.9"), sem.granola_id: D("0.08")}
    assert r.itens_sem_ficha == []
    assert await _saldo(s, sem.polpa_id) == D("9.1")
    assert await _saldo(s, sem.granola_id) == D("0.92")
    # uma saída por insumo (não por item), com o motivo da comanda
    assert await _movimentacoes(s, sem.polpa_id) == [
        ("entrada", "carga inicial"),
        ("saida", f"comanda:{cid}"),
    ]
    fechada = r.comanda
    assert fechada.status is StatusComanda.FECHADA
    assert fechada.fechada_por_id == caixa.id and fechada.fechada_em is not None
    assert fechada.total_fechado == D("66.70") == total_efetivo(fechada)  # 47,80 + 18,90


async def test_total_e_consumo_ficam_na_auditoria_e_o_total_nao_muda_com_o_cardapio(
    s: AsyncSession,
) -> None:
    sem = await semear_cardapio(s)
    gerente = await semear_usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(gerente, "Ana")).id_persistido
    await AdicionarItem(uow).executar(gerente, cid, sem.produto_id, sem.tamanho_id)
    await FecharComanda(uow).executar(gerente, cid)

    await uow.cardapio.definir_preco(ProdutoTamanho(sem.produto_id, sem.tamanho_id, D("50.00")))
    await s.commit()
    relida = await uow.comandas.obter(cid)
    assert relida is not None and total_efetivo(relida) == D("18.90")

    log = (await s.scalars(select(AuditLogModel).where(AuditLogModel.acao == "fechar"))).one()
    assert log.entidade_id == str(cid)
    assert log.detalhes == {
        "total": "18.90",
        "itens": 1,
        "consumo": {str(sem.polpa_id): "0.300"},
        "itens_sem_ficha": [],
    }


async def test_falta_de_estoque_faz_rollback_total_e_diz_qual_insumo(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    # três insumos na ficha; o de MAIOR id (o último a ser baixado) não tem saldo suficiente
    cobertura = await uow.estoque.adicionar_insumo(Insumo("Cobertura", UnidadeMedida.KG))
    await uow.estoque.movimentar(
        cobertura.id_persistido, TipoMovimentacao.ENTRADA, D("0.100"), None
    )
    await uow.ficha_tecnica.substituir_ficha_produto(
        sem.produto_id,
        sem.tamanho_id,
        [
            ItemFichaTecnica(sem.polpa_id, D("0.300")),
            ItemFichaTecnica(cobertura.id_persistido, D("0.050")),
        ],
    )
    await s.commit()
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    await AdicionarItem(uow).executar(
        caixa, cid, sem.produto_id, sem.tamanho_id, 3, [AdicionalPedido(sem.adicional_id)]
    )  # cobertura precisa de 0,150 e só há 0,100

    with pytest.raises(EstoqueInsuficienteNoFechamento) as erro:
        await FecharComanda(uow).executar(caixa, cid)

    assert erro.value.insumo_id == cobertura.id_persistido
    assert erro.value.insumo_nome == "Cobertura"
    assert (erro.value.disponivel, erro.value.solicitado) == (D("0.100"), D("0.150"))
    # polpa e granola (ids menores, baixados antes) voltam ao saldo original
    assert await _saldo(s, sem.polpa_id) == D("10")
    assert await _saldo(s, sem.granola_id) == D("1")
    assert await _saldo(s, cobertura.id_persistido) == D("0.100")
    for insumo_id in (sem.polpa_id, sem.granola_id, cobertura.id_persistido):
        assert all(tipo == "entrada" for tipo, _ in await _movimentacoes(s, insumo_id))
    relida = await uow.comandas.obter(cid)
    assert relida is not None and relida.status is StatusComanda.ABERTA
    assert relida.fechada_em is None and relida.total_fechado is None
    assert "fechar" not in await _acoes(s)


async def test_fechar_duas_vezes_baixa_uma_vez_so(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    await AdicionarItem(uow).executar(caixa, cid, sem.produto_id, sem.tamanho_id)
    await FecharComanda(uow).executar(caixa, cid)
    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await FecharComanda(uow).executar(caixa, cid)
    assert await _saldo(s, sem.polpa_id) == D("9.7")


async def test_nao_fecha_comanda_vazia_nem_inexistente(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    with pytest.raises(OperacaoNaoPermitida, match="comanda_vazia"):
        await FecharComanda(uow).executar(caixa, cid)
    with pytest.raises(ComandaNaoEncontrada):
        await FecharComanda(uow).executar(caixa, 999)


async def test_produto_sem_ficha_fecha_sem_baixar_e_avisa(s: AsyncSession) -> None:
    sem = await semear_cardapio(s, com_ficha=False)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    com_item = await AdicionarItem(uow).executar(caixa, cid, sem.produto_id, sem.tamanho_id)
    item_id = com_item.itens[0].id_persistido

    r = await FecharComanda(uow).executar(caixa, cid)

    assert r.itens_sem_ficha == [item_id] and r.consumo == {}
    assert r.comanda.status is StatusComanda.FECHADA
    assert await _saldo(s, sem.polpa_id) == D("10")
    log = (await s.scalars(select(AuditLogModel).where(AuditLogModel.acao == "fechar"))).one()
    assert log.detalhes is not None and log.detalhes["itens_sem_ficha"] == [item_id]


async def test_cancelar_nao_mexe_no_estoque_e_e_terminal(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    await AdicionarItem(uow).executar(caixa, cid, sem.produto_id, sem.tamanho_id)

    cancelada = await CancelarComanda(uow).executar(caixa, cid, "cliente desistiu")

    assert cancelada.status is StatusComanda.CANCELADA
    assert await _saldo(s, sem.polpa_id) == D("10")
    assert await _movimentacoes(s, sem.polpa_id) == [("entrada", "carga inicial")]
    log = (await s.scalars(select(AuditLogModel).where(AuditLogModel.acao == "cancelar"))).one()
    assert log.detalhes is not None and log.detalhes["motivo"] == "cliente desistiu"
    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await CancelarComanda(uow).executar(caixa, cid)
    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await FecharComanda(uow).executar(caixa, cid)


async def test_motivo_longo_demais_e_recusado(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    with pytest.raises(ValorInvalido):
        await CancelarComanda(uow).executar(caixa, cid, "x" * 256)


async def test_cancelar_comanda_fechada_e_recusado(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Ana")).id_persistido
    await AdicionarItem(uow).executar(caixa, cid, sem.produto_id, sem.tamanho_id)
    await FecharComanda(uow).executar(caixa, cid)
    with pytest.raises(OperacaoNaoPermitida, match="comanda_nao_aberta"):
        await CancelarComanda(uow).executar(caixa, cid)
    assert await _saldo(s, sem.polpa_id) == D("9.7")  # nada foi devolvido


async def test_atendente_lanca_mas_nao_fecha_nem_cancela(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    atendente = await semear_usuario(s, Papel.ATENDENTE)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(atendente, "Ana")).id_persistido
    await AdicionarItem(uow).executar(atendente, cid, sem.produto_id, sem.tamanho_id)
    with pytest.raises(PermissaoNegada):
        await FecharComanda(uow).executar(atendente, cid)
    with pytest.raises(PermissaoNegada):
        await CancelarComanda(uow).executar(atendente, cid)
    relida = await uow.comandas.obter(cid)
    assert relida is not None and relida.status is StatusComanda.ABERTA


@pytest.mark.parametrize("papel", [Papel.ADMIN, Papel.GERENTE, Papel.CAIXA])
async def test_admin_gerente_e_caixa_fecham(s: AsyncSession, papel: Papel) -> None:
    sem = await semear_cardapio(s)
    ator = await semear_usuario(s, papel)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(ator, "Ana")).id_persistido
    await AdicionarItem(uow).executar(ator, cid, sem.produto_id, sem.tamanho_id)
    resultado = await FecharComanda(uow).executar(ator, cid)
    assert resultado.comanda.status is StatusComanda.FECHADA
