"""API de comandas sobre SQLite: permissões, lançamento de itens, erros e formato das respostas."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.usuarios.entities import Papel
from tests.comandas_helpers import Semente, semear_cardapio
from tests.conftest import AuthHeaders


@pytest.fixture
async def sem(factory: async_sessionmaker[AsyncSession]) -> Semente:
    async with factory() as s:
        return await semear_cardapio(s)


async def _abrir(client: AsyncClient, headers: dict[str, str], nome: str = "Ana") -> int:
    r = await client.post("/comandas", json={"cliente_nome": nome}, headers=headers)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _item(sem: Semente, **extra: object) -> dict[str, object]:
    return {"produto_id": sem.produto_id, "tamanho_id": sem.tamanho_id, **extra}


# --- abrir ---


async def test_abrir_comanda(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    r = await client.post(
        "/comandas",
        json={"cliente_nome": "  Ana  ", "cliente_contato": "11999990000", "observacao": "mesa 2"},
        headers=h,
    )
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["cliente_nome"] == "Ana"
    assert corpo["origem"] == "balcao" and corpo["status"] == "aberta"
    assert corpo["cliente_contato"] == "11999990000" and corpo["observacao"] == "mesa 2"
    assert corpo["itens"] == [] and corpo["total"] == "0.00"
    assert corpo["aberta_por_id"] is not None and corpo["fechada_em"] is None


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"cliente_nome": ""},
        {"cliente_nome": "   "},
        {"cliente_nome": "x" * 121},
        {"cliente_nome": "Ana", "origem": "telegrama"},
        {"cliente_nome": "Ana", "observacao": "x" * 501},
        {"cliente_nome": "Ana", "status": "fechada"},  # campo desconhecido
    ],
)
async def test_abrir_com_dados_invalidos(
    client: AsyncClient, auth_headers: AuthHeaders, corpo: dict[str, object]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    assert (await client.post("/comandas", json=corpo, headers=h)).status_code == 422


async def test_sem_token_nao_acessa(client: AsyncClient) -> None:
    assert (await client.post("/comandas", json={"cliente_nome": "Ana"})).status_code == 401


@pytest.mark.parametrize("papel", list(Papel))
async def test_todos_os_papeis_abrem_e_lancam(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    cid = await _abrir(client, h)
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem), headers=h)
    assert r.status_code == 201


# --- itens ---


async def test_lancar_item_com_adicionais_devolve_totais(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = await _abrir(client, h)
    r = await client.post(
        f"/comandas/{cid}/itens",
        json=_item(
            sem,
            quantidade=2,
            observacao="sem granola",
            adicionais=[{"adicional_id": sem.adicional_id, "quantidade": 2}],
        ),
        headers=h,
    )
    assert r.status_code == 201, r.text
    comanda = r.json()
    item = comanda["itens"][0]
    assert item["nome_produto"] == "Tradicional" and item["nome_tamanho"] == "500 ml"
    assert item["preco_unitario"] == "18.90" and item["quantidade"] == 2
    assert item["observacao"] == "sem granola"
    assert item["adicionais"] == [
        {
            "adicional_id": sem.adicional_id,
            "nome": "Granola",
            "quantidade": 2,
            "preco_unitario": "2.50",
        }
    ]
    assert item["subtotal"] == "47.80"  # (18,90 + 2,50*2) * 2
    assert comanda["total"] == "47.80" and comanda["status"] == "aberta"

    # linhas separadas, sem mesclar o mesmo produto/tamanho
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem), headers=h)
    assert len(r.json()["itens"]) == 2 and r.json()["total"] == "66.70"


@pytest.mark.parametrize(
    ("alteracao", "codigo"),
    [
        ({"produto_id": 999}, 404),
        ({"tamanho_id": 999}, 404),
        ({"adicionais": [{"adicional_id": 999}]}, 404),
        ({"quantidade": 0}, 422),
        ({"quantidade": 100}, 422),
        ({"quantidade": 1.5}, 422),
        ({"quantidade": True}, 422),
        ({"adicionais": [{"adicional_id": 1, "quantidade": 0}]}, 422),
        ({"observacao": "x" * 501}, 422),
        ({"preco_unitario": "0.01"}, 422),  # preço vem sempre do cardápio
    ],
)
async def test_lancar_item_invalido(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    sem: Semente,
    alteracao: dict[str, object],
    codigo: int,
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = await _abrir(client, h)
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem) | alteracao, headers=h)
    assert r.status_code == codigo, r.text


async def test_codigos_de_erro_de_404(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = await _abrir(client, h)
    r = await client.post("/comandas/999/itens", json=_item(sem), headers=h)
    assert r.status_code == 404 and r.json()["code"] == "comanda_nao_encontrada"
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem, produto_id=999), headers=h)
    assert r.json()["code"] == "produto_nao_encontrado"
    r = await client.patch(f"/comandas/{cid}/itens/999", json={"quantidade": 1}, headers=h)
    assert r.status_code == 404 and r.json()["code"] == "item_comanda_nao_encontrado"
    r = await client.delete(f"/comandas/{cid}/itens/999", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "item_comanda_nao_encontrado"


async def test_produto_sem_preco_no_tamanho_e_adicional_repetido(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    sem: Semente,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.bootstrap.container import build_uow
    from app.domain.cardapio.entities import Tamanho

    async with factory() as s:
        outro = await build_uow(s).cardapio.adicionar_tamanho(Tamanho("1 L"))
        await s.commit()
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = await _abrir(client, h)

    r = await client.post(
        f"/comandas/{cid}/itens", json=_item(sem, tamanho_id=outro.id_persistido), headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "produto_sem_preco"
    dupla = [{"adicional_id": sem.adicional_id}, {"adicional_id": sem.adicional_id}]
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem, adicionais=dupla), headers=h)
    assert r.status_code == 422 and r.json()["code"] == "adicional_repetido"


async def test_produto_e_adicional_inativos(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    sem: Semente,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    cid = await _abrir(client, gerente)
    adicionais = [{"adicional_id": sem.adicional_id}]
    assert (
        await client.post(f"/adicionais/{sem.adicional_id}/desativar", headers=gerente)
    ).status_code == 200
    r = await client.post(
        f"/comandas/{cid}/itens", json=_item(sem, adicionais=adicionais), headers=gerente
    )
    assert r.status_code == 422 and r.json()["code"] == "adicional_inativo"
    assert (
        await client.post(f"/produtos/{sem.produto_id}/desativar", headers=gerente)
    ).status_code == 200
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem), headers=gerente)
    assert r.status_code == 422 and r.json()["code"] == "produto_inativo"


async def test_atualizar_e_remover_item(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = await _abrir(client, h)
    r = await client.post(f"/comandas/{cid}/itens", json=_item(sem, observacao="gelado"), headers=h)
    item_id = r.json()["itens"][0]["id"]

    r = await client.patch(f"/comandas/{cid}/itens/{item_id}", json={"quantidade": 3}, headers=h)
    assert r.status_code == 200
    assert r.json()["itens"][0]["quantidade"] == 3 and r.json()["total"] == "56.70"
    assert r.json()["itens"][0]["observacao"] == "gelado"
    r = await client.patch(f"/comandas/{cid}/itens/{item_id}", json={"observacao": ""}, headers=h)
    assert r.json()["itens"][0]["observacao"] is None
    assert (
        await client.patch(f"/comandas/{cid}/itens/{item_id}", json={}, headers=h)
    ).status_code == 422
    assert (
        await client.patch(f"/comandas/{cid}/itens/{item_id}", json={"quantidade": 0}, headers=h)
    ).status_code == 422

    r = await client.delete(f"/comandas/{cid}/itens/{item_id}", headers=h)
    assert r.status_code == 204 and r.content == b""
    assert (await client.delete(f"/comandas/{cid}/itens/{item_id}", headers=h)).status_code == 404
