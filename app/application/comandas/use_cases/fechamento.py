from datetime import UTC, datetime

from app.application.comandas.dto import ResultadoFechamento
from app.application.shared.permissoes import exigir_fechamento_comanda
from app.application.unit_of_work import UnitOfWork
from app.domain.comandas.entities import Comanda
from app.domain.comandas.regras import (
    consumo_da_comanda,
    itens_sem_ficha,
    total_comanda,
    validar_cancelamento,
    validar_fechamento,
    validar_texto_opcional,
)
from app.domain.estoque.entities import ItemFichaTecnica
from app.domain.exceptions import (
    ComandaNaoEncontrada,
    EstoqueInsuficiente,
    EstoqueInsuficienteNoFechamento,
)
from app.domain.usuarios.entities import Usuario

MAX_MOTIVO = 255


class FecharComanda:
    """Fecha a comanda baixando o estoque na mesma transação: ou tudo é gravado, ou nada.

    Ordem de locks: comanda -> insumos em ids crescentes (a ordem fixa evita deadlock entre
    dois fechamentos que disputam os mesmos insumos). Um único `commit()` no fim. Quando a
    Fase 3 ligar o pagamento, ele entra aqui, antes do commit.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, comanda_id: int) -> ResultadoFechamento:
        exigir_fechamento_comanda(ator)
        try:
            resultado = await self._fechar(ator, comanda_id)
            await self._uow.commit()
        except Exception as erro:
            await self._uow.rollback()  # desfaz as baixas já feitas e solta os locks
            if isinstance(erro, EstoqueInsuficiente) and not isinstance(
                erro, EstoqueInsuficienteNoFechamento
            ):
                raise EstoqueInsuficienteNoFechamento(
                    erro.disponivel, erro.solicitado, erro.insumo_id, erro.insumo_nome
                ) from erro
            raise
        return resultado

    async def _fechar(self, ator: Usuario, comanda_id: int) -> ResultadoFechamento:
        uow = self._uow
        # 1-2. trava a comanda e confere o status já com o lock; recusa comanda vazia
        comanda = await uow.comandas.obter(comanda_id, para_atualizar=True)
        if comanda is None:
            raise ComandaNaoEncontrada
        validar_fechamento(comanda)

        # 3. consumo agregado da comanda inteira
        fichas_produto, fichas_adicional = await self._carregar_fichas(comanda)
        consumo = consumo_da_comanda(comanda.itens, fichas_produto, fichas_adicional)
        sem_ficha = itens_sem_ficha(comanda.itens, fichas_produto)

        # 4-5. baixa uma vez por insumo, em ordem crescente; a primeira falta aborta tudo
        for insumo_id in sorted(consumo):
            await uow.estoque.aplicar_saida(
                insumo_id, consumo[insumo_id], ator.id_persistido, motivo=f"comanda:{comanda_id}"
            )

        # 6. status, quem/quando e o snapshot do total
        total = total_comanda(comanda.itens)
        await uow.comandas.marcar_fechada(comanda_id, ator.id_persistido, datetime.now(UTC), total)

        # 7. auditoria
        await uow.auditoria.registrar(
            ator.id_persistido,
            "fechar",
            "comanda",
            str(comanda_id),
            {
                "total": str(total),
                "itens": len(comanda.itens),
                "consumo": {str(i): str(q) for i, q in sorted(consumo.items())},
                "itens_sem_ficha": sem_ficha,
            },
        )
        fechada = await uow.comandas.obter(comanda_id)
        if fechada is None:  # pragma: no cover - acabou de ser travada
            raise ComandaNaoEncontrada
        return ResultadoFechamento(fechada, consumo, sem_ficha)

    async def _carregar_fichas(
        self, comanda: Comanda
    ) -> tuple[dict[tuple[int, int], list[ItemFichaTecnica]], dict[int, list[ItemFichaTecnica]]]:
        fichas = self._uow.ficha_tecnica
        por_produto: dict[tuple[int, int], list[ItemFichaTecnica]] = {}
        por_adicional: dict[int, list[ItemFichaTecnica]] = {}
        for item in comanda.itens:
            chave = (item.produto_id, item.tamanho_id)
            if chave not in por_produto:
                por_produto[chave] = await fichas.obter_ficha_produto(*chave)
            for adicional in item.adicionais:
                if adicional.adicional_id not in por_adicional:
                    por_adicional[adicional.adicional_id] = await fichas.obter_ficha_adicional(
                        adicional.adicional_id
                    )
        return por_produto, por_adicional


class CancelarComanda:
    """`aberta -> cancelada`. Não mexe no estoque: a baixa só acontece no fechamento."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def executar(self, ator: Usuario, comanda_id: int, motivo: str | None = None) -> Comanda:
        exigir_fechamento_comanda(ator)
        motivo = validar_texto_opcional(motivo, MAX_MOTIVO, "motivo_invalido")
        try:
            comanda = await self._uow.comandas.obter(comanda_id, para_atualizar=True)
            if comanda is None:
                raise ComandaNaoEncontrada
            validar_cancelamento(comanda)
            await self._uow.comandas.marcar_cancelada(comanda_id)
            await self._uow.auditoria.registrar(
                ator.id_persistido,
                "cancelar",
                "comanda",
                str(comanda_id),
                {
                    "motivo": motivo,
                    "itens": len(comanda.itens),
                    "total": str(total_comanda(comanda.itens)),
                },
            )
            await self._uow.commit()
        except Exception:
            await self._uow.rollback()
            raise
        cancelada = await self._uow.comandas.obter(comanda_id)
        if cancelada is None:  # pragma: no cover
            raise ComandaNaoEncontrada
        return cancelada
