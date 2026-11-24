import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository

pytestmark = pytest.mark.postgres


def test_pg_session_grava_e_le_usuario(pg_session: Session) -> None:
    repo = SqlAlchemyUsuarioRepository(pg_session)

    criado = repo.adicionar(
        Usuario(nome="Fumaça", email="fumaca@pg.test", senha_hash="x", papel=Papel.ATENDENTE)
    )
    pg_session.commit()  # vira savepoint; o rollback da fixture desfaz

    lido = repo.obter_por_email("fumaca@pg.test")
    assert lido is not None
    assert lido.id == criado.id
    assert lido.papel is Papel.ATENDENTE


def test_pg_session_isola_testes_e_usa_postgresql(pg_session: Session) -> None:
    assert pg_session.get_bind().dialect.name == "postgresql"
    # o usuário do teste anterior foi desfeito pelo rollback da fixture
    existe = pg_session.scalar(text("select count(*) from usuarios where email = 'fumaca@pg.test'"))
    assert existe == 0
