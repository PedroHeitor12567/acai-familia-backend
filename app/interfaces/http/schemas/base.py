from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


class EntradaEstrita(BaseModel):
    """Toda entrada rejeita campos desconhecidos (evita mass assignment)."""

    model_config = ConfigDict(extra="forbid")


def _escala(casas: int) -> AfterValidator:
    exp = Decimal(1).scaleb(-casas)
    return AfterValidator(lambda v: v.quantize(exp))


# Saída com escala fixa (igual à coluna `Numeric`), independente de como o banco devolve o valor.
DinheiroOut = Annotated[Decimal, _escala(2)]
QuantidadeOut = Annotated[Decimal, _escala(3)]
