from fastapi import APIRouter

router = APIRouter(tags=["infra"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
