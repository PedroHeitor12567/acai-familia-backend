"""Dados de apoio dos testes de comandas: cardápio, insumos, fichas e usuários já prontos."""

from dataclasses import dataclass
from decimal import Decimal

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.caixa.use_cases.sessoes import AbrirCaixa
from app.application.comandas.dto import ResultadoFechamento
from app.application.comandas.use_cases.fechamento import FecharComanda
from app.application.unit_of_work import UnitOfWork
from app.bootstrap.container import build_uow
from app.domain.caixa.entities import FormaPagamento, PagamentoPedido, SessaoCaixa
from app.domain.cardapio.entities import Adicional, Categoria, Produto, ProdutoTamanho, Tamanho
from app.domain.comandas.regras import total_comanda
from app.domain.estoque.entities import (
    Insumo,
    ItemFichaTecnica,
    TipoMovimentacao,
    UnidadeMedida,
)
from app.domain.usuarios.entities import Papel, Usuario
from app.infrastructure.persistence.usuarios.repository import SqlAlchemyUsuarioRepository

D = Decimal


@dataclass(frozen=True)
class Semente:
    """Açaí 500 ml (R$ 18,90) com ficha de 0,300 kg de polpa; adicional Granola (R$ 2,50) com
    ficha de 0,020 kg de granola. Estoque inicial: 10 kg de polpa e 1 kg de granola."""

    produto_id: int
    tamanho_id: int
    adicional_id: int
    polpa_id: int
    granola_id: int


async def semear_usuario(s: AsyncSession, papel: Papel, email: str | None = None) -> Usuario:
    u = await SqlAlchemyUsuarioRepository(s).adicionar(
        Usuario(nome="X", email=email or f"{papel}@acai.com", senha_hash="x", papel=papel)
    )
    await s.commit()
    return u


async def semear_cardapio(
    s: AsyncSession,
    *,
    com_ficha: bool = True,
    estoque_polpa: str = "10",
    estoque_granola: str = "1",
) -> Semente:
    uow = build_uow(s)
    categoria = await uow.cardapio.adicionar_categoria(Categoria("Açaí"))
    tamanho = await uow.cardapio.adicionar_tamanho(Tamanho("500 ml"))
    produto = await uow.cardapio.adicionar_produto(Produto("Tradicional", categoria.id_persistido))
    await uow.cardapio.definir_preco(
        ProdutoTamanho(produto.id_persistido, tamanho.id_persistido, D("18.90"))
    )
    adicional = await uow.cardapio.adicionar_adicional(Adicional("Granola", D("2.50")))
    polpa = await uow.estoque.adicionar_insumo(Insumo("Polpa de açaí", UnidadeMedida.KG))
    granola = await uow.estoque.adicionar_insumo(Insumo("Granola", UnidadeMedida.KG))
    for insumo, saldo in ((polpa, estoque_polpa), (granola, estoque_granola)):
        await uow.estoque.movimentar(
            insumo.id_persistido, TipoMovimentacao.ENTRADA, D(saldo), None, "carga inicial"
        )
    if com_ficha:
        await uow.ficha_tecnica.substituir_ficha_produto(
            produto.id_persistido,
            tamanho.id_persistido,
            [ItemFichaTecnica(polpa.id_persistido, D("0.300"))],
        )
        await uow.ficha_tecnica.substituir_ficha_adicional(
            adicional.id_persistido, [ItemFichaTecnica(granola.id_persistido, D("0.020"))]
        )
    await s.commit()
    return Semente(
        produto_id=produto.id_persistido,
        tamanho_id=tamanho.id_persistido,
        adicional_id=adicional.id_persistido,
        polpa_id=polpa.id_persistido,
        granola_id=granola.id_persistido,
    )


async def abrir_caixa(s: AsyncSession, valor: str = "0.00") -> SessaoCaixa:
    gerente = await semear_usuario(s, Papel.GERENTE, "abre-caixa@acai.com")
    return await AbrirCaixa(build_uow(s)).executar(gerente, D(valor))


async def fechar_com_pix(uow: UnitOfWork, ator: Usuario, comanda_id: int) -> ResultadoFechamento:
    comanda = await uow.comandas.obter(comanda_id)
    total = total_comanda(comanda.itens) if comanda else D("0.00")
    pagamentos = [PagamentoPedido(FormaPagamento.PIX, total)] if total > 0 else []
    return await FecharComanda(uow).executar(ator, comanda_id, pagamentos)


async def abrir_caixa_api(client: AsyncClient, headers: dict[str, str], valor: str = "0.00") -> int:
    r = await client.post("/caixa/sessoes", json={"valor_abertura": valor}, headers=headers)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


async def fechar_comanda_api(
    client: AsyncClient, headers: dict[str, str], comanda_id: int
) -> Response:
    detalhe = await client.get(f"/comandas/{comanda_id}", headers=headers)
    total = detalhe.json()["total"] if detalhe.status_code == 200 else "0.00"
    pagamentos = [{"forma": "pix", "valor": total}] if D(total) > 0 else []
    return await client.post(
        f"/comandas/{comanda_id}/fechar", json={"pagamentos": pagamentos}, headers=headers
    )
