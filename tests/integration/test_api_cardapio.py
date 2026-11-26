from httpx import AsyncClient

from app.domain.usuarios.entities import Papel
from tests.conftest import AuthHeaders


async def _gestor(auth_headers: AuthHeaders) -> dict[str, str]:
    return await auth_headers("gerente@acai.com", Papel.GERENTE)


# --- autenticação e papéis ---


async def test_sem_token_da_401_com_formato_padrao(client: AsyncClient) -> None:
    for rota in ("/categorias", "/tamanhos", "/adicionais", "/produtos"):
        r = await client.get(rota)
        assert r.status_code == 401
        assert r.json()["code"] == "token_invalido"


async def test_atendente_e_caixa_leem_mas_nao_escrevem(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    gestor = await _gestor(auth_headers)
    cat = (await client.post("/categorias", json={"nome": "Açaí"}, headers=gestor)).json()

    for papel in (Papel.ATENDENTE, Papel.CAIXA):
        h = await auth_headers(f"{papel}@acai.com", papel)
        assert (await client.get("/categorias", headers=h)).status_code == 200
        assert (await client.get(f"/categorias/{cat['id']}", headers=h)).status_code == 200
        assert (await client.get("/produtos", headers=h)).status_code == 200
        for rota, corpo in (
            ("/categorias", {"nome": "X"}),
            ("/tamanhos", {"nome": "X"}),
            ("/adicionais", {"nome": "X", "preco": "1"}),
            ("/produtos", {"nome": "X", "categoria_id": cat["id"]}),
        ):
            r = await client.post(rota, json=corpo, headers=h)
            assert r.status_code == 403, rota
            assert r.json()["code"] == "permissao_negada"
        assert (
            await client.post(f"/categorias/{cat['id']}/desativar", headers=h)
        ).status_code == 403
        assert (
            await client.put("/produtos/1/tamanhos/1", json={"preco": "1"}, headers=h)
        ).status_code == 403


# --- categorias ---


async def test_crud_de_categoria(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    r = await client.post("/categorias", json={"nome": "  Açaí  "}, headers=h)
    assert r.status_code == 201
    assert r.json() == {"id": r.json()["id"], "nome": "Açaí", "ativo": True}  # nome aparado
    cid = r.json()["id"]

    assert (await client.get(f"/categorias/{cid}", headers=h)).json()["nome"] == "Açaí"
    r = await client.patch(f"/categorias/{cid}", json={"nome": "Açaís"}, headers=h)
    assert r.status_code == 200 and r.json()["nome"] == "Açaís"

    r = await client.post(f"/categorias/{cid}/desativar", headers=h)
    assert r.json()["ativo"] is False
    inativas = await client.get("/categorias", params={"ativo": False}, headers=h)
    assert [c["id"] for c in inativas.json()["itens"]] == [cid]
    ativas = await client.get("/categorias", params={"ativo": True}, headers=h)
    assert ativas.json()["total"] == 0
    assert (await client.post(f"/categorias/{cid}/ativar", headers=h)).json()["ativo"] is True


async def test_categoria_erros(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    await client.post("/categorias", json={"nome": "Açaí"}, headers=h)
    dup = await client.post("/categorias", json={"nome": "açaí"}, headers=h)
    assert dup.status_code == 409 and dup.json()["code"] == "nome_ja_cadastrado"

    nf = await client.get("/categorias/999", headers=h)
    assert nf.status_code == 404 and nf.json()["code"] == "categoria_nao_encontrada"
    assert (
        await client.patch("/categorias/999", json={"nome": "Zz"}, headers=h)
    ).status_code == 404

    # validação de entrada: campo extra e nome curto
    assert (
        await client.post("/categorias", json={"nome": "Ok", "ativo": False}, headers=h)
    ).status_code == 422
    assert (await client.post("/categorias", json={"nome": "A"}, headers=h)).status_code == 422


async def test_paginacao_segue_o_padrao_de_usuarios(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    for n in ("Aa", "Bb", "Cc"):
        await client.post("/categorias", json={"nome": n}, headers=h)
    r = await client.get("/categorias", params={"limit": 2, "offset": 1}, headers=h)
    body = r.json()
    assert set(body) == {"itens", "total", "limit", "offset"}
    assert (body["total"], body["limit"], body["offset"]) == (3, 2, 1)
    assert [c["nome"] for c in body["itens"]] == ["Bb", "Cc"]
    assert (await client.get("/categorias", params={"limit": 0}, headers=h)).status_code == 422


# --- tamanhos e adicionais ---


async def test_tamanhos(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    r = await client.post("/tamanhos", json={"nome": "500 ml"}, headers=h)
    assert r.status_code == 201
    tid = r.json()["id"]
    assert (await client.post("/tamanhos", json={"nome": "500 ML"}, headers=h)).status_code == 409
    r = await client.patch(f"/tamanhos/{tid}", json={"nome": "500ml"}, headers=h)
    assert r.json()["nome"] == "500ml"
    assert (await client.post(f"/tamanhos/{tid}/desativar", headers=h)).json()["ativo"] is False
    assert (await client.post("/tamanhos/999/ativar", headers=h)).status_code == 404
    assert (await client.get("/tamanhos", headers=h)).json()["total"] == 1


async def test_adicionais_com_preco_decimal(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    r = await client.post("/adicionais", json={"nome": "Granola", "preco": "2.50"}, headers=h)
    assert r.status_code == 201
    assert r.json()["preco"] == "2.50"  # Decimal serializado como string, sem float
    aid = r.json()["id"]

    r = await client.patch(f"/adicionais/{aid}", json={"preco": "3.10"}, headers=h)
    assert r.json()["preco"] == "3.10"
    assert (await client.patch(f"/adicionais/{aid}", json={}, headers=h)).status_code == 422
    assert (
        await client.post("/adicionais", json={"nome": "GRANOLA", "preco": "1"}, headers=h)
    ).status_code == 409
    for preco in ("-1", "1.999", "abc"):
        r = await client.post("/adicionais", json={"nome": "Outro", "preco": preco}, headers=h)
        assert r.status_code == 422, preco
    assert (await client.post(f"/adicionais/{aid}/desativar", headers=h)).json()["ativo"] is False


# --- produtos ---


async def test_produto_com_precos_por_tamanho(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    cid = (await client.post("/categorias", json={"nome": "Açaí"}, headers=h)).json()["id"]
    t300 = (await client.post("/tamanhos", json={"nome": "300 ml"}, headers=h)).json()["id"]
    t500 = (await client.post("/tamanhos", json={"nome": "500 ml"}, headers=h)).json()["id"]

    r = await client.post("/produtos", json={"nome": "Tradicional", "categoria_id": cid}, headers=h)
    assert r.status_code == 201 and r.json()["precos"] == []
    pid = r.json()["id"]

    await client.put(f"/produtos/{pid}/tamanhos/{t300}", json={"preco": "12.90"}, headers=h)
    r = await client.put(f"/produtos/{pid}/tamanhos/{t500}", json={"preco": "18"}, headers=h)
    assert r.status_code == 200
    assert r.json()["precos"] == [
        {"tamanho_id": t300, "preco": "12.90"},
        {"tamanho_id": t500, "preco": "18.00"},
    ]
    r = await client.put(f"/produtos/{pid}/tamanhos/{t300}", json={"preco": "13.50"}, headers=h)
    assert r.json()["precos"][0]["preco"] == "13.50" and len(r.json()["precos"]) == 2

    for preco in ("-0.01", "10.999"):
        r = await client.put(f"/produtos/{pid}/tamanhos/{t300}", json={"preco": preco}, headers=h)
        assert r.status_code == 422, preco
    r = await client.put(f"/produtos/{pid}/tamanhos/999", json={"preco": "1"}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "tamanho_nao_encontrado"
    r = await client.put(f"/produtos/999/tamanhos/{t300}", json={"preco": "1"}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "produto_nao_encontrado"

    detalhe = (await client.get(f"/produtos/{pid}", headers=h)).json()
    assert len(detalhe["precos"]) == 2


async def test_produto_conflitos_e_categoria_invalida(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    c1 = (await client.post("/categorias", json={"nome": "Açaí"}, headers=h)).json()["id"]
    c2 = (await client.post("/categorias", json={"nome": "Combos"}, headers=h)).json()["id"]
    await client.post("/produtos", json={"nome": "Tradicional", "categoria_id": c1}, headers=h)

    dup = await client.post(
        "/produtos", json={"nome": "tradicional", "categoria_id": c1}, headers=h
    )
    assert dup.status_code == 409 and dup.json()["code"] == "nome_ja_cadastrado"
    ok = await client.post("/produtos", json={"nome": "Tradicional", "categoria_id": c2}, headers=h)
    assert ok.status_code == 201  # mesmo nome em outra categoria

    r = await client.post("/produtos", json={"nome": "X1", "categoria_id": 999}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "categoria_nao_encontrada"
    r = await client.patch(f"/produtos/{ok.json()['id']}", json={"categoria_id": c1}, headers=h)
    assert r.status_code == 409
    assert (
        await client.patch(f"/produtos/{ok.json()['id']}", json={}, headers=h)
    ).status_code == 422


async def test_listagem_de_produtos_filtra_e_busca(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    c1 = (await client.post("/categorias", json={"nome": "Açaí"}, headers=h)).json()["id"]
    c2 = (await client.post("/categorias", json={"nome": "Sorvete"}, headers=h)).json()["id"]
    ids = {}
    for nome, cat in (("Tradicional", c1), ("Zero Açúcar", c1), ("Napolitano", c2)):
        r = await client.post("/produtos", json={"nome": nome, "categoria_id": cat}, headers=h)
        ids[nome] = r.json()["id"]
    await client.post(f"/produtos/{ids['Napolitano']}/desativar", headers=h)

    def nomes(r: object) -> list[str]:
        return [p["nome"] for p in r.json()["itens"]]  # type: ignore[attr-defined]

    assert nomes(await client.get("/produtos", params={"categoria_id": c1}, headers=h)) == [
        "Tradicional",
        "Zero Açúcar",
    ]
    assert nomes(await client.get("/produtos", params={"ativo": False}, headers=h)) == [
        "Napolitano"
    ]
    assert nomes(await client.get("/produtos", params={"q": "trad"}, headers=h)) == ["Tradicional"]
    # `%` digitado é literal, não curinga
    assert nomes(await client.get("/produtos", params={"q": "%"}, headers=h)) == []
    r = await client.get("/produtos", params={"limit": 1}, headers=h)
    assert r.json()["total"] == 3 and len(r.json()["itens"]) == 1


async def test_produto_inativo_continua_consultavel(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    """Soft delete: comandas antigas precisam continuar apontando para o produto."""
    h = await _gestor(auth_headers)
    cid = (await client.post("/categorias", json={"nome": "Açaí"}, headers=h)).json()["id"]
    pid = (
        await client.post("/produtos", json={"nome": "Tradicional", "categoria_id": cid}, headers=h)
    ).json()["id"]
    assert (await client.post(f"/produtos/{pid}/desativar", headers=h)).json()["ativo"] is False
    assert (await client.get(f"/produtos/{pid}", headers=h)).json()["ativo"] is False
    assert (await client.post(f"/produtos/{pid}/ativar", headers=h)).json()["ativo"] is True
