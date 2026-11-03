"""Expressions cron à 5 champs, sans dépendance (hdrctl watch tourne sans l'extra [server]).

    minute heure jour-du-mois mois jour-de-semaine
    *   */15   1-5   1,15   mon-fri   jan-mar   0 ou 7 = dimanche

Comme cron : quand jour-du-mois ET jour-de-semaine sont restreints, l'un OU
l'autre suffit (« 0 9 1 * mon » = le 1er du mois et chaque lundi)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import FrozenSet, Optional

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_DAYS = {d: i for i, d in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}
_FIELDS = (("minute", 0, 59, {}), ("hour", 0, 23, {}), ("day", 1, 31, {}),
           ("month", 1, 12, _MONTHS), ("weekday", 0, 7, _DAYS))


@dataclass(frozen=True)
class Cron:
    expr: str
    minutes: FrozenSet[int]
    hours: FrozenSet[int]
    days: FrozenSet[int]
    months: FrozenSet[int]
    weekdays: FrozenSet[int]          # 0 = dimanche … 6 = samedi
    day_any: bool
    weekday_any: bool

    def matches(self, dt: datetime) -> bool:
        if dt.minute not in self.minutes or dt.hour not in self.hours or dt.month not in self.months:
            return False
        dom = dt.day in self.days
        dow = (dt.isoweekday() % 7) in self.weekdays
        if self.day_any and self.weekday_any:
            return True
        if self.day_any:
            return dow
        if self.weekday_any:
            return dom
        return dom or dow

    def next_after(self, dt: datetime) -> datetime:
        """Prochain instant (à la minute) strictement après `dt` ; même fuseau que `dt`."""
        t = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        end = t + timedelta(days=366 * 5)
        while t < end:
            if t.month not in self.months:
                y, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
                t = t.replace(year=y, month=m, day=1, hour=0, minute=0)
                continue
            if not self._day_ok(t):
                t = (t + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if t.hour not in self.hours:
                t = (t + timedelta(hours=1)).replace(minute=0)
                continue
            if t.minute not in self.minutes:
                t += timedelta(minutes=1)
                continue
            return t
        raise ValueError(f"cron '{self.expr}' never matches")

    def _day_ok(self, t: datetime) -> bool:
        dom = t.day in self.days
        dow = (t.isoweekday() % 7) in self.weekdays
        if self.day_any and self.weekday_any:
            return True
        if self.day_any:
            return dow
        if self.weekday_any:
            return dom
        return dom or dow


def _value(token: str, lo: int, hi: int, names: dict, field: str) -> int:
    t = token.lower()
    if t in names:
        return names[t]
    if not t.isdigit():
        raise ValueError(f"{field}: '{token}' is not a number" + (" or a name" if names else ""))
    v = int(t)
    if not lo <= v <= hi:
        raise ValueError(f"{field}: {v} is out of range ({lo}-{hi})")
    return v


def _field(text: str, lo: int, hi: int, names: dict, field: str) -> FrozenSet[int]:
    out = set()
    for part in text.split(","):
        if not part:
            raise ValueError(f"{field}: empty value in '{text}'")
        rng, _, step_s = part.partition("/")
        step = 1
        if step_s:
            if not step_s.isdigit() or int(step_s) == 0:
                raise ValueError(f"{field}: invalid step '/{step_s}'")
            step = int(step_s)
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            x, _, y = rng.partition("-")
            a, b = _value(x, lo, hi, names, field), _value(y, lo, hi, names, field)
            if a > b:
                raise ValueError(f"{field}: range '{rng}' goes backwards")
        else:
            a = _value(rng, lo, hi, names, field)
            b = hi if step_s else a
        out.update(range(a, b + 1, step))
    return frozenset(out)


def parse_cron(expr: str) -> Cron:
    parts = str(expr).split()
    if len(parts) != 5:
        raise ValueError(f"cron '{expr}': 5 fields expected (minute hour day month weekday)")
    try:
        sets = [_field(p, lo, hi, names, name) for p, (name, lo, hi, names) in zip(parts, _FIELDS)]
    except ValueError as e:
        raise ValueError(f"cron '{expr}': {e}") from None
    weekdays = frozenset(7 % 7 if d == 7 else d for d in sets[4])
    cron = Cron(str(expr), sets[0], sets[1], sets[2], sets[3], weekdays,
                day_any=parts[2] == "*", weekday_any=parts[4] == "*")
    if not any(d <= 29 for d in cron.days) and cron.months == frozenset({2}) and cron.weekday_any:
        raise ValueError(f"cron '{expr}': never matches (no such day in February)")
    return cron


def zone(name: Optional[str]):
    """Fuseau IANA (Europe/Paris) ; None = fuseau local de la machine."""
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001  (ZoneInfoNotFoundError, tzdata absent sous Windows)
        raise ValueError(f"unknown timezone '{name}' (e.g. Europe/Paris, UTC; "
                         f"on Windows: pip install tzdata)") from None


def next_run(expr: str, after: datetime, timezone: Optional[str] = None) -> datetime:
    """Prochaine exécution après `after` (datetime avec fuseau), rendue avec fuseau."""
    tz = zone(timezone)
    local = after.astimezone(tz) if tz else after.astimezone()
    nxt = parse_cron(expr).next_after(local.replace(tzinfo=None))
    return nxt.replace(tzinfo=local.tzinfo) if tz is None else nxt.replace(tzinfo=tz)
