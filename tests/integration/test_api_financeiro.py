from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.domain.usuarios.entities import Papel
from tests.conftest import AuthHeaders

Headers = dict[str, str]


async def _categoria(client: AsyncClient, h: Headers, nome: str, tipo: str) -> int:
    r = await client.post("/financeiro/categorias", json={"nome": nome, "tipo": tipo}, headers=h)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def _lancamento(client: AsyncClient, h: Headers, **campos: object) -> dict[str, object]:
    corpo: dict[str, object] = {
        "tipo": "pagar",
        "descricao": "Polpa",
        "valor": "100.00",
        "vencimento": "2999-12-31",
        **campos,
    }
    r = await client.post("/financeiro/lancamentos", json=corpo, headers=h)
    assert r.status_code == 201, r.text
    resposta: dict[str, object] = r.json()
    return resposta


@pytest.mark.parametrize("papel", [Papel.CAIXA, Papel.ATENDENTE])
async def test_caixa_e_atendente_nao_acessam_o_financeiro(
    client: AsyncClient, auth_headers: AuthHeaders, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    chamadas = [
        client.get("/financeiro/categorias", headers=h),
        client.post("/financeiro/categorias", json={"nome": "X", "tipo": "despesa"}, headers=h),
        client.get("/financeiro/lancamentos", headers=h),
        client.get("/financeiro/lancamentos/1", headers=h),
        client.post("/financeiro/lancamentos/1/cancelar", headers=h),
    ]
    for chamada in chamadas:
        r = await chamada
        assert r.status_code == 403 and r.json()["code"] == "permissao_negada"


@pytest.mark.parametrize("papel", [Papel.ADMIN, Papel.GERENTE])
async def test_admin_e_gerente_acessam_o_financeiro(
    client: AsyncClient, auth_headers: AuthHeaders, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    assert (await client.get("/financeiro/categorias", headers=h)).status_code == 200
    assert (await client.get("/financeiro/lancamentos", headers=h)).status_code == 200


async def test_categorias_criar_listar_renomear_e_desativar(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    despesa = await _categoria(client, h, "Fornecedores", "despesa")
    await _categoria(client, h, "Eventos", "receita")

    r = await client.post(
        "/financeiro/categorias", json={"nome": "fornecedores", "tipo": "despesa"}, headers=h
    )
    assert r.status_code == 409 and r.json()["code"] == "nome_ja_cadastrado"
    r = await client.post(
        "/financeiro/categorias", json={"nome": "Fornecedores", "tipo": "receita"}, headers=h
    )
    assert r.status_code == 201
    r = await client.post(
        "/financeiro/categorias", json={"nome": " ", "tipo": "despesa"}, headers=h
    )
    assert r.status_code == 422

    r = await client.patch(f"/financeiro/categorias/{despesa}", json={"nome": "Insumos"}, headers=h)
    assert r.status_code == 200 and r.json()["nome"] == "Insumos"
    r = await client.patch(f"/financeiro/categorias/{despesa}", json={"ativo": False}, headers=h)
    assert r.status_code == 200 and r.json()["ativo"] is False
    assert (
        await client.patch(f"/financeiro/categorias/{despesa}", json={}, headers=h)
    ).status_code == 422
    r = await client.patch("/financeiro/categorias/999", json={"ativo": True}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "categoria_financeira_nao_encontrada"

    todas = (await client.get("/financeiro/categorias", headers=h)).json()
    assert len(todas) == 3
    ativas = (await client.get("/financeiro/categorias", params={"ativo": True}, headers=h)).json()
    assert len(ativas) == 2
    receitas = (
        await client.get("/financeiro/categorias", params={"tipo": "receita"}, headers=h)
    ).json()
    assert {c["nome"] for c in receitas} == {"Eventos", "Fornecedores"}


async def test_lancamento_exige_categoria_compativel_e_ativa(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    despesa = await _categoria(client, h, "Fornecedores", "despesa")
    receita = await _categoria(client, h, "Eventos", "receita")
    base = {"descricao": "x", "valor": "10.00", "vencimento": "2999-01-01"}

    r = await client.post(
        "/financeiro/lancamentos",
        json={**base, "tipo": "pagar", "categoria_id": receita},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["code"] == "categoria_incompativel"
    r = await client.post(
        "/financeiro/lancamentos",
        json={**base, "tipo": "receber", "categoria_id": despesa},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["code"] == "categoria_incompativel"
    r = await client.post(
        "/financeiro/lancamentos", json={**base, "tipo": "pagar", "categoria_id": 999}, headers=h
    )
    assert r.status_code == 404 and r.json()["code"] == "categoria_financeira_nao_encontrada"
    await client.patch(f"/financeiro/categorias/{despesa}", json={"ativo": False}, headers=h)
    r = await client.post(
        "/financeiro/lancamentos",
        json={**base, "tipo": "pagar", "categoria_id": despesa},
        headers=h,
    )
    assert r.status_code == 409 and r.json()["code"] == "categoria_financeira_inativa"


@pytest.mark.parametrize(
    "campos",
    [
        {"valor": "0"},
        {"valor": "-5.00"},
        {"valor": "1.005"},
        {"descricao": ""},
        {"descricao": "x" * 161},
        {"vencimento": "31/12/2999"},
        {"contraparte": "x" * 121},
        {"tipo": "outro"},
    ],
)
async def test_lancamento_invalido_da_422(
    client: AsyncClient, auth_headers: AuthHeaders, campos: dict[str, object]
) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    categoria = await _categoria(client, h, "Fornecedores", "despesa")
    corpo = {
        "tipo": "pagar",
        "descricao": "Polpa",
        "valor": "10.00",
        "vencimento": "2999-01-01",
        "categoria_id": categoria,
        **campos,
    }
    r = await client.post("/financeiro/lancamentos", json=corpo, headers=h)
    assert r.status_code == 422


async def test_criar_ja_pago_baixar_e_cancelar(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    despesa = await _categoria(client, h, "Fornecedores", "despesa")

    pago = await _lancamento(
        client,
        h,
        categoria_id=despesa,
        baixa={"data_pagamento": "2026-11-20", "forma": "dinheiro"},
    )
    assert pago["status"] == "pago" and pago["data_pagamento"] == "2026-11-20"
    assert pago["forma_pagamento"] == "dinheiro" and pago["atrasado"] is False

    pendente = await _lancamento(client, h, categoria_id=despesa, contraparte="Fornecedor X")
    assert pendente["status"] == "pendente" and pendente["baixado_por_id"] is None
    lid = pendente["id"]
    r = await client.post(
        f"/financeiro/lancamentos/{lid}/baixar",
        json={"data_pagamento": "2026-11-27", "forma": "pix"},
        headers=h,
    )
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["forma_pagamento"]) == ("pago", "pix")
    assert r.json()["baixado_por_id"] is not None
    for chamada in (
        client.post(
            f"/financeiro/lancamentos/{lid}/baixar",
            json={"data_pagamento": "2026-11-27", "forma": "pix"},
            headers=h,
        ),
        client.post(f"/financeiro/lancamentos/{lid}/cancelar", headers=h),
        client.patch(f"/financeiro/lancamentos/{lid}", json={"descricao": "outra"}, headers=h),
    ):
        r = await chamada
        assert r.status_code == 409 and r.json()["code"] == "lancamento_nao_pendente"

    outro = await _lancamento(client, h, categoria_id=despesa)
    r = await client.post(
        f"/financeiro/lancamentos/{outro['id']}/cancelar", json={"motivo": "duplicado"}, headers=h
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelado"
    r = await client.post(
        f"/financeiro/lancamentos/{outro['id']}/baixar",
        json={"data_pagamento": "2026-11-27", "forma": "pix"},
        headers=h,
    )
    assert r.status_code == 409 and r.json()["code"] == "lancamento_nao_pendente"
    r = await client.post("/financeiro/lancamentos/999/cancelar", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "lancamento_nao_encontrado"
    r = await client.post(
        f"/financeiro/lancamentos/{pendente['id']}/baixar",
        json={"data_pagamento": "2026-11-27", "forma": "boleto"},
        headers=h,
    )
    assert r.status_code == 422


async def test_editar_lancamento_pendente(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    despesa = await _categoria(client, h, "Fornecedores", "despesa")
    receita = await _categoria(client, h, "Eventos", "receita")
    lancamento = await _lancamento(client, h, categoria_id=despesa, contraparte="Fornecedor X")
    url = f"/financeiro/lancamentos/{lancamento['id']}"

    r = await client.patch(
        url,
        json={"valor": "130.50", "vencimento": "2999-06-01", "contraparte": ""},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["valor"], r.json()["vencimento"], r.json()["contraparte"]) == (
        "130.50",
        "2999-06-01",
        None,
    )
    r = await client.patch(url, json={"categoria_id": receita}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "categoria_incompativel"
    assert (await client.patch(url, json={}, headers=h)).status_code == 422
    assert (await client.patch(url, json={"valor": "0"}, headers=h)).status_code == 422
    assert (
        await client.patch("/financeiro/lancamentos/999", json={"valor": "1.00"}, headers=h)
    ).status_code == 404


async def test_atrasado_e_derivado_e_nao_gravado(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    despesa = await _categoria(client, h, "Fornecedores", "despesa")
    ontem = (date.today() - timedelta(days=2)).isoformat()
    vencido = await _lancamento(client, h, categoria_id=despesa, vencimento=ontem)
    futuro = await _lancamento(client, h, categoria_id=despesa)
    assert vencido["status"] == "pendente" and vencido["atrasado"] is True
    assert futuro["atrasado"] is False
    r = await client.get("/financeiro/lancamentos", params={"atrasados": True}, headers=h)
    assert [i["id"] for i in r.json()["itens"]] == [vencido["id"]]
    r = await client.post(
        f"/financeiro/lancamentos/{vencido['id']}/baixar",
        json={"data_pagamento": date.today().isoformat(), "forma": "pix"},
        headers=h,
    )
    assert r.json()["atrasado"] is False
    r = await client.get("/financeiro/lancamentos", params={"atrasados": True}, headers=h)
    assert r.json()["total"] == 0


async def test_listagem_com_filtros_ordem_e_paginacao(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("gerente@acai.com", Papel.GERENTE)
    despesa = await _categoria(client, h, "Fornecedores", "despesa")
    receita = await _categoria(client, h, "Eventos", "receita")
    tarde = await _lancamento(
        client, h, categoria_id=despesa, vencimento="2999-12-30", contraparte="Cemig"
    )
    cedo = await _lancamento(
        client, h, categoria_id=despesa, vencimento="2999-12-01", contraparte="Gás_Ltda"
    )
    evento = await _lancamento(
        client,
        h,
        tipo="receber",
        categoria_id=receita,
        vencimento="2999-12-15",
        contraparte="Buffet 100%",
    )
    pago = await _lancamento(
        client,
        h,
        categoria_id=despesa,
        vencimento="2999-11-01",
        baixa={"data_pagamento": "2026-11-01", "forma": "pix"},
    )

    async def ids(**params: object) -> list[object]:
        r = await client.get("/financeiro/lancamentos", params=params, headers=h)  # type: ignore[arg-type]
        assert r.status_code == 200, r.text
        return [i["id"] for i in r.json()["itens"]]

    assert await ids() == [cedo["id"], evento["id"], tarde["id"], pago["id"]]
    assert await ids(tipo="receber") == [evento["id"]]
    assert await ids(status="pago") == [pago["id"]]
    assert await ids(categoria_id=receita) == [evento["id"]]
    assert await ids(vencimento_de="2999-12-01", vencimento_ate="2999-12-15") == [
        cedo["id"],
        evento["id"],
    ]
    assert await ids(contraparte="gás_") == [cedo["id"]]
    assert await ids(contraparte="100%") == [evento["id"]]
    assert await ids(contraparte="%") == [evento["id"]]
    r = await client.get("/financeiro/lancamentos", params={"limit": 2, "offset": 1}, headers=h)
    assert r.json()["total"] == 4 and [i["id"] for i in r.json()["itens"]] == [
        evento["id"],
        tarde["id"],
    ]
    assert (
        await client.get("/financeiro/lancamentos", params={"limit": 0}, headers=h)
    ).status_code == 422
    detalhe = await client.get(f"/financeiro/lancamentos/{cedo['id']}", headers=h)
    assert detalhe.status_code == 200 and detalhe.json()["contraparte"] == "Gás_Ltda"
