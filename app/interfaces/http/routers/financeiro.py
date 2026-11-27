from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.application.financeiro.ports import FiltrosLancamento
from app.domain.financeiro.entities import (
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)
from app.interfaces.http.deps import (
    AtualizarCategoriaFinanceiraDep,
    AtualizarLancamentoDep,
    BaixarLancamentoDep,
    CancelarLancamentoDep,
    CriarCategoriaFinanceiraDep,
    CriarLancamentoDep,
    GestorDep,
    HojeDep,
    ListarCategoriasFinanceirasDep,
    ListarLancamentosDep,
    ObterLancamentoDep,
)
from app.interfaces.http.schemas.financeiro import (
    BaixaIn,
    CancelarLancamentoIn,
    CategoriaIn,
    CategoriaOut,
    CategoriaUpdateIn,
    LancamentoIn,
    LancamentoOut,
    LancamentoUpdateIn,
    PaginaLancamentosOut,
)

router = APIRouter(prefix="/financeiro", tags=["financeiro"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("/categorias", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED)
async def criar_categoria(
    body: CategoriaIn, ator: GestorDep, caso: CriarCategoriaFinanceiraDep
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(ator, body.nome, body.tipo))


@router.get("/categorias", response_model=list[CategoriaOut])
async def listar_categorias(
    ator: GestorDep,
    caso: ListarCategoriasFinanceirasDep,
    tipo: TipoCategoria | None = None,
    ativo: bool | None = None,
) -> list[CategoriaOut]:
    return [CategoriaOut.de_entidade(c) for c in await caso.executar(ator, tipo, ativo)]


@router.patch("/categorias/{categoria_id}", response_model=CategoriaOut)
async def atualizar_categoria(
    categoria_id: int,
    body: CategoriaUpdateIn,
    ator: GestorDep,
    caso: AtualizarCategoriaFinanceiraDep,
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(ator, categoria_id, body.nome, body.ativo))


@router.post("/lancamentos", response_model=LancamentoOut, status_code=status.HTTP_201_CREATED)
async def criar_lancamento(
    body: LancamentoIn, ator: GestorDep, caso: CriarLancamentoDep, hoje: HojeDep
) -> LancamentoOut:
    lancamento = await caso.executar(
        ator,
        body.tipo,
        body.descricao,
        body.valor,
        body.vencimento,
        body.categoria_id,
        body.contraparte,
        body.observacao,
        body.baixa.para_baixa() if body.baixa else None,
    )
    return LancamentoOut.de_entidade(lancamento, hoje)


@router.get("/lancamentos", response_model=PaginaLancamentosOut)
async def listar_lancamentos(
    ator: GestorDep,
    caso: ListarLancamentosDep,
    hoje: HojeDep,
    tipo: TipoLancamento | None = None,
    status: StatusLancamento | None = None,
    categoria_id: int | None = None,
    atrasados: Annotated[bool, Query(description="Só pendentes já vencidos")] = False,
    vencimento_de: Annotated[date | None, Query(description="inclusivo")] = None,
    vencimento_ate: Annotated[date | None, Query(description="inclusivo")] = None,
    contraparte: Annotated[str | None, Query(max_length=120, description="Busca parcial")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaLancamentosOut:
    filtros = FiltrosLancamento(
        tipo, status, categoria_id, atrasados, hoje, vencimento_de, vencimento_ate, contraparte
    )
    itens, total = await caso.executar(ator, filtros, limit, offset)
    return PaginaLancamentosOut(
        itens=[LancamentoOut.de_entidade(i, hoje) for i in itens],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/lancamentos/{lancamento_id}", response_model=LancamentoOut)
async def obter_lancamento(
    lancamento_id: int, ator: GestorDep, caso: ObterLancamentoDep, hoje: HojeDep
) -> LancamentoOut:
    return LancamentoOut.de_entidade(await caso.executar(ator, lancamento_id), hoje)


@router.patch("/lancamentos/{lancamento_id}", response_model=LancamentoOut)
async def atualizar_lancamento(
    lancamento_id: int,
    body: LancamentoUpdateIn,
    ator: GestorDep,
    caso: AtualizarLancamentoDep,
    hoje: HojeDep,
) -> LancamentoOut:
    lancamento = await caso.executar(ator, lancamento_id, body.para_alteracao())
    return LancamentoOut.de_entidade(lancamento, hoje)


@router.post("/lancamentos/{lancamento_id}/baixar", response_model=LancamentoOut)
async def baixar_lancamento(
    lancamento_id: int, body: BaixaIn, ator: GestorDep, caso: BaixarLancamentoDep, hoje: HojeDep
) -> LancamentoOut:
    lancamento = await caso.executar(ator, lancamento_id, body.para_baixa())
    return LancamentoOut.de_entidade(lancamento, hoje)


@router.post("/lancamentos/{lancamento_id}/cancelar", response_model=LancamentoOut)
async def cancelar_lancamento(
    lancamento_id: int,
    ator: GestorDep,
    caso: CancelarLancamentoDep,
    hoje: HojeDep,
    body: CancelarLancamentoIn | None = None,
) -> LancamentoOut:
    motivo = body.motivo if body else None
    return LancamentoOut.de_entidade(await caso.executar(ator, lancamento_id, motivo), hoje)
