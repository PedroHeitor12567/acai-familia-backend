import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "chave-de-teste-com-mais-de-trinta-e-dois-caracteres"
os.environ["ENVIRONMENT"] = "test"

from collections.abc import AsyncIterator, Awaitable, Callable  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.bootstrap.container import get_db, get_hasher, get_login_throttle  # noqa: E402
from app.domain.usuarios.entities import Papel, Usuario  # noqa: E402
from app.infrastructure.persistence.registry import Base  # noqa: E402
from app.infrastructure.persistence.usuarios.repository import (  # noqa: E402
    SqlAlchemyUsuarioRepository,
)
from app.main import create_app  # noqa: E402

SENHA = "senha-forte-123"

# (email, papel) -> cria o usuário com a senha `SENHA`; ver a fixture `criar_usuario`.
CriarUsuarioFn = Callable[[str, Papel], Awaitable[None]]
# (email, papel) -> {"Authorization": "Bearer ..."}; ver a fixture `auth_headers`.
AuthHeaders = Callable[[str, Papel], Awaitable[dict[str, str]]]


@pytest.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # SQLite só nos testes unitários/de API; produção e migrations usam PostgreSQL.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    get_login_throttle().zerar_tudo()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def criar_usuario(factory: async_sessionmaker[AsyncSession]) -> CriarUsuarioFn:
    async def _criar(email: str, papel: Papel) -> None:
        async with factory() as s:
            await SqlAlchemyUsuarioRepository(s).adicionar(
                Usuario(
                    nome="Teste",
                    email=email,
                    senha_hash=await get_hasher().hash(SENHA),
                    papel=papel,
                )
            )
            await s.commit()

    return _criar


@pytest.fixture
def auth_headers(client: AsyncClient, criar_usuario: CriarUsuarioFn) -> AuthHeaders:
    """Cria o usuário (senha `SENHA`), faz login e devolve o header `Authorization`."""

    async def _headers(email: str, papel: Papel) -> dict[str, str]:
        await criar_usuario(email, papel)
        r = await client.post("/auth/login", json={"email": email, "senha": SENHA})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    return _headers


@pytest.fixture
async def pg_session() -> AsyncIterator[AsyncSession]:
    """Sessão em PostgreSQL real (schema já migrado pelo Alembic), isolada por rollback."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL não definida")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            # create_savepoint: commits feitos pelo código testado viram savepoints e o
            # rollback final da transação externa desfaz tudo.
            session = AsyncSession(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def pg_client(pg_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """API completa sobre o PostgreSQL migrado pelo Alembic (sem `create_all`).

    Todas as requisições usam a `pg_session`, então o que o teste grava some no rollback final.
    """
    app = create_app()

    async def _db() -> AsyncIterator[AsyncSession]:
        yield pg_session

    app.dependency_overrides[get_db] = _db
    get_login_throttle().zerar_tudo()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
