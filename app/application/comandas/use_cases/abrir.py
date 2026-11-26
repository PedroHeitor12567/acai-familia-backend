from datetime import UTC, datetime

from app.application.shared.permissoes import exigir_operador_comanda
from app.application.unit_of_work import UnitOfWork
from app.domain.comandas.entities import Comanda, OrigemComanda
from app.domain.comandas.regras import (
    MAX_CLIENTE_CONTATO,
    validar_cliente_nome,
    validar_observacao,
    validar_texto_opcional,
)
from app.domain.usuarios.entities import Usuario


class AbrirComanda:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        cliente_nome: str,
        origem: OrigemComanda = OrigemComanda.BALCAO,
        cliente_contato: str | None = None,
        observacao: str | None = None,
    ) -> Comanda:
        exigir_operador_comanda(ator)
        nova = Comanda(
            cliente_nome=validar_cliente_nome(cliente_nome),
            origem=origem,
            cliente_contato=validar_texto_opcional(
                cliente_contato, MAX_CLIENTE_CONTATO, "cliente_contato_invalido"
            ),
            observacao=validar_observacao(observacao),
            aberta_por_id=ator.id_persistido,
            aberta_em=datetime.now(UTC),
        )
        try:
            comanda = await self._uow.comandas.adicionar(nova)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "abrir",
                "comanda",
                str(comanda.id),
                {"cliente_nome": comanda.cliente_nome, "origem": str(comanda.origem)},
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return comanda
