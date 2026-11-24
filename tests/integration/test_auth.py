from httpx import AsyncClient, Response

from app.domain.usuarios.entities import Papel
from tests.conftest import SENHA, AuthHeaders, CriarUsuarioFn


async def _login(client: AsyncClient, email: str, senha: str = SENHA) -> Response:
    return await client.post("/auth/login", json={"email": email, "senha": senha})


async def test_health(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_login_me_e_refresh(client: AsyncClient, criar_usuario: CriarUsuarioFn) -> None:
    await criar_usuario("admin@acai.com", Papel.ADMIN)
    r = await _login(client, "admin@acai.com")
    assert r.status_code == 200
    tokens = r.json()
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.json()["papel"] == "admin"
    novo = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert novo.status_code == 200


async def test_refresh_nao_serve_como_access(
    client: AsyncClient, criar_usuario: CriarUsuarioFn
) -> None:
    await criar_usuario("a@acai.com", Papel.ADMIN)
    tokens = (await _login(client, "a@acai.com")).json()
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


async def test_senha_errada_e_usuario_inexistente_mesma_resposta(
    client: AsyncClient, criar_usuario: CriarUsuarioFn
) -> None:
    await criar_usuario("a@acai.com", Papel.ADMIN)
    r1 = await _login(client, "a@acai.com", "errada-errada")
    r2 = await _login(client, "ninguem@acai.com")
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


async def test_bloqueio_apos_tentativas(client: AsyncClient, criar_usuario: CriarUsuarioFn) -> None:
    await criar_usuario("a@acai.com", Papel.ADMIN)
    for _ in range(5):
        assert (await _login(client, "a@acai.com", "errada-errada")).status_code == 401
    r = await _login(client, "a@acai.com")
    assert r.status_code == 429
    assert "retry-after" in r.headers


async def test_sem_token_401(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401


async def test_apenas_admin_cria_usuario(client: AsyncClient, auth_headers: AuthHeaders) -> None:
    payload = {
        "nome": "Novo",
        "email": "novo@acai.com",
        "senha": "outra-senha-123",
        "papel": "caixa",
    }

    h_atd = await auth_headers("atd@acai.com", Papel.ATENDENTE)
    r = await client.post("/usuarios", json=payload, headers=h_atd)
    assert r.status_code == 403

    h = await auth_headers("adm@acai.com", Papel.ADMIN)
    assert (await client.post("/usuarios", json=payload, headers=h)).status_code == 201
    assert (await client.post("/usuarios", json=payload, headers=h)).status_code == 409


async def test_entrada_com_campo_extra_rejeitada(client: AsyncClient) -> None:
    r = await client.post("/auth/login", json={"email": "a@a.com", "senha": "x", "admin": True})
    assert r.status_code == 422
