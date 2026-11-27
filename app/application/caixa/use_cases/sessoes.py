from datetime import UTC, datetime
from decimal import Decimal

from app.application.caixa.dto import DetalheSessao
from app.application.caixa.ports import FiltrosSessao
from app.application.shared.permissoes import exigir_operador_caixa
from app.application.unit_of_work import UnitOfWork
from app.domain.caixa.entities import (
    FormaPagamento,
    SessaoCaixa,
    StatusSessao,
    TipoMovimento,
)
from app.domain.caixa.regras import (
    calcular_diferenca,
    exigir_aberta,
    exigir_justificativa,
    resumo_por_forma,
    validar_observacao,
    validar_valor_abertura,
    validar_valor_contado,
    valor_esperado,
)
from app.domain.exceptions import (
    NenhumaSessaoAberta,
    OperacaoNaoPermitida,
    SessaoCaixaNaoEncontrada,
)
from app.domain.usuarios.entities import Usuario


async def detalhar_sessao(uow: UnitOfWork, sessao: SessaoCaixa) -> DetalheSessao:
    movimentos = await uow.caixa.listar_movimentos(sessao.id_persistido)
    pagamentos = await uow.caixa.listar_pagamentos_da_sessao(sessao.id_persistido)
    resumo = resumo_por_forma(pagamentos)
    suprimentos = [m.valor for m in movimentos if m.tipo is TipoMovimento.SUPRIMENTO]
    sangrias = [m.valor for m in movimentos if m.tipo is TipoMovimento.SANGRIA]
    saldo = valor_esperado(
        sessao.valor_abertura, [resumo[FormaPagamento.DINHEIRO]], suprimentos, sangrias
    )
    return DetalheSessao(
        sessao=sessao,
        movimentos=movimentos,
        resumo_por_forma=resumo,
        saldo_dinheiro=sessao.valor_esperado if sessao.valor_esperado is not None else saldo,
        total_suprimentos=sum(suprimentos, start=Decimal("0.00")),
        total_sangrias=sum(sangrias, start=Decimal("0.00")),
    )


class AbrirCaixa:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, valor_abertura: Decimal, observacao: str | None = None
    ) -> SessaoCaixa:
        exigir_operador_caixa(ator)
        valor_abertura = validar_valor_abertura(valor_abertura)
        observacao = validar_observacao(observacao)
        try:
            if await self._uow.caixa.obter_sessao_aberta() is not None:
                raise OperacaoNaoPermitida("caixa_ja_aberto")
            sessao = await self._uow.caixa.adicionar_sessao(
                SessaoCaixa(
                    valor_abertura=valor_abertura,
                    aberta_por_id=ator.id_persistido,
                    aberta_em=datetime.now(UTC),
                    observacao=observacao,
                )
            )
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "abrir",
                "caixa_sessao",
                str(sessao.id),
                {"valor_abertura": str(valor_abertura), "observacao": observacao},
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return sessao


class ObterSessaoAtual:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario) -> DetalheSessao:
        exigir_operador_caixa(ator)
        sessao = await self._uow.caixa.obter_sessao_aberta()
        if sessao is None:
            raise NenhumaSessaoAberta
        return await detalhar_sessao(self._uow, sessao)


class ObterSessao:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, sessao_id: int) -> DetalheSessao:
        exigir_operador_caixa(ator)
        sessao = await self._uow.caixa.obter_sessao(sessao_id)
        if sessao is None:
            raise SessaoCaixaNaoEncontrada
        return await detalhar_sessao(self._uow, sessao)


class ListarSessoes:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, filtros: FiltrosSessao, limit: int, offset: int
    ) -> tuple[list[SessaoCaixa], int]:
        exigir_operador_caixa(ator)
        return await self._uow.caixa.listar_sessoes(filtros, limit, offset)


class FecharCaixa:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        sessao_id: int,
        valor_contado: Decimal,
        observacao: str | None = None,
    ) -> DetalheSessao:
        exigir_operador_caixa(ator)
        valor_contado = validar_valor_contado(valor_contado)
        observacao = validar_observacao(observacao)
        try:
            sessao = await self._uow.caixa.obter_sessao(sessao_id, para_atualizar=True)
            if sessao is None:
                raise SessaoCaixaNaoEncontrada
            exigir_aberta(sessao)
            esperado = (await detalhar_sessao(self._uow, sessao)).saldo_dinheiro
            diferenca = calcular_diferenca(valor_contado, esperado)
            exigir_justificativa(diferenca, observacao)

            sessao.status = StatusSessao.FECHADA
            sessao.fechada_por_id = ator.id_persistido
            sessao.fechada_em = datetime.now(UTC)
            sessao.valor_esperado, sessao.valor_contado = esperado, valor_contado
            sessao.diferenca = diferenca
            if observacao is not None:
                sessao.observacao = observacao
            await self._uow.caixa.marcar_sessao_fechada(sessao)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "fechar",
                "caixa_sessao",
                str(sessao_id),
                {
                    "valor_esperado": str(esperado),
                    "valor_contado": str(valor_contado),
                    "diferenca": str(diferenca),
                    "observacao": observacao,
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return await detalhar_sessao(self._uow, sessao)
