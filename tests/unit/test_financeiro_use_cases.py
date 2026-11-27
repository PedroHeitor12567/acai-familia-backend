from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.financeiro.ports import FiltrosLancamento
from app.application.financeiro.use_cases.categorias import (
    AtualizarCategoriaFinanceira,
    CriarCategoriaFinanceira,
    ListarCategoriasFinanceiras,
)
from app.application.financeiro.use_cases.lancamentos import (
    AlteracaoLancamento,
    AtualizarLancamento,
    BaixarLancamento,
    CancelarLancamento,
    CriarLancamento,
    ListarLancamentos,
    ObterLancamento,
)
from app.bootstrap.container import build_uow
from app.domain.caixa.entities import FormaPagamento
from app.domain.exceptions import (
    CategoriaFinanceiraNaoEncontrada,
    LancamentoInvalido,
    LancamentoNaoEncontrado,
    NomeJaCadastrado,
    OperacaoNaoPermitida,
    PermissaoNegada,
    ValorInvalido,
)
from app.domain.financeiro.entities import (
    Baixa,
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from tests.comandas_helpers import semear_usuario

D = Decimal
PAGAR, RECEBER = TipoLancamento.PAGAR, TipoLancamento.RECEBER
VENC = date(2026, 12, 10)
BAIXA = Baixa(date(2026, 12, 1), FormaPagamento.PIX)


@pytest.fixture
async def s(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


async def _gerente(s: AsyncSession) -> Usuario:
    return await semear_usuario(s, Papel.GERENTE)


async def _categorias(s: AsyncSession, ator: Usuario) -> tuple[int, int]:
    uow = build_uow(s)
    despesa = await CriarCategoriaFinanceira(uow).executar(
        ator, "Fornecedores", TipoCategoria.DESPESA
    )
    receita = await CriarCategoriaFinanceira(uow).executar(ator, "Eventos", TipoCategoria.RECEITA)
    return despesa.id_persistido, receita.id_persistido


async def _acoes(s: AsyncSession) -> list[tuple[str, str]]:
    linhas = await s.execute(
        select(AuditLogModel.entidade, AuditLogModel.acao).order_by(AuditLogModel.id)
    )
    return [(e, a) for e, a in linhas.all()]


async def test_nome_de_categoria_e_unico_por_tipo_sem_diferenciar_caixa(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    await CriarCategoriaFinanceira(uow).executar(gerente, "Aluguel", TipoCategoria.DESPESA)
    with pytest.raises(NomeJaCadastrado):
        await CriarCategoriaFinanceira(uow).executar(gerente, "  ALUGUEL ", TipoCategoria.DESPESA)
    await CriarCategoriaFinanceira(uow).executar(gerente, "Aluguel", TipoCategoria.RECEITA)


async def test_renomear_e_desativar_categoria(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    a = await CriarCategoriaFinanceira(uow).executar(gerente, "Aluguel", TipoCategoria.DESPESA)
    b = await CriarCategoriaFinanceira(uow).executar(gerente, "Luz", TipoCategoria.DESPESA)
    atualizar = AtualizarCategoriaFinanceira(uow)

    renomeada = await atualizar.executar(gerente, a.id_persistido, nome="Aluguel da loja")
    assert renomeada.nome == "Aluguel da loja"
    with pytest.raises(NomeJaCadastrado):
        await atualizar.executar(gerente, b.id_persistido, nome="aluguel da LOJA")
    inativa = await atualizar.executar(gerente, b.id_persistido, ativo=False)
    assert not inativa.ativo
    ativas = await ListarCategoriasFinanceiras(uow).executar(gerente, ativo=True)
    assert [c.nome for c in ativas] == ["Aluguel da loja"]
    with pytest.raises(CategoriaFinanceiraNaoEncontrada):
        await atualizar.executar(gerente, 999, ativo=False)


async def test_so_admin_e_gerente_acessam_o_financeiro(s: AsyncSession) -> None:
    uow = build_uow(s)
    gerente = await _gerente(s)
    despesa, _ = await _categorias(s, gerente)
    for papel in (Papel.CAIXA, Papel.ATENDENTE):
        ator = await semear_usuario(s, papel)
        with pytest.raises(PermissaoNegada):
            await CriarCategoriaFinanceira(uow).executar(ator, "X", TipoCategoria.DESPESA)
        with pytest.raises(PermissaoNegada):
            await ListarLancamentos(uow).executar(ator, FiltrosLancamento(), 20, 0)
        with pytest.raises(PermissaoNegada):
            await CriarLancamento(uow).executar(ator, PAGAR, "x", D("1.00"), VENC, despesa)


async def test_criar_lancamento_pendente_com_auditoria(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    despesa, _ = await _categorias(s, gerente)
    lancamento = await CriarLancamento(build_uow(s)).executar(
        gerente, PAGAR, "  Polpa de açaí ", D("350.00"), VENC, despesa, " Fornecedor X ", "  "
    )
    assert lancamento.status is StatusLancamento.PENDENTE
    assert lancamento.descricao == "Polpa de açaí" and lancamento.contraparte == "Fornecedor X"
    assert lancamento.observacao is None and lancamento.data_pagamento is None
    assert lancamento.criado_por_id == gerente.id and lancamento.baixado_por_id is None
    assert ("lancamento", "criar") in await _acoes(s)


async def test_criar_ja_pago_com_baixa(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    despesa, _ = await _categorias(s, gerente)
    lancamento = await CriarLancamento(build_uow(s)).executar(
        gerente, PAGAR, "Gás", D("120.00"), VENC, despesa, baixa=BAIXA
    )
    assert lancamento.status is StatusLancamento.PAGO
    assert (lancamento.data_pagamento, lancamento.forma_pagamento) == (
        BAIXA.data_pagamento,
        FormaPagamento.PIX,
    )
    assert lancamento.baixado_por_id == gerente.id


async def test_categoria_precisa_combinar_com_o_tipo_e_estar_ativa(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    despesa, receita = await _categorias(s, gerente)
    criar = CriarLancamento(uow)
    with pytest.raises(LancamentoInvalido) as erro:
        await criar.executar(gerente, PAGAR, "Gás", D("1.00"), VENC, receita)
    assert erro.value.motivo == "categoria_incompativel"
    with pytest.raises(LancamentoInvalido):
        await criar.executar(gerente, RECEBER, "Evento", D("1.00"), VENC, despesa)
    await AtualizarCategoriaFinanceira(uow).executar(gerente, despesa, ativo=False)
    with pytest.raises(OperacaoNaoPermitida) as erro2:
        await criar.executar(gerente, PAGAR, "Gás", D("1.00"), VENC, despesa)
    assert erro2.value.motivo == "categoria_financeira_inativa"
    with pytest.raises(CategoriaFinanceiraNaoEncontrada):
        await criar.executar(gerente, PAGAR, "Gás", D("1.00"), VENC, 999)


@pytest.mark.parametrize("valor", [D("0"), D("-1.00"), D("1.001")])
async def test_valor_do_lancamento_precisa_ser_positivo(s: AsyncSession, valor: Decimal) -> None:
    gerente = await _gerente(s)
    despesa, _ = await _categorias(s, gerente)
    with pytest.raises(ValorInvalido):
        await CriarLancamento(build_uow(s)).executar(gerente, PAGAR, "Gás", valor, VENC, despesa)
    with pytest.raises(ValorInvalido):
        await CriarLancamento(build_uow(s)).executar(gerente, PAGAR, " ", D("1.00"), VENC, despesa)


async def test_baixar_e_terminal(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    despesa, _ = await _categorias(s, gerente)
    criado = await CriarLancamento(uow).executar(gerente, PAGAR, "Gás", D("120.00"), VENC, despesa)

    pago = await BaixarLancamento(uow).executar(gerente, criado.id_persistido, BAIXA)

    assert pago.status is StatusLancamento.PAGO and pago.baixado_por_id == gerente.id
    for acao in (
        BaixarLancamento(uow).executar(gerente, criado.id_persistido, BAIXA),
        CancelarLancamento(uow).executar(gerente, criado.id_persistido),
        AtualizarLancamento(uow).executar(
            gerente, criado.id_persistido, AlteracaoLancamento(descricao="outra")
        ),
    ):
        with pytest.raises(OperacaoNaoPermitida) as erro:
            await acao
        assert erro.value.motivo == "lancamento_nao_pendente"


async def test_cancelar_e_terminal_e_guarda_o_motivo_na_auditoria(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    _, receita = await _categorias(s, gerente)
    criado = await CriarLancamento(uow).executar(
        gerente, RECEBER, "Evento", D("500.00"), VENC, receita
    )

    cancelado = await CancelarLancamento(uow).executar(
        gerente, criado.id_persistido, "cliente desistiu"
    )

    assert cancelado.status is StatusLancamento.CANCELADO
    log = (
        await s.scalars(
            select(AuditLogModel).where(
                AuditLogModel.entidade == "lancamento", AuditLogModel.acao == "cancelar"
            )
        )
    ).one()
    assert log.detalhes is not None and log.detalhes["motivo"] == "cliente desistiu"
    with pytest.raises(OperacaoNaoPermitida):
        await BaixarLancamento(uow).executar(gerente, criado.id_persistido, BAIXA)
    with pytest.raises(LancamentoNaoEncontrado):
        await CancelarLancamento(uow).executar(gerente, 999)


async def test_editar_lancamento_pendente(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    despesa, receita = await _categorias(s, gerente)
    outra = (
        await CriarCategoriaFinanceira(uow).executar(gerente, "Embalagens", TipoCategoria.DESPESA)
    ).id_persistido
    criado = await CriarLancamento(uow).executar(
        gerente, PAGAR, "Gás", D("120.00"), VENC, despesa, "Gás Ltda", "obs"
    )

    editado = await AtualizarLancamento(uow).executar(
        gerente,
        criado.id_persistido,
        AlteracaoLancamento(
            descricao="Gás de cozinha",
            valor=D("130.00"),
            vencimento=date(2026, 12, 20),
            categoria_id=outra,
            contraparte="",
            observacao="novo",
        ),
    )

    assert (editado.descricao, editado.valor, editado.vencimento) == (
        "Gás de cozinha",
        D("130.00"),
        date(2026, 12, 20),
    )
    assert editado.categoria_id == outra and editado.contraparte is None
    assert editado.observacao == "novo"
    with pytest.raises(LancamentoInvalido):
        await AtualizarLancamento(uow).executar(
            gerente, criado.id_persistido, AlteracaoLancamento(categoria_id=receita)
        )
    antes = len(await _acoes(s))
    await AtualizarLancamento(uow).executar(gerente, criado.id_persistido, AlteracaoLancamento())
    assert len(await _acoes(s)) == antes


async def test_filtros_de_listagem_e_ordem(s: AsyncSession) -> None:
    gerente = await _gerente(s)
    uow = build_uow(s)
    despesa, receita = await _categorias(s, gerente)
    criar = CriarLancamento(uow)
    tarde = await criar.executar(
        gerente, PAGAR, "Luz", D("90.00"), date(2026, 12, 30), despesa, "Cemig"
    )
    cedo = await criar.executar(
        gerente, PAGAR, "Gás", D("120.00"), date(2026, 12, 1), despesa, "Gás_Ltda"
    )
    vencido = await criar.executar(
        gerente, PAGAR, "Água", D("60.00"), date(2026, 11, 1), despesa, "Copasa"
    )
    evento = await criar.executar(
        gerente, RECEBER, "Evento", D("500.00"), date(2026, 12, 15), receita
    )
    pago = await criar.executar(
        gerente, PAGAR, "Taxa", D("10.00"), date(2026, 11, 5), despesa, baixa=BAIXA
    )
    listar = ListarLancamentos(uow)
    hoje = date(2026, 11, 27)

    async def ids(**filtros: object) -> list[int]:
        itens, _ = await listar.executar(gerente, FiltrosLancamento(hoje=hoje, **filtros), 20, 0)  # type: ignore[arg-type]
        return [i.id_persistido for i in itens]

    assert await ids() == [
        vencido.id_persistido,
        cedo.id_persistido,
        evento.id_persistido,
        tarde.id_persistido,
        pago.id_persistido,
    ]
    assert await ids(atrasados=True) == [vencido.id_persistido]
    assert await ids(tipo=RECEBER) == [evento.id_persistido]
    assert await ids(status=StatusLancamento.PAGO) == [pago.id_persistido]
    assert await ids(categoria_id=receita) == [evento.id_persistido]
    assert await ids(vencimento_de=date(2026, 12, 1), vencimento_ate=date(2026, 12, 15)) == [
        cedo.id_persistido,
        evento.id_persistido,
    ]
    assert await ids(contraparte="gás_") == [cedo.id_persistido]
    assert await ids(contraparte="cem") == [tarde.id_persistido]
    itens, total = await listar.executar(gerente, FiltrosLancamento(), 2, 1)
    assert total == 5 and len(itens) == 2
    assert (await ObterLancamento(uow).executar(gerente, cedo.id_persistido)).descricao == "Gás"
