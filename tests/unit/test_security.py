import pytest

from app.config import get_settings
from app.domain.exceptions import TokenInvalido
from app.domain.usuarios.entities import Papel
from app.infrastructure.security.hashing import Argon2Hasher
from app.infrastructure.security.jwt_service import JwtService


def test_hash_e_verificacao() -> None:
    h = Argon2Hasher()
    hashed = h.hash("segredo-123")
    assert hashed != "segredo-123"
    assert h.verify(hashed, "segredo-123")
    assert not h.verify(hashed, "outra")


def test_jwt_tipo_incorreto_rejeitado() -> None:
    svc = JwtService(get_settings())
    refresh = svc.criar_refresh(1)
    with pytest.raises(TokenInvalido):
        svc.decodificar(refresh, "access")
    claims = svc.decodificar(svc.criar_access(1, Papel.CAIXA), "access")
    assert claims.usuario_id == 1
    assert claims.papel is Papel.CAIXA


def test_jwt_adulterado_rejeitado() -> None:
    svc = JwtService(get_settings())
    with pytest.raises(TokenInvalido):
        svc.decodificar(svc.criar_access(1, Papel.ADMIN)[:-3] + "abc", "access")
