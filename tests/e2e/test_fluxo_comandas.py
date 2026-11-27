"""E2E de comandas: PostgreSQL migrado pelo Alembic, de ponta a ponta.

admin monta cardápio, insumos e ficha técnica -> entrada de estoque -> atendente abre comanda e
lança itens -> caixa fecha (baixa o estoque) -> confere saldo, movimentações, total e auditoria
-> fechar de novo dá 409 -> outra comanda cancelada não mexe no estoque.
"""

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


async def test_fluxo_completo_de_comandas(pg_client: AsyncClient, pg_session: AsyncSession) -> None:
    criar = build_criar_usuario(pg_session)
    for nome, papel in (
        ("Admin", Papel.ADMIN),
        ("Atendente", Papel.ATENDENTE),
        ("Caixa", Papel.CAIXA),
    ):
        await criar.executar(None, nome, f"{papel}-comandas@acai.com", SENHA, papel)
    admin = await _login(pg_client, "admin-comandas@acai.com")
    atendente = await _login(pg_client, "atendente-comandas@acai.com")
    caixa = await _login(pg_client, "caixa-comandas@acai.com")

    # 1. cardápio, insumos e ficha técnica (admin)
    cat = _id(await pg_client.post("/categorias", json={"nome": "Açaí"}, headers=admin))
    tam = _id(await pg_client.post("/tamanhos", json={"nome": "500 ml"}, headers=admin))
    prod = _id(
        await pg_client.post(
            "/produtos", json={"nome": "Tradicional", "categoria_id": cat}, headers=admin
        )
    )
    await pg_client.put(f"/produtos/{prod}/tamanhos/{tam}", json={"preco": "18.90"}, headers=admin)
    granola_add = _id(
        await pg_client.post(
            "/adicionais", json={"nome": "Granola", "preco": "2.50"}, headers=admin
        )
    )
    polpa = _id(
        await pg_client.post(
            "/estoque/insumos",
            json={"nome": "Polpa de açaí", "unidade": "kg", "estoque_minimo": "1"},
            headers=admin,
        )
    )
    granola = _id(
        await pg_client.post(
            "/estoque/insumos",
            json={"nome": "Granola", "unidade": "kg", "estoque_minimo": "0"},
            headers=admin,
        )
    )
    for insumo, qtd in ((polpa, "5"), (granola, "1")):
        r = await pg_client.post(
            f"/estoque/insumos/{insumo}/movimentacoes",
            json={"tipo": "entrada", "quantidade": qtd, "motivo": "compra"},
            headers=admin,
        )
        assert r.status_code == 201
    r = await pg_client.put(
        f"/produtos/{prod}/tamanhos/{tam}/ficha-tecnica",
        json={"itens": [{"insumo_id": polpa, "quantidade": "0.300"}]},
        headers=admin,
    )
    assert r.status_code == 200
    r = await pg_client.put(
        f"/adicionais/{granola_add}/ficha-tecnica",
        json={"itens": [{"insumo_id": granola, "quantidade": "0.020"}]},
        headers=admin,
    )
    assert r.status_code == 200

    # 2. atendente abre a comanda e lança dois itens (linhas separadas)
    r = await pg_client.post(
        "/comandas",
        json={"cliente_nome": "Ana", "origem": "balcao", "observacao": "mesa 4"},
        headers=atendente,
    )
    assert r.status_code == 201
    cid = r.json()["id"]
    r = await pg_client.post(
        f"/comandas/{cid}/itens",
        json={
            "produto_id": prod,
            "tamanho_id": tam,
            "quantidade": 2,
            "adicionais": [{"adicional_id": granola_add, "quantidade": 2}],
        },
        headers=atendente,
    )
    assert r.status_code == 201
    r = await pg_client.post(
        f"/comandas/{cid}/itens",
        json={"produto_id": prod, "tamanho_id": tam, "observacao": "sem granola"},
        headers=atendente,
    )
    assert r.status_code == 201 and len(r.json()["itens"]) == 2
    assert r.json()["total"] == "66.70"  # (18,90 + 2*2,50) * 2 + 18,90

    # o cardápio muda depois do lançamento: a comanda não muda
    await pg_client.put(f"/produtos/{prod}/tamanhos/{tam}", json={"preco": "30.00"}, headers=admin)
    detalhe = (await pg_client.get(f"/comandas/{cid}", headers=atendente)).json()
    assert detalhe["total"] == "66.70" and detalhe["itens"][0]["preco_unitario"] == "18.90"

    # 3. atendente não fecha; caixa fecha
    negado = await pg_client.post(f"/comandas/{cid}/fechar", headers=atendente)
    assert negado.status_code == 403
    await abrir_caixa_api(pg_client, caixa, "50.00")
    fechada = await fechar_comanda_api(pg_client, caixa, cid)
    assert fechada.status_code == 200, fechada.text
    corpo = fechada.json()
    assert corpo["status"] == "fechada" and corpo["total"] == "66.70"
    assert corpo["fechada_em"] is not None and corpo["itens_sem_ficha"] == []
    # polpa: 0,3 * 3 = 0,9 | granola: 0,02 * (2 * 2) = 0,08
    assert corpo["consumo"] == [
        {"insumo_id": polpa, "quantidade": "0.900"},
        {"insumo_id": granola, "quantidade": "0.080"},
    ]

    # 4. saldo, movimentações (uma saída por insumo, com o motivo) e auditoria
    assert (await pg_client.get(f"/estoque/insumos/{polpa}", headers=admin)).json()[
        "estoque_atual"
    ] == "4.100"
    assert (await pg_client.get(f"/estoque/insumos/{granola}", headers=admin)).json()[
        "estoque_atual"
    ] == "0.920"
    movs = (await pg_client.get(f"/estoque/insumos/{polpa}/movimentacoes", headers=admin)).json()
    assert [(m["tipo"], m["quantidade"], m["motivo"]) for m in movs["itens"]] == [
        ("saida", "0.900", f"comanda:{cid}"),
        ("entrada", "5.000", "compra"),
    ]
    log = (
        await pg_session.scalars(
            select(AuditLogModel).where(
                AuditLogModel.acao == "fechar", AuditLogModel.entidade_id == str(cid)
            )
        )
    ).one()
    assert log.detalhes is not None and log.detalhes["total"] == "66.70"
    assert log.detalhes["consumo"] == {str(polpa): "0.900", str(granola): "0.080"}

    # 5. fechar de novo: 409, sem nova baixa; e a comanda fechada não aceita itens
    de_novo = await fechar_comanda_api(pg_client, caixa, cid)
    assert de_novo.status_code == 409 and de_novo.json()["code"] == "comanda_nao_aberta"
    saldo = await pg_client.get(f"/estoque/insumos/{polpa}", headers=admin)
    assert saldo.json()["estoque_atual"] == "4.100"
    r = await pg_client.post(
        f"/comandas/{cid}/itens", json={"produto_id": prod, "tamanho_id": tam}, headers=atendente
    )
    assert r.status_code == 409

    # 6. falta de estoque: 409 com o insumo, nada baixado, comanda segue aberta
    grande = (
        await pg_client.post("/comandas", json={"cliente_nome": "Bia"}, headers=atendente)
    ).json()["id"]
    await pg_client.post(
        f"/comandas/{grande}/itens",
        json={"produto_id": prod, "tamanho_id": tam, "quantidade": 50},  # 15 kg de polpa
        headers=atendente,
    )
    r = await fechar_comanda_api(pg_client, caixa, grande)
    assert r.status_code == 409 and r.json()["code"] == "estoque_insuficiente"
    assert r.json()["insumo_id"] == polpa and r.json()["insumo_nome"] == "Polpa de açaí"
    assert (await pg_client.get(f"/comandas/{grande}", headers=caixa)).json()["status"] == "aberta"
    saldo = await pg_client.get(f"/estoque/insumos/{polpa}", headers=admin)
    assert saldo.json()["estoque_atual"] == "4.100"

    # 7. cancelar não mexe no estoque e é terminal
    r = await pg_client.post(
        f"/comandas/{grande}/cancelar", json={"motivo": "cliente desistiu"}, headers=caixa
    )
    assert r.status_code == 200 and r.json()["status"] == "cancelada"
    saldo = await pg_client.get(f"/estoque/insumos/{polpa}", headers=admin)
    assert saldo.json()["estoque_atual"] == "4.100"
    movs = (await pg_client.get(f"/estoque/insumos/{polpa}/movimentacoes", headers=admin)).json()
    assert movs["total"] == 2  # só a entrada e a saída do fechamento
    assert (await fechar_comanda_api(pg_client, caixa, grande)).status_code == 409

    # 8. listagem: fechadas e canceladas, da mais recente para a mais antiga
    r = await pg_client.get("/comandas", params={"cliente": "a"}, headers=atendente)
    assert [c["cliente_nome"] for c in r.json()["itens"]] == ["Bia", "Ana"]
    r = await pg_client.get("/comandas", params={"status": "fechada"}, headers=atendente)
    assert [(c["cliente_nome"], c["total"]) for c in r.json()["itens"]] == [("Ana", "66.70")]
