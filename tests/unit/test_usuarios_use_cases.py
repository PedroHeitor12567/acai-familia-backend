import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.usuarios.use_cases.criar_usuario import CriarUsuario
from app.bootstrap.container import build_uow, get_hasher
from app.domain.exceptions import PermissaoNegada
from app.domain.usuarios.entities import Papel, Usuario


async def test_caso_de_uso_recusa_ator_sem_papel_admin(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """A regra vale mesmo se alguém chamar o caso de uso fora do HTTP (worker, script)."""
    ator = Usuario(nome="A", email="a@a.com", senha_hash="x", papel=Papel.ATENDENTE, id=1)
    async with factory() as s:
        caso = CriarUsuario(build_uow(s), get_hasher())
        with pytest.raises(PermissaoNegada):
            await caso.executar(ator, "Novo", "novo@a.com", "senha-longa-123", Papel.CAIXA)
