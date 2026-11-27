"""Período de consulta do dashboard: datas locais inclusivas, validações e buckets."""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.domain.exceptions import PeriodoInvalido

DIAS_PADRAO = 30
MAX_DIAS_PERIODO = 366
MAX_DIAS_AGRUPADO_POR_DIA = 92


class Agrupamento(StrEnum):
    DIA = "dia"
    SEMANA = "semana"
    MES = "mes"


@dataclass(frozen=True)
class Periodo:
    """Intervalo de datas **locais** (fuso da loja), as duas pontas inclusivas."""

    de: date
    ate: date

    @property
    def dias(self) -> int:
        return (self.ate - self.de).days + 1

    def anterior(self) -> "Periodo":
        """Mesma duração, imediatamente antes (`de - n` a `de - 1`)."""
        return Periodo(self.de - timedelta(days=self.dias), self.de - timedelta(days=1))


@dataclass(frozen=True)
class Bucket:
    """Faixa da série. `chave` é o início natural (dia, segunda ou dia 1); `inicio`/`fim`
    já vêm recortados ao período pedido."""

    chave: date
    inicio: date
    fim: date


def montar_periodo(
    de: date | None, ate: date | None, hoje: date, *, permite_futuro: bool = False
) -> Periodo:
    """Aplica o padrão (últimos 30 dias até hoje) e valida. `permite_futuro` existe para a
    projeção do fluxo de caixa, cujos vencimentos pendentes estão no futuro."""
    fim = ate if ate is not None else hoje
    inicio = de if de is not None else fim - timedelta(days=DIAS_PADRAO - 1)
    if inicio > fim:
        raise PeriodoInvalido("periodo_invertido")
    if fim > hoje and not permite_futuro:
        raise PeriodoInvalido("periodo_no_futuro")
    periodo = Periodo(inicio, fim)
    if periodo.dias > MAX_DIAS_PERIODO:
        raise PeriodoInvalido("periodo_longo_demais")
    return periodo


def validar_agrupamento(periodo: Periodo, agrupamento: Agrupamento) -> None:
    if agrupamento is Agrupamento.DIA and periodo.dias > MAX_DIAS_AGRUPADO_POR_DIA:
        raise PeriodoInvalido("agrupamento_dia_longo_demais")


def limites_utc(periodo: Periodo, fuso: str) -> tuple[datetime, datetime]:
    """`[de 00:00 local, ate+1 dia 00:00 local)` em UTC (intervalo semiaberto)."""
    zona = ZoneInfo(fuso)
    inicio = datetime.combine(periodo.de, time.min, tzinfo=zona)
    fim = datetime.combine(periodo.ate + timedelta(days=1), time.min, tzinfo=zona)
    return inicio.astimezone(UTC), fim.astimezone(UTC)


def chave_bucket(dia: date, agrupamento: Agrupamento) -> date:
    if agrupamento is Agrupamento.SEMANA:
        return dia - timedelta(days=dia.weekday())  # semana começa na segunda
    if agrupamento is Agrupamento.MES:
        return dia.replace(day=1)
    return dia


def _fim_natural(chave: date, agrupamento: Agrupamento) -> date:
    if agrupamento is Agrupamento.SEMANA:
        return chave + timedelta(days=6)
    if agrupamento is Agrupamento.MES:
        return chave.replace(day=calendar.monthrange(chave.year, chave.month)[1])
    return chave


def buckets(periodo: Periodo, agrupamento: Agrupamento) -> list[Bucket]:
    """Todas as faixas do período, mesmo as sem movimento; as das pontas ficam recortadas."""
    faixas: list[Bucket] = []
    cursor = periodo.de
    while cursor <= periodo.ate:
        chave = chave_bucket(cursor, agrupamento)
        fim = min(_fim_natural(chave, agrupamento), periodo.ate)
        faixas.append(Bucket(chave, cursor, fim))
        cursor = fim + timedelta(days=1)
    return faixas
