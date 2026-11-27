from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.application.caixa.ports import FiltrosSessao
from app.domain.caixa.entities import StatusSessao
from app.interfaces.http.deps import (
    AbrirCaixaDep,
    FecharCaixaDep,
    ListarSessoesDep,
    ObterSessaoAtualDep,
    ObterSessaoDep,
    OperadorCaixaDep,
    RegistrarMovimentoDep,
)
from app.interfaces.http.schemas.caixa import (
    AbrirCaixaIn,
    FecharCaixaIn,
    MovimentoIn,
    MovimentoOut,
    PaginaSessoesOut,
    SessaoDetalheOut,
    SessaoResumoOut,
)

router = APIRouter(prefix="/caixa", tags=["caixa"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("/sessoes", response_model=SessaoDetalheOut, status_code=status.HTTP_201_CREATED)
async def abrir_caixa(
    body: AbrirCaixaIn, ator: OperadorCaixaDep, caso: AbrirCaixaDep, atual: ObterSessaoAtualDep
) -> SessaoDetalheOut:
    await caso.executar(ator, body.valor_abertura, body.observacao)
    return SessaoDetalheOut.de_detalhe(await atual.executar(ator))


@router.get("/sessoes/atual", response_model=SessaoDetalheOut)
async def sessao_atual(ator: OperadorCaixaDep, caso: ObterSessaoAtualDep) -> SessaoDetalheOut:
    return SessaoDetalheOut.de_detalhe(await caso.executar(ator))


@router.get("/sessoes", response_model=PaginaSessoesOut)
async def listar_sessoes(
    ator: OperadorCaixaDep,
    caso: ListarSessoesDep,
    status: StatusSessao | None = None,
    de: Annotated[datetime | None, Query(description="aberta_em >= de (inclusivo)")] = None,
    ate: Annotated[datetime | None, Query(description="aberta_em <= ate (inclusivo)")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaSessoesOut:
    itens, total = await caso.executar(ator, FiltrosSessao(status, de, ate), limit, offset)
    return PaginaSessoesOut(
        itens=[SessaoResumoOut.de_entidade(s) for s in itens],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessoes/{sessao_id}", response_model=SessaoDetalheOut)
async def obter_sessao(
    sessao_id: int, ator: OperadorCaixaDep, caso: ObterSessaoDep
) -> SessaoDetalheOut:
    return SessaoDetalheOut.de_detalhe(await caso.executar(ator, sessao_id))


@router.post(
    "/sessoes/{sessao_id}/movimentos",
    response_model=MovimentoOut,
    status_code=status.HTTP_201_CREATED,
)
async def registrar_movimento(
    sessao_id: int, body: MovimentoIn, ator: OperadorCaixaDep, caso: RegistrarMovimentoDep
) -> MovimentoOut:
    movimento = await caso.executar(ator, sessao_id, body.tipo, body.valor, body.motivo)
    return MovimentoOut.de_entidade(movimento)


@router.post("/sessoes/{sessao_id}/fechar", response_model=SessaoDetalheOut)
async def fechar_caixa(
    sessao_id: int, body: FecharCaixaIn, ator: OperadorCaixaDep, caso: FecharCaixaDep
) -> SessaoDetalheOut:
    return SessaoDetalheOut.de_detalhe(
        await caso.executar(ator, sessao_id, body.valor_contado, body.observacao)
    )
