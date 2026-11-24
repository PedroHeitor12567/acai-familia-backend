from app.application.seguranca.ports import LoginThrottle, PasswordHasher, TokenService
from app.application.unit_of_work import UnitOfWork
from app.application.usuarios.dto import TokenPar
from app.domain.exceptions import CredenciaisInvalidas


class AutenticarUsuario:
    def __init__(
        self,
        uow: UnitOfWork,
        hasher: PasswordHasher,
        tokens: TokenService,
        throttle: LoginThrottle,
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._tokens = tokens
        self._throttle = throttle

    async def executar(self, email: str, senha: str, origem: str) -> TokenPar:
        email = email.lower()
        chave = f"{origem}:{email}"
        self._throttle.verificar(chave)
        try:
            par = await self._autenticar(email, senha)
        except CredenciaisInvalidas:
            self._throttle.registrar_falha(chave)
            raise
        self._throttle.zerar(chave)
        return par

    async def _autenticar(self, email: str, senha: str) -> TokenPar:
        usuario = await self._uow.usuarios.obter_por_email(email)
        if usuario is None:
            await self._hasher.verify_dummy()  # evita enumeração de usuários por tempo de resposta
            raise CredenciaisInvalidas
        if not usuario.ativo or not await self._hasher.verify(usuario.senha_hash, senha):
            raise CredenciaisInvalidas
        return TokenPar(
            access_token=self._tokens.criar_access(usuario.id_persistido, usuario.papel),
            refresh_token=self._tokens.criar_refresh(usuario.id_persistido),
        )
