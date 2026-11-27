from fastapi import FastAPI

from app.config import get_settings
from app.interfaces.http.errors import register_error_handlers
from app.interfaces.http.middleware import register_middleware
from app.interfaces.http.routers import (
    auth,
    caixa,
    cardapio,
    comandas,
    dashboard,
    estoque,
    financeiro,
    health,
    usuarios,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Açaí Família API",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    register_middleware(app, settings)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(usuarios.router)
    for router in (
        *cardapio.routers,
        *estoque.routers,
        comandas.router,
        caixa.router,
        financeiro.router,
        dashboard.router,
    ):
        app.include_router(router)
    return app


app = create_app()
