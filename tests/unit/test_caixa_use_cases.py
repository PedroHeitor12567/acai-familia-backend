from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.caixa.ports import FiltrosSessao
from app.application.caixa.use_cases.movimentos import RegistrarMovimento
from app.application.caixa.use_cases.sessoes import (
    AbrirCaixa,
    FecharCaixa,
    ListarSessoes,
    ObterSessao,
    ObterSessaoAtual,
)
from app.application.comandas.use_cases.abrir import AbrirComanda
from app.application.comandas.use_cases.consulta import ObterComanda
from app.application.comandas.use_cases.fechamento import FecharComanda
from app.application.comandas.use_cases.itens import AdicionarItem
from app.bootstrap.container import build_uow
from app.domain.caixa.entities import (
    FormaPagamento,
    PagamentoPedido,
    SessaoCaixa,
    StatusSessao,
    TipoMovimento,
)
from app.domain.cardapio.entities import ProdutoTamanho
from app.domain.comandas.entities import StatusComanda
from app.domain.exceptions import (
    CaixaInvalido,
    NenhumaSessaoAberta,
    OperacaoNaoPermitida,
    PagamentoInvalido,
    PermissaoNegada,
    SessaoCaixaNaoEncontrada,
    ValorInvalido,
)
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.caixa.models import PagamentoModel
from tests.comandas_helpers import Semente, semear_cardapio, semear_usuario

D = Decimal
DIN, PIX, DEB = FormaPagamento.DINHEIRO, FormaPagamento.PIX, FormaPagamento.CARTAO_DEBITO


@pytest.fixture
async def s(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


async def _comanda(
    s: AsyncSession, ator: Usuario, sem: Semente, quantidade: int = 1
) -> tuple[int, Decimal]:
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(ator, "Ana")).id_persistido
    comanda = await AdicionarItem(uow).executar(
        ator, cid, sem.produto_id, sem.tamanho_id, quantidade
    )
    return cid, comanda.itens[0].preco_unitario * quantidade


async def _saldo_polpa(s: AsyncSession, sem: Semente) -> Decimal:
    s.expire_all()
    insumo = await build_uow(s).estoque.obter_insumo(sem.polpa_id)
    assert insumo is not None
    return insumo.estoque_atual


async def _pagamentos(s: AsyncSession) -> int:
    return await s.scalar(select(func.count()).select_from(PagamentoModel)) or 0


async def test_abrir_caixa_grava_sessao_aberta_e_auditoria(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    sessao = await AbrirCaixa(build_uow(s)).executar(caixa, D("100.00"), "  fundo de troco ")
    assert sessao.status is StatusSessao.ABERTA
    assert sessao.valor_abertura == D("100.00") and sessao.observacao == "fundo de troco"
    assert sessao.aberta_por_id == caixa.id and sessao.fechada_em is None
    log = (
        await s.scalars(select(AuditLogModel).where(AuditLogModel.entidade == "caixa_sessao"))
    ).one()
    assert log.acao == "abrir" and log.detalhes is not None
    assert log.detalhes["valor_abertura"] == "100.00"


async def test_abrir_caixa_duas_vezes_da_conflito(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    await AbrirCaixa(uow).executar(caixa, D("0.00"))
    with pytest.raises(OperacaoNaoPermitida) as erro:
        await AbrirCaixa(uow).executar(caixa, D("0.00"))
    assert erro.value.motivo == "caixa_ja_aberto"


async def test_indice_unico_parcial_barra_a_segunda_sessao_aberta(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sessao = await AbrirCaixa(uow).executar(caixa, D("0.00"))
    with pytest.raises(OperacaoNaoPermitida) as erro:
        await uow.caixa.adicionar_sessao(
            SessaoCaixa(D("0.00"), caixa.id_persistido, sessao.aberta_em)
        )
    assert erro.value.motivo == "caixa_ja_aberto"
    await s.rollback()
    await FecharCaixa(uow).executar(caixa, sessao.id_persistido, D("0.00"))
    await AbrirCaixa(uow).executar(caixa, D("0.00"))


async def test_abrir_caixa_valida_valor_e_papel(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    atendente = await semear_usuario(s, Papel.ATENDENTE)
    uow = build_uow(s)
    with pytest.raises(PermissaoNegada):
        await AbrirCaixa(uow).executar(atendente, D("0.00"))
    with pytest.raises(ValorInvalido):
        await AbrirCaixa(uow).executar(caixa, D("-1.00"))
    with pytest.raises(ValorInvalido):
        await AbrirCaixa(uow).executar(caixa, D("1.005"))


async def test_sessao_atual_sem_caixa_aberto_e_404(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    with pytest.raises(NenhumaSessaoAberta):
        await ObterSessaoAtual(build_uow(s)).executar(caixa)
    with pytest.raises(SessaoCaixaNaoEncontrada):
        await ObterSessao(build_uow(s)).executar(caixa, 999)


async def test_suprimento_e_sangria_mexem_no_saldo_em_dinheiro(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sessao = await AbrirCaixa(uow).executar(caixa, D("100.00"))
    sid = sessao.id_persistido
    await RegistrarMovimento(uow).executar(
        caixa, sid, TipoMovimento.SUPRIMENTO, D("50.00"), "troco"
    )
    await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SANGRIA, D("120.00"), "banco")

    atual = await ObterSessaoAtual(uow).executar(caixa)

    assert atual.saldo_dinheiro == D("30.00")
    assert (atual.total_suprimentos, atual.total_sangrias) == (D("50.00"), D("120.00"))
    assert [(m.tipo, m.valor) for m in atual.movimentos] == [
        (TipoMovimento.SUPRIMENTO, D("50.00")),
        (TipoMovimento.SANGRIA, D("120.00")),
    ]


async def test_sangria_que_deixaria_a_gaveta_negativa_e_recusada(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("30.00"))).id_persistido
    with pytest.raises(OperacaoNaoPermitida) as erro:
        await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SANGRIA, D("30.01"), "x")
    assert erro.value.motivo == "saldo_caixa_insuficiente"
    await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SUPRIMENTO, D("0.01"), "x")
    await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SANGRIA, D("30.01"), "x")
    assert (await ObterSessaoAtual(uow).executar(caixa)).saldo_dinheiro == D("0.00")


@pytest.mark.parametrize("valor", [D("0"), D("-5.00"), D("1.001")])
async def test_movimento_com_valor_invalido(s: AsyncSession, valor: Decimal) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("10.00"))).id_persistido
    with pytest.raises(ValorInvalido):
        await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SUPRIMENTO, valor, "x")
    with pytest.raises(ValorInvalido):
        await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SUPRIMENTO, D("1.00"), " ")


async def test_movimento_em_sessao_fechada_ou_inexistente(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("0.00"))).id_persistido
    await FecharCaixa(uow).executar(caixa, sid, D("0.00"))
    with pytest.raises(OperacaoNaoPermitida) as erro:
        await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SUPRIMENTO, D("1.00"), "x")
    assert erro.value.motivo == "sessao_nao_aberta"
    with pytest.raises(SessaoCaixaNaoEncontrada):
        await RegistrarMovimento(uow).executar(caixa, 999, TipoMovimento.SUPRIMENTO, D("1.00"), "x")


async def test_fechar_caixa_congela_esperado_contado_e_diferenca(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("100.00"))).id_persistido
    cid, total = await _comanda(s, caixa, sem, 2)
    await FecharComanda(uow).executar(
        caixa,
        cid,
        [PagamentoPedido(DIN, D("20.00"), D("50.00")), PagamentoPedido(PIX, total - D("20.00"))],
    )
    await RegistrarMovimento(uow).executar(caixa, sid, TipoMovimento.SANGRIA, D("15.00"), "banco")

    fechado = await FecharCaixa(uow).executar(caixa, sid, D("103.00"), "faltou moeda")

    sessao = fechado.sessao
    assert sessao.status is StatusSessao.FECHADA
    assert (sessao.valor_esperado, sessao.valor_contado, sessao.diferenca) == (
        D("105.00"),
        D("103.00"),
        D("-2.00"),
    )
    assert sessao.fechada_por_id == caixa.id and sessao.fechada_em is not None
    assert fechado.saldo_dinheiro == D("105.00")
    assert fechado.resumo_por_forma[DIN] == D("20.00")
    assert fechado.resumo_por_forma[PIX] == D("17.80")
    log = (
        await s.scalars(
            select(AuditLogModel).where(
                AuditLogModel.entidade == "caixa_sessao", AuditLogModel.acao == "fechar"
            )
        )
    ).one()
    assert log.detalhes is not None and log.detalhes["diferenca"] == "-2.00"


async def test_diferenca_sem_observacao_exige_justificativa_e_nada_muda(s: AsyncSession) -> None:
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("50.00"))).id_persistido
    for contado in (D("49.99"), D("50.01")):
        with pytest.raises(CaixaInvalido) as erro:
            await FecharCaixa(uow).executar(caixa, sid, contado)
        assert erro.value.motivo == "justificativa_obrigatoria"
    assert (await ObterSessaoAtual(uow).executar(caixa)).sessao.status is StatusSessao.ABERTA
    fechado = await FecharCaixa(uow).executar(caixa, sid, D("50.00"))
    assert fechado.sessao.diferenca == D("0.00")


async def test_fechar_caixa_com_comanda_aberta_e_permitido_e_fechar_de_novo_da_409(
    s: AsyncSession,
) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("0.00"))).id_persistido
    cid, _ = await _comanda(s, caixa, sem)

    await FecharCaixa(uow).executar(caixa, sid, D("0.00"))

    comanda = await uow.comandas.obter(cid)
    assert comanda is not None and comanda.status is StatusComanda.ABERTA
    with pytest.raises(OperacaoNaoPermitida) as erro:
        await FecharCaixa(uow).executar(caixa, sid, D("0.00"))
    assert erro.value.motivo == "sessao_nao_aberta"


async def test_listar_sessoes_filtra_por_status_e_ordena_da_mais_recente(s: AsyncSession) -> None:
    gerente = await semear_usuario(s, Papel.GERENTE)
    uow = build_uow(s)
    primeira = (await AbrirCaixa(uow).executar(gerente, D("0.00"))).id_persistido
    await FecharCaixa(uow).executar(gerente, primeira, D("0.00"))
    segunda = (await AbrirCaixa(uow).executar(gerente, D("0.00"))).id_persistido

    todas, total = await ListarSessoes(uow).executar(gerente, FiltrosSessao(), 20, 0)
    assert total == 2 and [x.id for x in todas] == [segunda, primeira]
    fechadas, total = await ListarSessoes(uow).executar(
        gerente, FiltrosSessao(status=StatusSessao.FECHADA), 20, 0
    )
    assert total == 1 and [x.id for x in fechadas] == [primeira]


async def test_fechar_comanda_sem_caixa_aberto_da_conflito_e_nada_muda(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid, total = await _comanda(s, caixa, sem)

    with pytest.raises(OperacaoNaoPermitida) as erro:
        await FecharComanda(uow).executar(caixa, cid, [PagamentoPedido(PIX, total)])

    assert erro.value.motivo == "caixa_fechado"
    comanda = await uow.comandas.obter(cid)
    assert comanda is not None and comanda.status is StatusComanda.ABERTA
    assert await _saldo_polpa(s, sem) == D("10") and await _pagamentos(s) == 0


@pytest.mark.parametrize(
    ("pagamentos", "motivo"),
    [
        ([], "pagamento_diferente_do_total"),
        ([PagamentoPedido(PIX, D("18.89"))], "pagamento_diferente_do_total"),
        ([PagamentoPedido(PIX, D("19.00"))], "pagamento_diferente_do_total"),
        ([PagamentoPedido(PIX, D("9.45")), PagamentoPedido(PIX, D("9.45"))], "forma_repetida"),
        ([PagamentoPedido(PIX, D("18.90"), D("20.00"))], "valor_recebido_invalido"),
        ([PagamentoPedido(DIN, D("18.90"), D("10.00"))], "valor_recebido_insuficiente"),
    ],
)
async def test_pagamento_errado_da_422_e_nao_grava_nada(
    s: AsyncSession, pagamentos: list[PagamentoPedido], motivo: str
) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    await AbrirCaixa(uow).executar(caixa, D("0.00"))
    cid, _ = await _comanda(s, caixa, sem)

    with pytest.raises(PagamentoInvalido) as erro:
        await FecharComanda(uow).executar(caixa, cid, pagamentos)

    assert erro.value.motivo == motivo
    comanda = await uow.comandas.obter(cid)
    assert comanda is not None and comanda.status is StatusComanda.ABERTA
    assert await _saldo_polpa(s, sem) == D("10") and await _pagamentos(s) == 0


async def test_dinheiro_com_troco_mais_pix_grava_pagamentos_na_sessao(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    sid = (await AbrirCaixa(uow).executar(caixa, D("0.00"))).id_persistido
    cid, total = await _comanda(s, caixa, sem, 2)

    r = await FecharComanda(uow).executar(
        caixa, cid, [PagamentoPedido(DIN, D("10.00"), D("20.00")), PagamentoPedido(PIX, D("27.80"))]
    )

    assert r.comanda.status is StatusComanda.FECHADA and r.sessao_id == sid
    assert [(p.forma, p.valor, p.troco, p.sessao_id) for p in r.pagamentos] == [
        (DIN, D("10.00"), D("10.00"), sid),
        (PIX, D("27.80"), D("0.00"), sid),
    ]
    assert r.troco_total == D("10.00") and r.comanda.total_fechado == total
    atual = await ObterSessaoAtual(uow).executar(caixa)
    assert atual.saldo_dinheiro == D("10.00")
    assert atual.resumo_por_forma == {
        DIN: D("10.00"),
        PIX: D("27.80"),
        DEB: D("0.00"),
        FormaPagamento.CARTAO_CREDITO: D("0.00"),
    }
    detalhe = await ObterComanda(uow).executar(caixa, cid)
    assert len(detalhe.pagamentos) == 2 and detalhe.troco == D("10.00")
    log = (await s.scalars(select(AuditLogModel).where(AuditLogModel.acao == "fechar"))).one()
    assert log.detalhes is not None and log.detalhes["troco"] == "10.00"
    assert log.detalhes["pagamentos"][0] == {
        "forma": "dinheiro",
        "valor": "10.00",
        "valor_recebido": "20.00",
    }


async def test_comanda_de_total_zero_fecha_sem_caixa_e_sem_pagamento(s: AsyncSession) -> None:
    sem = await semear_cardapio(s)
    caixa = await semear_usuario(s, Papel.CAIXA)
    uow = build_uow(s)
    cid = (await AbrirComanda(uow).executar(caixa, "Brinde")).id_persistido
    await uow.cardapio.definir_preco(ProdutoTamanho(sem.produto_id, sem.tamanho_id, D("0.00")))
    await s.commit()
    await AdicionarItem(uow).executar(caixa, cid, sem.produto_id, sem.tamanho_id)

    r = await FecharComanda(uow).executar(caixa, cid, [])

    assert r.comanda.status is StatusComanda.FECHADA and r.comanda.total_fechado == D("0.00")
    assert r.sessao_id is None and r.pagamentos == [] and await _pagamentos(s) == 0
