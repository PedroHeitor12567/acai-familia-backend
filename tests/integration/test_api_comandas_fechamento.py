"""API de fechar/cancelar comandas sobre SQLite: permissões, códigos de erro e respostas."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.usuarios.entities import Papel
from tests.comandas_helpers import (
    Semente,
    abrir_caixa,
    fechar_comanda_api,
    semear_cardapio,
)
from tests.conftest import AuthHeaders


@pytest.fixture
async def sem(factory: async_sessionmaker[AsyncSession]) -> Semente:
    async with factory() as s:
        semente = await semear_cardapio(s, estoque_granola="0.05")
        await abrir_caixa(s)
        return semente


async def _comanda_com_item(
    client: AsyncClient, h: dict[str, str], sem: Semente, quantidade: int = 1, adicionais: int = 0
) -> int:
    r = await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h)
    cid = int(r.json()["id"])
    corpo: dict[str, object] = {
        "produto_id": sem.produto_id,
        "tamanho_id": sem.tamanho_id,
        "quantidade": quantidade,
    }
    if adicionais:
        corpo["adicionais"] = [{"adicional_id": sem.adicional_id, "quantidade": adicionais}]
    assert (await client.post(f"/comandas/{cid}/itens", json=corpo, headers=h)).status_code == 201
    return cid


async def _saldo(client: AsyncClient, h: dict[str, str], insumo_id: int) -> str:
    r = await client.get(f"/estoque/insumos/{insumo_id}", headers=h)
    return str(r.json()["estoque_atual"])


async def test_atendente_nao_fecha_nem_cancela(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    atendente = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = await _comanda_com_item(client, atendente, sem)
    for acao in ("fechar", "cancelar"):
        r = await client.post(f"/comandas/{cid}/{acao}", headers=atendente)
        assert r.status_code == 403 and r.json()["code"] == "permissao_negada"


@pytest.mark.parametrize("papel", [Papel.ADMIN, Papel.GERENTE, Papel.CAIXA])
async def test_admin_gerente_e_caixa_fecham(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente, papel: Papel
) -> None:
    h = await auth_headers(f"{papel}@acai.com", papel)
    cid = await _comanda_com_item(client, h, sem, quantidade=2)
    r = await fechar_comanda_api(client, h, cid)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "fechada" and corpo["total"] == "37.80"
    assert corpo["fechada_em"] is not None and corpo["fechada_por_id"] is not None
    assert corpo["consumo"] == [{"insumo_id": sem.polpa_id, "quantidade": "0.600"}]
    assert corpo["itens_sem_ficha"] == []
    leitor = await auth_headers("leitor@acai.com", Papel.ADMIN)  # caixa não lê estoque
    assert await _saldo(client, leitor, sem.polpa_id) == "9.400"


async def test_fechar_de_novo_da_409_e_nao_baixa_de_novo(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    cid = await _comanda_com_item(client, h, sem)
    assert (await fechar_comanda_api(client, h, cid)).status_code == 200
    r = await fechar_comanda_api(client, h, cid)
    assert r.status_code == 409 and r.json()["code"] == "comanda_nao_aberta"
    assert await _saldo(client, gerente, sem.polpa_id) == "9.700"
    # comanda fechada não aceita mais itens
    r = await client.post(
        f"/comandas/{cid}/itens",
        json={"produto_id": sem.produto_id, "tamanho_id": sem.tamanho_id},
        headers=h,
    )
    assert r.status_code == 409 and r.json()["code"] == "comanda_nao_aberta"


async def test_fechar_comanda_vazia_e_inexistente(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    cid = (await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h)).json()["id"]
    r = await fechar_comanda_api(client, h, cid)
    assert r.status_code == 409 and r.json()["code"] == "comanda_vazia"
    r = await fechar_comanda_api(client, h, 999)
    assert r.status_code == 404 and r.json()["code"] == "comanda_nao_encontrada"


async def test_falta_de_estoque_da_409_com_o_insumo_e_nao_baixa_nada(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    # granola: 0,02 * 3 = 0,06 > 0,05 em estoque; a polpa (id menor) é baixada antes e desfeita
    cid = await _comanda_com_item(client, h, sem, quantidade=1, adicionais=3)

    r = await fechar_comanda_api(client, h, cid)

    assert r.status_code == 409, r.text
    corpo = r.json()
    assert corpo["code"] == "estoque_insuficiente"
    assert corpo["insumo_id"] == sem.granola_id and corpo["insumo_nome"] == "Granola"
    assert corpo["disponivel"] == "0.050" and corpo["solicitado"] == "0.060"
    assert "Granola" in corpo["detail"]
    assert await _saldo(client, gerente, sem.polpa_id) == "10.000"
    assert await _saldo(client, gerente, sem.granola_id) == "0.050"
    movs = await client.get(f"/estoque/insumos/{sem.polpa_id}/movimentacoes", headers=gerente)
    assert [m["tipo"] for m in movs.json()["itens"]] == ["entrada"]
    # a comanda segue aberta e dá para corrigir e fechar
    r = await client.patch(f"/comandas/{cid}/itens/1", json={"quantidade": 2}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "aberta"


async def test_movimentacao_manual_continua_422_com_o_nome_do_insumo(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    r = await client.post(
        f"/estoque/insumos/{sem.granola_id}/movimentacoes",
        json={"tipo": "saida", "quantidade": "9"},
        headers=gerente,
    )
    assert r.status_code == 422 and r.json()["code"] == "estoque_insuficiente"
    assert "Granola" in r.json()["detail"]


async def test_cancelar_nao_mexe_no_estoque(
    client: AsyncClient, auth_headers: AuthHeaders, sem: Semente
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    gerente = await auth_headers("gerente@acai.com", Papel.GERENTE)
    cid = await _comanda_com_item(client, h, sem)

    r = await client.post(f"/comandas/{cid}/cancelar", json={"motivo": "desistiu"}, headers=h)

    assert r.status_code == 200 and r.json()["status"] == "cancelada"
    assert await _saldo(client, gerente, sem.polpa_id) == "10.000"
    again = await client.post(f"/comandas/{cid}/cancelar", headers=h)  # sem corpo é válido
    assert again.status_code == 409 and again.json()["code"] == "comanda_nao_aberta"
    assert (await fechar_comanda_api(client, h, cid)).status_code == 409
    r = await client.patch(f"/comandas/{cid}/itens/1", json={"quantidade": 2}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "comanda_nao_aberta"
    r = await client.delete(f"/comandas/{cid}/itens/1", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "comanda_nao_aberta"


async def test_cancelar_sem_corpo_e_com_motivo_invalido(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("caixa@acai.com", Papel.CAIXA)
    cid = (await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h)).json()["id"]
    r = await client.post(f"/comandas/{cid}/cancelar", json={"motivo": "x" * 256}, headers=h)
    assert r.status_code == 422
    assert (await client.post(f"/comandas/{cid}/cancelar", headers=h)).status_code == 200
