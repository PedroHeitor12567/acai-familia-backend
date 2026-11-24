from app.application.seguranca.ports import LoginThrottle, PasswordHasher
from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import OperacaoNaoPermitida, SenhaAtualIncorreta
from app.domain.usuarios.entities import Usuario


class AlterarPropriaSenha:
    def __init__(self, uow: UnitOfWork, hasher: PasswordHasher, throttle: LoginThrottle) -> None:
        self._uow = uow
        self._hasher = hasher
        self._throttle = throttle

    async def executar(self, ator: Usuario, senha_atual: str, nova_senha: str) -> None:
        # Mesmo limite do login: impede força bruta da senha atual com um token roubado.
        chave = f"alterar-senha:{ator.id_persistido}"
        self._throttle.verificar(chave)
        if not await self._hasher.verify(ator.senha_hash, senha_atual):
            self._throttle.registrar_falha(chave)
            raise SenhaAtualIncorreta
        self._throttle.zerar(chave)
        if nova_senha == senha_atual:
            raise OperacaoNaoPermitida("senha_igual_a_atual")

        ator.senha_hash = await self._hasher.hash(nova_senha)
        await self._uow.usuarios.atualizar(ator)
        # Nunca gravar senha nem hash: só registra que o campo mudou.
        await self._uow.auditoria.registrar(
            ator.id_persistido,
            "alterar_senha",
            "usuario",
            str(ator.id_persistido),
            {"campos": ["senha"]},
        )
        await self._uow.commit()
