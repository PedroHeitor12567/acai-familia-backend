from datetime import UTC, datetime
from decimal import Decimal

from app.application.caixa.use_cases.sessoes import detalhar_sessao
from app.application.shared.permissoes import exigir_operador_caixa
from app.application.unit_of_work import UnitOfWork
from app.domain.caixa.entities import MovimentoCaixa, TipoMovimento
from app.domain.caixa.regras import exigir_aberta, validar_motivo_movimento, validar_sangria
from app.domain.exceptions import SessaoCaixaNaoEncontrada
from app.domain.shared import validar_valor_monetario
from app.domain.usuarios.entities import Usuario


class RegistrarMovimento:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        sessao_id: int,
        tipo: TipoMovimento,
        valor: Decimal,
        motivo: str,
    ) -> MovimentoCaixa:
        exigir_operador_caixa(ator)
        valor = validar_valor_monetario(valor)
        motivo = validar_motivo_movimento(motivo)
        try:
            sessao = await self._uow.caixa.obter_sessao(sessao_id, para_atualizar=True)
            if sessao is None:
                raise SessaoCaixaNaoEncontrada
            exigir_aberta(sessao)
            if tipo is TipoMovimento.SANGRIA:
                saldo = (await detalhar_sessao(self._uow, sessao)).saldo_dinheiro
                validar_sangria(saldo, valor)
            movimento = await self._uow.caixa.adicionar_movimento(
                MovimentoCaixa(
                    sessao_id=sessao_id,
                    tipo=tipo,
                    valor=valor,
                    motivo=motivo,
                    criado_por_id=ator.id_persistido,
                    criado_em=datetime.now(UTC),
                )
            )
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                str(tipo),
                "caixa_sessao",
                str(sessao_id),
                {"valor": str(valor), "motivo": motivo},
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return movimento
