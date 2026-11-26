"""Consulta de comandas: detalhe, filtros, ordenação e paginação (SQLite)."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.container import build_uow
from app.domain.comandas.entities import Comanda, OrigemComanda, StatusComanda
from app.domain.usuarios.entities import Papel
from tests.comandas_helpers import Semente, semear_cardapio, semear_usuario
from tests.conftest import AuthHeaders

BASE = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


async def _criar(
    factory: async_sessionmaker[AsyncSession],
    nome: str,
    minutos: int,
    status: StatusComanda = StatusComanda.ABERTA,
    origem: OrigemComanda = OrigemComanda.BALCAO,
    aberta_por_id: int | None = None,
) -> int:
    async with factory() as s:
        uow = build_uow(s)
        comanda = await uow.comandas.adicionar(
            Comanda(
                cliente_nome=nome,
                aberta_em=BASE + timedelta(minutes=minutos),
                origem=origem,
                aberta_por_id=aberta_por_id,
            )
        )
        if status is StatusComanda.CANCELADA:
            await uow.comandas.marcar_cancelada(comanda.id_persistido)
        elif status is StatusComanda.FECHADA:
            from decimal import Decimal

            await uow.comandas.marcar_fechada(
                comanda.id_persistido, aberta_por_id or 1, BASE, Decimal("0.00")
            )
        await s.commit()
        return comanda.id_persistido


@pytest.fixture
async def cenario(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with factory() as s:
        u1 = (await semear_usuario(s, Papel.ATENDENTE, "u1@acai.com")).id_persistido
        u2 = (await semear_usuario(s, Papel.CAIXA, "u2@acai.com")).id_persistido
    return {
        "u1": u1,
        "u2": u2,
        # abertas (mais antiga = menor minuto)
        "bruno": await _criar(factory, "Bruno", 20, aberta_por_id=u1),
        "ana": await _criar(factory, "Ana", 10, aberta_por_id=u1),
        "mariana": await _criar(factory, "Mariana", 30, aberta_por_id=u2),
        # terminais
        "carla": await _criar(factory, "Carla", 40, StatusComanda.FECHADA, aberta_por_id=u2),
        "davi": await _criar(
            factory, "Davi", 50, StatusComanda.CANCELADA, OrigemComanda.WHATSAPP, aberta_por_id=None
        ),
        "promo": await _criar(factory, "100%_off", 60, StatusComanda.FECHADA, aberta_por_id=u1),
    }


async def _listar(client: AsyncClient, h: dict[str, str], **params: object) -> dict[str, object]:
    r = await client.get("/comandas", params=params, headers=h)  # type: ignore[arg-type]
    assert r.status_code == 200, r.text
    corpo: dict[str, object] = r.json()
    return corpo


def _nomes(pagina: dict[str, object]) -> list[str]:
    itens = pagina["itens"]
    assert isinstance(itens, list)
    return [i["cliente_nome"] for i in itens]


async def test_ordem_padrao_abertas_mais_antigas_primeiro_depois_as_demais_recentes_primeiro(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    pagina = await _listar(client, h)
    assert _nomes(pagina) == ["Ana", "Bruno", "Mariana", "100%_off", "Davi", "Carla"]
    assert pagina["total"] == 6 and pagina["limit"] == 20 and pagina["offset"] == 0


async def test_filtro_por_status(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    assert _nomes(await _listar(client, h, status="aberta")) == ["Ana", "Bruno", "Mariana"]
    assert _nomes(await _listar(client, h, status="fechada")) == ["100%_off", "Carla"]
    assert _nomes(await _listar(client, h, status="cancelada")) == ["Davi"]


async def test_filtro_por_origem_e_aberta_por(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    assert _nomes(await _listar(client, h, origem="whatsapp")) == ["Davi"]
    por_u1 = await _listar(client, h, aberta_por_id=cenario["u1"])
    assert _nomes(por_u1) == ["Ana", "Bruno", "100%_off"]


async def test_busca_por_cliente_parcial_sem_caixa_e_com_curingas_literais(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    assert _nomes(await _listar(client, h, cliente="ANA")) == ["Ana", "Mariana"]
    assert _nomes(await _listar(client, h, cliente="aria")) == ["Mariana"]
    assert _nomes(await _listar(client, h, cliente="%")) == ["100%_off"]  # % não é curinga
    assert _nomes(await _listar(client, h, cliente="_")) == ["100%_off"]  # _ também não
    assert _nomes(await _listar(client, h, cliente="inexistente")) == []


async def test_filtro_por_periodo_inclusivo(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    de = (BASE + timedelta(minutes=20)).isoformat()
    ate = (BASE + timedelta(minutes=40)).isoformat()
    # 20 (Bruno), 30 (Mariana) e 40 (Carla): as duas pontas entram
    assert _nomes(await _listar(client, h, de=de, ate=ate)) == ["Bruno", "Mariana", "Carla"]
    assert _nomes(await _listar(client, h, de=de, ate=de)) == ["Bruno"]
    assert _nomes(await _listar(client, h, ate=BASE.isoformat())) == []


async def test_filtros_combinados_e_total_respeita_os_filtros(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    pagina = await _listar(client, h, status="aberta", cliente="ana", aberta_por_id=cenario["u1"])
    assert _nomes(pagina) == ["Ana"] and pagina["total"] == 1


async def test_paginacao(
    client: AsyncClient, auth_headers: AuthHeaders, cenario: dict[str, int]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    p1 = await _listar(client, h, limit=2, offset=0)
    p2 = await _listar(client, h, limit=2, offset=2)
    p3 = await _listar(client, h, limit=2, offset=4)
    assert _nomes(p1) + _nomes(p2) + _nomes(p3) == [
        "Ana",
        "Bruno",
        "Mariana",
        "100%_off",
        "Davi",
        "Carla",
    ]
    assert p1["total"] == p2["total"] == p3["total"] == 6
    assert p1["limit"] == 2 and p2["offset"] == 2
    assert _nomes(await _listar(client, h, limit=2, offset=99)) == []


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"status": "inexistente"},
        {"origem": "telegrama"},
        {"de": "ontem"},
        {"cliente": "x" * 121},
    ],
)
async def test_parametros_invalidos(
    client: AsyncClient, auth_headers: AuthHeaders, params: dict[str, object]
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    r = await client.get("/comandas", params=params, headers=h)  # type: ignore[arg-type]
    assert r.status_code == 422


async def test_resumo_da_listagem_traz_total_e_quantidade_de_itens(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as s:
        sem: Semente = await semear_cardapio(s)
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    cid = (await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h)).json()["id"]
    item = {"produto_id": sem.produto_id, "tamanho_id": sem.tamanho_id, "quantidade": 2}
    await client.post(f"/comandas/{cid}/itens", json=item, headers=h)
    await client.post(f"/comandas/{cid}/itens", json=item, headers=h)

    linha = (await _listar(client, h))["itens"][0]  # type: ignore[index]
    assert linha["quantidade_itens"] == 2 and linha["total"] == "75.60"
    assert "itens" not in linha


@pytest.mark.parametrize("papel", list(Papel))
async def test_todos_os_papeis_consultam_o_detalhe(
    client: AsyncClient,
    auth_headers: AuthHeaders,
    factory: async_sessionmaker[AsyncSession],
    papel: Papel,
) -> None:
    async with factory() as s:
        sem = await semear_cardapio(s)
    h = await auth_headers(f"{papel}@acai.com", papel)
    cid = (await client.post("/comandas", json={"cliente_nome": "Ana"}, headers=h)).json()["id"]
    corpo = {
        "produto_id": sem.produto_id,
        "tamanho_id": sem.tamanho_id,
        "adicionais": [{"adicional_id": sem.adicional_id}],
    }
    await client.post(f"/comandas/{cid}/itens", json=corpo, headers=h)

    r = await client.get(f"/comandas/{cid}", headers=h)

    assert r.status_code == 200
    detalhe = r.json()
    assert detalhe["id"] == cid and detalhe["total"] == "21.40"
    assert detalhe["itens"][0]["adicionais"][0]["nome"] == "Granola"
    assert detalhe["itens"][0]["subtotal"] == "21.40"


async def test_detalhe_inexistente_e_sem_token(
    client: AsyncClient, auth_headers: AuthHeaders
) -> None:
    h = await auth_headers("atendente@acai.com", Papel.ATENDENTE)
    r = await client.get("/comandas/999", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "comanda_nao_encontrada"
    assert (await client.get("/comandas/1")).status_code == 401
    assert (await client.get("/comandas")).status_code == 401
