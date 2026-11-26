"""E2E de cardápio e estoque: PostgreSQL migrado pelo Alembic, de ponta a ponta.

admin cria categoria, produto, tamanho e preço -> cria insumo -> registra entrada -> monta a
ficha técnica -> baixa o saldo abaixo do mínimo e consulta o alerta.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.bootstrap.container import build_criar_usuario, build_uow
from app.domain.estoque.regras import calcular_consumo
from app.domain.usuarios.entities import Papel

pytestmark = pytest.mark.postgres

SENHA_ADMIN = "admin-senha-123"
SENHA_ATENDENTE = "atendente-senha-123"


async def _login(client: AsyncClient, email: str, senha: str) -> dict[str, str]:
    r = await client.post("/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_fluxo_completo_de_cardapio_e_estoque(
    pg_client: AsyncClient, pg_session: AsyncSession
) -> None:
    criar = build_criar_usuario(pg_session)
    await criar.executar(None, "Admin E2E", "admin-cardapio@acai.com", SENHA_ADMIN, Papel.ADMIN)
    await criar.executar(
        None, "Atendente E2E", "atendente-cardapio@acai.com", SENHA_ATENDENTE, Papel.ATENDENTE
    )
    admin = await _login(pg_client, "admin-cardapio@acai.com", SENHA_ADMIN)
    atendente = await _login(pg_client, "atendente-cardapio@acai.com", SENHA_ATENDENTE)

    # 1. cardápio: categoria, tamanho, produto e preço
    cat = (await pg_client.post("/categorias", json={"nome": "Açaí"}, headers=admin)).json()
    tam = (await pg_client.post("/tamanhos", json={"nome": "500 ml"}, headers=admin)).json()
    prod = await pg_client.post(
        "/produtos", json={"nome": "Tradicional", "categoria_id": cat["id"]}, headers=admin
    )
    assert prod.status_code == 201
    pid = prod.json()["id"]
    r = await pg_client.put(
        f"/produtos/{pid}/tamanhos/{tam['id']}", json={"preco": "18.90"}, headers=admin
    )
    assert r.json()["precos"] == [{"tamanho_id": tam["id"], "preco": "18.90"}]

    # o atendente enxerga o cardápio, mas não altera
    visto = await pg_client.get("/produtos", params={"q": "trad"}, headers=atendente)
    assert visto.json()["total"] == 1
    assert visto.json()["itens"][0]["precos"][0]["preco"] == "18.90"
    negado = await pg_client.put(
        f"/produtos/{pid}/tamanhos/{tam['id']}", json={"preco": "1"}, headers=atendente
    )
    assert negado.status_code == 403
    assert (await pg_client.get("/estoque/alertas", headers=atendente)).status_code == 403

    # 2. insumo com mínimo de 1 kg e entrada de 5 kg
    r = await pg_client.post(
        "/estoque/insumos",
        json={"nome": "Polpa de açaí", "unidade": "kg", "estoque_minimo": "1"},
        headers=admin,
    )
    assert r.status_code == 201
    polpa = r.json()["id"]
    mov = f"/estoque/insumos/{polpa}/movimentacoes"
    entrada = await pg_client.post(
        mov, json={"tipo": "entrada", "quantidade": "5", "motivo": "compra"}, headers=admin
    )
    assert entrada.status_code == 201 and entrada.json()["saldo_apos"] == "5.000"
    # com saldo 5 > mínimo 1 ainda não há alerta
    assert (await pg_client.get("/estoque/alertas", headers=admin)).json()["total"] == 0

    # 3. ficha técnica: 300 g (0,3 kg) de polpa por açaí de 500 ml
    ficha_url = f"/produtos/{pid}/tamanhos/{tam['id']}/ficha-tecnica"
    r = await pg_client.put(
        ficha_url, json={"itens": [{"insumo_id": polpa, "quantidade": "0.300"}]}, headers=admin
    )
    assert r.status_code == 200
    ficha = await build_uow(pg_session).ficha_tecnica.obter_ficha_produto(pid, tam["id"])
    assert calcular_consumo(ficha, 10) == {polpa: ficha[0].quantidade * 10}  # 3 kg para 10 açaís

    # 4. saída que passa do saldo é barrada; saída válida leva o saldo ao mínimo -> alerta
    barrada = await pg_client.post(
        mov, json={"tipo": "saida", "quantidade": "5.001"}, headers=admin
    )
    assert barrada.status_code == 422 and barrada.json()["code"] == "estoque_insuficiente"
    saida = await pg_client.post(mov, json={"tipo": "saida", "quantidade": "4"}, headers=admin)
    assert saida.json()["saldo_apos"] == "1.000"

    alertas = await pg_client.get("/estoque/alertas", headers=admin)
    assert [i["id"] for i in alertas.json()["itens"]] == [polpa]
    assert alertas.json()["itens"][0]["abaixo_do_minimo"] is True

    # 5. histórico completo, mais recente primeiro
    hist = await pg_client.get(mov, headers=admin)
    assert [(m["tipo"], m["saldo_apos"]) for m in hist.json()["itens"]] == [
        ("saida", "1.000"),
        ("entrada", "5.000"),
    ]
