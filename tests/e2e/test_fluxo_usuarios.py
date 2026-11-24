"""Fluxo e2e de usuários: PostgreSQL migrado pelo Alembic → admin → login → operação.

Este é o molde dos e2e dos próximos módulos: marcado `postgres`, usa `pg_client` (API completa
sobre o PostgreSQL, sem `create_all`) e conta uma história de ponta a ponta num único teste.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.bootstrap.container import build_criar_usuario
from app.domain.usuarios.entities import Papel

pytestmark = pytest.mark.postgres

SENHA_ADMIN = "admin-senha-123"
SENHA_ATENDENTE = "atendente-senha-123"


def _login(client: TestClient, email: str, senha: str) -> dict[str, str]:
    r = client.post("/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    tokens: dict[str, str] = r.json()
    return tokens


def _bearer(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_fluxo_completo_de_usuarios(pg_client: TestClient, pg_session: Session) -> None:
    # 1. primeiro admin, como o script `scripts.create_admin` faz (ator=None = bootstrap)
    build_criar_usuario(pg_session).executar(
        None, "Admin E2E", "admin-e2e@acai.com", SENHA_ADMIN, Papel.ADMIN
    )

    # 2. login do admin → /auth/me
    tokens_admin = _login(pg_client, "admin-e2e@acai.com", SENHA_ADMIN)
    h_admin = _bearer(tokens_admin)
    me = pg_client.get("/auth/me", headers=h_admin)
    assert me.status_code == 200
    assert me.json()["email"] == "admin-e2e@acai.com"
    assert me.json()["papel"] == "admin"

    # 3. admin cria um atendente → o atendente faz login
    criado = pg_client.post(
        "/usuarios",
        json={
            "nome": "Atendente E2E",
            "email": "Atendente-E2E@acai.com",
            "senha": SENHA_ATENDENTE,
            "papel": "atendente",
        },
        headers=h_admin,
    )
    assert criado.status_code == 201
    atendente_id = criado.json()["id"]
    assert criado.json()["email"] == "atendente-e2e@acai.com"  # normalizado
    tokens_atd = _login(pg_client, "atendente-e2e@acai.com", SENHA_ATENDENTE)
    h_atd = _bearer(tokens_atd)
    assert pg_client.get("/auth/me", headers=h_atd).status_code == 200

    # 4. admin lista e vê os dois (busca com ilike no PostgreSQL)
    lista = pg_client.get("/usuarios", params={"q": "E2E"}, headers=h_admin)
    assert lista.status_code == 200
    assert lista.json()["total"] == 2
    assert {u["email"] for u in lista.json()["itens"]} == {
        "admin-e2e@acai.com",
        "atendente-e2e@acai.com",
    }
    # atendente não lista
    assert pg_client.get("/usuarios", headers=h_atd).status_code == 403

    # 5. admin desativa o atendente → access e refresh dele dão 401 na hora
    r = pg_client.post(f"/usuarios/{atendente_id}/desativar", headers=h_admin)
    assert r.status_code == 200 and r.json()["ativo"] is False
    assert pg_client.get("/auth/me", headers=h_atd).status_code == 401
    refresh = pg_client.post("/auth/refresh", json={"refresh_token": tokens_atd["refresh_token"]})
    assert refresh.status_code == 401
    inativos = pg_client.get("/usuarios", params={"ativo": False}, headers=h_admin)
    assert [u["id"] for u in inativos.json()["itens"]] == [atendente_id]

    # 6. admin reativa → o atendente volta a logar
    r = pg_client.post(f"/usuarios/{atendente_id}/reativar", headers=h_admin)
    assert r.status_code == 200 and r.json()["ativo"] is True
    voltou = _login(pg_client, "atendente-e2e@acai.com", SENHA_ATENDENTE)
    assert pg_client.get("/auth/me", headers=_bearer(voltou)).status_code == 200
