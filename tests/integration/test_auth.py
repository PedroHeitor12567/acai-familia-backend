from collections.abc import Callable

from fastapi.testclient import TestClient
from httpx import Response

from app.domain.usuarios.entities import Papel
from tests.conftest import SENHA, AuthHeaders


def _login(client: TestClient, email: str, senha: str = SENHA) -> Response:
    return client.post("/auth/login", json={"email": email, "senha": senha})


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"


def test_login_me_e_refresh(
    client: TestClient, criar_usuario: Callable[[str, Papel], None]
) -> None:
    criar_usuario("admin@acai.com", Papel.ADMIN)
    r = _login(client, "admin@acai.com")
    assert r.status_code == 200
    tokens = r.json()
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.json()["papel"] == "admin"
    novo = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert novo.status_code == 200


def test_refresh_nao_serve_como_access(
    client: TestClient, criar_usuario: Callable[[str, Papel], None]
) -> None:
    criar_usuario("a@acai.com", Papel.ADMIN)
    tokens = _login(client, "a@acai.com").json()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


def test_senha_errada_e_usuario_inexistente_mesma_resposta(
    client: TestClient, criar_usuario: Callable[[str, Papel], None]
) -> None:
    criar_usuario("a@acai.com", Papel.ADMIN)
    r1 = _login(client, "a@acai.com", "errada-errada")
    r2 = _login(client, "ninguem@acai.com")
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_bloqueio_apos_tentativas(
    client: TestClient, criar_usuario: Callable[[str, Papel], None]
) -> None:
    criar_usuario("a@acai.com", Papel.ADMIN)
    for _ in range(5):
        assert _login(client, "a@acai.com", "errada-errada").status_code == 401
    r = _login(client, "a@acai.com")
    assert r.status_code == 429
    assert "retry-after" in r.headers


def test_sem_token_401(client: TestClient) -> None:
    assert client.get("/auth/me").status_code == 401


def test_apenas_admin_cria_usuario(client: TestClient, auth_headers: AuthHeaders) -> None:
    payload = {
        "nome": "Novo",
        "email": "novo@acai.com",
        "senha": "outra-senha-123",
        "papel": "caixa",
    }

    h_atd = auth_headers("atd@acai.com", Papel.ATENDENTE)
    r = client.post("/usuarios", json=payload, headers=h_atd)
    assert r.status_code == 403

    h = auth_headers("adm@acai.com", Papel.ADMIN)
    assert client.post("/usuarios", json=payload, headers=h).status_code == 201
    assert client.post("/usuarios", json=payload, headers=h).status_code == 409


def test_entrada_com_campo_extra_rejeitada(client: TestClient) -> None:
    r = client.post("/auth/login", json={"email": "a@a.com", "senha": "x", "admin": True})
    assert r.status_code == 422
