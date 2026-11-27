"""Composition root: único lugar que conhece as implementações concretas das portas.

Routers e casos de uso nunca importam `infrastructure`; recebem o que este módulo monta.
"""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated, TypeVar

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dashboard.ports import DashboardQueries
from app.application.seguranca.ports import LoginThrottle, PasswordHasher, TokenService
from app.application.unit_of_work import UnitOfWork
from app.application.usuarios.use_cases.alterar_propria_senha import AlterarPropriaSenha
from app.application.usuarios.use_cases.alterar_status_usuario import AlterarStatusUsuario
from app.application.usuarios.use_cases.atualizar_usuario import AtualizarUsuario
from app.application.usuarios.use_cases.autenticar_usuario import AutenticarUsuario
from app.application.usuarios.use_cases.criar_usuario import CriarUsuario
from app.application.usuarios.use_cases.listar_usuarios import ListarUsuarios
from app.application.usuarios.use_cases.obter_usuario import ObterUsuario
from app.application.usuarios.use_cases.redefinir_senha import RedefinirSenha
from app.application.usuarios.use_cases.renovar_token import RenovarToken
from app.config import Settings, get_settings
from app.domain.financeiro.regras import data_local
from app.infrastructure.persistence.dashboard_queries import SqlAlchemyDashboardQueries
from app.infrastructure.persistence.session import get_session, get_session_factory
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.hashing import Argon2Hasher
from app.infrastructure.security.jwt_service import JwtService
from app.infrastructure.security.rate_limit import InMemoryLoginThrottle

# --- singletons ----------------------------------------------------------------------------


@lru_cache
def get_hasher() -> PasswordHasher:
    return Argon2Hasher()


@lru_cache
def get_login_throttle() -> InMemoryLoginThrottle:
    s = get_settings()
    return InMemoryLoginThrottle(s.login_max_attempts, s.login_lockout_seconds)


# --- construtores puros (usáveis fora do FastAPI: scripts, workers, testes) -----------------


def build_uow(session: AsyncSession) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def build_dashboard_queries(session: AsyncSession, fuso: str) -> DashboardQueries:
    return SqlAlchemyDashboardQueries(session, fuso)


def build_token_service(settings: Settings) -> TokenService:
    return JwtService(settings)


def build_criar_usuario(session: AsyncSession) -> CriarUsuario:
    return CriarUsuario(build_uow(session), get_hasher())


def abrir_sessao() -> AsyncSession:
    return get_session_factory()()


# --- providers do FastAPI -------------------------------------------------------------------


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_uow(session: SessionDep) -> UnitOfWork:
    return build_uow(session)


def get_token_service(settings: SettingsDep) -> TokenService:
    return build_token_service(settings)


def get_throttle() -> LoginThrottle:
    return get_login_throttle()


def get_hoje(settings: SettingsDep) -> date:
    return data_local(datetime.now(UTC), settings.timezone)


def get_dashboard_queries(session: SessionDep, settings: SettingsDep) -> DashboardQueries:
    """Consultas de leitura do dashboard: a mesma sessão da requisição, sem UoW de escrita."""
    return build_dashboard_queries(session, settings.timezone)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]
DashboardQueriesDep = Annotated[DashboardQueries, Depends(get_dashboard_queries)]
TokensDep = Annotated[TokenService, Depends(get_token_service)]

_Caso = TypeVar("_Caso")


def caso_de_uso(caso: Callable[[UnitOfWork], _Caso]) -> Callable[[UowDep], _Caso]:
    """Provider FastAPI de um caso de uso que só depende da UoW (cardápio e estoque)."""

    def provider(uow: UowDep) -> _Caso:
        return caso(uow)

    return provider


def consulta_de_uso(
    caso: Callable[[DashboardQueries], _Caso],
) -> Callable[[DashboardQueriesDep], _Caso]:
    """Provider FastAPI de um caso de uso de leitura do dashboard."""

    def provider(queries: DashboardQueriesDep) -> _Caso:
        return caso(queries)

    return provider


def get_autenticar_usuario(
    uow: UowDep, tokens: TokensDep, throttle: Annotated[LoginThrottle, Depends(get_throttle)]
) -> AutenticarUsuario:
    return AutenticarUsuario(uow, get_hasher(), tokens, throttle)


def get_renovar_token(uow: UowDep, tokens: TokensDep) -> RenovarToken:
    return RenovarToken(uow, tokens)


def get_criar_usuario(uow: UowDep) -> CriarUsuario:
    return CriarUsuario(uow, get_hasher())


def get_listar_usuarios(uow: UowDep) -> ListarUsuarios:
    return ListarUsuarios(uow)


def get_obter_usuario(uow: UowDep) -> ObterUsuario:
    return ObterUsuario(uow)


def get_atualizar_usuario(uow: UowDep) -> AtualizarUsuario:
    return AtualizarUsuario(uow)


def get_alterar_status_usuario(uow: UowDep) -> AlterarStatusUsuario:
    return AlterarStatusUsuario(uow)


def get_alterar_propria_senha(
    uow: UowDep, throttle: Annotated[LoginThrottle, Depends(get_throttle)]
) -> AlterarPropriaSenha:
    return AlterarPropriaSenha(uow, get_hasher(), throttle)


def get_redefinir_senha(uow: UowDep) -> RedefinirSenha:
    return RedefinirSenha(uow, get_hasher())
