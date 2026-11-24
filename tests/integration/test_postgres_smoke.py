import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository

pytestmark = pytest.mark.postgres


async def test_pg_session_grava_e_le_usuario(pg_session: AsyncSession) -> None:
    repo = SqlAlchemyUsuarioRepository(pg_session)

    criado = await repo.adicionar(
        Usuario(nome="Fumaça", email="fumaca@pg.example.com", senha_hash="x", papel=Papel.ATENDENTE)
    )
    await pg_session.commit()  # vira savepoint; o rollback da fixture desfaz

    lido = await repo.obter_por_email("fumaca@pg.example.com")
    assert lido is not None
    assert lido.id == criado.id
    assert lido.papel is Papel.ATENDENTE


async def test_pg_session_isola_testes_e_usa_postgresql(pg_session: AsyncSession) -> None:
    assert pg_session.get_bind().dialect.name == "postgresql"
    # o usuário do teste anterior foi desfeito pelo rollback da fixture
    existe = await pg_session.scalar(
        text("select count(*) from usuarios where email = 'fumaca@pg.example.com'")
    )
    assert existe == 0
