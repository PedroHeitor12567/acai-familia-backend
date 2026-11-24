from app.application.seguranca.ports import TokenService
from app.application.unit_of_work import UnitOfWork
from app.application.usuarios.dto import TokenPar
from app.domain.exceptions import TokenInvalido


class RenovarToken:
    """Gera novo par de tokens a partir de um refresh token válido.

    TODO: rotação com revogação (guardar jti no banco/Redis) para invalidar o refresh antigo.
    """

    def __init__(self, uow: UnitOfWork, tokens: TokenService) -> None:
        self._uow = uow
        self._tokens = tokens

    async def executar(self, refresh_token: str) -> TokenPar:
        claims = self._tokens.decodificar(refresh_token, "refresh")
        usuario = await self._uow.usuarios.obter_por_id(claims.usuario_id)
        if usuario is None or not usuario.ativo:
            raise TokenInvalido
        return TokenPar(
            access_token=self._tokens.criar_access(usuario.id_persistido, usuario.papel),
            refresh_token=self._tokens.criar_refresh(usuario.id_persistido),
        )
