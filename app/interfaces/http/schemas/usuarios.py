from pydantic import BaseModel, EmailStr, Field

from app.domain.usuarios.entities import Papel, Usuario
from app.interfaces.http.schemas.base import EntradaEstrita


class UsuarioCreateIn(EntradaEstrita):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=128)
    papel: Papel


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
