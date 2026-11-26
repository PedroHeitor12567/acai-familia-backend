from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.application.comandas.ports import FiltrosComanda
from app.domain.comandas.entities import OrigemComanda, StatusComanda
from app.interfaces.http.deps import (
    AbrirComandaDep,
    AdicionarItemDep,
    AtualizarItemDep,
    CancelarComandaDep,
    FechamentoComandaDep,
    FecharComandaDep,
    ListarComandasDep,
    ObterComandaDep,
    OperadorComandaDep,
    RemoverItemDep,
)
from app.interfaces.http.schemas.comandas import (
    CancelarIn,
    ComandaIn,
    ComandaOut,
    ComandaResumoOut,
    FechamentoOut,
    ItemIn,
    ItemUpdateIn,
    PaginaComandasOut,
)

router = APIRouter(prefix="/comandas", tags=["comandas"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("", response_model=ComandaOut, status_code=status.HTTP_201_CREATED)
async def abrir_comanda(
    body: ComandaIn, ator: OperadorComandaDep, caso: AbrirComandaDep
) -> ComandaOut:
    comanda = await caso.executar(
        ator, body.cliente_nome, body.origem, body.cliente_contato, body.observacao
    )
    return ComandaOut.de_entidade(comanda)


@router.get("", response_model=PaginaComandasOut)
async def listar_comandas(
    ator: OperadorComandaDep,
    caso: ListarComandasDep,
    status: StatusComanda | None = None,
    origem: OrigemComanda | None = None,
    cliente: Annotated[str | None, Query(max_length=120, description="Busca no nome")] = None,
    aberta_por_id: int | None = None,
    de: Annotated[datetime | None, Query(description="aberta_em >= de (inclusivo)")] = None,
    ate: Annotated[datetime | None, Query(description="aberta_em <= ate (inclusivo)")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaComandasOut:
    """Abertas: as mais antigas primeiro. Demais: da mais recente para a mais antiga."""
    filtros = FiltrosComanda(status, origem, cliente, aberta_por_id, de, ate)
    itens, total = await caso.executar(ator, filtros, limit, offset)
    return PaginaComandasOut(
        itens=[ComandaResumoOut.de_entidade(c) for c in itens],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{comanda_id}", response_model=ComandaOut)
async def obter_comanda(
    comanda_id: int, ator: OperadorComandaDep, caso: ObterComandaDep
) -> ComandaOut:
    return ComandaOut.de_entidade(await caso.executar(ator, comanda_id))


@router.post("/{comanda_id}/itens", response_model=ComandaOut, status_code=status.HTTP_201_CREATED)
async def adicionar_item(
    comanda_id: int, body: ItemIn, ator: OperadorComandaDep, caso: AdicionarItemDep
) -> ComandaOut:
    """Lança o item com o preço do cardápio de agora (congelado) e devolve a comanda."""
    comanda = await caso.executar(
        ator,
        comanda_id,
        body.produto_id,
        body.tamanho_id,
        body.quantidade,
        [a.para_pedido() for a in body.adicionais],
        body.observacao,
    )
    return ComandaOut.de_entidade(comanda)


@router.patch("/{comanda_id}/itens/{item_id}", response_model=ComandaOut)
async def atualizar_item(
    comanda_id: int,
    item_id: int,
    body: ItemUpdateIn,
    ator: OperadorComandaDep,
    caso: AtualizarItemDep,
) -> ComandaOut:
    comanda = await caso.executar(ator, comanda_id, item_id, body.quantidade, body.observacao)
    return ComandaOut.de_entidade(comanda)


@router.delete("/{comanda_id}/itens/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_item(
    comanda_id: int, item_id: int, ator: OperadorComandaDep, caso: RemoverItemDep
) -> Response:
    await caso.executar(ator, comanda_id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{comanda_id}/fechar", response_model=FechamentoOut)
async def fechar_comanda(
    comanda_id: int, ator: FechamentoComandaDep, caso: FecharComandaDep
) -> FechamentoOut:
    """Baixa o estoque pela ficha técnica e fecha, tudo na mesma transação. Falta de qualquer
    insumo (409) não baixa nada e a comanda continua aberta."""
    return FechamentoOut.de_resultado(await caso.executar(ator, comanda_id))


@router.post("/{comanda_id}/cancelar", response_model=ComandaOut)
async def cancelar_comanda(
    comanda_id: int,
    ator: FechamentoComandaDep,
    caso: CancelarComandaDep,
    body: CancelarIn | None = None,
) -> ComandaOut:
    """Só comanda aberta. Não mexe no estoque (a baixa só acontece no fechamento)."""
    motivo = body.motivo if body else None
    return ComandaOut.de_entidade(await caso.executar(ator, comanda_id, motivo))
