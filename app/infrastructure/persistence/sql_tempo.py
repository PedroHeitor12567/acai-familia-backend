"""Conversão de fuso no SQL: "dia local" e "hora local" de um `timestamptz` guardado em UTC.

PostgreSQL converte de verdade (`timezone(fuso, coluna)`, com horário de verão). O SQLite, usado
só nos testes funcionais, guarda o instante em UTC sem fuso e não conhece zonas: aplica-se o
deslocamento fixo que a zona tem no início do período consultado.
"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import (
    ColumnElement,
    Date,
    Integer,
    SQLColumnExpression,
    String,
    cast,
    extract,
    func,
    literal,
)


class SqlTempo:
    def __init__(self, dialeto: str, fuso: str, referencia: datetime) -> None:
        self._dialeto = dialeto
        self._fuso = fuso
        deslocamento = ZoneInfo(fuso).utcoffset(referencia.astimezone(ZoneInfo(fuso)))
        minutos = int(deslocamento.total_seconds() // 60) if deslocamento else 0
        self._modificador = f"{minutos:+d} minutes"

    def _local(self, coluna: SQLColumnExpression[Any]) -> ColumnElement[datetime]:
        # `literal_execute` escreve o fuso no texto do SQL (e não como `$n`), para a mesma
        # expressão aparecer idêntica no SELECT e no GROUP BY.
        return func.timezone(literal(self._fuso, type_=String, literal_execute=True), coluna)

    def dia_local(self, coluna: SQLColumnExpression[Any]) -> ColumnElement[date]:
        if self._dialeto == "postgresql":
            return cast(self._local(coluna), Date)
        return func.date(coluna, self._modificador, type_=Date)

    def hora_local(self, coluna: SQLColumnExpression[Any]) -> ColumnElement[int]:
        if self._dialeto == "postgresql":
            return cast(extract("hour", self._local(coluna)), Integer)
        return cast(func.strftime("%H", coluna, self._modificador), Integer)
