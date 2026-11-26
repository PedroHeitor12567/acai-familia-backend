from typing import Annotated

from fastapi import APIRouter, Query, status

from app.application.cardapio.ports import FiltrosProduto
from app.interfaces.http.deps import (
    AlterarStatusAdicionalDep,
    AlterarStatusCategoriaDep,
    AlterarStatusProdutoDep,
    AlterarStatusTamanhoDep,
    AtualizarAdicionalDep,
    AtualizarCategoriaDep,
    AtualizarProdutoDep,
    AtualizarTamanhoDep,
    CriarAdicionalDep,
    CriarCategoriaDep,
    CriarProdutoDep,
    CriarTamanhoDep,
    CurrentUser,
    DefinirPrecoProdutoDep,
    GestorDep,
    ListarAdicionaisDep,
    ListarCategoriasDep,
    ListarProdutosDep,
    ListarTamanhosDep,
    ObterCategoriaDep,
    ObterProdutoDep,
)
from app.interfaces.http.schemas.cardapio import (
    AdicionalCreateIn,
    AdicionalOut,
    AdicionalUpdateIn,
    CategoriaIn,
    CategoriaOut,
    CategoriaUpdateIn,
    PaginaAdicionaisOut,
    PaginaCategoriasOut,
    PaginaProdutosOut,
    PaginaTamanhosOut,
    PrecoIn,
    ProdutoCreateIn,
    ProdutoOut,
    ProdutoUpdateIn,
    TamanhoIn,
    TamanhoOut,
)

# Leitura: qualquer usuário autenticado. Escrita: admin e gerente.
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]

categorias = APIRouter(prefix="/categorias", tags=["cardápio"])
tamanhos = APIRouter(prefix="/tamanhos", tags=["cardápio"])
adicionais = APIRouter(prefix="/adicionais", tags=["cardápio"])
produtos = APIRouter(prefix="/produtos", tags=["cardápio"])
routers = (categorias, tamanhos, adicionais, produtos)


# --- categorias ---


@categorias.post("", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED)
async def criar_categoria(
    body: CategoriaIn, ator: GestorDep, caso: CriarCategoriaDep
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(ator, body.nome))


@categorias.get("", response_model=PaginaCategoriasOut)
async def listar_categorias(
    _: CurrentUser,
    caso: ListarCategoriasDep,
    ativo: bool | None = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaCategoriasOut:
    itens, total = await caso.executar(ativo, limit, offset)
    return PaginaCategoriasOut(
        itens=[CategoriaOut.de_entidade(c) for c in itens], total=total, limit=limit, offset=offset
    )


@categorias.get("/{categoria_id}", response_model=CategoriaOut)
async def obter_categoria(
    categoria_id: int, _: CurrentUser, caso: ObterCategoriaDep
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(categoria_id))


@categorias.patch("/{categoria_id}", response_model=CategoriaOut)
async def atualizar_categoria(
    categoria_id: int, body: CategoriaUpdateIn, ator: GestorDep, caso: AtualizarCategoriaDep
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(ator, categoria_id, body.nome))


@categorias.post("/{categoria_id}/desativar", response_model=CategoriaOut)
async def desativar_categoria(
    categoria_id: int, ator: GestorDep, caso: AlterarStatusCategoriaDep
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(ator, categoria_id, ativo=False))


@categorias.post("/{categoria_id}/ativar", response_model=CategoriaOut)
async def ativar_categoria(
    categoria_id: int, ator: GestorDep, caso: AlterarStatusCategoriaDep
) -> CategoriaOut:
    return CategoriaOut.de_entidade(await caso.executar(ator, categoria_id, ativo=True))


# --- tamanhos ---


@tamanhos.post("", response_model=TamanhoOut, status_code=status.HTTP_201_CREATED)
async def criar_tamanho(body: TamanhoIn, ator: GestorDep, caso: CriarTamanhoDep) -> TamanhoOut:
    return TamanhoOut.de_entidade(await caso.executar(ator, body.nome))


@tamanhos.get("", response_model=PaginaTamanhosOut)
async def listar_tamanhos(
    _: CurrentUser,
    caso: ListarTamanhosDep,
    ativo: bool | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PaginaTamanhosOut:
    itens, total = await caso.executar(ativo, limit, offset)
    return PaginaTamanhosOut(
        itens=[TamanhoOut.de_entidade(t) for t in itens], total=total, limit=limit, offset=offset
    )


@tamanhos.patch("/{tamanho_id}", response_model=TamanhoOut)
async def atualizar_tamanho(
    tamanho_id: int, body: TamanhoIn, ator: GestorDep, caso: AtualizarTamanhoDep
) -> TamanhoOut:
    return TamanhoOut.de_entidade(await caso.executar(ator, tamanho_id, body.nome))


@tamanhos.post("/{tamanho_id}/desativar", response_model=TamanhoOut)
async def desativar_tamanho(
    tamanho_id: int, ator: GestorDep, caso: AlterarStatusTamanhoDep
) -> TamanhoOut:
    return TamanhoOut.de_entidade(await caso.executar(ator, tamanho_id, ativo=False))


@tamanhos.post("/{tamanho_id}/ativar", response_model=TamanhoOut)
async def ativar_tamanho(
    tamanho_id: int, ator: GestorDep, caso: AlterarStatusTamanhoDep
) -> TamanhoOut:
    return TamanhoOut.de_entidade(await caso.executar(ator, tamanho_id, ativo=True))


# --- adicionais ---


@adicionais.post("", response_model=AdicionalOut, status_code=status.HTTP_201_CREATED)
async def criar_adicional(
    body: AdicionalCreateIn, ator: GestorDep, caso: CriarAdicionalDep
) -> AdicionalOut:
    return AdicionalOut.de_entidade(await caso.executar(ator, body.nome, body.preco))


@adicionais.get("", response_model=PaginaAdicionaisOut)
async def listar_adicionais(
    _: CurrentUser,
    caso: ListarAdicionaisDep,
    ativo: bool | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PaginaAdicionaisOut:
    itens, total = await caso.executar(ativo, limit, offset)
    return PaginaAdicionaisOut(
        itens=[AdicionalOut.de_entidade(a) for a in itens], total=total, limit=limit, offset=offset
    )


@adicionais.patch("/{adicional_id}", response_model=AdicionalOut)
async def atualizar_adicional(
    adicional_id: int, body: AdicionalUpdateIn, ator: GestorDep, caso: AtualizarAdicionalDep
) -> AdicionalOut:
    atualizado = await caso.executar(ator, adicional_id, body.nome, body.preco)
    return AdicionalOut.de_entidade(atualizado)


@adicionais.post("/{adicional_id}/desativar", response_model=AdicionalOut)
async def desativar_adicional(
    adicional_id: int, ator: GestorDep, caso: AlterarStatusAdicionalDep
) -> AdicionalOut:
    return AdicionalOut.de_entidade(await caso.executar(ator, adicional_id, ativo=False))


@adicionais.post("/{adicional_id}/ativar", response_model=AdicionalOut)
async def ativar_adicional(
    adicional_id: int, ator: GestorDep, caso: AlterarStatusAdicionalDep
) -> AdicionalOut:
    return AdicionalOut.de_entidade(await caso.executar(ator, adicional_id, ativo=True))


# --- produtos ---


@produtos.post("", response_model=ProdutoOut, status_code=status.HTTP_201_CREATED)
async def criar_produto(
    body: ProdutoCreateIn, ator: GestorDep, caso: CriarProdutoDep
) -> ProdutoOut:
    return ProdutoOut.de_dto(await caso.executar(ator, body.nome, body.categoria_id))


@produtos.get("", response_model=PaginaProdutosOut)
async def listar_produtos(
    _: CurrentUser,
    caso: ListarProdutosDep,
    categoria_id: int | None = None,
    ativo: bool | None = None,
    q: Annotated[str | None, Query(max_length=120, description="Busca no nome")] = None,
    limit: Limit = 20,
    offset: Offset = 0,
) -> PaginaProdutosOut:
    itens, total = await caso.executar(
        FiltrosProduto(categoria_id=categoria_id, ativo=ativo, q=q), limit, offset
    )
    return PaginaProdutosOut(
        itens=[ProdutoOut.de_dto(p) for p in itens], total=total, limit=limit, offset=offset
    )


@produtos.get("/{produto_id}", response_model=ProdutoOut)
async def obter_produto(produto_id: int, _: CurrentUser, caso: ObterProdutoDep) -> ProdutoOut:
    return ProdutoOut.de_dto(await caso.executar(produto_id))


@produtos.patch("/{produto_id}", response_model=ProdutoOut)
async def atualizar_produto(
    produto_id: int, body: ProdutoUpdateIn, ator: GestorDep, caso: AtualizarProdutoDep
) -> ProdutoOut:
    atualizado = await caso.executar(ator, produto_id, body.nome, body.categoria_id)
    return ProdutoOut.de_dto(atualizado)


@produtos.put("/{produto_id}/tamanhos/{tamanho_id}", response_model=ProdutoOut)
async def definir_preco(
    produto_id: int, tamanho_id: int, body: PrecoIn, ator: GestorDep, caso: DefinirPrecoProdutoDep
) -> ProdutoOut:
    """Define (ou altera) o preço do produto neste tamanho."""
    return ProdutoOut.de_dto(await caso.executar(ator, produto_id, tamanho_id, body.preco))


@produtos.post("/{produto_id}/desativar", response_model=ProdutoOut)
async def desativar_produto(
    produto_id: int, ator: GestorDep, caso: AlterarStatusProdutoDep
) -> ProdutoOut:
    return ProdutoOut.de_dto(await caso.executar(ator, produto_id, ativo=False))


@produtos.post("/{produto_id}/ativar", response_model=ProdutoOut)
async def ativar_produto(
    produto_id: int, ator: GestorDep, caso: AlterarStatusProdutoDep
) -> ProdutoOut:
    return ProdutoOut.de_dto(await caso.executar(ator, produto_id, ativo=True))
