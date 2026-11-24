import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "chave-de-teste-com-mais-de-trinta-e-dois-caracteres"
os.environ["ENVIRONMENT"] = "test"

from collections.abc import Callable, Iterator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.bootstrap.container import get_db, get_hasher, get_login_throttle  # noqa: E402
from app.domain.usuarios.entities import Papel, Usuario  # noqa: E402
from app.infrastructure.persistence.registry import Base  # noqa: E402
from app.infrastructure.persistence.usuarios.repository import (  # noqa: E402
    SqlAlchemyUsuarioRepository,
)
from app.main import create_app  # noqa: E402

SENHA = "senha-forte-123"


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    # SQLite só nos testes unitários/de API; produção e migrations usam PostgreSQL.
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def _db() -> Iterator[Session]:
        with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    get_login_throttle().zerar_tudo()
    yield TestClient(app)


@pytest.fixture
def criar_usuario(factory: sessionmaker[Session]) -> Callable[[str, Papel], None]:
    def _criar(email: str, papel: Papel) -> None:
        with factory() as s:
            SqlAlchemyUsuarioRepository(s).adicionar(
                Usuario(nome="Teste", email=email, senha_hash=get_hasher().hash(SENHA), papel=papel)
            )
            s.commit()

    return _criar
