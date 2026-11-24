from pydantic import BaseModel, ConfigDict


class EntradaEstrita(BaseModel):
    """Toda entrada rejeita campos desconhecidos (evita mass assignment)."""

    model_config = ConfigDict(extra="forbid")
