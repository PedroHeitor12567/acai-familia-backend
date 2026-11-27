"""Fluxo ponta a ponta do dashboard: vende pela API e confere os números agregados.

Cardápio, estoque, comandas, caixa e financeiro são montados só pelas rotas públicas; o dashboard
é conferido contra o que foi de fato vendido, baixado e lançado.
"""

from datetime import timedelta
from typing import Any

from httpx import AsyncClient, Response

from app.domain.usuarios.entities import Papel
from tests.comandas_helpers import abrir_caixa_api
from tests.conftest import AuthHeaders
from tests.dashboard_helpers import hoje_local

Headers = dict[str, str]


def _id(r: Response) -> int:
    assert r.status_code in (200, 201), r.text
    return int(r.json()["id"])


async def _get(client: AsyncClient, url: str, h: Headers, **params: str) -> dict[str, Any]:
    r = await client.get(url, params=params, headers=h)
    assert r.status_code == 200, r.text
    corpo: dict[str, Any] = r.json()
    return corpo


async def _vender(
    client: AsyncClient,
    h: Headers,
    itens: list[tuple[int, int, int]],
    pagamentos: list[dict[str, str]],
) -> None:
    cid = _id(await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h))
    for produto, tamanho, quantidade in itens:
        r = await client.post(
            f"/comandas/{cid}/itens",
            json={"produto_id": produto, "tamanho_id": tamanho, "quantidade": quantidade},
            headers=h,
        )
        assert r.status_code == 201, r.text
    r = await client.post(f"/comandas/{cid}/fechar", json={"pagamentos": pagamentos}, headers=h)
    assert r.status_code == 200, r.text


async def test_dashboard_acompanha_vendas_estoque_e_financeiro(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    admin = await auth_headers("admin@acai.com", Papel.ADMIN)
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    hoje = hoje_local()

    # cardápio, insumo e ficha: cada açaí gasta 1 kg de polpa; mínimo de 2 kg
    cat = _id(await client.post("/categorias", json={"nome": "Açaí"}, headers=admin))
    tam = _id(await client.post("/tamanhos", json={"nome": "500 ml"}, headers=admin))
    acai = _id(
        await client.post(
            "/produtos", json={"nome": "Tradicional", "categoria_id": cat}, headers=admin
        )
    )
    suco = _id(
        await client.post("/produtos", json={"nome": "Suco", "categoria_id": cat}, headers=admin)
    )
    for produto, preco in ((acai, "20.00"), (suco, "10.00")):
        r = await client.put(
            f"/produtos/{produto}/tamanhos/{tam}", json={"preco": preco}, headers=admin
        )
        assert r.status_code == 200, r.text
    polpa = _id(
        await client.post(
            "/estoque/insumos",
            json={"nome": "Polpa", "unidade": "kg", "estoque_minimo": "2.000"},
            headers=admin,
        )
    )
    r = await client.post(
        f"/estoque/insumos/{polpa}/movimentacoes",
        json={"tipo": "entrada", "quantidade": "5.000", "motivo": "carga inicial"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    r = await client.put(
        f"/produtos/{acai}/tamanhos/{tam}/ficha-tecnica",
        json={"itens": [{"insumo_id": polpa, "quantidade": "1.000"}]},
        headers=admin,
    )
    assert r.status_code == 200, r.text

    # antes de vender: nada vendido, nada crítico, caixa fechado
    visao = await _get(client, "/dashboard/visao-geral", admin)
    assert visao["vendas_hoje"]["faturamento"] == "0.00"
    assert visao["caixa"] == {"aberto": False, "sessao_id": None, "saldo_dinheiro": None}
    assert (await _get(client, "/dashboard/estoque/critico", admin))["total"] == 0

    # abrir o caixa e vender com formas variadas
    sessao = await abrir_caixa_api(client, caixa, "100.00")
    await _vender(client, caixa, [(acai, tam, 2)], [{"forma": "pix", "valor": "40.00"}])
    await _vender(
        client,
        caixa,
        [(acai, tam, 2), (suco, tam, 1)],
        [{"forma": "dinheiro", "valor": "20.00"}, {"forma": "cartao_credito", "valor": "30.00"}],
    )
    _id(await client.post("/comandas", json={"cliente_nome": "Aberta"}, headers=caixa))

    visao = await _get(client, "/dashboard/visao-geral", admin)
    assert visao["vendas_hoje"]["faturamento"] == "90.00"
    assert visao["vendas_hoje"]["qtd_comandas"] == 2
    assert visao["vendas_hoje"]["ticket_medio"] == "45.00"
    assert visao["vendas_hoje"]["variacao_pct"]["faturamento"] is None  # sem venda no dia anterior
    assert visao["comandas_abertas"] == 1
    assert visao["caixa"] == {"aberto": True, "sessao_id": sessao, "saldo_dinheiro": "120.00"}
    assert visao["estoque"] == {"total_zerados": 0, "total_criticos": 1}

    resumo = await _get(client, "/dashboard/vendas/resumo", admin)
    assert resumo["atual"]["faturamento"] == "90.00" and resumo["atual"]["itens_vendidos"] == 5
    formas = await _get(client, "/dashboard/vendas/por-forma-pagamento", admin)
    assert {f["forma"]: f["valor"] for f in formas["formas"]} == {
        "dinheiro": "20.00",
        "pix": "40.00",
        "cartao_debito": "0.00",
        "cartao_credito": "30.00",
    }
    assert formas["total"] == resumo["atual"]["faturamento"]
    ranking = await _get(client, "/dashboard/vendas/mais-vendidos", admin)
    assert [(i["nome"], i["quantidade"], i["receita"]) for i in ranking["itens"]] == [
        ("Tradicional", 4, "80.00"),
        ("Suco", 1, "10.00"),
    ]

    # 4 kg baixados do estoque: sobra 1 kg de um mínimo de 2 kg
    critico = await _get(client, "/dashboard/estoque/critico", admin)
    assert (critico["total_zerados"], critico["total_criticos"]) == (0, 1)
    assert critico["itens"][0] == {
        "insumo_id": polpa,
        "nome": "Polpa",
        "unidade": "kg",
        "estoque_atual": "1.000",
        "estoque_minimo": "2.000",
        "deficit": "1.000",
        "cobertura_pct": 50.0,
        "nivel": "critico",
    }
    r = await client.post(
        f"/estoque/insumos/{polpa}/movimentacoes",
        json={"tipo": "saida", "quantidade": "1.000", "motivo": "perda"},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    zerado = await _get(client, "/dashboard/estoque/critico", admin, nivel="zerado")
    assert [i["nivel"] for i in zerado["itens"]] == ["zerado"]

    # financeiro: um pago, um pendente futuro (a receber) e um pendente atrasado (a pagar)
    despesa = _id(
        await client.post(
            "/financeiro/categorias",
            json={"nome": "Fornecedores", "tipo": "despesa"},
            headers=admin,
        )
    )
    receita = _id(
        await client.post(
            "/financeiro/categorias", json={"nome": "Eventos", "tipo": "receita"}, headers=admin
        )
    )
    lancamentos = [
        {
            "tipo": "pagar",
            "descricao": "Polpa paga",
            "valor": "45.00",
            "vencimento": hoje.isoformat(),
            "categoria_id": despesa,
            "baixa": {"data_pagamento": hoje.isoformat(), "forma": "pix"},
        },
        {
            "tipo": "receber",
            "descricao": "Buffet",
            "valor": "200.00",
            "vencimento": (hoje + timedelta(days=3)).isoformat(),
            "categoria_id": receita,
        },
        {
            "tipo": "pagar",
            "descricao": "Aluguel atrasado",
            "valor": "80.00",
            "vencimento": (hoje - timedelta(days=2)).isoformat(),
            "categoria_id": despesa,
        },
    ]
    for corpo in lancamentos:
        _id(await client.post("/financeiro/lancamentos", json=corpo, headers=admin))

    fluxo = await _get(
        client,
        "/dashboard/financeiro/fluxo-caixa",
        admin,
        de=hoje.isoformat(),
        ate=hoje.isoformat(),
    )
    assert fluxo["resultado"] == {
        "entradas_vendas": "90.00",
        "entradas_outras": "0.00",
        "saidas": "45.00",
        "resultado": "45.00",
    }  # sangria/suprimento/fundo de troco e pendentes ficam de fora
    assert fluxo["projecao"] is None
    assert fluxo["saidas_por_categoria"] == [
        {"categoria": "Fornecedores", "valor": "45.00", "participacao_pct": 100.0}
    ]

    com_projecao = await _get(
        client,
        "/dashboard/financeiro/fluxo-caixa",
        admin,
        de=(hoje - timedelta(days=3)).isoformat(),
        ate=(hoje + timedelta(days=5)).isoformat(),
        incluir_projecao="true",
    )
    assert com_projecao["resultado"]["resultado"] == "45.00"
    projecao = com_projecao["projecao"]
    assert sum(float(p["a_receber"]) for p in projecao) == 200.0
    assert sum(float(p["a_pagar"]) for p in projecao) == 80.0

    contas = await _get(client, "/dashboard/financeiro/contas", admin)
    assert contas["pagar"]["total_pendente"] == "80.00"
    assert (contas["pagar"]["total_atrasado"], contas["pagar"]["qtd_atrasado"]) == ("80.00", 1)
    assert contas["receber"]["vence_em_7_dias"] == {"valor": "200.00", "qtd": 1}
    assert [(v["descricao"], v["atrasado"]) for v in contas["proximos_vencimentos"]] == [
        ("Aluguel atrasado", True),
        ("Buffet", False),
    ]
    visao = await _get(client, "/dashboard/visao-geral", admin)
    assert visao["contas"]["qtd_atrasadas_pagar"] == 1
    assert visao["contas"]["valor_atrasado_pagar"] == "80.00"

    # o caixa, que já vê a própria sessão, não acessa o dashboard
    r = await client.get("/dashboard/visao-geral", headers=caixa)
    assert r.status_code == 403
