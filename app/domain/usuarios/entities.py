from dataclasses import dataclass
from enum import StrEnum


class Papel(StrEnum):
    ADMIN = "admin"
    GERENTE = "gerente"
    ATENDENTE = "atendente"
    CAIXA = "caixa"


@dataclass
class Usuario:
    nome: str
    email: str
    senha_hash: str
    papel: Papel
    ativo: bool = True
    id: int | None = None

    @property
    def id_persistido(self) -> int:
        """Identificador de um usuário já salvo. Erro de programação se ainda não foi."""
        if self.id is None:
            raise ValueError("Usuário ainda não foi persistido")
        return self.id
