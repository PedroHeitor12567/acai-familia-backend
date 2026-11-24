from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.usuarios.ports import FiltrosUsuario
from app.application.usuarios.use_cases.alterar_propria_senha import AlterarPropriaSenha
from app.application.usuarios.use_cases.alterar_status_usuario import AlterarStatusUsuario
from app.application.usuarios.use_cases.atualizar_usuario import AtualizarUsuario
from app.application.usuarios.use_cases.listar_usuarios import ListarUsuarios
from app.application.usuarios.use_cases.obter_usuario import ObterUsuario
from app.application.usuarios.use_cases.redefinir_senha import RedefinirSenha
from app.bootstrap.container import build_uow, get_hasher
from app.domain.exceptions import (
    EmailJaCadastrado,
    MuitasTentativas,
    OperacaoNaoPermitida,
    PermissaoNegada,
    SenhaAtualIncorreta,
    UsuarioNaoEncontrado,
)
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository
from app.infrastructure.security.rate_limit import InMemoryLoginThrottle

SENHA_ATUAL = "senha-atual-123"
SENHA_NOVA = "senha-nova-456"


async def _novo(s: AsyncSession, email: str, papel: Papel, ativo: bool = True) -> Usuario:
    usuario = await SqlAlchemyUsuarioRepository(s).adicionar(
        Usuario(
            nome="Fulano",
            email=email,
            senha_hash=await get_hasher().hash(SENHA_ATUAL),
            papel=papel,
            ativo=ativo,
        )
    )
    await s.commit()
    return usuario


async def _auditoria(s: AsyncSession) -> list[AuditLogModel]:
    return list(await s.scalars(select(AuditLogModel).order_by(AuditLogModel.id)))


@pytest.fixture
async def s(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session


# --- listar / obter ----------------------------------------------------------------------


@pytest.mark.parametrize("papel", [Papel.ATENDENTE, Papel.CAIXA])
async def test_listar_e_obter_exigem_admin_ou_gerente(s: AsyncSession, papel: Papel) -> None:
    ator = await _novo(s, "x@a.com", papel)
    with pytest.raises(PermissaoNegada):
        await ListarUsuarios(build_uow(s)).executar(ator, FiltrosUsuario(), 20, 0)
    with pytest.raises(PermissaoNegada):
        await ObterUsuario(build_uow(s)).executar(ator, 1)


async def test_gerente_lista_e_obtem(s: AsyncSession) -> None:
    gerente = await _novo(s, "g@a.com", Papel.GERENTE)
    itens, total = await ListarUsuarios(build_uow(s)).executar(gerente, FiltrosUsuario(), 20, 0)
    assert total == 1 and itens[0].id == gerente.id
    assert (
        await ObterUsuario(build_uow(s)).executar(gerente, gerente.id_persistido)
    ).id == gerente.id


async def test_obter_inexistente(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        await ObterUsuario(build_uow(s)).executar(admin, 999)


# --- atualizar ---------------------------------------------------------------------------


async def test_atualizar_exige_admin(s: AsyncSession) -> None:
    gerente = await _novo(s, "g@a.com", Papel.GERENTE)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(PermissaoNegada):
        await AtualizarUsuario(build_uow(s)).executar(gerente, alvo.id_persistido, nome="Novo")


async def test_atualizar_inexistente(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        await AtualizarUsuario(build_uow(s)).executar(admin, 999, nome="Novo")


async def test_atualizar_normaliza_email_e_audita_apenas_o_diff(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    r = await AtualizarUsuario(build_uow(s)).executar(
        admin, alvo.id_persistido, nome="Fulano", email="Novo@A.com", papel=Papel.GERENTE
    )
    assert r.email == "novo@a.com" and r.papel is Papel.GERENTE
    (log,) = await _auditoria(s)
    assert log.acao == "atualizar" and log.entidade == "usuario"
    assert log.entidade_id == str(alvo.id) and log.usuario_id == admin.id
    # "nome" não mudou, então não entra no diff
    assert log.detalhes == {
        "email": {"antes": "t@a.com", "depois": "novo@a.com"},
        "papel": {"antes": "caixa", "depois": "gerente"},
    }


async def test_atualizar_sem_mudanca_nao_audita(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    await AtualizarUsuario(build_uow(s)).executar(admin, alvo.id_persistido, email="T@a.com")
    assert await _auditoria(s) == []


async def test_atualizar_email_ja_usado(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(EmailJaCadastrado):
        await AtualizarUsuario(build_uow(s)).executar(admin, alvo.id_persistido, email="A@a.com")


async def test_admin_nao_rebaixa_a_si_mesmo(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    await _novo(s, "b@a.com", Papel.ADMIN)
    with pytest.raises(OperacaoNaoPermitida) as e:
        await AtualizarUsuario(build_uow(s)).executar(
            admin, admin.id_persistido, papel=Papel.GERENTE
        )
    assert e.value.motivo == "auto_rebaixamento"


async def test_nao_rebaixa_o_ultimo_admin_ativo(s: AsyncSession) -> None:
    unico = await _novo(s, "a@a.com", Papel.ADMIN)
    # ator é outro admin (ex.: já desativado/removido do banco): ainda assim o último fica.
    ator = Usuario(nome="X", email="x@a.com", senha_hash="x", papel=Papel.ADMIN, id=999)
    with pytest.raises(OperacaoNaoPermitida) as e:
        await AtualizarUsuario(build_uow(s)).executar(ator, unico.id_persistido, papel=Papel.CAIXA)
    assert e.value.motivo == "ultimo_admin"


async def test_rebaixa_admin_quando_ha_outro_ativo(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    outro = await _novo(s, "b@a.com", Papel.ADMIN)
    r = await AtualizarUsuario(build_uow(s)).executar(
        admin, outro.id_persistido, papel=Papel.GERENTE
    )
    assert r.papel is Papel.GERENTE


# --- desativar / reativar ----------------------------------------------------------------


async def test_status_exige_admin(s: AsyncSession) -> None:
    gerente = await _novo(s, "g@a.com", Papel.GERENTE)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(PermissaoNegada):
        await AlterarStatusUsuario(build_uow(s)).executar(gerente, alvo.id_persistido, ativo=False)


async def test_desativar_e_reativar_auditam(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    caso = AlterarStatusUsuario(build_uow(s))
    assert (await caso.executar(admin, alvo.id_persistido, ativo=False)).ativo is False
    assert (await caso.executar(admin, alvo.id_persistido, ativo=True)).ativo is True
    acoes = [(a.acao, a.detalhes) for a in await _auditoria(s)]
    assert acoes == [
        ("desativar", {"ativo": {"antes": True, "depois": False}}),
        ("reativar", {"ativo": {"antes": False, "depois": True}}),
    ]


async def test_status_repetido_e_idempotente_e_nao_audita(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    await AlterarStatusUsuario(build_uow(s)).executar(admin, alvo.id_persistido, ativo=True)
    assert await _auditoria(s) == []


async def test_admin_nao_desativa_a_si_mesmo(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    await _novo(s, "b@a.com", Papel.ADMIN)
    with pytest.raises(OperacaoNaoPermitida) as e:
        await AlterarStatusUsuario(build_uow(s)).executar(admin, admin.id_persistido, ativo=False)
    assert e.value.motivo == "auto_desativacao"


async def test_nao_desativa_o_ultimo_admin_ativo(s: AsyncSession) -> None:
    unico = await _novo(s, "a@a.com", Papel.ADMIN)
    ator = Usuario(nome="X", email="x@a.com", senha_hash="x", papel=Papel.ADMIN, id=999)
    with pytest.raises(OperacaoNaoPermitida) as e:
        await AlterarStatusUsuario(build_uow(s)).executar(ator, unico.id_persistido, ativo=False)
    assert e.value.motivo == "ultimo_admin"


async def test_desativa_admin_quando_ha_outro_ativo(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    outro = await _novo(s, "b@a.com", Papel.ADMIN)
    r = await AlterarStatusUsuario(build_uow(s)).executar(admin, outro.id_persistido, ativo=False)
    assert r.ativo is False


async def test_status_inexistente(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        await AlterarStatusUsuario(build_uow(s)).executar(admin, 999, ativo=False)


# --- senhas ------------------------------------------------------------------------------


def _alterar_senha(
    s: AsyncSession, throttle: InMemoryLoginThrottle | None = None
) -> AlterarPropriaSenha:
    return AlterarPropriaSenha(
        build_uow(s), get_hasher(), throttle or InMemoryLoginThrottle(5, 300)
    )


async def test_alterar_propria_senha_com_sucesso_sem_vazar_na_auditoria(s: AsyncSession) -> None:
    ator = await _novo(s, "a@a.com", Papel.CAIXA)
    await _alterar_senha(s).executar(ator, SENHA_ATUAL, SENHA_NOVA)
    salvo = await SqlAlchemyUsuarioRepository(s).obter_por_id(ator.id_persistido)
    assert salvo is not None
    assert await get_hasher().verify(salvo.senha_hash, SENHA_NOVA)
    assert not await get_hasher().verify(salvo.senha_hash, SENHA_ATUAL)
    (log,) = await _auditoria(s)
    assert log.acao == "alterar_senha" and log.detalhes == {"campos": ["senha"]}
    texto = str(log.detalhes)
    assert SENHA_NOVA not in texto and SENHA_ATUAL not in texto and "argon2" not in texto


async def test_alterar_senha_com_atual_incorreta(s: AsyncSession) -> None:
    ator = await _novo(s, "a@a.com", Papel.CAIXA)
    with pytest.raises(SenhaAtualIncorreta):
        await _alterar_senha(s).executar(ator, "errada-errada", SENHA_NOVA)
    assert await _auditoria(s) == []


async def test_nova_senha_deve_ser_diferente_da_atual(s: AsyncSession) -> None:
    ator = await _novo(s, "a@a.com", Papel.CAIXA)
    with pytest.raises(OperacaoNaoPermitida) as e:
        await _alterar_senha(s).executar(ator, SENHA_ATUAL, SENHA_ATUAL)
    assert e.value.motivo == "senha_igual_a_atual"


async def test_alterar_senha_aplica_throttle_contra_forca_bruta(s: AsyncSession) -> None:
    ator = await _novo(s, "a@a.com", Papel.CAIXA)
    caso = _alterar_senha(s, InMemoryLoginThrottle(3, 300))
    for _ in range(3):
        with pytest.raises(SenhaAtualIncorreta):
            await caso.executar(ator, "errada-errada", SENHA_NOVA)
    # bloqueado: nem a senha correta é aceita agora
    with pytest.raises(MuitasTentativas):
        await caso.executar(ator, SENHA_ATUAL, SENHA_NOVA)


async def test_redefinir_senha_exige_admin(s: AsyncSession) -> None:
    gerente = await _novo(s, "g@a.com", Papel.GERENTE)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(PermissaoNegada):
        await RedefinirSenha(build_uow(s), get_hasher()).executar(
            gerente, alvo.id_persistido, SENHA_NOVA
        )


async def test_redefinir_senha_inexistente(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        await RedefinirSenha(build_uow(s), get_hasher()).executar(admin, 999, SENHA_NOVA)


async def test_redefinir_senha_nao_exige_a_atual_e_audita_sem_segredos(s: AsyncSession) -> None:
    admin = await _novo(s, "a@a.com", Papel.ADMIN)
    alvo = await _novo(s, "t@a.com", Papel.CAIXA)
    await RedefinirSenha(build_uow(s), get_hasher()).executar(admin, alvo.id_persistido, SENHA_NOVA)
    salvo = await SqlAlchemyUsuarioRepository(s).obter_por_id(alvo.id_persistido)
    assert salvo is not None and await get_hasher().verify(salvo.senha_hash, SENHA_NOVA)
    (log,) = await _auditoria(s)
    assert log.acao == "redefinir_senha" and log.entidade_id == str(alvo.id)
    assert log.detalhes == {"campos": ["senha"]}
