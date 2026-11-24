from typing import Self

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.domain.usuarios.entities import Papel, Usuario
from app.interfaces.http.schemas.base import EntradaEstrita


class UsuarioCreateIn(EntradaEstrita):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    papel: Papel


class UsuarioUpdateIn(EntradaEstrita):
    """Só nome, e-mail e papel. `ativo`, `senha_hash` e `id` são rejeitados (extra=forbid)."""

    nome: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    papel: Papel | None = None

    @model_validator(mode="after")
    def _ao_menos_um_campo(self) -> Self:
        if self.nome is None and self.email is None and self.papel is None:
            raise ValueError("Informe ao menos um campo: nome, email ou papel")
        return self


class RedefinirSenhaIn(EntradaEstrita):
    nova_senha: str = Field(min_length=8, max_length=128)


class AlterarSenhaIn(EntradaEstrita):
    senha_atual: str = Field(min_length=1, max_length=128)
    nova_senha: str = Field(min_length=8, max_length=128)


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    papel: Papel
    ativo: bool

    @classmethod
    def de_entidade(cls, usuario: Usuario) -> "UsuarioOut":
        return cls(
            id=usuario.id_persistido,
            nome=usuario.nome,
            email=usuario.email,
            papel=usuario.papel,
            ativo=usuario.ativo,
        )


class PaginaUsuariosOut(BaseModel):
    itens: list[UsuarioOut]
    total: int
    limit: int
    offset: int
