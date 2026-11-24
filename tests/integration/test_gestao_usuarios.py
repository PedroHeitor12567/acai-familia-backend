import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.usuarios.entities import Papel
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from tests.conftest import SENHA, CriarUsuarioFn

NOVA_SENHA = "senha-nova-456"


async def _tokens(client: AsyncClient, email: str, senha: str = SENHA) -> dict[str, str]:
    r = await client.post("/auth/login", json={"email": email, "senha": senha})
    assert r.status_code == 200, r.text
    tokens: dict[str, str] = r.json()
    return tokens


async def _h(client: AsyncClient, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {(await _tokens(client, email))['access_token']}"}


async def _id(client: AsyncClient, headers: dict[str, str]) -> int:
    uid: int = (await client.get("/auth/me", headers=headers)).json()["id"]
    return uid


@pytest.fixture
async def cenario(client: AsyncClient, criar_usuario: CriarUsuarioFn) -> dict[str, dict[str, str]]:
    for papel in Papel:
        await criar_usuario(f"{papel}@acai.com", papel)
    return {str(papel): await _h(client, f"{papel}@acai.com") for papel in Papel}


# --- permissões --------------------------------------------------------------------------


@pytest.mark.parametrize("papel", ["atendente", "caixa"])
async def test_atendente_e_caixa_recebem_403(
    client: AsyncClient, cenario: dict[str, dict[str, str]], papel: str
) -> None:
    h = cenario[papel]
    assert (await client.get("/usuarios", headers=h)).status_code == 403
    assert (await client.get("/usuarios/1", headers=h)).status_code == 403
    assert (await client.patch("/usuarios/1", json={"nome": "Novo"}, headers=h)).status_code == 403
    assert (await client.post("/usuarios/1/desativar", headers=h)).status_code == 403
    assert (await client.post("/usuarios/1/reativar", headers=h)).status_code == 403
    r = await client.post("/usuarios/1/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h)
    assert r.status_code == 403


async def test_gerente_lista_mas_nao_edita(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["gerente"]
    assert (await client.get("/usuarios", headers=h)).status_code == 200
    assert (await client.get("/usuarios/1", headers=h)).status_code == 200
    assert (await client.patch("/usuarios/1", json={"nome": "Novo"}, headers=h)).status_code == 403
    assert (await client.post("/usuarios/1/desativar", headers=h)).status_code == 403
    r = await client.post("/usuarios/1/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h)
    assert r.status_code == 403


async def test_sem_token_401(client: AsyncClient) -> None:
    assert (await client.get("/usuarios")).status_code == 401


async def test_obter_inexistente_404(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    r = await client.get("/usuarios/9999", headers=cenario["admin"])
    assert r.status_code == 404
    assert r.json()["code"] == "usuario_nao_encontrado"


# --- listagem ----------------------------------------------------------------------------


async def test_listagem_paginacao_e_filtros(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    pag = (await client.get("/usuarios", headers=h)).json()
    assert pag["total"] == 4 and pag["limit"] == 20 and pag["offset"] == 0
    ids = [u["id"] for u in pag["itens"]]
    assert ids == sorted(ids)
    assert "senha_hash" not in pag["itens"][0] and "senha" not in pag["itens"][0]

    p1 = (await client.get("/usuarios", params={"limit": 3, "offset": 0}, headers=h)).json()
    p2 = (await client.get("/usuarios", params={"limit": 3, "offset": 3}, headers=h)).json()
    assert len(p1["itens"]) == 3 and len(p2["itens"]) == 1 and p1["total"] == 4
    assert [u["id"] for u in p1["itens"] + p2["itens"]] == ids

    por_papel = (await client.get("/usuarios", params={"papel": "caixa"}, headers=h)).json()
    assert [u["email"] for u in por_papel["itens"]] == ["caixa@acai.com"]

    busca = (await client.get("/usuarios", params={"q": "ATENDE"}, headers=h)).json()
    assert [u["email"] for u in busca["itens"]] == ["atendente@acai.com"]

    caixa_id = por_papel["itens"][0]["id"]
    await client.post(f"/usuarios/{caixa_id}/desativar", headers=h)
    inativos = (await client.get("/usuarios", params={"ativo": False}, headers=h)).json()
    assert [u["id"] for u in inativos["itens"]] == [caixa_id]
    ativos = (await client.get("/usuarios", params={"ativo": True}, headers=h)).json()
    assert ativos["total"] == 3


async def test_busca_trata_curingas_como_texto_literal(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    assert (await client.get("/usuarios", params={"q": "%"}, headers=h)).json()["total"] == 0
    assert (await client.get("/usuarios", params={"q": "_"}, headers=h)).json()["total"] == 0


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_paginacao_invalida_422(
    client: AsyncClient, cenario: dict[str, dict[str, str]], params: dict[str, int]
) -> None:
    assert (
        await client.get("/usuarios", params=params, headers=cenario["admin"])
    ).status_code == 422


# --- edição ------------------------------------------------------------------------------


async def test_admin_edita_usuario(client: AsyncClient, cenario: dict[str, dict[str, str]]) -> None:
    h = cenario["admin"]
    alvo = await _id(client, cenario["caixa"])
    r = await client.patch(
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
async def test_patch_rejeita_campos_extras_ou_vazio_422(
    client: AsyncClient, cenario: dict[str, dict[str, str]], corpo: dict[str, object]
) -> None:
    alvo = await _id(client, cenario["caixa"])
    r = await client.patch(f"/usuarios/{alvo}", json=corpo, headers=cenario["admin"])
    assert r.status_code == 422


async def test_trocar_email_para_um_ja_usado_409(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    alvo = await _id(client, cenario["caixa"])
    r = await client.patch(
        f"/usuarios/{alvo}", json={"email": "ADMIN@acai.com"}, headers=cenario["admin"]
    )
    assert r.status_code == 409
    assert r.json()["code"] == "email_ja_cadastrado"


async def test_patch_inexistente_404(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    r = await client.patch("/usuarios/9999", json={"nome": "Novo"}, headers=cenario["admin"])
    assert r.status_code == 404


# --- desativar / reativar ----------------------------------------------------------------


async def test_desativar_derruba_access_e_refresh_na_hora_e_reativar_volta(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    tokens = await _tokens(client, "atendente@acai.com")
    h_atd = {"Authorization": f"Bearer {tokens['access_token']}"}
    alvo = await _id(client, h_atd)
    assert (await client.get("/auth/me", headers=h_atd)).status_code == 200

    r = await client.post(f"/usuarios/{alvo}/desativar", headers=cenario["admin"])
    assert r.status_code == 200 and r.json()["ativo"] is False

    assert (await client.get("/auth/me", headers=h_atd)).status_code == 401
    refresh = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401
    login = await client.post("/auth/login", json={"email": "atendente@acai.com", "senha": SENHA})
    assert login.status_code == 401

    r = await client.post(f"/usuarios/{alvo}/reativar", headers=cenario["admin"])
    assert r.status_code == 200 and r.json()["ativo"] is True
    assert (
        await client.post("/auth/login", json={"email": "atendente@acai.com", "senha": SENHA})
    ).status_code == 200


async def test_admin_nao_desativa_nem_rebaixa_a_si_mesmo_nem_o_ultimo(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    eu = await _id(client, h)
    r = await client.post(f"/usuarios/{eu}/desativar", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "operacao_nao_permitida"
    r = await client.patch(f"/usuarios/{eu}", json={"papel": "gerente"}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "operacao_nao_permitida"
    # continua admin e ativo
    me = (await client.get("/auth/me", headers=h)).json()
    assert me["papel"] == "admin" and me["ativo"] is True


async def test_com_dois_admins_um_pode_desativar_o_outro_mas_nao_o_ultimo(
    client: AsyncClient, criar_usuario: CriarUsuarioFn, cenario: dict[str, dict[str, str]]
) -> None:
    await criar_usuario("admin2@acai.com", Papel.ADMIN)
    h1, h2 = cenario["admin"], await _h(client, "admin2@acai.com")
    id1, id2 = await _id(client, h1), await _id(client, h2)
    assert (await client.post(f"/usuarios/{id2}/desativar", headers=h1)).status_code == 200
    # admin2 caiu (401); admin1 é o único e não consegue se desativar
    assert (await client.post(f"/usuarios/{id1}/desativar", headers=h1)).status_code == 409
    assert (
        await client.patch(f"/usuarios/{id1}", json={"papel": "caixa"}, headers=h1)
    ).status_code == 409


# --- senhas ------------------------------------------------------------------------------


async def test_alterar_propria_senha(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["caixa"]
    errada = await client.post(
        "/auth/alterar-senha",
        json={"senha_atual": "errada-errada", "nova_senha": NOVA_SENHA},
        headers=h,
    )
    assert errada.status_code == 400 and errada.json()["code"] == "senha_atual_incorreta"

    igual = await client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": SENHA}, headers=h
    )
    assert igual.status_code == 409

    curta = await client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": "curta"}, headers=h
    )
    assert curta.status_code == 422

    ok = await client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA}, headers=h
    )
    assert ok.status_code == 204

    nova = await client.post("/auth/login", json={"email": "caixa@acai.com", "senha": NOVA_SENHA})
    antiga = await client.post("/auth/login", json={"email": "caixa@acai.com", "senha": SENHA})
    assert nova.status_code == 200 and antiga.status_code == 401


async def test_alterar_senha_bloqueia_forca_bruta(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["caixa"]
    corpo = {"senha_atual": "errada-errada", "nova_senha": NOVA_SENHA}
    for _ in range(5):
        assert (await client.post("/auth/alterar-senha", json=corpo, headers=h)).status_code == 400
    r = await client.post(
        "/auth/alterar-senha", json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA}, headers=h
    )
    assert r.status_code == 429 and "retry-after" in r.headers


async def test_alterar_senha_exige_autenticacao(client: AsyncClient) -> None:
    r = await client.post(
        "/auth/alterar-senha", json={"senha_atual": "x", "nova_senha": NOVA_SENHA}
    )
    assert r.status_code == 401


async def test_admin_redefine_senha_de_outro_usuario(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    alvo = await _id(client, cenario["atendente"])
    r = await client.post(
        f"/usuarios/{alvo}/redefinir-senha",
        json={"nova_senha": NOVA_SENHA},
        headers=cenario["admin"],
    )
    assert r.status_code == 204
    assert (
        await client.post("/auth/login", json={"email": "atendente@acai.com", "senha": NOVA_SENHA})
    ).status_code == 200
    assert (
        await client.post("/auth/login", json={"email": "atendente@acai.com", "senha": SENHA})
    ).status_code == 401


async def test_redefinir_senha_valida_entrada_e_existencia(
    client: AsyncClient, cenario: dict[str, dict[str, str]]
) -> None:
    h = cenario["admin"]
    assert (
        await client.post(
            "/usuarios/9999/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h
        )
    ).status_code == 404
    assert (
        await client.post("/usuarios/1/redefinir-senha", json={"nova_senha": "curta"}, headers=h)
    ).status_code == 422
    assert (
        await client.post(
            "/usuarios/1/redefinir-senha", json={"nova_senha": NOVA_SENHA, "x": 1}, headers=h
        )
    ).status_code == 422


# --- auditoria ---------------------------------------------------------------------------


async def test_auditoria_registra_acoes_e_nao_contem_senha_nem_hash(
    client: AsyncClient,
    cenario: dict[str, dict[str, str]],
    factory: async_sessionmaker[AsyncSession],
) -> None:
    h = cenario["admin"]
    alvo = await _id(client, cenario["atendente"])
    await client.patch(f"/usuarios/{alvo}", json={"nome": "Outro Nome"}, headers=h)
    await client.post(f"/usuarios/{alvo}/desativar", headers=h)
    await client.post(f"/usuarios/{alvo}/reativar", headers=h)
    await client.post(
        f"/usuarios/{alvo}/redefinir-senha", json={"nova_senha": NOVA_SENHA}, headers=h
    )
    await client.post(
        "/auth/alterar-senha",
        json={"senha_atual": SENHA, "nova_senha": NOVA_SENHA},
        headers=cenario["caixa"],
    )

    async with factory() as s:
        logs = list(
            await s.scalars(select(AuditLogModel).where(AuditLogModel.entidade == "usuario"))
        )
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
