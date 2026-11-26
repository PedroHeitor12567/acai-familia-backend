from decimal import Decimal


class ComId:
    """Mixin das entidades persistidas: `id` é None até o primeiro save."""

    id: int | None

    @property
    def id_persistido(self) -> int:
        """Identificador de uma entidade já salva. Erro de programação se ainda não foi."""
        if self.id is None:
            raise ValueError(f"{type(self).__name__} ainda não foi persistido")
        return self.id


def decimal_valido(valor: Decimal, casas: int) -> bool:
    """Finito e com no máximo `casas` casas decimais (nunca arredonda em silêncio)."""
    if not valor.is_finite():
        return False
    expoente = valor.as_tuple().exponent
    return isinstance(expoente, int) and expoente >= -casas
