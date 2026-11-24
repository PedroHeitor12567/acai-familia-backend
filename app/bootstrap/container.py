"""Composition root: único lugar que conhece as implementações concretas das portas.

Routers e casos de uso nunca importam `infrastructure`; recebem o que este módulo monta.
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.seguranca.ports import LoginThrottle, PasswordHasher, TokenService
from app.application.unit_of_work import UnitOfWork
from app.application.usuarios.use_cases.autenticar_usuario import AutenticarUsuario
from app.application.usuarios.use_cases.criar_usuario import CriarUsuario
from app.application.usuarios.use_cases.renovar_token import RenovarToken
from app.config import Settings, get_settings
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


def build_uow(session: Session) -> UnitOfWork:
    return SqlAlchemyUnitOfWork(session)


def build_token_service(settings: Settings) -> TokenService:
    return JwtService(settings)


def build_criar_usuario(session: Session) -> CriarUsuario:
    return CriarUsuario(build_uow(session), get_hasher())


def abrir_sessao() -> Session:
    return get_session_factory()()


# --- providers do FastAPI -------------------------------------------------------------------


def get_db() -> Iterator[Session]:
    yield from get_session()


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_db)]


def get_uow(session: SessionDep) -> UnitOfWork:
    return build_uow(session)


def get_token_service(settings: SettingsDep) -> TokenService:
    return build_token_service(settings)


def get_throttle() -> LoginThrottle:
    return get_login_throttle()


UowDep = Annotated[UnitOfWork, Depends(get_uow)]
TokensDep = Annotated[TokenService, Depends(get_token_service)]


def get_autenticar_usuario(
    uow: UowDep, tokens: TokensDep, throttle: Annotated[LoginThrottle, Depends(get_throttle)]
) -> AutenticarUsuario:
    return AutenticarUsuario(uow, get_hasher(), tokens, throttle)


def get_renovar_token(uow: UowDep, tokens: TokensDep) -> RenovarToken:
    return RenovarToken(uow, tokens)


def get_criar_usuario(uow: UowDep) -> CriarUsuario:
    return CriarUsuario(uow, get_hasher())
