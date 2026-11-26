"""Casos de uso de cardápio e estoque sobre SQLite (permissões, conflitos, auditoria)."""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.cardapio.use_cases.adicionais import AtualizarAdicional, CriarAdicional
from app.application.cardapio.use_cases.categorias import (
    AlterarStatusCategoria,
    AtualizarCategoria,
    CriarCategoria,
)
from app.application.cardapio.use_cases.produtos import (
    AtualizarProduto,
    CriarProduto,
    DefinirPrecoProduto,
)
from app.application.cardapio.use_cases.tamanhos import AlterarStatusTamanho, CriarTamanho
from app.application.estoque.ports import FiltrosInsumo, FiltrosMovimentacao
from app.application.estoque.use_cases.ficha_tecnica import (
    DefinirFichaAdicional,
    DefinirFichaTecnica,
    ObterFichaTecnica,
)
from app.application.estoque.use_cases.insumos import (
    AlterarStatusInsumo,
    AtualizarInsumo,
    CriarInsumo,
    ListarAlertasEstoque,
    ListarInsumos,
)
from app.application.estoque.use_cases.movimentacoes import ListarMovimentacoes, MovimentarEstoque
from app.bootstrap.container import build_uow
from app.domain.estoque.entities import ItemFichaTecnica, TipoMovimentacao, UnidadeMedida
from app.domain.exceptions import (
    CategoriaNaoEncontrada,
    EstoqueInsuficiente,
    FichaTecnicaInvalida,
    InsumoNaoEncontrado,
    NomeJaCadastrado,
    OperacaoNaoPermitida,
    PermissaoNegada,
    ValorInvalido,
)
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository

D = Decimal


@pytest.fixture
async def s(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


async def _usuario(s: AsyncSession, papel: Papel) -> Usuario:
    u = await SqlAlchemyUsuarioRepository(s).adicionar(
        Usuario(nome="X", email=f"{papel}@acai.com", senha_hash="x", papel=papel)
    )
    await s.commit()
    return u


async def _acoes(s: AsyncSession) -> list[tuple[str, str]]:
    linhas = await s.execute(
        select(AuditLogModel.acao, AuditLogModel.entidade).order_by(AuditLogModel.id)
    )
    return [(a, e) for a, e in linhas.all()]


# --- permissões: só admin/gerente escrevem ---


@pytest.mark.parametrize("papel", [Papel.ATENDENTE, Papel.CAIXA])
async def test_atendente_e_caixa_nao_escrevem(s: AsyncSession, papel: Papel) -> None:
    ator = await _usuario(s, papel)
    uow = build_uow(s)
    with pytest.raises(PermissaoNegada):
        await CriarCategoria(uow).executar(ator, "Açaí")
    with pytest.raises(PermissaoNegada):
        await CriarTamanho(uow).executar(ator, "500 ml")
    with pytest.raises(PermissaoNegada):
        await CriarAdicional(uow).executar(ator, "Granola", D("2"))
    with pytest.raises(PermissaoNegada):
        await CriarInsumo(uow).executar(ator, "Polpa", UnidadeMedida.KG, D("1"))
    with pytest.raises(PermissaoNegada):
        await ListarInsumos(uow).executar(ator, FiltrosInsumo(), 10, 0)
    with pytest.raises(PermissaoNegada):
        await MovimentarEstoque(uow).executar(ator, 1, TipoMovimentacao.ENTRADA, D("1"))
    with pytest.raises(PermissaoNegada):
        await ObterFichaTecnica(uow).executar(ator, 1, 1)
    assert await _acoes(s) == []


@pytest.mark.parametrize("papel", [Papel.ADMIN, Papel.GERENTE])
async def test_admin_e_gerente_escrevem(s: AsyncSession, papel: Papel) -> None:
    ator = await _usuario(s, papel)
    categoria = await CriarCategoria(build_uow(s)).executar(ator, "Açaí")
    assert categoria.id is not None and categoria.ativo


# --- cardápio ---


async def test_categoria_nome_unico_ignora_caixa(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    await CriarCategoria(uow).executar(ator, "Açaí")
    with pytest.raises(NomeJaCadastrado):
        await CriarCategoria(uow).executar(ator, "açaí")
    outra = await CriarCategoria(uow).executar(ator, "Sorvetes")
    with pytest.raises(NomeJaCadastrado):
        await AtualizarCategoria(uow).executar(ator, outra.id_persistido, "AÇAÍ")


async def test_produto_unico_dentro_da_categoria_mas_repete_entre_categorias(
    s: AsyncSession,
) -> None:
    ator = await _usuario(s, Papel.ADMIN)
    uow = build_uow(s)
    a = await CriarCategoria(uow).executar(ator, "Açaí")
    b = await CriarCategoria(uow).executar(ator, "Combos")
    await CriarProduto(uow).executar(ator, "Tradicional", a.id_persistido)
    with pytest.raises(NomeJaCadastrado):
        await CriarProduto(uow).executar(ator, "Tradicional", a.id_persistido)
    outro = await CriarProduto(uow).executar(ator, "Tradicional", b.id_persistido)
    # mover para a categoria onde o nome já existe também conflita
    with pytest.raises(NomeJaCadastrado):
        await AtualizarProduto(uow).executar(
            ator, outro.produto.id_persistido, categoria_id=a.id_persistido
        )


async def test_produto_exige_categoria_existente_e_ativa(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.ADMIN)
    uow = build_uow(s)
    with pytest.raises(CategoriaNaoEncontrada):
        await CriarProduto(uow).executar(ator, "X", 999)
    cat = await CriarCategoria(uow).executar(ator, "Açaí")
    await AlterarStatusCategoria(uow).executar(ator, cat.id_persistido, ativo=False)
    with pytest.raises(OperacaoNaoPermitida):
        await CriarProduto(uow).executar(ator, "X", cat.id_persistido)


async def test_preco_por_tamanho_e_auditoria(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    cat = await CriarCategoria(uow).executar(ator, "Açaí")
    prod = await CriarProduto(uow).executar(ator, "Tradicional", cat.id_persistido)
    t300 = await CriarTamanho(uow).executar(ator, "300 ml")
    t500 = await CriarTamanho(uow).executar(ator, "500 ml")
    pid = prod.produto.id_persistido

    await DefinirPrecoProduto(uow).executar(ator, pid, t300.id_persistido, D("12.90"))
    r = await DefinirPrecoProduto(uow).executar(ator, pid, t500.id_persistido, D("18.50"))
    assert [(p.tamanho_id, p.preco) for p in r.precos] == [
        (t300.id_persistido, D("12.90")),
        (t500.id_persistido, D("18.50")),
    ]
    # reajuste do mesmo tamanho altera, não duplica
    r = await DefinirPrecoProduto(uow).executar(ator, pid, t300.id_persistido, D("13.00"))
    assert len(r.precos) == 2 and r.precos[0].preco == D("13.00")
    with pytest.raises(ValorInvalido):
        await DefinirPrecoProduto(uow).executar(ator, pid, t300.id_persistido, D("-1"))
    with pytest.raises(ValorInvalido):
        await DefinirPrecoProduto(uow).executar(ator, pid, t300.id_persistido, D("1.999"))

    await AlterarStatusTamanho(uow).executar(ator, t500.id_persistido, ativo=False)
    with pytest.raises(OperacaoNaoPermitida):
        await DefinirPrecoProduto(uow).executar(ator, pid, t500.id_persistido, D("19"))

    # 3 preços gravados com sucesso (o terceiro é o reajuste); os inválidos não auditam
    assert (await _acoes(s)).count(("definir_preco", "produto")) == 3


async def test_atualizar_adicional_audita_so_o_que_mudou(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    ad = await CriarAdicional(uow).executar(ator, "Granola", D("2.00"))
    id_ = ad.id_persistido
    await AtualizarAdicional(uow).executar(ator, id_, preco=D("2.00"))  # sem mudança
    await AtualizarAdicional(uow).executar(ator, id_, preco=D("2.50"))
    log = await s.scalar(
        select(AuditLogModel)
        .where(AuditLogModel.acao == "atualizar")
        .order_by(AuditLogModel.id.desc())
    )
    assert log is not None and log.detalhes == {"preco": {"antes": "2.00", "depois": "2.50"}}
    assert (await _acoes(s)).count(("atualizar", "adicional")) == 1


async def test_desativar_e_idempotente_e_audita_uma_vez(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    cat = await CriarCategoria(uow).executar(ator, "Açaí")
    for _ in range(2):
        r = await AlterarStatusCategoria(uow).executar(ator, cat.id_persistido, ativo=False)
        assert r.ativo is False
    assert (await _acoes(s)).count(("desativar", "categoria")) == 1


# --- insumos e movimentações ---


async def _insumo(s: AsyncSession, ator: Usuario, minimo: str = "5") -> int:
    i = await CriarInsumo(build_uow(s)).executar(ator, "Polpa", UnidadeMedida.KG, D(minimo))
    return i.id_persistido


async def test_insumo_nasce_com_saldo_zero_e_nome_unico(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    i = await CriarInsumo(uow).executar(ator, "Polpa", UnidadeMedida.KG, D("5"))
    assert i.estoque_atual == D("0") and i.abaixo_do_minimo
    with pytest.raises(NomeJaCadastrado):
        await CriarInsumo(uow).executar(ator, "polpa", UnidadeMedida.G, D("1"))
    with pytest.raises(ValorInvalido):
        await CriarInsumo(uow).executar(ator, "Leite", UnidadeMedida.L, D("-1"))


async def test_movimentacoes_atualizam_saldo_e_historico(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    insumo_id = await _insumo(s, ator)
    mov = MovimentarEstoque(uow)

    e = await mov.executar(ator, insumo_id, TipoMovimentacao.ENTRADA, D("20"), "compra")
    assert (e.saldo_antes, e.saldo_apos, e.usuario_id) == (D("0"), D("20"), ator.id)
    await mov.executar(ator, insumo_id, TipoMovimentacao.SAIDA, D("7.5"))
    aj = await mov.executar(ator, insumo_id, TipoMovimentacao.AJUSTE, D("10"), "contagem")
    assert (aj.quantidade, aj.saldo_antes, aj.saldo_apos) == (D("2.5"), D("12.5"), D("10"))

    insumo = await build_uow(s).estoque.obter_insumo(insumo_id)
    assert insumo is not None and insumo.estoque_atual == D("10")
    itens, total = await ListarMovimentacoes(uow).executar(
        ator, insumo_id, FiltrosMovimentacao(), 10, 0
    )
    assert total == 3
    assert [m.tipo for m in itens] == [
        TipoMovimentacao.AJUSTE,
        TipoMovimentacao.SAIDA,
        TipoMovimentacao.ENTRADA,
    ]  # mais recentes primeiro
    so_saidas, total = await ListarMovimentacoes(uow).executar(
        ator, insumo_id, FiltrosMovimentacao(tipo=TipoMovimentacao.SAIDA), 10, 0
    )
    assert total == 1 and so_saidas[0].quantidade == D("7.5")
    assert (await _acoes(s)).count(("movimentar", "insumo")) == 3


async def test_saida_insuficiente_nao_grava_nada(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    insumo_id = await _insumo(s, ator)
    await MovimentarEstoque(uow).executar(ator, insumo_id, TipoMovimentacao.ENTRADA, D("3"))
    with pytest.raises(EstoqueInsuficiente):
        await MovimentarEstoque(uow).executar(ator, insumo_id, TipoMovimentacao.SAIDA, D("3.001"))
    insumo = await uow.estoque.obter_insumo(insumo_id)
    assert insumo is not None and insumo.estoque_atual == D("3")
    total = await s.scalar(
        select(func.count()).select_from(AuditLogModel).where(AuditLogModel.acao == "movimentar")
    )
    assert total == 1


async def test_movimentar_insumo_inexistente_ou_inativo(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    with pytest.raises(InsumoNaoEncontrado):
        await MovimentarEstoque(uow).executar(ator, 999, TipoMovimentacao.ENTRADA, D("1"))
    insumo_id = await _insumo(s, ator)
    await AlterarStatusInsumo(uow).executar(ator, insumo_id, ativo=False)
    with pytest.raises(OperacaoNaoPermitida):
        await MovimentarEstoque(uow).executar(ator, insumo_id, TipoMovimentacao.ENTRADA, D("1"))


async def test_aplicar_saida_e_reutilizavel_numa_transacao_externa(s: AsyncSession) -> None:
    """É o que o fechamento de comanda (Fase 2) fará: várias saídas, um único commit."""
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    a = await CriarInsumo(uow).executar(ator, "Polpa", UnidadeMedida.KG, D("1"))
    b = await CriarInsumo(uow).executar(ator, "Granola", UnidadeMedida.G, D("100"))
    for i, q in ((a, "10"), (b, "500")):
        await MovimentarEstoque(uow).executar(ator, i.id_persistido, TipoMovimentacao.ENTRADA, D(q))

    await uow.estoque.aplicar_saida(a.id_persistido, D("2"), ator.id, "comanda #1")
    await uow.estoque.aplicar_saida(b.id_persistido, D("50"), ator.id, "comanda #1")
    await uow.rollback()  # a comanda falhou depois: nada das saídas deve sobrar

    pa = await build_uow(s).estoque.obter_insumo(a.id_persistido)
    pb = await build_uow(s).estoque.obter_insumo(b.id_persistido)
    assert pa is not None and pb is not None
    assert (pa.estoque_atual, pb.estoque_atual) == (D("10"), D("500"))


async def test_alertas_listam_exatamente_os_insumos_no_minimo_ou_abaixo(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    ids = {}
    for nome, minimo, saldo in (
        ("Abaixo", "5", "4"),
        ("Igual", "5", "5"),
        ("Acima", "5", "6"),
        ("Zero", "0", "0"),
    ):
        i = await CriarInsumo(uow).executar(ator, nome, UnidadeMedida.UN, D(minimo))
        ids[nome] = i.id_persistido
        if D(saldo) > 0:
            await MovimentarEstoque(uow).executar(
                ator, i.id_persistido, TipoMovimentacao.ENTRADA, D(saldo)
            )
    inativo = await CriarInsumo(uow).executar(ator, "Inativo", UnidadeMedida.UN, D("5"))
    await AlterarStatusInsumo(uow).executar(ator, inativo.id_persistido, ativo=False)

    itens, total = await ListarAlertasEstoque(uow).executar(ator, 100, 0)
    assert sorted(i.nome for i in itens) == ["Abaixo", "Igual", "Zero"]
    assert total == 3
    acima, _ = await ListarInsumos(uow).executar(ator, FiltrosInsumo(abaixo_do_minimo=False), 10, 0)
    assert [i.nome for i in acima] == ["Acima"]


async def test_atualizar_insumo_nao_altera_saldo(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    insumo_id = await _insumo(s, ator)
    await MovimentarEstoque(uow).executar(ator, insumo_id, TipoMovimentacao.ENTRADA, D("8"))
    atual = await AtualizarInsumo(uow).executar(
        ator, insumo_id, nome="Polpa de açaí", estoque_minimo=D("9")
    )
    assert (atual.nome, atual.estoque_minimo, atual.estoque_atual) == (
        "Polpa de açaí",
        D("9"),
        D("8"),
    )
    assert atual.abaixo_do_minimo


# --- ficha técnica ---


async def _cenario_ficha(s: AsyncSession, ator: Usuario) -> tuple[int, int, int, int]:
    uow = build_uow(s)
    cat = await CriarCategoria(uow).executar(ator, "Açaí")
    prod = await CriarProduto(uow).executar(ator, "Tradicional", cat.id_persistido)
    tam = await CriarTamanho(uow).executar(ator, "500 ml")
    await DefinirPrecoProduto(uow).executar(
        ator, prod.produto.id_persistido, tam.id_persistido, D("18")
    )
    polpa = await CriarInsumo(uow).executar(ator, "Polpa", UnidadeMedida.G, D("100"))
    granola = await CriarInsumo(uow).executar(ator, "Granola", UnidadeMedida.G, D("100"))
    return (
        prod.produto.id_persistido,
        tam.id_persistido,
        polpa.id_persistido,
        granola.id_persistido,
    )


async def test_ficha_e_substituida_por_inteiro(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    produto, tamanho, polpa, granola = await _cenario_ficha(s, ator)
    definir = DefinirFichaTecnica(uow)

    await definir.executar(
        ator,
        produto,
        tamanho,
        [ItemFichaTecnica(polpa, D("300")), ItemFichaTecnica(granola, D("20"))],
    )
    await definir.executar(ator, produto, tamanho, [ItemFichaTecnica(polpa, D("250.5"))])
    atual = await ObterFichaTecnica(uow).executar(ator, produto, tamanho)
    assert atual == [ItemFichaTecnica(polpa, D("250.5"))]  # granola saiu
    await definir.executar(ator, produto, tamanho, [])
    assert await ObterFichaTecnica(uow).executar(ator, produto, tamanho) == []
    assert (await _acoes(s)).count(("definir_ficha", "ficha_tecnica")) == 3


async def test_ficha_invalida_nao_altera_a_receita(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    produto, tamanho, polpa, granola = await _cenario_ficha(s, ator)
    original = [ItemFichaTecnica(polpa, D("300"))]
    await DefinirFichaTecnica(uow).executar(ator, produto, tamanho, original)

    casos = {
        "insumo_repetido": [ItemFichaTecnica(polpa, D("1")), ItemFichaTecnica(polpa, D("2"))],
        "insumo_inexistente": [ItemFichaTecnica(polpa, D("1")), ItemFichaTecnica(999, D("1"))],
    }
    for motivo, itens in casos.items():
        with pytest.raises(FichaTecnicaInvalida) as exc:
            await DefinirFichaTecnica(uow).executar(ator, produto, tamanho, itens)
        assert exc.value.motivo == motivo

    await AlterarStatusInsumo(uow).executar(ator, granola, ativo=False)
    with pytest.raises(FichaTecnicaInvalida) as exc:
        await DefinirFichaTecnica(uow).executar(
            ator, produto, tamanho, [ItemFichaTecnica(granola, D("1"))]
        )
    assert exc.value.motivo == "insumo_inativo"

    assert await ObterFichaTecnica(uow).executar(ator, produto, tamanho) == original


async def test_ficha_exige_produto_ativo_e_tamanho_vendido(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    produto, tamanho, polpa, _ = await _cenario_ficha(s, ator)
    outro_tamanho = await CriarTamanho(uow).executar(ator, "700 ml")
    with pytest.raises(FichaTecnicaInvalida) as exc:
        await DefinirFichaTecnica(uow).executar(
            ator, produto, outro_tamanho.id_persistido, [ItemFichaTecnica(polpa, D("1"))]
        )
    assert exc.value.motivo == "produto_sem_tamanho"


async def test_ficha_de_adicional(s: AsyncSession) -> None:
    ator = await _usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    _, _, _, granola = await _cenario_ficha(s, ator)
    ad = await CriarAdicional(uow).executar(ator, "Granola extra", D("2"))
    itens = await DefinirFichaAdicional(uow).executar(
        ator, ad.id_persistido, [ItemFichaTecnica(granola, D("30"))]
    )
    assert itens == [ItemFichaTecnica(granola, D("30"))]
    with pytest.raises(FichaTecnicaInvalida):
        await DefinirFichaAdicional(uow).executar(
            ator,
            ad.id_persistido,
            [ItemFichaTecnica(granola, D("1")), ItemFichaTecnica(granola, D("2"))],
        )
