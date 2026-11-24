from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings


def register_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # lista explícita, nunca "*"
        allow_credentials=False,  # autenticação é por header Bearer, sem cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def seguranca(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Só vale para Content-Length; o proxy reverso deve impor o limite também (chunked).
        tamanho = request.headers.get("content-length")
        if tamanho and tamanho.isdigit() and int(tamanho) > settings.max_body_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "code": "corpo_grande_demais",
                    "detail": "Corpo da requisição grande demais",
                },
            )
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        if settings.is_production:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp
