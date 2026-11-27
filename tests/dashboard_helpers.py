"""Massa de dados do dashboard gravada direto nos models, com datas controladas.

Os instantes são sempre passados em horário **local** (`America/Sao_Paulo`) e gravados em UTC,
como o sistema faz. Assim os testes de recorte por dia local escrevem a hora que um humano leria.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.financeiro.regras import data_local
from app.infrastructure.persistence.auditoria.models import AuditLogModel
from app.infrastructure.persistence.caixa.models import (
    MovimentoCaixaModel,
    PagamentoModel,
    SessaoCaixaModel,
)
from app.infrastructure.persistence.comandas.models import (
    ComandaModel,
    ItemComandaAdicionalModel,
    ItemComandaModel,
)
from app.infrastructure.persistence.estoque.models import InsumoModel
from app.infrastructure.persistence.financeiro.models import (
    CategoriaFinanceiraModel,
    LancamentoModel,
)
from app.infrastructure.persistence.usuarios.models import UsuarioModel

D = Decimal
FUSO = "America/Sao_Paulo"
Factory = async_sessionmaker[AsyncSession]


def hoje_local() -> date:
    return data_local(datetime.now(UTC), FUSO)


def local(dia: date, hora: int = 12, minuto: int = 0) -> datetime:
    """Instante em UTC de `dia hora:minuto` no fuso da loja."""
    return datetime.combine(dia, time(hora, minuto), tzinfo=ZoneInfo(FUSO)).astimezone(UTC)


def dias_atras(n: int) -> date:
    return hoje_local() - timedelta(days=n)


@dataclass(frozen=True)
class ItemSemente:
    produto_id: int = 1
    nome: str = "Açaí"
    quantidade: int = 1
    preco: str = "20.00"
    adicionais: Sequence[tuple[str, int, str]] = field(default_factory=tuple)  # (nome, qtd, preço)

    @property
    def subtotal(self) -> Decimal:
        extras = sum((D(p) * q for _, q, p in self.adicionais), start=D("0"))
        return (D(self.preco) + extras) * self.quantidade


class Massa:
    """Cria usuário, sessão de caixa e as vendas/lançamentos de um teste."""

    def __init__(self, factory: Factory) -> None:
        self._f = factory
        self.usuario_id = 0
        self.sessao_id = 0
        self.tamanho_id = 1  # no PostgreSQL a FK exige um tamanho real
        self._adicional_id = 0

    async def preparar(self) -> "Massa":
        async with self._f() as s:
            usuario = UsuarioModel(
                nome="Massa", email="massa@acai.com", senha_hash="x", papel="admin", ativo=True
            )
            s.add(usuario)
            await s.flush()
            self.usuario_id = usuario.id
            sessao = SessaoCaixaModel(
                status="aberta",
                valor_abertura=D("100.00"),
                aberta_por_id=usuario.id,
                aberta_em=local(dias_atras(400)),
            )
            s.add(sessao)
            await s.flush()
            self.sessao_id = sessao.id
            await s.commit()
        return self

    async def comanda(
        self,
        quando: datetime,
        itens: Sequence[ItemSemente] = (ItemSemente(),),
        pagamentos: Sequence[tuple[str, str]] | None = None,
        status: str = "fechada",
    ) -> int:
        """Comanda fechada em `quando` (UTC). `pagamentos` padrão: o total todo em pix."""
        total = sum((i.subtotal for i in itens), start=D("0.00"))
        async with self._f() as s:
            comanda = ComandaModel(
                cliente_nome="Cliente",
                origem="balcao",
                status=status,
                aberta_em=quando - timedelta(minutes=10),
                fechada_em=quando if status == "fechada" else None,
                total=total if status == "fechada" else None,
            )
            for i in itens:
                item = ItemComandaModel(
                    produto_id=i.produto_id,
                    tamanho_id=self.tamanho_id,
                    nome_produto=i.nome,
                    nome_tamanho="500 ml",
                    quantidade=i.quantidade,
                    preco_unitario=D(i.preco),
                )
                for nome, qtd, preco in i.adicionais:
                    self._adicional_id += 1
                    item.adicionais.append(
                        ItemComandaAdicionalModel(
                            adicional_id=self._adicional_id,
                            nome=nome,
                            quantidade=qtd,
                            preco_unitario=D(preco),
                        )
                    )
                comanda.itens.append(item)
            s.add(comanda)
            await s.flush()
            if status == "fechada":
                for forma, valor in pagamentos if pagamentos is not None else [("pix", str(total))]:
                    s.add(
                        PagamentoModel(
                            comanda_id=comanda.id,
                            sessao_id=self.sessao_id,
                            forma=forma,
                            valor=D(valor),
                            criado_por_id=self.usuario_id,
                            criado_em=quando,
                        )
                    )
            if status == "cancelada":
                s.add(
                    AuditLogModel(
                        usuario_id=self.usuario_id,
                        acao="cancelar",
                        entidade="comanda",
                        entidade_id=str(comanda.id),
                        criado_em=quando,
                    )
                )
            await s.commit()
            return comanda.id

    async def movimento(self, tipo: str, valor: str) -> None:
        async with self._f() as s:
            s.add(
                MovimentoCaixaModel(
                    sessao_id=self.sessao_id,
                    tipo=tipo,
                    valor=D(valor),
                    motivo="teste",
                    criado_por_id=self.usuario_id,
                    criado_em=local(hoje_local()),
                )
            )
            await s.commit()

    async def categoria(self, nome: str, tipo: str) -> int:
        async with self._f() as s:
            categoria = CategoriaFinanceiraModel(nome=nome, tipo=tipo, ativo=True)
            s.add(categoria)
            await s.commit()
            return categoria.id

    async def lancamento(
        self,
        tipo: str,
        valor: str,
        vencimento: date,
        categoria_id: int,
        status: str = "pendente",
        pago_em: date | None = None,
        descricao: str = "Conta",
    ) -> int:
        async with self._f() as s:
            lancamento = LancamentoModel(
                tipo=tipo,
                descricao=descricao,
                valor=D(valor),
                vencimento=vencimento,
                categoria_id=categoria_id,
                status=status,
                data_pagamento=pago_em if status == "pago" else None,
                forma_pagamento="pix" if status == "pago" else None,
                criado_por_id=self.usuario_id,
                baixado_por_id=self.usuario_id if status == "pago" else None,
            )
            s.add(lancamento)
            await s.commit()
            return lancamento.id

    async def insumo(
        self, nome: str, atual: str, minimo: str, unidade: str = "kg", ativo: bool = True
    ) -> int:
        async with self._f() as s:
            insumo = InsumoModel(
                nome=nome,
                unidade=unidade,
                estoque_atual=D(atual),
                estoque_minimo=D(minimo),
                ativo=ativo,
            )
            s.add(insumo)
            await s.commit()
            return insumo.id
