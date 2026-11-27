from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.usuarios.entities import Papel
from tests.comandas_helpers import abrir_caixa_api, fechar_comanda_api
from tests.conftest import AuthHeaders
from tests.dashboard_helpers import (
    ItemSemente,
    Massa,
    dias_atras,
    hoje_local,
    local,
)

D = Decimal
Headers = dict[str, str]
Factory = async_sessionmaker[AsyncSession]

ROTAS = [
    "/dashboard/visao-geral",
    "/dashboard/vendas/resumo",
    "/dashboard/vendas/serie",
    "/dashboard/vendas/mais-vendidos",
    "/dashboard/vendas/por-forma-pagamento",
    "/dashboard/vendas/por-hora",
    "/dashboard/estoque/critico",
    "/dashboard/financeiro/fluxo-caixa",
    "/dashboard/financeiro/contas",
]


@pytest.fixture
async def massa(factory: Factory) -> Massa:
    return await Massa(factory).preparar()


@pytest.fixture
async def gerente(auth_headers: AuthHeaders) -> Headers:
    return await auth_headers("gerente@acai.com", Papel.GERENTE)


async def _get(client: AsyncClient, url: str, h: Headers, **params: object) -> dict[str, Any]:
    r = await client.get(url, params={k: str(v) for k, v in params.items()}, headers=h)
    assert r.status_code == 200, r.text
    corpo: dict[str, Any] = r.json()
    return corpo


def _periodo(de: int, ate: int = 0) -> dict[str, str]:
    return {"de": dias_atras(de).isoformat(), "ate": dias_atras(ate).isoformat()}


# --- permissões --------------------------------------------------------------------------------


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("papel", [Papel.ADMIN, Papel.GERENTE])
async def test_admin_e_gerente_acessam(
    client: AsyncClient, auth_headers: AuthHeaders, rota: str, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    assert (await client.get(rota, headers=h)).status_code == 200


@pytest.mark.parametrize("rota", ROTAS)
@pytest.mark.parametrize("papel", [Papel.CAIXA, Papel.ATENDENTE])
async def test_caixa_e_atendente_recebem_403(
    client: AsyncClient, auth_headers: AuthHeaders, rota: str, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    r = await client.get(rota, headers=h)
    assert r.status_code == 403 and r.json()["code"] == "permissao_negada"


@pytest.mark.parametrize("rota", ROTAS)
async def test_sem_token_recebe_401(client: AsyncClient, rota: str) -> None:
    r = await client.get(rota)
    assert r.status_code == 401 and r.json()["code"] == "token_invalido"


# --- vendas: resumo ----------------------------------------------------------------------------


async def test_faturamento_conta_so_fechadas_e_canceladas_ficam_so_informativas(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    dia = dias_atras(2)
    await massa.comanda(local(dia, 10), [ItemSemente(quantidade=2, preco="20.00")])  # 40
    await massa.comanda(local(dia, 11), [ItemSemente(quantidade=1, preco="30.00")])  # 30
    await massa.comanda(local(dia, 12), [ItemSemente(preco="99.00")], status="aberta")
    await massa.comanda(local(dia, 13), [ItemSemente(preco="88.00")], status="cancelada")

    r = await _get(client, "/dashboard/vendas/resumo", gerente, de=dia, ate=dia)
    assert r["periodo"] == {"de": dia.isoformat(), "ate": dia.isoformat(), "dias": 1}
    assert r["atual"] == {
        "faturamento": "70.00",
        "qtd_comandas": 2,
        "ticket_medio": "35.00",
        "itens_vendidos": 3,
        "comandas_canceladas": 1,
    }


async def test_resumo_traz_periodo_anterior_e_variacao(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    # período: 3 dias [-3, -1]; anterior: [-6, -4]
    await massa.comanda(local(dias_atras(1)), [ItemSemente(preco="150.00")])
    await massa.comanda(local(dias_atras(2)), [ItemSemente(preco="50.00")])
    await massa.comanda(local(dias_atras(5)), [ItemSemente(preco="100.00")])

    r = await _get(client, "/dashboard/vendas/resumo", gerente, **_periodo(3, 1))
    assert r["atual"]["faturamento"] == "200.00" and r["atual"]["ticket_medio"] == "100.00"
    assert r["anterior"] == {
        "periodo": {"de": dias_atras(6).isoformat(), "ate": dias_atras(4).isoformat(), "dias": 3},
        "faturamento": "100.00",
        "qtd_comandas": 1,
        "ticket_medio": "100.00",
    }
    assert r["variacao_pct"] == {"faturamento": 100.0, "qtd_comandas": 100.0, "ticket_medio": 0.0}


async def test_variacao_e_nula_quando_o_periodo_anterior_nao_tem_venda(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await massa.comanda(local(dias_atras(1)), [ItemSemente(preco="10.00")])
    r = await _get(client, "/dashboard/vendas/resumo", gerente, **_periodo(2, 1))
    assert r["anterior"]["faturamento"] == "0.00" and r["anterior"]["ticket_medio"] == "0.00"
    assert r["variacao_pct"] == {"faturamento": None, "qtd_comandas": None, "ticket_medio": None}


async def test_periodo_sem_vendas_devolve_200_com_zeros_e_serie_completa(
    client: AsyncClient, gerente: Headers
) -> None:
    resumo = await _get(client, "/dashboard/vendas/resumo", gerente, **_periodo(6))
    assert resumo["atual"]["faturamento"] == "0.00" and resumo["atual"]["qtd_comandas"] == 0
    assert resumo["atual"]["ticket_medio"] == "0.00"

    serie = await _get(client, "/dashboard/vendas/serie", gerente, **_periodo(6))
    assert len(serie["pontos"]) == 7
    assert all(p["faturamento"] == "0.00" and p["qtd_comandas"] == 0 for p in serie["pontos"])

    formas = await _get(client, "/dashboard/vendas/por-forma-pagamento", gerente, **_periodo(6))
    assert [f["valor"] for f in formas["formas"]] == ["0.00"] * 4
    horas = await _get(client, "/dashboard/vendas/por-hora", gerente, **_periodo(6))
    assert len(horas["horas"]) == 24
    ranking = await _get(client, "/dashboard/vendas/mais-vendidos", gerente, **_periodo(6))
    assert ranking["itens"] == []


async def test_padrao_sao_os_ultimos_30_dias(client: AsyncClient, gerente: Headers) -> None:
    r = await _get(client, "/dashboard/vendas/resumo", gerente)
    assert r["periodo"] == {
        "de": dias_atras(29).isoformat(),
        "ate": hoje_local().isoformat(),
        "dias": 30,
    }


# --- vendas: série, fuso e consistência --------------------------------------------------------


async def test_venda_das_23h30_locais_cai_no_dia_local_e_a_das_00h10_no_seguinte(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    dia = dias_atras(3)
    await massa.comanda(local(dia, 23, 30), [ItemSemente(preco="10.00")])  # 02:30 UTC do dia+1
    await massa.comanda(local(dia + timedelta(days=1), 0, 10), [ItemSemente(preco="20.00")])

    serie = await _get(client, "/dashboard/vendas/serie", gerente, **_periodo(4, 2))
    assert [(p["inicio"], p["faturamento"]) for p in serie["pontos"]] == [
        (dias_atras(4).isoformat(), "0.00"),
        (dia.isoformat(), "10.00"),
        (dias_atras(2).isoformat(), "20.00"),
    ]
    resumo_dia = await _get(client, "/dashboard/vendas/resumo", gerente, de=dia, ate=dia)
    assert resumo_dia["atual"]["faturamento"] == "10.00"


async def test_por_hora_usa_a_hora_local(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    dia = dias_atras(2)
    await massa.comanda(local(dia, 23, 30), [ItemSemente(preco="10.00")])
    await massa.comanda(local(dia, 0, 10), [ItemSemente(preco="20.00")])
    await massa.comanda(local(dia, 14, 5), [ItemSemente(preco="5.00")])
    await massa.comanda(local(dia, 14, 55), [ItemSemente(preco="7.00")])

    r = await _get(client, "/dashboard/vendas/por-hora", gerente, de=dia, ate=dia)
    horas = {h["hora"]: h for h in r["horas"]}
    assert list(horas) == list(range(24))
    assert (horas[23]["qtd_comandas"], horas[23]["faturamento"]) == (1, "10.00")
    assert (horas[0]["qtd_comandas"], horas[0]["faturamento"]) == (1, "20.00")
    assert (horas[14]["qtd_comandas"], horas[14]["faturamento"]) == (2, "12.00")
    assert horas[3]["qtd_comandas"] == 0


async def test_serie_semanal_comeca_na_segunda_e_recorta_as_pontas(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    # 20 dias terminando hoje: cobre ao menos 3 semanas, com as duas pontas parciais.
    for n in range(0, 20, 3):
        await massa.comanda(local(dias_atras(n)), [ItemSemente(preco="10.00")])
    r = await _get(client, "/dashboard/vendas/serie", gerente, **_periodo(19), agrupamento="semana")
    pontos = r["pontos"]
    assert pontos[0]["inicio"] == dias_atras(19).isoformat()
    assert pontos[-1]["fim"] == hoje_local().isoformat()
    for p in pontos[1:]:
        assert (
            date.fromisoformat(p["inicio"]).weekday() == 0
        )  # toda semana (menos a 1ª) abre na segunda
    assert sum(D(p["faturamento"]) for p in pontos) == D(r["total_faturamento"]) == D("70.00")


async def test_serie_mensal(client: AsyncClient, gerente: Headers, massa: Massa) -> None:
    await massa.comanda(local(dias_atras(40)), [ItemSemente(preco="10.00")])
    await massa.comanda(local(dias_atras(1)), [ItemSemente(preco="5.00")])
    r = await _get(client, "/dashboard/vendas/serie", gerente, **_periodo(60), agrupamento="mes")
    assert 2 <= len(r["pontos"]) <= 3
    assert sum(D(p["faturamento"]) for p in r["pontos"]) == D("15.00")


async def test_serie_resumo_e_formas_fecham_o_mesmo_total(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await massa.comanda(
        local(dias_atras(1)),
        [ItemSemente(quantidade=2, preco="20.00", adicionais=(("Granola", 1, "2.50"),))],
        pagamentos=[("dinheiro", "20.00"), ("pix", "25.00")],
    )
    await massa.comanda(local(dias_atras(2)), [ItemSemente(preco="13.30")])
    await massa.comanda(local(dias_atras(3), 23, 59), [ItemSemente(preco="7.70")])
    await massa.comanda(local(dias_atras(30)), [ItemSemente(preco="999.00")])  # fora do período

    p = _periodo(5)
    resumo = await _get(client, "/dashboard/vendas/resumo", gerente, **p)
    serie = await _get(client, "/dashboard/vendas/serie", gerente, **p)
    formas = await _get(client, "/dashboard/vendas/por-forma-pagamento", gerente, **p)
    ranking = await _get(client, "/dashboard/vendas/mais-vendidos", gerente, **p)

    faturamento = D(resumo["atual"]["faturamento"])
    assert faturamento == D("66.00")  # 45 + 13.30 + 7.70
    assert sum(D(x["faturamento"]) for x in serie["pontos"]) == faturamento
    assert sum(D(f["valor"]) for f in formas["formas"]) == D(formas["total"]) == faturamento
    assert sum(D(i["receita"]) for i in ranking["itens"]) == faturamento  # adicional incluso


# --- vendas: por forma -------------------------------------------------------------------------


async def test_por_forma_traz_as_quatro_formas_inclusive_zeradas(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    dia = dias_atras(1)
    await massa.comanda(
        local(dia),
        [ItemSemente(preco="100.00")],
        pagamentos=[("pix", "60.00"), ("dinheiro", "40.00")],
    )
    await massa.comanda(local(dia, 15), [ItemSemente(preco="50.00")], pagamentos=[("pix", "50.00")])
    # Pagamento de comanda aberta/cancelada não existe; e o recorte é pela data da comanda.
    r = await _get(client, "/dashboard/vendas/por-forma-pagamento", gerente, de=dia, ate=dia)
    assert [f["forma"] for f in r["formas"]] == [
        "dinheiro",
        "pix",
        "cartao_debito",
        "cartao_credito",
    ]
    por_forma = {f["forma"]: f for f in r["formas"]}
    assert (por_forma["pix"]["valor"], por_forma["pix"]["qtd_pagamentos"]) == ("110.00", 2)
    assert por_forma["pix"]["participacao_pct"] == 73.3
    assert por_forma["dinheiro"]["participacao_pct"] == 26.7
    assert (por_forma["cartao_debito"]["valor"], por_forma["cartao_credito"]["qtd_pagamentos"]) == (
        "0.00",
        0,
    )
    assert r["total"] == "150.00"


# --- vendas: mais vendidos ---------------------------------------------------------------------


async def _massa_ranking(massa: Massa) -> None:
    dia = dias_atras(2)
    await massa.comanda(
        local(dia, 10),
        [
            ItemSemente(1, "Açaí", 2, "20.00"),
            ItemSemente(3, "Banana", 1, "10.00"),
            ItemSemente(4, "Abacate", 1, "10.00"),
        ],
    )
    await massa.comanda(
        local(dia, 11),
        [
            ItemSemente(1, "Açaí", 1, "20.00", adicionais=(("Granola", 2, "2.50"),)),
            ItemSemente(3, "Banana", 1, "10.00"),
            ItemSemente(4, "Abacate", 1, "10.00"),
            ItemSemente(2, "Suco", 5, "4.00"),
        ],
    )


async def test_ranking_por_quantidade_com_desempate_por_nome(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await _massa_ranking(massa)
    r = await _get(client, "/dashboard/vendas/mais-vendidos", gerente, **_periodo(3))
    assert [(i["nome"], i["quantidade"], i["receita"]) for i in r["itens"]] == [
        ("Suco", 5, "20.00"),
        ("Açaí", 3, "65.00"),
        ("Abacate", 2, "20.00"),
        ("Banana", 2, "20.00"),
    ]
    assert r["itens"][1]["participacao_pct"] == 52.0  # 65 / 125


async def test_ranking_por_receita_com_adicionais_e_desempate_deterministico(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await _massa_ranking(massa)
    for _ in range(3):  # chamadas repetidas não "dançam"
        r = await _get(
            client, "/dashboard/vendas/mais-vendidos", gerente, **_periodo(3), ordenar_por="receita"
        )
        assert [i["nome"] for i in r["itens"]] == ["Açaí", "Abacate", "Banana", "Suco"]


async def test_ranking_respeita_o_limite_e_a_participacao_e_sobre_todos_os_produtos(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await _massa_ranking(massa)
    r = await _get(client, "/dashboard/vendas/mais-vendidos", gerente, **_periodo(3), limite=1)
    assert [i["nome"] for i in r["itens"]] == ["Suco"]
    assert r["itens"][0]["participacao_pct"] == 16.0  # 20 / 125, não 100%


async def test_ranking_agrupa_tamanhos_do_mesmo_produto_e_usa_o_nome_mais_recente(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await massa.comanda(local(dias_atras(3)), [ItemSemente(1, "Açaí Antigo", 1, "10.00")])
    await massa.comanda(local(dias_atras(1)), [ItemSemente(1, "Açaí Novo", 2, "12.00")])
    r = await _get(client, "/dashboard/vendas/mais-vendidos", gerente, **_periodo(5))
    assert len(r["itens"]) == 1
    assert (r["itens"][0]["nome"], r["itens"][0]["quantidade"], r["itens"][0]["receita"]) == (
        "Açaí Novo",
        3,
        "34.00",
    )


async def test_historico_nao_muda_quando_o_produto_e_renomeado_ou_reprecificado(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    admin = await auth_headers("admin@acai.com", Papel.ADMIN)
    cat = (await client.post("/categorias", json={"nome": "Açaí"}, headers=admin)).json()["id"]
    tam = (await client.post("/tamanhos", json={"nome": "500 ml"}, headers=admin)).json()["id"]
    prod = (
        await client.post(
            "/produtos", json={"nome": "Tradicional", "categoria_id": cat}, headers=admin
        )
    ).json()["id"]
    r = await client.put(f"/produtos/{prod}/tamanhos/{tam}", json={"preco": "20.00"}, headers=admin)
    assert r.status_code == 200, r.text
    await abrir_caixa_api(client, admin, "0.00")
    cid = (await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=admin)).json()["id"]
    r = await client.post(
        f"/comandas/{cid}/itens",
        json={"produto_id": prod, "tamanho_id": tam, "quantidade": 2},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    assert (await fechar_comanda_api(client, admin, cid)).status_code == 200

    antes = await _get(client, "/dashboard/vendas/mais-vendidos", admin)
    assert antes["itens"][0]["nome"] == "Tradicional" and antes["itens"][0]["receita"] == "40.00"

    r = await client.patch(f"/produtos/{prod}", json={"nome": "Renomeado"}, headers=admin)
    assert r.status_code == 200, r.text
    r = await client.put(f"/produtos/{prod}/tamanhos/{tam}", json={"preco": "99.00"}, headers=admin)
    assert r.status_code == 200, r.text

    depois = await _get(client, "/dashboard/vendas/mais-vendidos", admin)
    assert depois == antes
    resumo = await _get(client, "/dashboard/vendas/resumo", admin)
    assert resumo["atual"]["faturamento"] == "40.00"


# --- estoque -----------------------------------------------------------------------------------


async def test_estoque_critico_regras_ordem_e_contadores(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    await massa.insumo("Polpa", "2.000", "2.000")  # exatamente no mínimo: entra
    await massa.insumo("Leite", "1.000", "4.000", "l")  # 25%
    await massa.insumo("Granola", "0.000", "2.000")  # zerado
    await massa.insumo("Banana", "5.000", "2.000")  # acima do mínimo: fora
    await massa.insumo("Calda", "0.000", "0.000")  # sem mínimo: fora
    await massa.insumo("Antigo", "0.000", "2.000", ativo=False)  # inativo: fora

    r = await _get(client, "/dashboard/estoque/critico", gerente)
    assert (r["total_zerados"], r["total_criticos"], r["total"]) == (1, 2, 3)
    assert [(i["nome"], i["nivel"]) for i in r["itens"]] == [
        ("Granola", "zerado"),
        ("Leite", "critico"),
        ("Polpa", "critico"),
    ]
    assert r["itens"][0] == {
        "insumo_id": r["itens"][0]["insumo_id"],
        "nome": "Granola",
        "unidade": "kg",
        "estoque_atual": "0.000",
        "estoque_minimo": "2.000",
        "deficit": "2.000",
        "cobertura_pct": 0.0,
        "nivel": "zerado",
    }
    assert (r["itens"][1]["deficit"], r["itens"][1]["cobertura_pct"]) == ("3.000", 25.0)
    assert (r["itens"][2]["deficit"], r["itens"][2]["cobertura_pct"]) == ("0.000", 100.0)


async def test_estoque_critico_filtra_por_nivel_e_pagina_sem_perder_os_contadores(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    for i in range(4):
        await massa.insumo(f"Crit{i}", "1.000", "4.000")
    await massa.insumo("Zero", "0.000", "1.000")

    so_criticos = await _get(client, "/dashboard/estoque/critico", gerente, nivel="critico")
    assert so_criticos["total"] == 4 and all(i["nivel"] == "critico" for i in so_criticos["itens"])
    assert (so_criticos["total_zerados"], so_criticos["total_criticos"]) == (1, 4)

    pagina = await _get(client, "/dashboard/estoque/critico", gerente, limit=2, offset=3)
    assert (pagina["total"], pagina["limit"], pagina["offset"]) == (5, 2, 3)
    assert len(pagina["itens"]) == 2
    alem = await _get(client, "/dashboard/estoque/critico", gerente, limit=2, offset=40)
    assert alem["itens"] == [] and (alem["total_zerados"], alem["total_criticos"]) == (1, 4)


async def test_estoque_critico_sem_nada_critico(client: AsyncClient, gerente: Headers) -> None:
    r = await _get(client, "/dashboard/estoque/critico", gerente)
    assert r == {
        "total_zerados": 0,
        "total_criticos": 0,
        "itens": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


# --- financeiro: fluxo de caixa ----------------------------------------------------------------


async def test_fluxo_realizado_soma_vendas_e_lancamentos_pagos_sem_contagem_dupla(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    ontem, anteontem = dias_atras(1), dias_atras(2)
    despesa = await massa.categoria("Aluguel", "despesa")
    luz = await massa.categoria("Luz", "despesa")
    receita = await massa.categoria("Eventos", "receita")

    # vendas: TODAS as formas entram (fluxo financeiro, não gaveta)
    await massa.comanda(
        local(ontem),
        [ItemSemente(preco="100.00")],
        pagamentos=[("pix", "60.00"), ("dinheiro", "40.00")],
    )
    await massa.comanda(
        local(anteontem), [ItemSemente(preco="30.00")], pagamentos=[("cartao_credito", "30.00")]
    )
    await massa.comanda(local(ontem), [ItemSemente(preco="9.00")], status="aberta")
    await massa.comanda(local(ontem), [ItemSemente(preco="8.00")], status="cancelada")
    # movimentação interna da gaveta não é receita nem despesa
    await massa.movimento("sangria", "500.00")
    await massa.movimento("suprimento", "300.00")
    # lançamentos
    await massa.lancamento("receber", "30.00", ontem, receita, "pago", ontem)
    await massa.lancamento("pagar", "45.00", ontem, despesa, "pago", ontem)
    await massa.lancamento("pagar", "5.00", anteontem, luz, "pago", anteontem)
    await massa.lancamento("pagar", "999.00", ontem, despesa, "pendente")
    await massa.lancamento("receber", "777.00", ontem, receita, "cancelado")

    r = await _get(client, "/dashboard/financeiro/fluxo-caixa", gerente, **_periodo(2, 0))
    assert r["agrupamento"] == "dia" and r["projecao"] is None
    assert r["resultado"] == {
        "entradas_vendas": "130.00",
        "entradas_outras": "30.00",
        "saidas": "50.00",
        "resultado": "110.00",
    }
    realizado = r["realizado"]
    assert len(realizado) == 3
    assert realizado[0]["entradas_vendas"] == "30.00" and realizado[0]["saidas"] == "5.00"
    assert realizado[0]["saldo_periodo"] == "25.00" and realizado[0]["saldo_acumulado"] == "25.00"
    assert (
        realizado[1]["entradas_vendas"] == "100.00" and realizado[1]["entradas_outras"] == "30.00"
    )
    assert realizado[1]["saldo_acumulado"] == "110.00"
    assert realizado[2]["saldo_periodo"] == "0.00" and realizado[2]["saldo_acumulado"] == "110.00"
    assert [
        (s["categoria"], s["valor"], s["participacao_pct"]) for s in r["saidas_por_categoria"]
    ] == [
        ("Aluguel", "45.00", 90.0),
        ("Luz", "5.00", 10.0),
    ]


async def test_projecao_so_aparece_com_a_flag_e_nunca_soma_ao_realizado(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    hoje = hoje_local()
    despesa = await massa.categoria("Aluguel", "despesa")
    receita = await massa.categoria("Eventos", "receita")
    await massa.comanda(local(dias_atras(1)), [ItemSemente(preco="100.00")])
    await massa.lancamento("pagar", "80.00", hoje + timedelta(days=2), despesa)
    await massa.lancamento("receber", "200.00", hoje + timedelta(days=2), receita)
    await massa.lancamento("pagar", "11.00", dias_atras(1), despesa)  # atrasado, dentro do período
    await massa.lancamento("pagar", "500.00", hoje + timedelta(days=30), despesa)  # fora do período

    base = {"de": dias_atras(1), "ate": hoje + timedelta(days=5)}
    r = await client.get(
        "/dashboard/financeiro/fluxo-caixa",
        params={**{k: str(v) for k, v in base.items()}},
        headers=gerente,
    )
    assert (
        r.status_code == 422 and r.json()["motivo"] == "periodo_no_futuro"
    )  # sem projeção, futuro não vale

    com = await _get(
        client, "/dashboard/financeiro/fluxo-caixa", gerente, **base, incluir_projecao="true"
    )
    assert com["resultado"]["resultado"] == "100.00"  # pendentes não entram no realizado
    projecao = com["projecao"]
    assert len(projecao) == 7
    assert sum(D(p["a_receber"]) for p in projecao) == D("200.00")
    assert sum(D(p["a_pagar"]) for p in projecao) == D("91.00")
    assert projecao[0]["a_pagar"] == "11.00"  # o atrasado fica no dia do vencimento original
    assert projecao[3]["a_receber"] == "200.00" and projecao[3]["a_pagar"] == "80.00"


async def test_fluxo_semanal_e_mensal(client: AsyncClient, gerente: Headers, massa: Massa) -> None:
    await massa.comanda(local(dias_atras(1)), [ItemSemente(preco="10.00")])
    await massa.comanda(local(dias_atras(40)), [ItemSemente(preco="20.00")])
    semanal = await _get(
        client, "/dashboard/financeiro/fluxo-caixa", gerente, **_periodo(45), agrupamento="semana"
    )
    mensal = await _get(
        client, "/dashboard/financeiro/fluxo-caixa", gerente, **_periodo(45), agrupamento="mes"
    )
    for r in (semanal, mensal):
        assert r["resultado"]["entradas_vendas"] == "30.00"
        assert r["realizado"][-1]["saldo_acumulado"] == "30.00"
    assert len(semanal["realizado"]) > len(mensal["realizado"])


# --- financeiro: contas ------------------------------------------------------------------------


async def test_contas_posicao_atrasados_hoje_e_proximos_7_dias(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    hoje = hoje_local()
    despesa = await massa.categoria("Aluguel", "despesa")
    receita = await massa.categoria("Eventos", "receita")
    mais = lambda n: hoje + timedelta(days=n)  # noqa: E731
    await massa.lancamento("pagar", "100.00", mais(-3), despesa, descricao="Atrasada")
    await massa.lancamento("pagar", "50.00", hoje, despesa, descricao="Vence hoje")
    await massa.lancamento("pagar", "30.00", mais(3), despesa)
    await massa.lancamento("pagar", "20.00", mais(7), despesa)
    await massa.lancamento("pagar", "10.00", mais(8), despesa)  # só no total pendente
    await massa.lancamento("pagar", "999.00", mais(-9), despesa, "pago", mais(-9))  # ignorado
    await massa.lancamento("pagar", "888.00", mais(-9), despesa, "cancelado")  # ignorado
    await massa.lancamento("receber", "40.00", mais(-1), receita, descricao="Recebimento atrasado")

    r = await _get(client, "/dashboard/financeiro/contas", gerente)
    assert r["hoje"] == hoje.isoformat()
    assert r["pagar"] == {
        "total_pendente": "210.00",
        "qtd_pendente": 5,
        "total_atrasado": "100.00",
        "qtd_atrasado": 1,
        "vence_hoje": {"valor": "50.00", "qtd": 1},
        "vence_em_7_dias": {"valor": "50.00", "qtd": 2},
    }
    assert r["receber"]["total_atrasado"] == "40.00" and r["receber"]["qtd_atrasado"] == 1
    assert r["receber"]["vence_hoje"] == {"valor": "0.00", "qtd": 0}

    proximos = r["proximos_vencimentos"]
    assert [p["atrasado"] for p in proximos] == [True, True, False, False, False, False]
    assert [p["vencimento"] for p in proximos] == sorted(p["vencimento"] for p in proximos)
    assert proximos[0]["descricao"] == "Atrasada" and proximos[0]["valor"] == "100.00"
    assert proximos[2]["descricao"] == "Vence hoje" and proximos[2]["atrasado"] is False


async def test_contas_limita_a_10_proximos(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    despesa = await massa.categoria("Aluguel", "despesa")
    for n in range(12):
        await massa.lancamento("pagar", "1.00", hoje_local() + timedelta(days=n), despesa)
    r = await _get(client, "/dashboard/financeiro/contas", gerente)
    assert len(r["proximos_vencimentos"]) == 10
    assert r["pagar"]["qtd_pendente"] == 12


async def test_contas_vazio_devolve_zeros(client: AsyncClient, gerente: Headers) -> None:
    r = await _get(client, "/dashboard/financeiro/contas", gerente)
    for lado in ("pagar", "receber"):
        assert r[lado]["total_pendente"] == "0.00" and r[lado]["qtd_pendente"] == 0
    assert r["proximos_vencimentos"] == []


# --- visão geral -------------------------------------------------------------------------------


async def test_visao_geral_junta_os_numeros_de_hoje(
    client: AsyncClient, gerente: Headers, massa: Massa
) -> None:
    hoje = hoje_local()
    despesa = await massa.categoria("Aluguel", "despesa")
    await massa.comanda(
        local(hoje, 0, 1), [ItemSemente(preco="60.00")], pagamentos=[("dinheiro", "60.00")]
    )
    await massa.comanda(local(hoje, 0, 2), [ItemSemente(preco="40.00")])
    await massa.comanda(local(hoje - timedelta(days=7), 12), [ItemSemente(preco="50.00")])
    await massa.comanda(local(hoje, 0, 3), [ItemSemente(preco="1.00")], status="aberta")
    await massa.movimento("suprimento", "20.00")
    await massa.movimento("sangria", "30.00")
    await massa.insumo("Granola", "0.000", "2.000")
    await massa.lancamento("pagar", "80.00", hoje - timedelta(days=1), despesa)
    await massa.lancamento("pagar", "15.00", hoje, despesa)

    r = await _get(client, "/dashboard/visao-geral", gerente)
    assert r["vendas_hoje"]["faturamento"] == "100.00" and r["vendas_hoje"]["qtd_comandas"] == 2
    assert r["vendas_hoje"]["ticket_medio"] == "50.00"
    assert r["vendas_hoje"]["mesmo_dia_semana_anterior"] == {
        "data": (hoje - timedelta(days=7)).isoformat(),
        "faturamento": "50.00",
        "qtd_comandas": 1,
        "ticket_medio": "50.00",
    }
    assert r["vendas_hoje"]["variacao_pct"] == {
        "faturamento": 100.0,
        "qtd_comandas": 100.0,
        "ticket_medio": 0.0,
    }
    assert r["comandas_abertas"] == 1
    # abertura 100 + dinheiro 60 + suprimento 20 - sangria 30 (pix não entra na gaveta)
    assert r["caixa"] == {"aberto": True, "sessao_id": massa.sessao_id, "saldo_dinheiro": "150.00"}
    assert r["estoque"] == {"total_zerados": 1, "total_criticos": 0}
    assert r["contas"] == {
        "qtd_atrasadas_pagar": 1,
        "valor_atrasado_pagar": "80.00",
        "qtd_atrasadas_receber": 0,
        "valor_atrasado_receber": "0.00",
        "vence_hoje_pagar": "15.00",
    }


async def test_visao_geral_com_caixa_fechado(client: AsyncClient, gerente: Headers) -> None:
    r = await _get(client, "/dashboard/visao-geral", gerente)
    assert r["caixa"] == {"aberto": False, "sessao_id": None, "saldo_dinheiro": None}
    assert r["vendas_hoje"]["variacao_pct"]["faturamento"] is None


# --- validação ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "motivo"),
    [
        ({"de": "2026-11-20", "ate": "2026-11-19"}, "periodo_invertido"),
        ({"de": "2020-01-01"}, "periodo_longo_demais"),
        ({"ate": "2999-01-01", "de": "2998-12-01"}, "periodo_no_futuro"),
    ],
)
@pytest.mark.parametrize(
    "rota",
    [
        "/dashboard/vendas/resumo",
        "/dashboard/vendas/serie",
        "/dashboard/vendas/mais-vendidos",
        "/dashboard/vendas/por-forma-pagamento",
        "/dashboard/vendas/por-hora",
        "/dashboard/financeiro/fluxo-caixa",
    ],
)
async def test_periodo_invalido_devolve_422(
    client: AsyncClient, gerente: Headers, rota: str, params: dict[str, str], motivo: str
) -> None:
    r = await client.get(rota, params={**params, "agrupamento": "mes"}, headers=gerente)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "periodo_invalido" and r.json()["motivo"] == motivo


async def test_agrupar_por_dia_so_ate_92_dias(client: AsyncClient, gerente: Headers) -> None:
    r = await client.get(
        "/dashboard/vendas/serie", params={**_periodo(92), "agrupamento": "dia"}, headers=gerente
    )
    assert r.status_code == 422 and r.json()["motivo"] == "agrupamento_dia_longo_demais"
    ok = await client.get(
        "/dashboard/vendas/serie", params={**_periodo(91), "agrupamento": "dia"}, headers=gerente
    )
    assert ok.status_code == 200 and len(ok.json()["pontos"]) == 92
    semana = await client.get(
        "/dashboard/vendas/serie",
        params={**_periodo(365), "agrupamento": "semana"},
        headers=gerente,
    )
    assert semana.status_code == 200


@pytest.mark.parametrize(
    ("rota", "params"),
    [
        ("/dashboard/vendas/serie", {"agrupamento": "ano"}),
        ("/dashboard/vendas/mais-vendidos", {"ordenar_por": "nome"}),
        ("/dashboard/vendas/mais-vendidos", {"limite": "0"}),
        ("/dashboard/vendas/mais-vendidos", {"limite": "51"}),
        ("/dashboard/estoque/critico", {"nivel": "baixo"}),
        ("/dashboard/estoque/critico", {"limit": "0"}),
        ("/dashboard/vendas/resumo", {"de": "ontem"}),
    ],
)
async def test_parametros_fora_do_contrato_devolvem_422(
    client: AsyncClient, gerente: Headers, rota: str, params: dict[str, str]
) -> None:
    assert (await client.get(rota, params=params, headers=gerente)).status_code == 422


# --- leitura pura e número de consultas --------------------------------------------------------


class _Contador:
    def __init__(self, factory: Factory) -> None:
        self.comandos: list[str] = []  # da última medição
        self.todos: list[str] = []  # de tudo desde que o contador existe
        engine = factory.kw["bind"].sync_engine
        event.listen(engine, "before_cursor_execute", self._contar)

    def _contar(self, _c: Any, _cur: Any, statement: str, *_: Any) -> None:
        self.comandos.append(statement)
        self.todos.append(statement)

    async def medir(self, client: AsyncClient, url: str, h: Headers, **params: str) -> int:
        self.comandos.clear()
        r = await client.get(url, params=params, headers=h)
        assert r.status_code == 200, r.text
        return len(self.comandos)


# (rota, parâmetros, teto de consultas do dashboard). Soma-se 1 da autenticação do usuário.
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


async def test_numero_de_consultas_e_fixo_e_nao_cresce_com_o_volume(
    client: AsyncClient, gerente: Headers, massa: Massa, factory: Factory
) -> None:
    contador = _Contador(factory)
    categoria = await massa.categoria("Aluguel", "despesa")

    async def semear(qtd: int, base: int = 0) -> None:
        for n in range(base, base + qtd):
            await massa.comanda(
                local(dias_atras(n % 10), 8 + n % 12),
                [ItemSemente(n % 5, f"Produto {n % 5}", 1 + n % 3, "12.00")],
                pagamentos=[("pix", "5.00"), ("dinheiro", str(D("12.00") * (1 + n % 3) - 5))],
            )
            await massa.lancamento(
                "pagar", "3.00", dias_atras(n % 7), categoria, "pago", dias_atras(n % 7)
            )
            await massa.insumo(f"Insumo {n}", "0.000", "1.000")

    await semear(5)
    pequeno = {}
    for rota, params, teto in TETOS:
        total = await contador.medir(client, rota, gerente, **params)
        assert total <= teto + 1, f"{rota}: {total} consultas (teto {teto} + autenticação)"
        pequeno[(rota, tuple(params))] = total

    await semear(40, base=5)
    for rota, params, _ in TETOS:
        assert (
            await contador.medir(client, rota, gerente, **params) == pequeno[(rota, tuple(params))]
        )


async def test_dashboard_nao_escreve_no_banco_nem_na_auditoria(
    client: AsyncClient, gerente: Headers, massa: Massa, factory: Factory
) -> None:
    await massa.comanda(local(dias_atras(1)), [ItemSemente()])
    contador = _Contador(factory)
    for rota, params, _ in TETOS:
        await contador.medir(client, rota, gerente, **params)
    escritas = [
        c
        for c in contador.todos
        if c.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        or "FOR UPDATE" in c.upper()
    ]
    assert escritas == []
