from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.application.financeiro.use_cases.lancamentos import AlteracaoLancamento
from app.domain.caixa.entities import FormaPagamento
from app.domain.financeiro.entities import (
    Baixa,
    CategoriaFinanceira,
    Lancamento,
    StatusLancamento,
    TipoCategoria,
    TipoLancamento,
)
from app.domain.financeiro.regras import esta_atrasado
from app.interfaces.http.schemas.base import DinheiroOut, EntradaEstrita

ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
NomeCategoria = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
]
Descricao = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Contraparte = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
Observacao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class CategoriaIn(EntradaEstrita):
    nome: NomeCategoria
    tipo: TipoCategoria


class CategoriaUpdateIn(EntradaEstrita):
    nome: NomeCategoria | None = None
    ativo: bool | None = None

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if self.nome is None and self.ativo is None:
            raise ValueError("Informe ao menos um campo: nome ou ativo")
        return self


class CategoriaOut(BaseModel):
    id: int
    nome: str
    tipo: TipoCategoria
    ativo: bool

    @classmethod
    def de_entidade(cls, c: CategoriaFinanceira) -> Self:
        return cls(id=c.id_persistido, nome=c.nome, tipo=c.tipo, ativo=c.ativo)


class BaixaIn(EntradaEstrita):
    data_pagamento: date
    forma: FormaPagamento

    def para_baixa(self) -> Baixa:
        return Baixa(self.data_pagamento, self.forma)


class LancamentoIn(EntradaEstrita):
    tipo: TipoLancamento
    descricao: Descricao
    valor: ValorPositivo
    vencimento: date
    categoria_id: int
    contraparte: Contraparte | None = None
    observacao: Observacao | None = None
    baixa: BaixaIn | None = Field(default=None, description="Cria já pago (despesa à vista)")


class LancamentoUpdateIn(EntradaEstrita):
    descricao: Descricao | None = None
    valor: ValorPositivo | None = None
    vencimento: date | None = None
    categoria_id: int | None = None
    contraparte: Contraparte | None = Field(default=None, description='"" limpa o campo')
    observacao: Observacao | None = Field(default=None, description='"" limpa o campo')

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if all(getattr(self, campo) is None for campo in type(self).model_fields):
            raise ValueError("Informe ao menos um campo para alterar")
        return self

    def para_alteracao(self) -> AlteracaoLancamento:
        return AlteracaoLancamento(
            descricao=self.descricao,
            valor=self.valor,
            vencimento=self.vencimento,
            categoria_id=self.categoria_id,
            contraparte=self.contraparte,
            observacao=self.observacao,
        )


class CancelarLancamentoIn(EntradaEstrita):
    motivo: Motivo | None = None


class LancamentoOut(BaseModel):
    id: int
    tipo: TipoLancamento
    descricao: str
    valor: DinheiroOut
    vencimento: date
    categoria_id: int
    contraparte: str | None
    observacao: str | None
    status: StatusLancamento
    atrasado: bool
    data_pagamento: date | None
    forma_pagamento: FormaPagamento | None
    criado_por_id: int
    baixado_por_id: int | None

    @classmethod
    def de_entidade(cls, lancamento: Lancamento, hoje: date) -> Self:
        return cls(
            id=lancamento.id_persistido,
            tipo=lancamento.tipo,
            descricao=lancamento.descricao,
            valor=lancamento.valor,
            vencimento=lancamento.vencimento,
            categoria_id=lancamento.categoria_id,
            contraparte=lancamento.contraparte,
            observacao=lancamento.observacao,
            status=lancamento.status,
            atrasado=esta_atrasado(lancamento, hoje),
            data_pagamento=lancamento.data_pagamento,
            forma_pagamento=lancamento.forma_pagamento,
            criado_por_id=lancamento.criado_por_id,
            baixado_por_id=lancamento.baixado_por_id,
        )


class PaginaLancamentosOut(BaseModel):
    itens: list[LancamentoOut]
    total: int
    limit: int
    offset: int
