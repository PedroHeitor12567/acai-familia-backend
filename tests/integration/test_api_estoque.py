from httpx import AsyncClient

from app.domain.usuarios.entities import Papel
from tests.conftest import AuthHeaders


async def _gestor(auth_headers: AuthHeaders) -> dict[str, str]:
    return await auth_headers("gerente@acai.com", Papel.GERENTE)


async def _insumo(
    client: AsyncClient, h: dict[str, str], nome: str = "Polpa", minimo: str = "5"
) -> int:
    r = await client.post(
        "/estoque/insumos",
        json={"nome": nome, "unidade": "kg", "estoque_minimo": minimo},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def test_estoque_e_so_para_admin_e_gerente(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    gestor = await _gestor(auth_headers)
    iid = await _insumo(client, gestor)
    for papel in (Papel.ATENDENTE, Papel.CAIXA):
        h = await auth_headers(f"{papel}@acai.com", papel)
        chamadas = [
            client.get("/estoque/insumos", headers=h),
            client.get(f"/estoque/insumos/{iid}", headers=h),
            client.get("/estoque/alertas", headers=h),
            client.get(f"/estoque/insumos/{iid}/movimentacoes", headers=h),
            client.post(
                f"/estoque/insumos/{iid}/movimentacoes",
                json={"tipo": "entrada", "quantidade": "1"},
                headers=h,
            ),
            client.post("/estoque/insumos", json={"nome": "X1", "unidade": "g"}, headers=h),
            client.get("/produtos/1/tamanhos/1/ficha-tecnica", headers=h),
        ]
        for chamada in chamadas:
            r = await chamada
            assert r.status_code == 403
            assert r.json()["code"] == "permissao_negada"
    admin = await auth_headers("admin@acai.com", Papel.ADMIN)
    assert (await client.get("/estoque/insumos", headers=admin)).status_code == 200


async def test_crud_de_insumo(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    r = await client.post(
        "/estoque/insumos",
        json={"nome": "Polpa de açaí", "unidade": "kg", "estoque_minimo": "5.5"},
        headers=h,
    )
    assert r.status_code == 201
    corpo = r.json()
    assert (corpo["estoque_atual"], corpo["estoque_minimo"]) == ("0.000", "5.500")
    assert corpo["abaixo_do_minimo"] is True and corpo["unidade"] == "kg"
    iid = corpo["id"]

    dup = await client.post(
        "/estoque/insumos", json={"nome": "POLPA DE AÇAÍ", "unidade": "g"}, headers=h
    )
    assert dup.status_code == 409 and dup.json()["code"] == "nome_ja_cadastrado"

    r = await client.patch(f"/estoque/insumos/{iid}", json={"estoque_minimo": "2"}, headers=h)
    assert r.json()["estoque_minimo"] == "2.000"
    # a unidade e o saldo não são editáveis por PATCH
    for extra in ({"unidade": "g"}, {"estoque_atual": "100"}):
        assert (
            await client.patch(f"/estoque/insumos/{iid}", json=extra, headers=h)
        ).status_code == 422
    assert (await client.patch(f"/estoque/insumos/{iid}", json={}, headers=h)).status_code == 422

    r = await client.get("/estoque/insumos/999", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "insumo_nao_encontrado"
    bad = await client.post(
        "/estoque/insumos", json={"nome": "Leite", "unidade": "galão"}, headers=h
    )
    assert bad.status_code == 422
    neg = await client.post(
        "/estoque/insumos",
        json={"nome": "Leite", "unidade": "l", "estoque_minimo": "-1"},
        headers=h,
    )
    assert neg.status_code == 422

    assert (await client.post(f"/estoque/insumos/{iid}/desativar", headers=h)).json()[
        "ativo"
    ] is False
    inativos = await client.get("/estoque/insumos", params={"ativo": False}, headers=h)
    assert inativos.json()["total"] == 1
    assert (await client.post(f"/estoque/insumos/{iid}/ativar", headers=h)).json()["ativo"] is True


async def test_movimentacoes_e_historico(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    iid = await _insumo(client, h)
    url = f"/estoque/insumos/{iid}/movimentacoes"

    r = await client.post(
        url, json={"tipo": "entrada", "quantidade": "20", "motivo": "compra"}, headers=h
    )
    assert r.status_code == 201
    assert (r.json()["saldo_antes"], r.json()["saldo_apos"], r.json()["motivo"]) == (
        "0.000",
        "20.000",
        "compra",
    )
    r = await client.post(url, json={"tipo": "saida", "quantidade": "4.25"}, headers=h)
    assert r.json()["saldo_apos"] == "15.750"
    r = await client.post(url, json={"tipo": "ajuste", "quantidade": "15"}, headers=h)
    assert (r.json()["quantidade"], r.json()["saldo_apos"]) == ("0.750", "15.000")

    assert (await client.get(f"/estoque/insumos/{iid}", headers=h)).json()[
        "estoque_atual"
    ] == "15.000"

    hist = await client.get(url, headers=h)
    assert hist.json()["total"] == 3
    assert [m["tipo"] for m in hist.json()["itens"]] == ["ajuste", "saida", "entrada"]
    so_entradas = await client.get(url, params={"tipo": "entrada"}, headers=h)
    assert so_entradas.json()["total"] == 1
    futuro = await client.get(url, params={"de": "2999-01-01T00:00:00Z"}, headers=h)
    assert futuro.json()["total"] == 0
    passado = await client.get(url, params={"ate": "2000-01-01T00:00:00Z"}, headers=h)
    assert passado.json()["total"] == 0
    tudo = await client.get(
        url,
        params={"de": "2000-01-01T00:00:00Z", "ate": "2999-01-01T00:00:00Z", "limit": 2},
        headers=h,
    )
    assert tudo.json()["total"] == 3 and len(tudo.json()["itens"]) == 2


async def test_histórico_e_imutavel(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    iid = await _insumo(client, h)
    url = f"/estoque/insumos/{iid}/movimentacoes"
    mid = (await client.post(url, json={"tipo": "entrada", "quantidade": "1"}, headers=h)).json()[
        "id"
    ]
    for metodo in ("put", "patch", "delete"):
        r = await client.request(metodo, f"{url}/{mid}", headers=h)
        assert r.status_code in (404, 405), metodo


async def test_saldo_insuficiente_e_quantidades_invalidas(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    iid = await _insumo(client, h)
    url = f"/estoque/insumos/{iid}/movimentacoes"
    await client.post(url, json={"tipo": "entrada", "quantidade": "3"}, headers=h)

    r = await client.post(url, json={"tipo": "saida", "quantidade": "3.001"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "estoque_insuficiente"
    assert (await client.get(f"/estoque/insumos/{iid}", headers=h)).json()[
        "estoque_atual"
    ] == "3.000"
    assert (await client.get(url, headers=h)).json()["total"] == 1  # nada foi gravado

    for corpo in (
        {"tipo": "entrada", "quantidade": "0"},
        {"tipo": "saida", "quantidade": "0"},
        {"tipo": "entrada", "quantidade": "-1"},
        {"tipo": "entrada", "quantidade": "1.0001"},
        {"tipo": "ajuste", "quantidade": "-1"},
        {"tipo": "transferencia", "quantidade": "1"},
        {"tipo": "entrada", "quantidade": "1", "usuario_id": 7},
    ):
        assert (await client.post(url, json=corpo, headers=h)).status_code == 422, corpo
    sem_diferenca = await client.post(url, json={"tipo": "ajuste", "quantidade": "3"}, headers=h)
    assert sem_diferenca.status_code == 422 and sem_diferenca.json()["code"] == "valor_invalido"

    assert (
        await client.post(
            "/estoque/insumos/999/movimentacoes",
            json={"tipo": "entrada", "quantidade": "1"},
            headers=h,
        )
    ).status_code == 404
    assert (await client.get("/estoque/insumos/999/movimentacoes", headers=h)).status_code == 404

    await client.post(f"/estoque/insumos/{iid}/desativar", headers=h)
    r = await client.post(url, json={"tipo": "entrada", "quantidade": "1"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "operacao_nao_permitida"


async def test_alertas_listam_exatamente_saldo_menor_ou_igual_ao_minimo(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    esperados = set()
    for nome, minimo, saldo in (
        ("Abaixo", "5", "4"),
        ("Igual", "5", "5"),
        ("Acima", "5", "5.001"),
        ("Zerado", "1", None),
    ):
        iid = await _insumo(client, h, nome, minimo)
        if saldo:
            await client.post(
                f"/estoque/insumos/{iid}/movimentacoes",
                json={"tipo": "entrada", "quantidade": saldo},
                headers=h,
            )
        if nome != "Acima":
            esperados.add(nome)

    alertas = await client.get("/estoque/alertas", headers=h)
    assert alertas.status_code == 200
    assert {i["nome"] for i in alertas.json()["itens"]} == esperados
    assert all(i["abaixo_do_minimo"] for i in alertas.json()["itens"])
    assert alertas.json()["total"] == 3

    filtrado = await client.get("/estoque/insumos", params={"abaixo_do_minimo": False}, headers=h)
    assert [i["nome"] for i in filtrado.json()["itens"]] == ["Acima"]
    busca = await client.get("/estoque/insumos", params={"q": "zer"}, headers=h)
    assert [i["nome"] for i in busca.json()["itens"]] == ["Zerado"]


# --- ficha técnica ---


async def _produto_com_tamanho(client: AsyncClient, h: dict[str, str]) -> tuple[int, int]:
    cid = (await client.post("/categorias", json={"nome": "Açaí"}, headers=h)).json()["id"]
    pid = (
        await client.post("/produtos", json={"nome": "Tradicional", "categoria_id": cid}, headers=h)
    ).json()["id"]
    tid = (await client.post("/tamanhos", json={"nome": "500 ml"}, headers=h)).json()["id"]
    await client.put(f"/produtos/{pid}/tamanhos/{tid}", json={"preco": "18"}, headers=h)
    return pid, tid


async def test_ficha_tecnica_put_substitui_e_get_le(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await _gestor(auth_headers)
    pid, tid = await _produto_com_tamanho(client, h)
    polpa = await _insumo(client, h, "Polpa")
    granola = await _insumo(client, h, "Granola")
    url = f"/produtos/{pid}/tamanhos/{tid}/ficha-tecnica"

    assert (await client.get(url, headers=h)).json() == {"itens": []}
    r = await client.put(
        url,
        json={
            "itens": [
                {"insumo_id": granola, "quantidade": "20"},
                {"insumo_id": polpa, "quantidade": "0.300"},
            ]
        },
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["itens"] == [
        {"insumo_id": polpa, "quantidade": "0.300"},
        {"insumo_id": granola, "quantidade": "20.000"},
    ]
    r = await client.put(
        url, json={"itens": [{"insumo_id": polpa, "quantidade": "0.250"}]}, headers=h
    )
    assert [i["insumo_id"] for i in (await client.get(url, headers=h)).json()["itens"]] == [polpa]
    assert (await client.put(url, json={"itens": []}, headers=h)).json() == {"itens": []}


async def test_ficha_tecnica_erros(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    pid, tid = await _produto_com_tamanho(client, h)
    polpa = await _insumo(client, h, "Polpa")
    url = f"/produtos/{pid}/tamanhos/{tid}/ficha-tecnica"
    original = {"itens": [{"insumo_id": polpa, "quantidade": "1"}]}
    await client.put(url, json=original, headers=h)

    repetido = {
        "itens": [{"insumo_id": polpa, "quantidade": "1"}, {"insumo_id": polpa, "quantidade": "2"}]
    }
    r = await client.put(url, json=repetido, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "ficha_tecnica_invalida"
    inexistente = {"itens": [{"insumo_id": 999, "quantidade": "1"}]}
    assert (await client.put(url, json=inexistente, headers=h)).json()[
        "code"
    ] == "ficha_tecnica_invalida"
    for q in ("0", "-1"):
        r = await client.put(
            url, json={"itens": [{"insumo_id": polpa, "quantidade": q}]}, headers=h
        )
        assert r.status_code == 422, q

    assert (await client.get(url, headers=h)).json()["itens"][0]["quantidade"] == "1.000"  # intacta

    r = await client.get(f"/produtos/999/tamanhos/{tid}/ficha-tecnica", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "produto_nao_encontrado"
    r = await client.get(f"/produtos/{pid}/tamanhos/999/ficha-tecnica", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "tamanho_nao_encontrado"

    outro = (await client.post("/tamanhos", json={"nome": "700 ml"}, headers=h)).json()["id"]
    r = await client.put(
        f"/produtos/{pid}/tamanhos/{outro}/ficha-tecnica", json=original, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "ficha_tecnica_invalida"

    await client.post(f"/produtos/{pid}/desativar", headers=h)
    r = await client.put(url, json=original, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "ficha_tecnica_invalida"


async def test_ficha_tecnica_de_adicional(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await _gestor(auth_headers)
    aid = (
        await client.post("/adicionais", json={"nome": "Granola", "preco": "2"}, headers=h)
    ).json()["id"]
    granola = await _insumo(client, h, "Granola")
    url = f"/adicionais/{aid}/ficha-tecnica"
    r = await client.put(
        url, json={"itens": [{"insumo_id": granola, "quantidade": "30"}]}, headers=h
    )
    assert r.status_code == 200
    assert (await client.get(url, headers=h)).json()["itens"] == [
        {"insumo_id": granola, "quantidade": "30.000"}
    ]
    assert (await client.get("/adicionais/999/ficha-tecnica", headers=h)).status_code == 404
