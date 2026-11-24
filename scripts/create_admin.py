"""Cria o primeiro administrador. Uso: python -m scripts.create_admin"""

import asyncio
import getpass
import os

from app.bootstrap.container import abrir_sessao, build_criar_usuario
from app.domain.usuarios.entities import Papel


async def main() -> None:
    nome = os.getenv("ADMIN_NOME") or input("Nome: ")
    email = os.getenv("ADMIN_EMAIL") or input("E-mail: ")
    senha = os.getenv("ADMIN_PASSWORD") or getpass.getpass("Senha (mín. 8): ")
    if len(senha) < 8:
        raise SystemExit("Senha muito curta.")
    async with abrir_sessao() as db:
        u = await build_criar_usuario(db).executar(None, nome, email, senha, Papel.ADMIN)
    print(f"Admin criado: {u.email}")


if __name__ == "__main__":
    asyncio.run(main())
