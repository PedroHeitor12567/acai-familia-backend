from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.caixa.use_cases.movimentos import RegistrarMovimento
from app.application.caixa.use_cases.sessoes import (
    AbrirCaixa,
    FecharCaixa,
    ListarSessoes,
    ObterSessao,
    ObterSessaoAtual,
)
from app.application.cardapio.use_cases.adicionais import (
    AlterarStatusAdicional,
    AtualizarAdicional,
    CriarAdicional,
    ListarAdicionais,
)
from app.application.cardapio.use_cases.categorias import (
    AlterarStatusCategoria,
    AtualizarCategoria,
    CriarCategoria,
    ListarCategorias,
    ObterCategoria,
)
from app.application.cardapio.use_cases.produtos import (
    AlterarStatusProduto,
    AtualizarProduto,
    CriarProduto,
    DefinirPrecoProduto,
    ListarProdutos,
    ObterProduto,
)
from app.application.cardapio.use_cases.tamanhos import (
    AlterarStatusTamanho,
    AtualizarTamanho,
    CriarTamanho,
    ListarTamanhos,
)
from app.application.comandas.use_cases.abrir import AbrirComanda
from app.application.comandas.use_cases.consulta import ListarComandas, ObterComanda
from app.application.comandas.use_cases.fechamento import CancelarComanda, FecharComanda
from app.application.comandas.use_cases.itens import AdicionarItem, AtualizarItem, RemoverItem
from app.application.estoque.use_cases.ficha_tecnica import (
    DefinirFichaAdicional,
    DefinirFichaTecnica,
    ObterFichaAdicional,
    ObterFichaTecnica,
)
from app.application.estoque.use_cases.insumos import (
    AlterarStatusInsumo,
    AtualizarInsumo,
    CriarInsumo,
    ListarAlertasEstoque,
    ListarInsumos,
    ObterInsumo,
)
from app.application.estoque.use_cases.movimentacoes import ListarMovimentacoes, MovimentarEstoque
from app.application.financeiro.use_cases.categorias import (
    AtualizarCategoriaFinanceira,
    CriarCategoriaFinanceira,
    ListarCategoriasFinanceiras,
)
from app.application.financeiro.use_cases.lancamentos import (
    AtualizarLancamento,
    BaixarLancamento,
    CancelarLancamento,
    CriarLancamento,
    ListarLancamentos,
    ObterLancamento,
)
from app.application.usuarios.use_cases.alterar_propria_senha import AlterarPropriaSenha
from app.application.usuarios.use_cases.alterar_status_usuario import AlterarStatusUsuario
from app.application.usuarios.use_cases.atualizar_usuario import AtualizarUsuario
from app.application.usuarios.use_cases.autenticar_usuario import AutenticarUsuario
from app.application.usuarios.use_cases.criar_usuario import CriarUsuario
from app.application.usuarios.use_cases.listar_usuarios import ListarUsuarios
from app.application.usuarios.use_cases.obter_usuario import ObterUsuario
from app.application.usuarios.use_cases.redefinir_senha import RedefinirSenha
from app.application.usuarios.use_cases.renovar_token import RenovarToken
from app.bootstrap.container import (
    TokensDep,
    UowDep,
    caso_de_uso,
    get_alterar_propria_senha,
    get_alterar_status_usuario,
    get_atualizar_usuario,
    get_autenticar_usuario,
    get_criar_usuario,
    get_hoje,
    get_listar_usuarios,
    get_obter_usuario,
    get_redefinir_senha,
    get_renovar_token,
)
from app.domain.exceptions import PermissaoNegada, TokenInvalido
from app.domain.usuarios.entities import Papel, Usuario

_bearer = HTTPBearer(auto_error=False)

AutenticarUsuarioDep = Annotated[AutenticarUsuario, Depends(get_autenticar_usuario)]
RenovarTokenDep = Annotated[RenovarToken, Depends(get_renovar_token)]
CriarUsuarioDep = Annotated[CriarUsuario, Depends(get_criar_usuario)]
ListarUsuariosDep = Annotated[ListarUsuarios, Depends(get_listar_usuarios)]
ObterUsuarioDep = Annotated[ObterUsuario, Depends(get_obter_usuario)]
AtualizarUsuarioDep = Annotated[AtualizarUsuario, Depends(get_atualizar_usuario)]
AlterarStatusUsuarioDep = Annotated[AlterarStatusUsuario, Depends(get_alterar_status_usuario)]
AlterarPropriaSenhaDep = Annotated[AlterarPropriaSenha, Depends(get_alterar_propria_senha)]
RedefinirSenhaDep = Annotated[RedefinirSenha, Depends(get_redefinir_senha)]

# --- cardápio ---
CriarCategoriaDep = Annotated[CriarCategoria, Depends(caso_de_uso(CriarCategoria))]
AtualizarCategoriaDep = Annotated[AtualizarCategoria, Depends(caso_de_uso(AtualizarCategoria))]
AlterarStatusCategoriaDep = Annotated[
    AlterarStatusCategoria, Depends(caso_de_uso(AlterarStatusCategoria))
]
ObterCategoriaDep = Annotated[ObterCategoria, Depends(caso_de_uso(ObterCategoria))]
ListarCategoriasDep = Annotated[ListarCategorias, Depends(caso_de_uso(ListarCategorias))]
CriarTamanhoDep = Annotated[CriarTamanho, Depends(caso_de_uso(CriarTamanho))]
AtualizarTamanhoDep = Annotated[AtualizarTamanho, Depends(caso_de_uso(AtualizarTamanho))]
AlterarStatusTamanhoDep = Annotated[
    AlterarStatusTamanho, Depends(caso_de_uso(AlterarStatusTamanho))
]
ListarTamanhosDep = Annotated[ListarTamanhos, Depends(caso_de_uso(ListarTamanhos))]
CriarAdicionalDep = Annotated[CriarAdicional, Depends(caso_de_uso(CriarAdicional))]
AtualizarAdicionalDep = Annotated[AtualizarAdicional, Depends(caso_de_uso(AtualizarAdicional))]
AlterarStatusAdicionalDep = Annotated[
    AlterarStatusAdicional, Depends(caso_de_uso(AlterarStatusAdicional))
]
ListarAdicionaisDep = Annotated[ListarAdicionais, Depends(caso_de_uso(ListarAdicionais))]
CriarProdutoDep = Annotated[CriarProduto, Depends(caso_de_uso(CriarProduto))]
AtualizarProdutoDep = Annotated[AtualizarProduto, Depends(caso_de_uso(AtualizarProduto))]
AlterarStatusProdutoDep = Annotated[
    AlterarStatusProduto, Depends(caso_de_uso(AlterarStatusProduto))
]
DefinirPrecoProdutoDep = Annotated[DefinirPrecoProduto, Depends(caso_de_uso(DefinirPrecoProduto))]
ObterProdutoDep = Annotated[ObterProduto, Depends(caso_de_uso(ObterProduto))]
ListarProdutosDep = Annotated[ListarProdutos, Depends(caso_de_uso(ListarProdutos))]

# --- estoque ---
CriarInsumoDep = Annotated[CriarInsumo, Depends(caso_de_uso(CriarInsumo))]
AtualizarInsumoDep = Annotated[AtualizarInsumo, Depends(caso_de_uso(AtualizarInsumo))]
AlterarStatusInsumoDep = Annotated[AlterarStatusInsumo, Depends(caso_de_uso(AlterarStatusInsumo))]
ObterInsumoDep = Annotated[ObterInsumo, Depends(caso_de_uso(ObterInsumo))]
ListarInsumosDep = Annotated[ListarInsumos, Depends(caso_de_uso(ListarInsumos))]
ListarAlertasEstoqueDep = Annotated[
    ListarAlertasEstoque, Depends(caso_de_uso(ListarAlertasEstoque))
]
MovimentarEstoqueDep = Annotated[MovimentarEstoque, Depends(caso_de_uso(MovimentarEstoque))]
ListarMovimentacoesDep = Annotated[ListarMovimentacoes, Depends(caso_de_uso(ListarMovimentacoes))]
DefinirFichaTecnicaDep = Annotated[DefinirFichaTecnica, Depends(caso_de_uso(DefinirFichaTecnica))]
ObterFichaTecnicaDep = Annotated[ObterFichaTecnica, Depends(caso_de_uso(ObterFichaTecnica))]
DefinirFichaAdicionalDep = Annotated[
    DefinirFichaAdicional, Depends(caso_de_uso(DefinirFichaAdicional))
]
ObterFichaAdicionalDep = Annotated[ObterFichaAdicional, Depends(caso_de_uso(ObterFichaAdicional))]

# --- comandas ---
AbrirComandaDep = Annotated[AbrirComanda, Depends(caso_de_uso(AbrirComanda))]
AdicionarItemDep = Annotated[AdicionarItem, Depends(caso_de_uso(AdicionarItem))]
AtualizarItemDep = Annotated[AtualizarItem, Depends(caso_de_uso(AtualizarItem))]
RemoverItemDep = Annotated[RemoverItem, Depends(caso_de_uso(RemoverItem))]
ObterComandaDep = Annotated[ObterComanda, Depends(caso_de_uso(ObterComanda))]
ListarComandasDep = Annotated[ListarComandas, Depends(caso_de_uso(ListarComandas))]
FecharComandaDep = Annotated[FecharComanda, Depends(caso_de_uso(FecharComanda))]
CancelarComandaDep = Annotated[CancelarComanda, Depends(caso_de_uso(CancelarComanda))]

AbrirCaixaDep = Annotated[AbrirCaixa, Depends(caso_de_uso(AbrirCaixa))]
ObterSessaoAtualDep = Annotated[ObterSessaoAtual, Depends(caso_de_uso(ObterSessaoAtual))]
ObterSessaoDep = Annotated[ObterSessao, Depends(caso_de_uso(ObterSessao))]
ListarSessoesDep = Annotated[ListarSessoes, Depends(caso_de_uso(ListarSessoes))]
RegistrarMovimentoDep = Annotated[RegistrarMovimento, Depends(caso_de_uso(RegistrarMovimento))]
FecharCaixaDep = Annotated[FecharCaixa, Depends(caso_de_uso(FecharCaixa))]

CriarCategoriaFinanceiraDep = Annotated[
    CriarCategoriaFinanceira, Depends(caso_de_uso(CriarCategoriaFinanceira))
]
AtualizarCategoriaFinanceiraDep = Annotated[
    AtualizarCategoriaFinanceira, Depends(caso_de_uso(AtualizarCategoriaFinanceira))
]
ListarCategoriasFinanceirasDep = Annotated[
    ListarCategoriasFinanceiras, Depends(caso_de_uso(ListarCategoriasFinanceiras))
]
CriarLancamentoDep = Annotated[CriarLancamento, Depends(caso_de_uso(CriarLancamento))]
ObterLancamentoDep = Annotated[ObterLancamento, Depends(caso_de_uso(ObterLancamento))]
ListarLancamentosDep = Annotated[ListarLancamentos, Depends(caso_de_uso(ListarLancamentos))]
AtualizarLancamentoDep = Annotated[AtualizarLancamento, Depends(caso_de_uso(AtualizarLancamento))]
BaixarLancamentoDep = Annotated[BaixarLancamento, Depends(caso_de_uso(BaixarLancamento))]
CancelarLancamentoDep = Annotated[CancelarLancamento, Depends(caso_de_uso(CancelarLancamento))]


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    tokens: TokensDep,
    uow: UowDep,
) -> Usuario:
    if creds is None:
        raise TokenInvalido
    claims = tokens.decodificar(creds.credentials, "access")
    usuario = await uow.usuarios.obter_por_id(claims.usuario_id)
    if usuario is None or not usuario.ativo:
        raise TokenInvalido
    return usuario


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require_roles(*papeis: Papel) -> Callable[[Usuario], Awaitable[Usuario]]:
    """Barreira de borda (HTTP). A regra de quem pode o quê também é checada no caso de uso."""

    async def checker(usuario: CurrentUser) -> Usuario:
        if usuario.papel not in papeis:
            raise PermissaoNegada
        return usuario

    return checker


GestorDep = Annotated[Usuario, Depends(require_roles(Papel.ADMIN, Papel.GERENTE))]
OperadorComandaDep = Annotated[
    Usuario,
    Depends(require_roles(Papel.ADMIN, Papel.GERENTE, Papel.ATENDENTE, Papel.CAIXA)),
]
FechamentoComandaDep = Annotated[
    Usuario, Depends(require_roles(Papel.ADMIN, Papel.GERENTE, Papel.CAIXA))
]
HojeDep = Annotated[date, Depends(get_hoje)]
OperadorCaixaDep = Annotated[
    Usuario, Depends(require_roles(Papel.ADMIN, Papel.GERENTE, Papel.CAIXA))
]
