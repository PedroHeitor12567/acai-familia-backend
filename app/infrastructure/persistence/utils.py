def escapar_like(texto: str) -> str:
    """Neutraliza os curingas do LIKE para que `%` e `_` digitados sejam literais."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
