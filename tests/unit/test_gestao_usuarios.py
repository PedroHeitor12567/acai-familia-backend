import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

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


def _novo(s: Session, email: str, papel: Papel, ativo: bool = True) -> Usuario:
    usuario = SqlAlchemyUsuarioRepository(s).adicionar(
        Usuario(
            nome="Fulano",
            email=email,
            senha_hash=get_hasher().hash(SENHA_ATUAL),
            papel=papel,
            ativo=ativo,
        )
    )
    s.commit()
    return usuario


def _auditoria(s: Session) -> list[AuditLogModel]:
    return list(s.scalars(select(AuditLogModel).order_by(AuditLogModel.id)))


@pytest.fixture
def s(factory: sessionmaker[Session]) -> Session:
    return factory()


# --- listar / obter ----------------------------------------------------------------------


@pytest.mark.parametrize("papel", [Papel.ATENDENTE, Papel.CAIXA])
def test_listar_e_obter_exigem_admin_ou_gerente(s: Session, papel: Papel) -> None:
    ator = _novo(s, "x@a.com", papel)
    with pytest.raises(PermissaoNegada):
        ListarUsuarios(build_uow(s)).executar(ator, FiltrosUsuario(), 20, 0)
    with pytest.raises(PermissaoNegada):
        ObterUsuario(build_uow(s)).executar(ator, 1)


def test_gerente_lista_e_obtem(s: Session) -> None:
    gerente = _novo(s, "g@a.com", Papel.GERENTE)
    itens, total = ListarUsuarios(build_uow(s)).executar(gerente, FiltrosUsuario(), 20, 0)
    assert total == 1 and itens[0].id == gerente.id
    assert ObterUsuario(build_uow(s)).executar(gerente, gerente.id_persistido).id == gerente.id


def test_obter_inexistente(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        ObterUsuario(build_uow(s)).executar(admin, 999)


# --- atualizar ---------------------------------------------------------------------------


def test_atualizar_exige_admin(s: Session) -> None:
    gerente = _novo(s, "g@a.com", Papel.GERENTE)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(PermissaoNegada):
        AtualizarUsuario(build_uow(s)).executar(gerente, alvo.id_persistido, nome="Novo")


def test_atualizar_inexistente(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        AtualizarUsuario(build_uow(s)).executar(admin, 999, nome="Novo")


def test_atualizar_normaliza_email_e_audita_apenas_o_diff(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    r = AtualizarUsuario(build_uow(s)).executar(
        admin, alvo.id_persistido, nome="Fulano", email="Novo@A.com", papel=Papel.GERENTE
    )
    assert r.email == "novo@a.com" and r.papel is Papel.GERENTE
    (log,) = _auditoria(s)
    assert log.acao == "atualizar" and log.entidade == "usuario"
    assert log.entidade_id == str(alvo.id) and log.usuario_id == admin.id
    # "nome" não mudou, então não entra no diff
    assert log.detalhes == {
        "email": {"antes": "t@a.com", "depois": "novo@a.com"},
        "papel": {"antes": "caixa", "depois": "gerente"},
    }


def test_atualizar_sem_mudanca_nao_audita(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    AtualizarUsuario(build_uow(s)).executar(admin, alvo.id_persistido, email="T@a.com")
    assert _auditoria(s) == []


def test_atualizar_email_ja_usado(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(EmailJaCadastrado):
        AtualizarUsuario(build_uow(s)).executar(admin, alvo.id_persistido, email="A@a.com")


def test_admin_nao_rebaixa_a_si_mesmo(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    _novo(s, "b@a.com", Papel.ADMIN)
    with pytest.raises(OperacaoNaoPermitida) as e:
        AtualizarUsuario(build_uow(s)).executar(admin, admin.id_persistido, papel=Papel.GERENTE)
    assert e.value.motivo == "auto_rebaixamento"


def test_nao_rebaixa_o_ultimo_admin_ativo(s: Session) -> None:
    unico = _novo(s, "a@a.com", Papel.ADMIN)
    # ator é outro admin (ex.: já desativado/removido do banco): ainda assim o último fica.
    ator = Usuario(nome="X", email="x@a.com", senha_hash="x", papel=Papel.ADMIN, id=999)
    with pytest.raises(OperacaoNaoPermitida) as e:
        AtualizarUsuario(build_uow(s)).executar(ator, unico.id_persistido, papel=Papel.CAIXA)
    assert e.value.motivo == "ultimo_admin"


def test_rebaixa_admin_quando_ha_outro_ativo(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    outro = _novo(s, "b@a.com", Papel.ADMIN)
    r = AtualizarUsuario(build_uow(s)).executar(admin, outro.id_persistido, papel=Papel.GERENTE)
    assert r.papel is Papel.GERENTE


# --- desativar / reativar ----------------------------------------------------------------


def test_status_exige_admin(s: Session) -> None:
    gerente = _novo(s, "g@a.com", Papel.GERENTE)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(PermissaoNegada):
        AlterarStatusUsuario(build_uow(s)).executar(gerente, alvo.id_persistido, ativo=False)


def test_desativar_e_reativar_auditam(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    caso = AlterarStatusUsuario(build_uow(s))
    assert caso.executar(admin, alvo.id_persistido, ativo=False).ativo is False
    assert caso.executar(admin, alvo.id_persistido, ativo=True).ativo is True
    acoes = [(a.acao, a.detalhes) for a in _auditoria(s)]
    assert acoes == [
        ("desativar", {"ativo": {"antes": True, "depois": False}}),
        ("reativar", {"ativo": {"antes": False, "depois": True}}),
    ]


def test_status_repetido_e_idempotente_e_nao_audita(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    AlterarStatusUsuario(build_uow(s)).executar(admin, alvo.id_persistido, ativo=True)
    assert _auditoria(s) == []


def test_admin_nao_desativa_a_si_mesmo(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    _novo(s, "b@a.com", Papel.ADMIN)
    with pytest.raises(OperacaoNaoPermitida) as e:
        AlterarStatusUsuario(build_uow(s)).executar(admin, admin.id_persistido, ativo=False)
    assert e.value.motivo == "auto_desativacao"


def test_nao_desativa_o_ultimo_admin_ativo(s: Session) -> None:
    unico = _novo(s, "a@a.com", Papel.ADMIN)
    ator = Usuario(nome="X", email="x@a.com", senha_hash="x", papel=Papel.ADMIN, id=999)
    with pytest.raises(OperacaoNaoPermitida) as e:
        AlterarStatusUsuario(build_uow(s)).executar(ator, unico.id_persistido, ativo=False)
    assert e.value.motivo == "ultimo_admin"


def test_desativa_admin_quando_ha_outro_ativo(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    outro = _novo(s, "b@a.com", Papel.ADMIN)
    r = AlterarStatusUsuario(build_uow(s)).executar(admin, outro.id_persistido, ativo=False)
    assert r.ativo is False


def test_status_inexistente(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        AlterarStatusUsuario(build_uow(s)).executar(admin, 999, ativo=False)


# --- senhas ------------------------------------------------------------------------------


def _alterar_senha(
    s: Session, throttle: InMemoryLoginThrottle | None = None
) -> AlterarPropriaSenha:
    return AlterarPropriaSenha(
        build_uow(s), get_hasher(), throttle or InMemoryLoginThrottle(5, 300)
    )


def test_alterar_propria_senha_com_sucesso_sem_vazar_na_auditoria(s: Session) -> None:
    ator = _novo(s, "a@a.com", Papel.CAIXA)
    _alterar_senha(s).executar(ator, SENHA_ATUAL, SENHA_NOVA)
    salvo = SqlAlchemyUsuarioRepository(s).obter_por_id(ator.id_persistido)
    assert salvo is not None
    assert get_hasher().verify(salvo.senha_hash, SENHA_NOVA)
    assert not get_hasher().verify(salvo.senha_hash, SENHA_ATUAL)
    (log,) = _auditoria(s)
    assert log.acao == "alterar_senha" and log.detalhes == {"campos": ["senha"]}
    texto = str(log.detalhes)
    assert SENHA_NOVA not in texto and SENHA_ATUAL not in texto and "argon2" not in texto


def test_alterar_senha_com_atual_incorreta(s: Session) -> None:
    ator = _novo(s, "a@a.com", Papel.CAIXA)
    with pytest.raises(SenhaAtualIncorreta):
        _alterar_senha(s).executar(ator, "errada-errada", SENHA_NOVA)
    assert _auditoria(s) == []


def test_nova_senha_deve_ser_diferente_da_atual(s: Session) -> None:
    ator = _novo(s, "a@a.com", Papel.CAIXA)
    with pytest.raises(OperacaoNaoPermitida) as e:
        _alterar_senha(s).executar(ator, SENHA_ATUAL, SENHA_ATUAL)
    assert e.value.motivo == "senha_igual_a_atual"


def test_alterar_senha_aplica_throttle_contra_forca_bruta(s: Session) -> None:
    ator = _novo(s, "a@a.com", Papel.CAIXA)
    caso = _alterar_senha(s, InMemoryLoginThrottle(3, 300))
    for _ in range(3):
        with pytest.raises(SenhaAtualIncorreta):
            caso.executar(ator, "errada-errada", SENHA_NOVA)
    # bloqueado: nem a senha correta é aceita agora
    with pytest.raises(MuitasTentativas):
        caso.executar(ator, SENHA_ATUAL, SENHA_NOVA)


def test_redefinir_senha_exige_admin(s: Session) -> None:
    gerente = _novo(s, "g@a.com", Papel.GERENTE)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    with pytest.raises(PermissaoNegada):
        RedefinirSenha(build_uow(s), get_hasher()).executar(gerente, alvo.id_persistido, SENHA_NOVA)


def test_redefinir_senha_inexistente(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    with pytest.raises(UsuarioNaoEncontrado):
        RedefinirSenha(build_uow(s), get_hasher()).executar(admin, 999, SENHA_NOVA)


def test_redefinir_senha_nao_exige_a_atual_e_audita_sem_segredos(s: Session) -> None:
    admin = _novo(s, "a@a.com", Papel.ADMIN)
    alvo = _novo(s, "t@a.com", Papel.CAIXA)
    RedefinirSenha(build_uow(s), get_hasher()).executar(admin, alvo.id_persistido, SENHA_NOVA)
    salvo = SqlAlchemyUsuarioRepository(s).obter_por_id(alvo.id_persistido)
    assert salvo is not None and get_hasher().verify(salvo.senha_hash, SENHA_NOVA)
    (log,) = _auditoria(s)
    assert log.acao == "redefinir_senha" and log.entidade_id == str(alvo.id)
    assert log.detalhes == {"campos": ["senha"]}
