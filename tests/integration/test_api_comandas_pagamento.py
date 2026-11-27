import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.usuarios.entities import Papel
from tests.comandas_helpers import Semente, abrir_caixa_api, semear_cardapio
from tests.conftest import AuthHeaders


@pytest.fixture
async def sem(factory: async_sessionmaker[AsyncSession]) -> Semente:
    async with factory() as s:
        return await semear_cardapio(s)


async def _comanda(
    client: AsyncClient, h: dict[str, str], sem: Semente, quantidade: int = 2
) -> int:
    cid = int(
        (await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h)).json()["id"]
    )
    r = await client.post(
        f"/comandas/{cid}/itens",
        json={"produto_id": sem.produto_id, "tamanho_id": sem.tamanho_id, "quantidade": quantidade},
        headers=h,
    )
    assert r.status_code == 201
    return cid


async def _saldo_polpa(client: AsyncClient, h: dict[str, str], sem: Semente) -> str:
    return str(
        (await client.get(f"/estoque/insumos/{sem.polpa_id}", headers=h)).json()["estoque_atual"]
    )


async def test_fechar_sem_caixa_aberto_da_409_e_nada_muda(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    cid = await _comanda(client, caixa, sem)

    r = await client.post(
        f"/comandas/{cid}/fechar",
        json={"pagamentos": [{"forma": "pix", "valor": "37.80"}]},
        headers=caixa,
    )

    assert r.status_code == 409 and r.json()["code"] == "caixa_fechado"
    assert (await client.get(f"/comandas/{cid}", headers=caixa)).json()["status"] == "aberta"
    assert await _saldo_polpa(client, gerente, sem) == "10.000"


@pytest.mark.parametrize(
    ("corpo", "status", "code"),
    [
        (None, 422, "pagamento_diferente_do_total"),
        ({}, 422, "pagamento_diferente_do_total"),
        ({"pagamentos": []}, 422, "pagamento_diferente_do_total"),
        ({"pagamentos": [{"forma": "pix", "valor": "37.79"}]}, 422, "pagamento_diferente_do_total"),
        ({"pagamentos": [{"forma": "pix", "valor": "37.81"}]}, 422, "pagamento_diferente_do_total"),
        (
            {"pagamentos": [{"forma": "pix", "valor": "30.00"}, {"forma": "pix", "valor": "7.80"}]},
            422,
            "forma_repetida",
        ),
        (
            {"pagamentos": [{"forma": "pix", "valor": "37.80", "valor_recebido": "40.00"}]},
            422,
            "valor_recebido_invalido",
        ),
        (
            {"pagamentos": [{"forma": "dinheiro", "valor": "37.80", "valor_recebido": "30.00"}]},
            422,
            "valor_recebido_insuficiente",
        ),
    ],
)
async def test_pagamento_errado_da_422_e_nao_grava_nada(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    sem: Semente,
    corpo: dict[str, object] | None,
    status: int,
    code: str,
) -> None:
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    await abrir_caixa_api(client, caixa)
    cid = await _comanda(client, caixa, sem)

    r = await client.post(f"/comandas/{cid}/fechar", json=corpo, headers=caixa)

    assert r.status_code == status and r.json()["code"] == code, r.text
    assert (await client.get(f"/comandas/{cid}", headers=caixa)).json()["status"] == "aberta"
    assert await _saldo_polpa(client, gerente, sem) == "10.000"
    assert (await client.get("/caixa/sessoes/atual", headers=caixa)).json()["resumo_por_forma"][
        "pix"
    ] == "0.00"


@pytest.mark.parametrize(
    "pagamento",
    [
        {"forma": "pix", "valor": "0"},
        {"forma": "pix", "valor": "-1.00"},
        {"forma": "pix", "valor": "10.005"},
        {"forma": "boleto", "valor": "37.80"},
        {"forma": "pix"},
        {"forma": "pix", "valor": "37.80", "extra": 1},
    ],
)
async def test_pagamento_malformado_da_422(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente, pagamento: dict[str, object]
) -> None:
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    await abrir_caixa_api(client, caixa)
    cid = await _comanda(client, caixa, sem)
    r = await client.post(
        f"/comandas/{cid}/fechar", json={"pagamentos": [pagamento]}, headers=caixa
    )
    assert r.status_code == 422


async def test_dinheiro_com_troco_e_pix_aparecem_no_fechamento_na_comanda_e_na_sessao(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    sid = await abrir_caixa_api(client, caixa, "100.00")
    cid = await _comanda(client, caixa, sem)

    r = await client.post(
        f"/comandas/{cid}/fechar",
        json={
            "pagamentos": [
                {"forma": "dinheiro", "valor": "10.00", "valor_recebido": "20.00"},
                {"forma": "pix", "valor": "27.80"},
            ]
        },
        headers=caixa,
    )

    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "fechada" and corpo["total"] == "37.80"
    assert corpo["troco"] == "10.00" and corpo["sessao_caixa_id"] == sid
    assert [
        (p["forma"], p["valor"], p["valor_recebido"], p["troco"]) for p in corpo["pagamentos"]
    ] == [
        ("dinheiro", "10.00", "20.00", "10.00"),
        ("pix", "27.80", None, "0.00"),
    ]
    detalhe = (await client.get(f"/comandas/{cid}", headers=caixa)).json()
    assert detalhe["troco"] == "10.00" and len(detalhe["pagamentos"]) == 2
    atual = (await client.get("/caixa/sessoes/atual", headers=caixa)).json()
    assert atual["saldo_dinheiro"] == "110.00"
    assert atual["resumo_por_forma"] == {
        "dinheiro": "10.00",
        "pix": "27.80",
        "cartao_debito": "0.00",
        "cartao_credito": "0.00",
    }


async def test_comanda_aberta_nao_tem_pagamentos(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    cid = await _comanda(client, caixa, sem)
    detalhe = (await client.get(f"/comandas/{cid}", headers=caixa)).json()
    assert detalhe["pagamentos"] == [] and detalhe["troco"] == "0.00"


async def test_fechar_comanda_depois_de_fechar_o_caixa_da_409(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    caixa = await auth_headers("caixa@acai.com", Papel.CAIXA)
    sid = await abrir_caixa_api(client, caixa)
    cid = await _comanda(client, caixa, sem)
    r = await client.post(
        f"/caixa/sessoes/{sid}/fechar", json={"valor_contado": "0.00"}, headers=caixa
    )
    assert r.status_code == 200

    r = await client.post(
        f"/comandas/{cid}/fechar",
        json={"pagamentos": [{"forma": "pix", "valor": "37.80"}]},
        headers=caixa,
    )
    assert r.status_code == 409 and r.json()["code"] == "caixa_fechado"
    novo = await abrir_caixa_api(client, caixa)
    r = await client.post(
        f"/comandas/{cid}/fechar",
        json={"pagamentos": [{"forma": "pix", "valor": "37.80"}]},
        headers=caixa,
    )
    assert r.status_code == 200 and r.json()["sessao_caixa_id"] == novo


async def test_comanda_de_total_zero_fecha_sem_caixa_aberto(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    factory: async_sessionmaker[AsyncSession],
    sem: Semente,
) -> None:
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    await client.put(
        f"/produtos/{sem.produto_id}/tamanhos/{sem.tamanho_id}",
        json={"preco": "0.00"},
        headers=gerente,
    )
    cid = await _comanda(client, gerente, sem, quantidade=1)

    r = await client.post(f"/comandas/{cid}/fechar", json={"pagamentos": []}, headers=gerente)

    assert r.status_code == 200, r.text
    assert r.json()["total"] == "0.00" and r.json()["pagamentos"] == []
    assert r.json()["sessao_caixa_id"] is None
