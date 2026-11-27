import pytest
from httpx import AsyncClient

from app.domain.usuarios.entities import Papel
from tests.conftest import AuthHeaders


async def _abrir(
    client: AsyncClient, h: dict[str, str], valor: str = "100.00"
) -> dict[str, object]:
    r = await client.post("/caixa/sessoes", json={"valor_abertura": valor}, headers=h)
    assert r.status_code == 201, r.text
    corpo: dict[str, object] = r.json()
    return corpo


async def test_atendente_nao_acessa_o_caixa(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    atendente = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    chamadas = [
        client.post("/caixa/sessoes", json={"valor_abertura": "10.00"}, headers=atendente),
        client.get("/caixa/sessoes", headers=atendente),
        client.get("/caixa/sessoes/atual", headers=atendente),
        client.get("/caixa/sessoes/1", headers=atendente),
        client.post(
            "/caixa/sessoes/1/movimentos",
            json={"tipo": "sangria", "valor": "1.00", "motivo": "x"},
            headers=atendente,
        ),
        client.post("/caixa/sessoes/1/fechar", json={"valor_contado": "0.00"}, headers=atendente),
    ]
    for chamada in chamadas:
        r = await chamada
        assert r.status_code == 403 and r.json()["code"] == "permissao_negada"


@pytest.mark.parametrize("papel", [Papel.ADMIN, Papel.GERENTE, Papel.CAIXA])
async def test_admin_gerente_e_caixa_operam_o_caixa(
    client: AsyncClient, auth_headers: AuthHeaders, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    sessao = await _abrir(client, h)
    assert sessao["status"] == "aberta" and sessao["valor_abertura"] == "100.00"
    assert sessao["saldo_dinheiro"] == "100.00" and sessao["movimentos"] == []
    assert sessao["resumo_por_forma"] == {
        "dinheiro": "0.00",
        "pix": "0.00",
        "cartao_debito": "0.00",
        "cartao_credito": "0.00",
    }
    assert (await client.get("/caixa/sessoes/atual", headers=h)).status_code == 200


async def test_sem_sessao_aberta_atual_da_404(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    r = await client.get("/caixa/sessoes/atual", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "nenhuma_sessao_aberta"
    r = await client.get("/caixa/sessoes/999", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "sessao_caixa_nao_encontrada"


async def test_abrir_duas_vezes_da_409(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    await _abrir(client, h)
    r = await client.post("/caixa/sessoes", json={"valor_abertura": "5.00"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "caixa_ja_aberto"


@pytest.mark.parametrize("corpo", [{}, {"valor_abertura": "-1.00"}, {"valor_abertura": "1.005"}])
async def test_abertura_com_valor_invalido_da_422(
    client: AsyncClient, auth_headers: AuthHeaders, corpo: dict[str, str]
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    r = await client.post("/caixa/sessoes", json=corpo, headers=h)
    assert r.status_code == 422


async def test_movimentos_alteram_o_saldo_e_a_sangria_respeita_o_saldo(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    sid = (await _abrir(client, h, "50.00"))["id"]
    url = f"/caixa/sessoes/{sid}/movimentos"

    r = await client.post(
        url, json={"tipo": "suprimento", "valor": "25.50", "motivo": "troco"}, headers=h
    )
    assert r.status_code == 201 and r.json()["tipo"] == "suprimento"
    r = await client.post(
        url, json={"tipo": "sangria", "valor": "75.51", "motivo": "banco"}, headers=h
    )
    assert r.status_code == 409 and r.json()["code"] == "saldo_caixa_insuficiente"
    r = await client.post(
        url, json={"tipo": "sangria", "valor": "75.50", "motivo": "banco"}, headers=h
    )
    assert r.status_code == 201

    atual = (await client.get("/caixa/sessoes/atual", headers=h)).json()
    assert atual["saldo_dinheiro"] == "0.00"
    assert atual["total_suprimentos"] == "25.50" and atual["total_sangrias"] == "75.50"
    assert [m["tipo"] for m in atual["movimentos"]] == ["suprimento", "sangria"]


@pytest.mark.parametrize(
    "corpo",
    [
        {"tipo": "sangria", "valor": "0", "motivo": "x"},
        {"tipo": "sangria", "valor": "-1.00", "motivo": "x"},
        {"tipo": "sangria", "valor": "1.00", "motivo": ""},
        {"tipo": "sangria", "valor": "1.00"},
        {"tipo": "troca", "valor": "1.00", "motivo": "x"},
    ],
)
async def test_movimento_invalido_da_422(
    client: AsyncClient, auth_headers: AuthHeaders, corpo: dict[str, str]
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    sid = (await _abrir(client, h))["id"]
    r = await client.post(f"/caixa/sessoes/{sid}/movimentos", json=corpo, headers=h)
    assert r.status_code == 422


async def test_fechar_caixa_congela_snapshot_e_bloqueia_novas_operacoes(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    sid = (await _abrir(client, h, "100.00"))["id"]

    r = await client.post(
        f"/caixa/sessoes/{sid}/fechar", json={"valor_contado": "98.00"}, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "justificativa_obrigatoria"
    assert (await client.get("/caixa/sessoes/atual", headers=h)).status_code == 200

    r = await client.post(
        f"/caixa/sessoes/{sid}/fechar",
        json={"valor_contado": "98.00", "observacao": "troco errado"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "fechada" and corpo["fechada_em"] is not None
    assert (corpo["valor_esperado"], corpo["valor_contado"], corpo["diferenca"]) == (
        "100.00",
        "98.00",
        "-2.00",
    )
    assert corpo["observacao"] == "troco errado"

    r = await client.post(
        f"/caixa/sessoes/{sid}/fechar", json={"valor_contado": "98.00"}, headers=h
    )
    assert r.status_code == 409 and r.json()["code"] == "sessao_nao_aberta"
    r = await client.post(
        f"/caixa/sessoes/{sid}/movimentos",
        json={"tipo": "suprimento", "valor": "1.00", "motivo": "x"},
        headers=h,
    )
    assert r.status_code == 409 and r.json()["code"] == "sessao_nao_aberta"
    assert (await client.get("/caixa/sessoes/atual", headers=h)).status_code == 404
    await _abrir(client, h, "0.00")


async def test_listar_sessoes_com_filtros_e_paginacao(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    primeira = (await _abrir(client, h))["id"]
    await client.post(
        f"/caixa/sessoes/{primeira}/fechar", json={"valor_contado": "100.00"}, headers=h
    )
    segunda = (await _abrir(client, h))["id"]

    r = await client.get("/caixa/sessoes", headers=h)
    corpo = r.json()
    assert corpo["total"] == 2 and corpo["limit"] == 20 and corpo["offset"] == 0
    assert [s["id"] for s in corpo["itens"]] == [segunda, primeira]
    r = await client.get("/caixa/sessoes", params={"status": "fechada"}, headers=h)
    assert [s["id"] for s in r.json()["itens"]] == [primeira]
    r = await client.get("/caixa/sessoes", params={"limit": 1, "offset": 1}, headers=h)
    assert r.json()["total"] == 2 and [s["id"] for s in r.json()["itens"]] == [primeira]
    r = await client.get("/caixa/sessoes", params={"de": "2999-01-01T00:00:00"}, headers=h)
    assert r.json()["total"] == 0
    r = await client.get("/caixa/sessoes", params={"limit": 101}, headers=h)
    assert r.status_code == 422
    detalhe = await client.get(f"/caixa/sessoes/{primeira}", headers=h)
    assert detalhe.status_code == 200 and detalhe.json()["valor_esperado"] == "100.00"
