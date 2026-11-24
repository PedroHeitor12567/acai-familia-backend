from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.domain.usuarios.entities import Papel, Usuario
from app.interfaces.http.deps import CriarUsuarioDep, require_roles
from app.interfaces.http.schemas.usuarios import UsuarioCreateIn, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

AdminDep = Annotated[Usuario, Depends(require_roles(Papel.ADMIN))]


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(body: UsuarioCreateIn, admin: AdminDep, caso: CriarUsuarioDep) -> UsuarioOut:
    novo = caso.executar(admin, body.nome, body.email, body.senha, body.papel)
    return UsuarioOut.de_entidade(novo)
