from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.application.estoque.ports import FiltrosInsumo, FiltrosMovimentacao
from app.domain.estoque.entities import ItemFichaTecnica, TipoMovimentacao
from app.interfaces.http.deps import (
    AlterarStatusInsumoDep,
    AtualizarInsumoDep,
    CriarInsumoDep,
    DefinirFichaAdicionalDep,
    DefinirFichaTecnicaDep,
    GestorDep,
    ListarAlertasEstoqueDep,
    ListarInsumosDep,
    ListarMovimentacoesDep,
    MovimentarEstoqueDep,
    ObterFichaAdicionalDep,
    ObterFichaTecnicaDep,
    ObterInsumoDep,
)
from app.interfaces.http.schemas.estoque import (
    FichaTecnicaIn,
    FichaTecnicaOut,
    InsumoCreateIn,
    InsumoOut,
    InsumoUpdateIn,
    MovimentacaoIn,
    MovimentacaoOut,
    PaginaInsumosOut,
    PaginaMovimentacoesOut,
)

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

# Todo o estoque é restrito a admin e gerente.
insumos = APIRouter(prefix="/estoque", tags=["estoque"])
fichas = APIRouter(tags=["ficha técnica"])
routers = (insumos, fichas)


@insumos.post("/insumos", response_model=InsumoOut, status_code=status.HTTP_201_CREATED)
async def criar_insumo(body: InsumoCreateIn, ator: GestorDep, caso: CriarInsumoDep) -> InsumoOut:
    novo = await caso.executar(ator, body.nome, body.unidade, body.estoque_minimo)
    return InsumoOut.de_entidade(novo)


@insumos.get("/insumos", response_model=PaginaInsumosOut)
async def listar_insumos(
    ator: GestorDep,
    caso: ListarInsumosDep,
    abaixo_do_minimo: bool | None = None,
    ativo: bool | None = None,
    q: Annotated[str | None, Query(max_length=120, description="Busca no nome")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaInsumosOut:
    itens, total = await caso.executar(
        ator, FiltrosInsumo(ativo=ativo, abaixo_do_minimo=abaixo_do_minimo, q=q), limit, offset
    )
    return PaginaInsumosOut(
        itens=[InsumoOut.de_entidade(i) for i in itens], total=total, limit=limit, offset=offset
    )


@insumos.get("/alertas", response_model=PaginaInsumosOut)
async def alertas_de_estoque(
    ator: GestorDep, caso: ListarAlertasEstoqueDep, limit: Limit = 100, offset: Offset = 0
) -> PaginaInsumosOut:
    """Insumos ativos com saldo menor ou igual ao mínimo."""
    itens, total = await caso.executar(ator, limit, offset)
    return PaginaInsumosOut(
        itens=[InsumoOut.de_entidade(i) for i in itens], total=total, limit=limit, offset=offset
    )


@insumos.get("/insumos/{insumo_id}", response_model=InsumoOut)
async def obter_insumo(insumo_id: int, ator: GestorDep, caso: ObterInsumoDep) -> InsumoOut:
    return InsumoOut.de_entidade(await caso.executar(ator, insumo_id))


@insumos.patch("/insumos/{insumo_id}", response_model=InsumoOut)
async def atualizar_insumo(
    insumo_id: int, body: InsumoUpdateIn, ator: GestorDep, caso: AtualizarInsumoDep
) -> InsumoOut:
    atualizado = await caso.executar(ator, insumo_id, body.nome, body.estoque_minimo)
    return InsumoOut.de_entidade(atualizado)


@insumos.post("/insumos/{insumo_id}/desativar", response_model=InsumoOut)
async def desativar_insumo(
    insumo_id: int, ator: GestorDep, caso: AlterarStatusInsumoDep
) -> InsumoOut:
    return InsumoOut.de_entidade(await caso.executar(ator, insumo_id, ativo=False))


@insumos.post("/insumos/{insumo_id}/ativar", response_model=InsumoOut)
async def ativar_insumo(insumo_id: int, ator: GestorDep, caso: AlterarStatusInsumoDep) -> InsumoOut:
    return InsumoOut.de_entidade(await caso.executar(ator, insumo_id, ativo=True))


@insumos.post(
    "/insumos/{insumo_id}/movimentacoes",
    response_model=MovimentacaoOut,
    status_code=status.HTTP_201_CREATED,
)
async def movimentar(
    insumo_id: int, body: MovimentacaoIn, ator: GestorDep, caso: MovimentarEstoqueDep
) -> MovimentacaoOut:
    """`entrada` soma, `saida` subtrai e `ajuste` define o saldo (`quantidade` = contagem)."""
    mov = await caso.executar(ator, insumo_id, body.tipo, body.quantidade, body.motivo)
    return MovimentacaoOut.de_entidade(mov)


@insumos.get("/insumos/{insumo_id}/movimentacoes", response_model=PaginaMovimentacoesOut)
async def listar_movimentacoes(
    insumo_id: int,
    ator: GestorDep,
    caso: ListarMovimentacoesDep,
    tipo: TipoMovimentacao | None = None,
    de: datetime | None = None,
    ate: datetime | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaMovimentacoesOut:
    itens, total = await caso.executar(
        ator, insumo_id, FiltrosMovimentacao(tipo=tipo, de=de, ate=ate), limit, offset
    )
    return PaginaMovimentacoesOut(
        itens=[MovimentacaoOut.de_entidade(m) for m in itens],
        total=total,
        limit=limit,
        offset=offset,
    )


def _itens(body: FichaTecnicaIn) -> list[ItemFichaTecnica]:
    return [ItemFichaTecnica(i.insumo_id, Decimal(i.quantidade)) for i in body.itens]


@fichas.get(
    "/produtos/{produto_id}/tamanhos/{tamanho_id}/ficha-tecnica", response_model=FichaTecnicaOut
)
async def obter_ficha_tecnica(
    produto_id: int, tamanho_id: int, ator: GestorDep, caso: ObterFichaTecnicaDep
) -> FichaTecnicaOut:
    return FichaTecnicaOut.de_itens(await caso.executar(ator, produto_id, tamanho_id))


@fichas.put(
    "/produtos/{produto_id}/tamanhos/{tamanho_id}/ficha-tecnica", response_model=FichaTecnicaOut
)
async def definir_ficha_tecnica(
    produto_id: int,
    tamanho_id: int,
    body: FichaTecnicaIn,
    ator: GestorDep,
    caso: DefinirFichaTecnicaDep,
) -> FichaTecnicaOut:
    """Substitui a receita inteira (atômico). Lista vazia limpa a ficha."""
    return FichaTecnicaOut.de_itens(await caso.executar(ator, produto_id, tamanho_id, _itens(body)))


@fichas.get("/adicionais/{adicional_id}/ficha-tecnica", response_model=FichaTecnicaOut)
async def obter_ficha_adicional(
    adicional_id: int, ator: GestorDep, caso: ObterFichaAdicionalDep
) -> FichaTecnicaOut:
    return FichaTecnicaOut.de_itens(await caso.executar(ator, adicional_id))


@fichas.put("/adicionais/{adicional_id}/ficha-tecnica", response_model=FichaTecnicaOut)
async def definir_ficha_adicional(
    adicional_id: int, body: FichaTecnicaIn, ator: GestorDep, caso: DefinirFichaAdicionalDep
) -> FichaTecnicaOut:
    return FichaTecnicaOut.de_itens(await caso.executar(ator, adicional_id, _itens(body)))
