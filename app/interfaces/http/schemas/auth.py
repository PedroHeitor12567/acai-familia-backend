from pydantic import BaseModel, EmailStr, Field

from app.interfaces.http.schemas.base import EntradaEstrita


class LoginIn(EntradaEstrita):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class RefreshIn(EntradaEstrita):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
