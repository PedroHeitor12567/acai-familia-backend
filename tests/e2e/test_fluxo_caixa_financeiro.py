from datetime import date, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.container import build_criar_usuario
from app.domain.usuarios.entities import Papel
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from tests.comandas_helpers import abrir_caixa_api, fechar_comanda_api

pytestmark = pytest.mark.postgres

SENHA = "senha-e2e-123"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    r = await client.post("/auth/login", json={"email": email, "senha": SENHA})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _id(resposta: Response) -> int:
    assert resposta.status_code in (200, 201), resposta.text
    return int(resposta.json()["id"])


async def _comanda(client: AsyncClient, h: dict[str, str], produto: int, tamanho: int) -> int:
    cid = _id(await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h))
    r = await client.post(
        f"/comandas/{cid}/itens",
        json={"produto_id": produto, "tamanho_id": tamanho, "quantidade": 2},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return cid


async def test_fluxo_completo_de_caixa_e_financeiro(
    pg_client: AsyncClient, pg_session: AsyncSession
) -> None:
    criar = build_criar_usuario(pg_session)
    for nome, papel in (
        ("Admin", Papel.ADMIN),
        ("Caixa", Papel.CAIXA),
        ("Atendente", Papel.ATENDENTE),
    ):
        await criar.executar(None, nome, f"{papel}-caixa-fin@acai.com", SENHA, papel)
    admin = await _login(pg_client, "admin-caixa-fin@acai.com")
    caixa = await _login(pg_client, "caixa-caixa-fin@acai.com")
    atendente = await _login(pg_client, "atendente-caixa-fin@acai.com")

    cat = _id(await pg_client.post("/categorias", json={"nome": "Açaí"}, headers=admin))
    tam = _id(await pg_client.post("/tamanhos", json={"nome": "500 ml"}, headers=admin))
    prod = _id(
        await pg_client.post(
            "/produtos", json={"nome": "Tradicional", "categoria_id": cat}, headers=admin
        )
    )
    await pg_client.put(f"/produtos/{prod}/tamanhos/{tam}", json={"preco": "20.00"}, headers=admin)

    r = await pg_client.post("/caixa/sessoes", json={"valor_abertura": "100.00"}, headers=atendente)
    assert r.status_code == 403
    sessao = await abrir_caixa_api(pg_client, caixa, "100.00")
    r = await pg_client.post("/caixa/sessoes", json={"valor_abertura": "1.00"}, headers=caixa)
    assert r.status_code == 409 and r.json()["code"] == "caixa_ja_aberto"
    r = await pg_client.post(
        f"/caixa/sessoes/{sessao}/movimentos",
        json={"tipo": "suprimento", "valor": "50.00", "motivo": "reforço de troco"},
        headers=caixa,
    )
    assert r.status_code == 201

    cid = await _comanda(pg_client, atendente, prod, tam)
    r = await pg_client.post(
        f"/comandas/{cid}/fechar",
        json={
            "pagamentos": [
                {"forma": "dinheiro", "valor": "20.00", "valor_recebido": "50.00"},
                {"forma": "pix", "valor": "20.00"},
            ]
        },
        headers=caixa,
    )
    assert r.status_code == 200, r.text
    assert r.json()["troco"] == "30.00" and r.json()["sessao_caixa_id"] == sessao

    r = await pg_client.post(
        f"/caixa/sessoes/{sessao}/movimentos",
        json={"tipo": "sangria", "valor": "40.00", "motivo": "depósito no banco"},
        headers=caixa,
    )
    assert r.status_code == 201
    atual = (await pg_client.get("/caixa/sessoes/atual", headers=caixa)).json()
    assert atual["saldo_dinheiro"] == "130.00"
    r = await pg_client.post(
        f"/caixa/sessoes/{sessao}/movimentos",
        json={"tipo": "sangria", "valor": "130.01", "motivo": "tudo"},
        headers=caixa,
    )
    assert r.status_code == 409 and r.json()["code"] == "saldo_caixa_insuficiente"

    r = await pg_client.post(
        f"/caixa/sessoes/{sessao}/fechar", json={"valor_contado": "128.00"}, headers=caixa
    )
    assert r.status_code == 422 and r.json()["code"] == "justificativa_obrigatoria"
    r = await pg_client.post(
        f"/caixa/sessoes/{sessao}/fechar",
        json={"valor_contado": "128.00", "observacao": "troco dado a mais"},
        headers=caixa,
    )
    assert r.status_code == 200, r.text
    fechada = r.json()
    assert (fechada["valor_esperado"], fechada["valor_contado"], fechada["diferenca"]) == (
        "130.00",
        "128.00",
        "-2.00",
    )
    assert fechada["resumo_por_forma"] == {
        "dinheiro": "20.00",
        "pix": "20.00",
        "cartao_debito": "0.00",
        "cartao_credito": "0.00",
    }
    r = await pg_client.post(
        f"/caixa/sessoes/{sessao}/fechar", json={"valor_contado": "128.00"}, headers=caixa
    )
    assert r.status_code == 409 and r.json()["code"] == "sessao_nao_aberta"

    cid2 = await _comanda(pg_client, atendente, prod, tam)
    r = await fechar_comanda_api(pg_client, caixa, cid2)
    assert r.status_code == 409 and r.json()["code"] == "caixa_fechado"
    assert (await pg_client.get(f"/comandas/{cid2}", headers=caixa)).json()["status"] == "aberta"
    nova = await abrir_caixa_api(pg_client, caixa, "0.00")
    r = await fechar_comanda_api(pg_client, caixa, cid2)
    assert r.status_code == 200 and r.json()["sessao_caixa_id"] == nova
    r = await pg_client.post(
        f"/caixa/sessoes/{nova}/fechar", json={"valor_contado": "0.00"}, headers=caixa
    )
    assert r.status_code == 200 and r.json()["diferenca"] == "0.00"
    sessoes = (await pg_client.get("/caixa/sessoes", headers=caixa)).json()
    assert [s["id"] for s in sessoes["itens"][:2]] == [nova, sessao]

    r = await pg_client.get("/financeiro/lancamentos", headers=caixa)
    assert r.status_code == 403
    despesa = _id(
        await pg_client.post(
            "/financeiro/categorias",
            json={"nome": "Fornecedores", "tipo": "despesa"},
            headers=admin,
        )
    )
    receita = _id(
        await pg_client.post(
            "/financeiro/categorias", json={"nome": "Eventos", "tipo": "receita"}, headers=admin
        )
    )
    hoje = date.today()
    vencido = _id(
        await pg_client.post(
            "/financeiro/lancamentos",
            json={
                "tipo": "pagar",
                "descricao": "Polpa de açaí",
                "valor": "350.00",
                "vencimento": (hoje - timedelta(days=5)).isoformat(),
                "categoria_id": despesa,
                "contraparte": "Fornecedor X",
            },
            headers=admin,
        )
    )
    a_receber = _id(
        await pg_client.post(
            "/financeiro/lancamentos",
            json={
                "tipo": "receber",
                "descricao": "Buffet de aniversário",
                "valor": "800.00",
                "vencimento": (hoje + timedelta(days=10)).isoformat(),
                "categoria_id": receita,
            },
            headers=admin,
        )
    )
    r = await pg_client.post(
        "/financeiro/lancamentos",
        json={
            "tipo": "pagar",
            "descricao": "Errado",
            "valor": "10.00",
            "vencimento": hoje.isoformat(),
            "categoria_id": receita,
        },
        headers=admin,
    )
    assert r.status_code == 422 and r.json()["code"] == "categoria_incompativel"

    atrasados = (
        await pg_client.get("/financeiro/lancamentos", params={"atrasados": True}, headers=admin)
    ).json()
    assert [i["id"] for i in atrasados["itens"]] == [vencido] and atrasados["itens"][0]["atrasado"]

    r = await pg_client.post(
        f"/financeiro/lancamentos/{vencido}/baixar",
        json={"data_pagamento": hoje.isoformat(), "forma": "pix"},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["status"] == "pago" and not r.json()["atrasado"]
    r = await pg_client.post(
        f"/financeiro/lancamentos/{a_receber}/cancelar",
        json={"motivo": "evento cancelado"},
        headers=admin,
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelado"
    r = await pg_client.patch(
        f"/financeiro/lancamentos/{vencido}", json={"descricao": "outra"}, headers=admin
    )
    assert r.status_code == 409 and r.json()["code"] == "lancamento_nao_pendente"
    atrasados = (
        await pg_client.get("/financeiro/lancamentos", params={"atrasados": True}, headers=admin)
    ).json()
    assert atrasados["total"] == 0

    logs = (
        await pg_session.execute(
            select(AuditLogModel.entidade, AuditLogModel.acao).where(
                AuditLogModel.entidade.in_(["caixa_sessao", "lancamento", "categoria_financeira"])
            )
        )
    ).all()
    esperados = {
        ("caixa_sessao", "abrir"),
        ("caixa_sessao", "suprimento"),
        ("caixa_sessao", "sangria"),
        ("caixa_sessao", "fechar"),
        ("categoria_financeira", "criar"),
        ("lancamento", "criar"),
        ("lancamento", "baixar"),
        ("lancamento", "cancelar"),
    }
    assert esperados <= {(e, a) for e, a in logs}
