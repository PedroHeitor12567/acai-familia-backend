from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.domain.usuarios.entities import Papel
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from tests.conftest import SENHA

CriarUsuario = Callable[[str, Papel], None]
NOVA_SENHA = "senha-nova-456"


def _tokens(client: TestClient, email: str, senha: str = SENHA) -> dict[str, str]:
    r = client.post("/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    tokens: dict[str, str] = r.json()
    return tokens


def _h(client: TestClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_tokens(client, email)['access_token']}"}


def _id(client: TestClient, headers: dict[str, str]) -> int:
    uid: int = client.get("/auth/me", headers=headers).json()["id"]
    return uid


@pytest.fixture
def cenario(client: TestClient, criar_usuario: CriarUsuario) -> dict[str, dict[str, str]]:
    for papel in Papel:
        criar_usuario(f"{papel}@acai.com", papel)
    return {str(papel): _h(client, f"{papel}@acai.com") for papel in Papel}


# --- permissões --------------------------------------------------------------------------


@pytest.mark.parametrize("papel", ["atendente", "caixa"])
def test_atendente_e_caixa_recebem_403(
    client: TestClient, cenario: dict[str, dict[str, str]], papel: str
) -> None:
    h = cenario[papel]
    assert client.get("/usuarios", headers=h).status_code == 403
    assert client.get("/usuarios/1", headers=h).status_code == 403
    assert client.patch("/usuarios/1", json={"nome": "Novo"}, headers=h).status_code == 403
    assert client.post("/usuarios/1/desativar", headers=h).status_code == 403
    assert client.post("/usuarios/1/reativar", headers=h).status_code == 403
    r = client.post("/usuarios/1/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h)
    assert r.status_code == 403


def test_gerente_lista_mas_nao_edita(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["gerente"]
    assert client.get("/usuarios", headers=h).status_code == 200
    assert client.get("/usuarios/1", headers=h).status_code == 200
    assert client.patch("/usuarios/1", json={"nome": "Novo"}, headers=h).status_code == 403
    assert client.post("/usuarios/1/desativar", headers=h).status_code == 403
    r = client.post("/usuarios/1/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h)
    assert r.status_code == 403


def test_sem_token_401(client: TestClient) -> None:
    assert client.get("/usuarios").status_code == 401


def test_obter_inexistente_404(client: TestClient, cenario: dict[str, dict[str, str]]) -> None:
    r = client.get("/usuarios/9999", headers=cenario["admin"])
    assert r.status_code == 404
    assert r.json()["code"] == "usuario_nao_encontrado"


# --- listagem ----------------------------------------------------------------------------


def test_listagem_paginacao_e_filtros(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    pag = client.get("/usuarios", headers=h).json()
    assert pag["total"] == 4 and pag["limit"] == 20 and pag["offset"] == 0
    ids = [u["id"] for u in pag["itens"]]
    assert ids == sorted(ids)
    assert "senha_hash" not in pag["itens"][0] and "senha" not in pag["itens"][0]

    p1 = client.get("/usuarios", params={"limit": 3, "offset": 0}, headers=h).json()
    p2 = client.get("/usuarios", params={"limit": 3, "offset": 3}, headers=h).json()
    assert len(p1["itens"]) == 3 and len(p2["itens"]) == 1 and p1["total"] == 4
    assert [u["id"] for u in p1["itens"] + p2["itens"]] == ids

    por_papel = client.get("/usuarios", params={"papel": "caixa"}, headers=h).json()
    assert [u["email"] for u in por_papel["itens"]] == ["caixa@acai.com"]

    busca = client.get("/usuarios", params={"q": "ATENDE"}, headers=h).json()
    assert [u["email"] for u in busca["itens"]] == ["atendente@acai.com"]

    caixa_id = por_papel["itens"][0]["id"]
    client.post(f"/usuarios/{caixa_id}/desativar", headers=h)
    inativos = client.get("/usuarios", params={"ativo": False}, headers=h).json()
    assert [u["id"] for u in inativos["itens"]] == [caixa_id]
    ativos = client.get("/usuarios", params={"ativo": True}, headers=h).json()
    assert ativos["total"] == 3


def test_busca_trata_curingas_como_texto_literal(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    assert client.get("/usuarios", params={"q": "%"}, headers=h).json()["total"] == 0
    assert client.get("/usuarios", params={"q": "_"}, headers=h).json()["total"] == 0


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_paginacao_invalida_422(
    client: TestClient, cenario: dict[str, dict[str, str]], params: dict[str, int]
) -> None:
    assert client.get("/usuarios", params=params, headers=cenario["admin"]).status_code == 422


# --- edição ------------------------------------------------------------------------------


def test_admin_edita_usuario(client: TestClient, cenario: dict[str, dict[str, str]]) -> None:
    h = cenario["admin"]
    alvo = _id(client, cenario["caixa"])
    r = client.patch(
        f"/usuarios/{alvo}",
        json={"nome": "Maria", "email": "Maria@Acai.com", "papel": "atendente"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json() == {
        "id": alvo,
        "nome": "Maria",
        "email": "maria@acai.com",
        "papel": "atendente",
        "ativo": True,
    }


@pytest.mark.parametrize(
    "corpo",
    [{"ativo": False}, {"senha_hash": "x"}, {"id": 1}, {"nome": "Ok", "ativo": True}, {}],
)
def test_patch_rejeita_campos_extras_ou_vazio_422(
    client: TestClient, cenario: dict[str, dict[str, str]], corpo: dict[str, object]
) -> None:
    alvo = _id(client, cenario["caixa"])
    r = client.patch(f"/usuarios/{alvo}", json=corpo, headers=cenario["admin"])
    assert r.status_code == 422


def test_trocar_email_para_um_ja_usado_409(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    alvo = _id(client, cenario["caixa"])
    r = client.patch(
        f"/usuarios/{alvo}", json={"email": "ADMIN@acai.com"}, headers=cenario["admin"]
    )
    assert r.status_code == 409
    assert r.json()["code"] == "email_ja_cadastrado"


def test_patch_inexistente_404(client: TestClient, cenario: dict[str, dict[str, str]]) -> None:
    r = client.patch("/usuarios/9999", json={"nome": "Novo"}, headers=cenario["admin"])
    assert r.status_code == 404


# --- desativar / reativar ----------------------------------------------------------------


def test_desativar_derruba_access_e_refresh_na_hora_e_reativar_volta(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    tokens = _tokens(client, "atendente@acai.com")
    h_atd = {"Authorization": f"Bearer {tokens['access_token']}"}
    alvo = _id(client, h_atd)
    assert client.get("/auth/me", headers=h_atd).status_code == 200

    r = client.post(f"/usuarios/{alvo}/desativar", headers=cenario["admin"])
    assert r.status_code == 200 and r.json()["ativo"] is False

    assert client.get("/auth/me", headers=h_atd).status_code == 401
    refresh = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401
    login = client.post("/auth/login", json={"email": "atendente@acai.com", "senha": SENHA})
    assert login.status_code == 401

    r = client.post(f"/usuarios/{alvo}/reativar", headers=cenario["admin"])
    assert r.status_code == 200 and r.json()["ativo"] is True
    assert (
        client.post("/auth/login", json={"email": "atendente@acai.com", "senha": SENHA}).status_code
        == 200
    )


def test_admin_nao_desativa_nem_rebaixa_a_si_mesmo_nem_o_ultimo(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    eu = _id(client, h)
    r = client.post(f"/usuarios/{eu}/desativar", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "operacao_nao_permitida"
    r = client.patch(f"/usuarios/{eu}", json={"papel": "gerente"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "operacao_nao_permitida"
    # continua admin e ativo
    me = client.get("/auth/me", headers=h).json()
    assert me["papel"] == "admin" and me["ativo"] is True


def test_com_dois_admins_um_pode_desativar_o_outro_mas_nao_o_ultimo(
    client: TestClient, criar_usuario: CriarUsuario, cenario: dict[str, dict[str, str]]
) -> None:
    criar_usuario("admin2@acai.com", Papel.ADMIN)
    h1, h2 = cenario["admin"], _h(client, "admin2@acai.com")
    id1, id2 = _id(client, h1), _id(client, h2)
    assert client.post(f"/usuarios/{id2}/desativar", headers=h1).status_code == 200
    # admin2 caiu (401); admin1 é o único e não consegue se desativar
    assert client.post(f"/usuarios/{id1}/desativar", headers=h1).status_code == 409
    assert client.patch(f"/usuarios/{id1}", json={"papel": "caixa"}, headers=h1).status_code == 409


# --- senhas ------------------------------------------------------------------------------


def test_alterar_propria_senha(client: TestClient, cenario: dict[str, dict[str, str]]) -> None:
    h = cenario["caixa"]
    errada = client.post(
        "/auth/alterar-senha",
        json={"senha_atual": "errada-errada", "nova_senha": NOVA_SENHA},
        headers=h,
    )
    assert errada.status_code == 400 and errada.json()["code"] == "senha_atual_incorreta"

    igual = client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": SENHA}, headers=h
    )
    assert igual.status_code == 409

    curta = client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": "curta"}, headers=h
    )
    assert curta.status_code == 422

    ok = client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA}, headers=h
    )
    assert ok.status_code == 204

    nova = client.post("/auth/login", json={"email": "caixa@acai.com", "senha": NOVA_SENHA})
    antiga = client.post("/auth/login", json={"email": "caixa@acai.com", "senha": SENHA})
    assert nova.status_code == 200 and antiga.status_code == 401


def test_alterar_senha_bloqueia_forca_bruta(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["caixa"]
    corpo = {"senha_atual": "errada-errada", "nova_senha": NOVA_SENHA}
    for _ in range(5):
        assert client.post("/auth/alterar-senha", json=corpo, headers=h).status_code == 400
    r = client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA}, headers=h
    )
    assert r.status_code == 429 and "retry-after" in r.headers


def test_alterar_senha_exige_autenticacao(client: TestClient) -> None:
    r = client.post("/auth/alterar-senha", json={"senha_atual": "x", "nova_senha": NOVA_SENHA})
    assert r.status_code == 401


def test_admin_redefine_senha_de_outro_usuario(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    alvo = _id(client, cenario["atendente"])
    r = client.post(
        f"/usuarios/{alvo}/redefinir-senha",
        json={"nova_senha": NOVA_SENHA},
        headers=cenario["admin"],
    )
    assert r.status_code == 204
    assert (
        client.post(
            "/auth/login", json={"email": "atendente@acai.com", "senha": NOVA_SENHA}
        ).status_code
        == 200
    )
    assert (
        client.post("/auth/login", json={"email": "atendente@acai.com", "senha": SENHA}).status_code
        == 401
    )


def test_redefinir_senha_valida_entrada_e_existencia(
    client: TestClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    assert (
        client.post(
            "/usuarios/9999/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/usuarios/1/redefinir-senha", json={"nova_senha": "curta"}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/usuarios/1/redefinir-senha", json={"nova_senha": NOVA_SENHA, "x": 1}, headers=h
        ).status_code
        == 422
    )


# --- auditoria ---------------------------------------------------------------------------


def test_auditoria_registra_acoes_e_nao_contem_senha_nem_hash(
    client: TestClient,
    cenario: dict[str, dict[str, str]],
    factory: sessionmaker[Session],
) -> None:
    h = cenario["admin"]
    alvo = _id(client, cenario["atendente"])
    client.patch(f"/usuarios/{alvo}", json={"nome": "Outro Nome"}, headers=h)
    client.post(f"/usuarios/{alvo}/desativar", headers=h)
    client.post(f"/usuarios/{alvo}/reativar", headers=h)
    client.post(f"/usuarios/{alvo}/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h)
    client.post(
        "/auth/alterar-senha",
        json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA},
        headers=cenario["caixa"],
    )

    with factory() as s:
        logs = list(s.scalars(select(AuditLogModel).where(AuditLogModel.entidade == "usuario")))
    assert [a.acao for a in logs] == [
        "atualizar",
        "desativar",
        "reativar",
        "redefinir_senha",
        "alterar_senha",
    ]
    assert logs[0].detalhes == {"nome": {"antes": "Teste", "depois": "Outro Nome"}}
    for log in logs:
        texto = str(log.detalhes).lower()
        assert NOVA_SENHA not in texto and SENHA not in texto
        assert "argon2" not in texto and "hash" not in texto
