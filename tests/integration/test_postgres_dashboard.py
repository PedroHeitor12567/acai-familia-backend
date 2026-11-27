"""Dashboard no PostgreSQL real: fuso de verdade, plano de execução, consultas e migration.

O SQLite só simula o fuso com um deslocamento fixo; aqui `timezone('America/Sao_Paulo', ...)`
é quem decide o "dia local". Cada teste roda numa transação com rollback (`pg_session`).
"""

import os
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.bootstrap.container import build_criar_usuario
from app.domain.usuarios.entities import Papel
from app.infrastructure.persistence.cardapio.models import (
    CategoriaModel,
    ProdutoModel,
    ProdutoTamanhoModel,
    TamanhoModel,
)
from tests.dashboard_helpers import ItemSemente, Massa, dias_atras, local
from tests.integration.test_postgres_estoque import _alembic

pytestmark = pytest.mark.postgres

D = Decimal
SENHA = "senha-dashboard-123"
Headers = dict[str, str]


class _SessaoCompartilhada:
    """Faz o `Massa` usar a sessão do teste (a do rollback) sem fechá-la ao sair do `with`."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def __call__(self) -> "_SessaoCompartilhada":
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._s

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.fixture
async def gerente(pg_client: AsyncClient, pg_session: AsyncSession) -> Headers:
    await build_criar_usuario(pg_session).executar(
        None, "Gerente", "gerente-dashboard@acai.com", SENHA, Papel.GERENTE
    )
    r = await pg_client.post(
        "/auth/login", json={"email": "gerente-dashboard@acai.com", "senha": SENHA}
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
async def massa(pg_session: AsyncSession) -> AsyncIterator[Massa]:
    m = await Massa(_SessaoCompartilhada(pg_session)).preparar()  # type: ignore[arg-type]
    categoria = CategoriaModel(nome="Cat dashboard")
    tamanho = TamanhoModel(nome="Tam dashboard")
    pg_session.add_all([categoria, tamanho])
    await pg_session.flush()
    m.tamanho_id = tamanho.id
    m.produtos = []  # type: ignore[attr-defined]
    for i in range(5):
        produto = ProdutoModel(nome=f"Produto {i}", categoria_id=categoria.id)
        pg_session.add(produto)
        await pg_session.flush()
        pg_session.add(
            ProdutoTamanhoModel(produto_id=produto.id, tamanho_id=tamanho.id, preco=D("20.00"))
        )
        m.produtos.append(produto.id)  # type: ignore[attr-defined]
    await pg_session.flush()
    yield m


async def _get(client: AsyncClient, url: str, h: Headers, **params: object) -> dict[str, Any]:
    r = await client.get(url, params={k: str(v) for k, v in params.items()}, headers=h)
    assert r.status_code == 200, r.text
    corpo: dict[str, Any] = r.json()
    return corpo


def _periodo(de: int, ate: int = 0) -> dict[str, str]:
    return {"de": dias_atras(de).isoformat(), "ate": dias_atras(ate).isoformat()}


async def _massa_em_bloco(session: AsyncSession, massa: Massa, quantidade: int) -> None:
    """`quantidade` comandas fechadas (a cada 2 h para trás), com itens e pagamentos, por SQL."""
    ids = massa.produtos  # type: ignore[attr-defined]
    await session.execute(
        text(
            "INSERT INTO comandas (cliente_nome, origem, status, aberta_em, fechada_em, total) "
            "SELECT 'bloco', 'balcao', 'fechada', "
            "now() - g * interval '2 hours' - interval '10 minutes', "
            "now() - g * interval '2 hours', 20.00 FROM generate_series(1, :n) AS g"
        ),
        {"n": quantidade},
    )
    await session.execute(
        text(
            "INSERT INTO itens_comanda (comanda_id, produto_id, tamanho_id, nome_produto, "
            "nome_tamanho, quantidade, preco_unitario) "
            "SELECT c.id, (CAST(:ids AS int[]))[1 + c.id % 5], :tam, 'Produto', 'Tam', 1, 20.00 "
            "FROM comandas c WHERE c.cliente_nome = 'bloco'"
        ).bindparams(ids=ids),
        {"tam": massa.tamanho_id},
    )
    await session.execute(
        text(
            "INSERT INTO pagamentos "
            "(comanda_id, sessao_id, forma, valor, criado_por_id, criado_em) "
            "SELECT id, :sessao, CASE WHEN id % 2 = 0 THEN 'pix' ELSE 'dinheiro' END, total, "
            ":uid, fechada_em FROM comandas WHERE cliente_nome = 'bloco'"
        ),
        {"sessao": massa.sessao_id, "uid": massa.usuario_id},
    )
    await session.execute(text("ANALYZE comandas, itens_comanda, pagamentos"))


# --- fuso ----------------------------------------------------------------------------------------


async def test_fuso_real_recorta_o_dia_local_na_serie_no_resumo_no_fluxo_e_na_hora(
    pg_client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    dia = dias_atras(3)
    await massa.comanda(
        local(dia, 23, 30),
        [ItemSemente(massa.produtos[0], quantidade=1, preco="10.00")],  # type: ignore[attr-defined]
    )  # 02:30 UTC do dia seguinte
    await massa.comanda(
        local(dia + timedelta(days=1), 0, 10),
        [ItemSemente(massa.produtos[0], quantidade=1, preco="20.00")],  # type: ignore[attr-defined]
    )

    serie = await _get(pg_client, "/dashboard/vendas/serie", gerente, **_periodo(4, 2))
    assert [(p["inicio"], p["faturamento"]) for p in serie["pontos"]] == [
        (dias_atras(4).isoformat(), "0.00"),
        (dia.isoformat(), "10.00"),
        (dias_atras(2).isoformat(), "20.00"),
    ]
    resumo = await _get(pg_client, "/dashboard/vendas/resumo", gerente, de=dia, ate=dia)
    assert resumo["atual"]["faturamento"] == "10.00" and resumo["atual"]["qtd_comandas"] == 1

    fluxo = await _get(pg_client, "/dashboard/financeiro/fluxo-caixa", gerente, **_periodo(4, 2))
    assert [p["entradas_vendas"] for p in fluxo["realizado"]] == ["0.00", "10.00", "20.00"]

    horas = await _get(pg_client, "/dashboard/vendas/por-hora", gerente, **_periodo(4, 2))
    por_hora = {h["hora"]: h["qtd_comandas"] for h in horas["horas"]}
    assert (por_hora[23], por_hora[0], sum(por_hora.values())) == (1, 1, 2)
    assert por_hora[2] == 0  # a hora UTC (02h) não vale


async def test_serie_resumo_e_formas_fecham_o_mesmo_total(
    pg_client: AsyncClient, gerente: Headers, massa: Massa, pg_session: AsyncSession
) -> None:
    await _massa_em_bloco(pg_session, massa, 300)
    await massa.comanda(
        local(dias_atras(1)),
        [ItemSemente(massa.produtos[1], quantidade=2, preco="13.35")],  # type: ignore[attr-defined]
        pagamentos=[("cartao_debito", "10.00"), ("cartao_credito", "16.70")],
    )
    for rota in ("serie", "por-forma-pagamento", "mais-vendidos"):
        assert await _get(pg_client, f"/dashboard/vendas/{rota}", gerente, **_periodo(29))
    p = _periodo(29)
    resumo = await _get(pg_client, "/dashboard/vendas/resumo", gerente, **p)
    serie = await _get(pg_client, "/dashboard/vendas/serie", gerente, **p)
    formas = await _get(pg_client, "/dashboard/vendas/por-forma-pagamento", gerente, **p)
    ranking = await _get(pg_client, "/dashboard/vendas/mais-vendidos", gerente, **p, limite=50)
    faturamento = D(resumo["atual"]["faturamento"])
    assert faturamento > 0
    assert sum(D(x["faturamento"]) for x in serie["pontos"]) == faturamento
    assert sum(D(f["valor"]) for f in formas["formas"]) == faturamento
    assert sum(D(i["receita"]) for i in ranking["itens"]) == faturamento


# --- consultas e plano ---------------------------------------------------------------------------

TETOS = [
    ("/dashboard/visao-geral", {}, 5),
    ("/dashboard/vendas/resumo", {}, 1),
    ("/dashboard/vendas/serie", {}, 1),
    ("/dashboard/vendas/mais-vendidos", {}, 1),
    ("/dashboard/vendas/por-forma-pagamento", {}, 1),
    ("/dashboard/vendas/por-hora", {}, 1),
    ("/dashboard/estoque/critico", {}, 1),
    ("/dashboard/financeiro/fluxo-caixa", {}, 1),
    ("/dashboard/financeiro/fluxo-caixa", {"incluir_projecao": "true"}, 1),
    ("/dashboard/financeiro/contas", {}, 2),
]


def _capturar(session: AsyncSession) -> list[tuple[str, Any]]:
    capturadas: list[tuple[str, Any]] = []

    def _antes(_c: Any, _cur: Any, statement: str, parameters: Any, *_: Any) -> None:
        capturadas.append((statement, parameters))

    event.listen(session.bind.sync_connection, "before_cursor_execute", _antes)  # type: ignore[union-attr]
    return capturadas


async def test_numero_de_consultas_e_fixo_com_500_comandas(
    pg_client: AsyncClient, gerente: Headers, massa: Massa, pg_session: AsyncSession
) -> None:
    await _massa_em_bloco(pg_session, massa, 500)
    capturadas = _capturar(pg_session)
    for rota, params, teto in TETOS:
        capturadas.clear()
        await _get(pg_client, rota, gerente, **params)
        # +1: a consulta que autentica o usuário a cada requisição
        assert len(capturadas) <= teto + 1, f"{rota}: {len(capturadas)} consultas"


async def test_consultas_de_vendas_usam_o_indice_parcial_de_comandas(
    pg_client: AsyncClient, gerente: Headers, massa: Massa, pg_session: AsyncSession
) -> None:
    await _massa_em_bloco(pg_session, massa, 10_000)  # ~833 dias de vendas
    capturadas = _capturar(pg_session)
    for rota in ("resumo", "serie", "mais-vendidos", "por-forma-pagamento", "por-hora"):
        await _get(pg_client, f"/dashboard/vendas/{rota}", gerente)
    await _get(pg_client, "/dashboard/financeiro/fluxo-caixa", gerente)

    conexao = await pg_session.connection()
    consultas = [(s, p) for s, p in capturadas if "comandas" in s and "fechada_em" in s]
    assert len(consultas) >= 6
    for statement, parametros in consultas:
        plano = "\n".join(
            linha for (linha,) in await conexao.exec_driver_sql("EXPLAIN " + statement, parametros)
        )
        assert "Seq Scan on comandas" not in plano, plano
        assert "ix_comandas_fechadas_em" in plano, plano


# --- migration -----------------------------------------------------------------------------------


async def test_migration_0009_sobe_e_desce_so_com_indices() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    indices = {
        "comandas": "ix_comandas_fechadas_em",
        "itens_comanda": "ix_itens_comanda_comanda_produto",
        "lancamentos": "ix_lancamentos_status_data_pagamento",
    }

    async def _estado() -> tuple[set[str], dict[str, set[str]]]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:

                def _ler(c: Any) -> tuple[set[str], dict[str, set[str]]]:
                    insp = inspect(c)
                    return set(insp.get_table_names()), {
                        t: {i["name"] for i in insp.get_indexes(t) if i["name"]} for t in indices
                    }

                return await conn.run_sync(_ler)
        finally:
            await engine.dispose()

    _alembic("upgrade", "head", url=url)
    tabelas, presentes = await _estado()
    assert all(nome in presentes[t] for t, nome in indices.items())
    try:
        _alembic("downgrade", "-1", url=url)
        tabelas_antes, ausentes = await _estado()
        assert not any(nome in ausentes[t] for t, nome in indices.items())
        assert tabelas_antes == tabelas  # a 0009 não criou nem removeu tabela
    finally:
        _alembic("upgrade", "head", url=url)
    _, finais = await _estado()
    assert all(nome in finais[t] for t, nome in indices.items())
