from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.application.financeiro.ports import FiltrosLancamento
from app.application.shared.permissoes import exigir_gestor
from app.application.unit_of_work import UnitOfWork
from app.domain.exceptions import (
    CategoriaFinanceiraNaoEncontrada,
    LancamentoNaoEncontrado,
)
from app.domain.financeiro.entities import (
    Baixa,
    CategoriaFinanceira,
    Lancamento,
    StatusLancamento,
    TipoLancamento,
)
from app.domain.financeiro.regras import (
    MAX_CONTRAPARTE,
    MAX_MOTIVO,
    MAX_OBSERVACAO,
    exigir_pendente,
    validar_categoria,
    validar_descricao,
    validar_texto_opcional,
    validar_valor_lancamento,
)
from app.domain.usuarios.entities import Usuario


@dataclass(frozen=True)
class AlteracaoLancamento:
    descricao: str | None = None
    valor: Decimal | None = None
    vencimento: date | None = None
    categoria_id: int | None = None
    contraparte: str | None = None
    observacao: str | None = None


async def _categoria(uow: UnitOfWork, categoria_id: int) -> CategoriaFinanceira:
    categoria = await uow.financeiro.obter_categoria(categoria_id)
    if categoria is None:
        raise CategoriaFinanceiraNaoEncontrada
    return categoria


def _dados_baixa(baixa: Baixa) -> dict[str, str]:
    return {"data_pagamento": baixa.data_pagamento.isoformat(), "forma": str(baixa.forma)}


class CriarLancamento:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self,
        ator: Usuario,
        tipo: TipoLancamento,
        descricao: str,
        valor: Decimal,
        vencimento: date,
        categoria_id: int,
        contraparte: str | None = None,
        observacao: str | None = None,
        baixa: Baixa | None = None,
    ) -> Lancamento:
        exigir_gestor(ator)
        descricao = validar_descricao(descricao)
        valor = validar_valor_lancamento(valor)
        contraparte = validar_texto_opcional(contraparte, MAX_CONTRAPARTE, "contraparte_invalida")
        observacao = validar_texto_opcional(observacao, MAX_OBSERVACAO, "observacao_invalida")
        try:
            validar_categoria(tipo, await _categoria(self._uow, categoria_id))
            novo = Lancamento(
                tipo=tipo,
                descricao=descricao,
                valor=valor,
                vencimento=vencimento,
                categoria_id=categoria_id,
                criado_por_id=ator.id_persistido,
                contraparte=contraparte,
                observacao=observacao,
            )
            if baixa is not None:
                novo.status = StatusLancamento.PAGO
                novo.data_pagamento, novo.forma_pagamento = baixa.data_pagamento, baixa.forma
                novo.baixado_por_id = ator.id_persistido
            lancamento = await self._uow.financeiro.adicionar_lancamento(novo)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "criar",
                "lancamento",
                str(lancamento.id),
                {
                    "tipo": str(tipo),
                    "descricao": descricao,
                    "valor": str(valor),
                    "vencimento": vencimento.isoformat(),
                    "categoria_id": categoria_id,
                    "baixa": None if baixa is None else _dados_baixa(baixa),
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return lancamento


class ObterLancamento:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, lancamento_id: int) -> Lancamento:
        exigir_gestor(ator)
        lancamento = await self._uow.financeiro.obter_lancamento(lancamento_id)
        if lancamento is None:
            raise LancamentoNaoEncontrado
        return lancamento


class ListarLancamentos:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, filtros: FiltrosLancamento, limit: int, offset: int
    ) -> tuple[list[Lancamento], int]:
        exigir_gestor(ator)
        return await self._uow.financeiro.listar_lancamentos(filtros, limit, offset)


class AtualizarLancamento:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, lancamento_id: int, alteracao: AlteracaoLancamento
    ) -> Lancamento:
        exigir_gestor(ator)
        descricao = None if alteracao.descricao is None else validar_descricao(alteracao.descricao)
        valor = None if alteracao.valor is None else validar_valor_lancamento(alteracao.valor)
        try:
            lancamento = await self._uow.financeiro.obter_lancamento(
                lancamento_id, para_atualizar=True
            )
            if lancamento is None:
                raise LancamentoNaoEncontrado
            exigir_pendente(lancamento)
            mudancas: dict[str, object] = {}

            def registrar(campo: str, antes: object, depois: object) -> None:
                if antes != depois:
                    mudancas[campo] = {"antes": str(antes), "depois": str(depois)}

            if descricao is not None:
                registrar("descricao", lancamento.descricao, descricao)
                lancamento.descricao = descricao
            if valor is not None:
                registrar("valor", lancamento.valor, valor)
                lancamento.valor = valor
            if alteracao.vencimento is not None:
                registrar("vencimento", lancamento.vencimento, alteracao.vencimento)
                lancamento.vencimento = alteracao.vencimento
            if alteracao.categoria_id is not None and alteracao.categoria_id != (
                lancamento.categoria_id
            ):
                categoria = await _categoria(self._uow, alteracao.categoria_id)
                validar_categoria(lancamento.tipo, categoria)
                registrar("categoria_id", lancamento.categoria_id, alteracao.categoria_id)
                lancamento.categoria_id = alteracao.categoria_id
            if alteracao.contraparte is not None:
                nova = validar_texto_opcional(
                    alteracao.contraparte, MAX_CONTRAPARTE, "contraparte_invalida"
                )
                registrar("contraparte", lancamento.contraparte, nova)
                lancamento.contraparte = nova
            if alteracao.observacao is not None:
                nova = validar_texto_opcional(
                    alteracao.observacao, MAX_OBSERVACAO, "observacao_invalida"
                )
                registrar("observacao", lancamento.observacao, nova)
                lancamento.observacao = nova
            if not mudancas:
                return lancamento
            atualizado = await self._uow.financeiro.atualizar_lancamento(lancamento)
            await self._uow.auditoria.registrar(
                ator.id_persistido, "atualizar", "lancamento", str(lancamento_id), mudancas
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return atualizado


class BaixarLancamento:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, lancamento_id: int, baixa: Baixa) -> Lancamento:
        exigir_gestor(ator)
        try:
            lancamento = await self._uow.financeiro.obter_lancamento(
                lancamento_id, para_atualizar=True
            )
            if lancamento is None:
                raise LancamentoNaoEncontrado
            exigir_pendente(lancamento)
            lancamento.status = StatusLancamento.PAGO
            lancamento.data_pagamento, lancamento.forma_pagamento = (
                baixa.data_pagamento,
                baixa.forma,
            )
            lancamento.baixado_por_id = ator.id_persistido
            baixado = await self._uow.financeiro.atualizar_lancamento(lancamento)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "baixar",
                "lancamento",
                str(lancamento_id),
                {"valor": str(lancamento.valor), **_dados_baixa(baixa)},
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return baixado


class CancelarLancamento:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(
        self, ator: Usuario, lancamento_id: int, motivo: str | None = None
    ) -> Lancamento:
        exigir_gestor(ator)
        motivo = validar_texto_opcional(motivo, MAX_MOTIVO, "motivo_invalido")
        try:
            lancamento = await self._uow.financeiro.obter_lancamento(
                lancamento_id, para_atualizar=True
            )
            if lancamento is None:
                raise LancamentoNaoEncontrado
            exigir_pendente(lancamento)
            lancamento.status = StatusLancamento.CANCELADO
            cancelado = await self._uow.financeiro.atualizar_lancamento(lancamento)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "cancelar",
                "lancamento",
                str(lancamento_id),
                {"motivo": motivo, "valor": str(lancamento.valor)},
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        return cancelado
