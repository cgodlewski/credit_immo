from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests


class DataLoadError(RuntimeError):
    pass


INSEE_URL = "https://api.insee.fr/series/BDM/V1/data/SERIES_BDM/{series_id}"

NS = {
    "gen": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic",
    "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
    "str": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
}


@dataclass(frozen=True)
class RequestConfig:
    timeout_seconds: int = 30


def _raise_for_status(response: requests.Response, label: str) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:400].strip()
        raise DataLoadError(f"{label} a echoue ({response.status_code}): {detail}") from exc


def _parse_period(period_value: Any) -> pd.Timestamp | None:
    raw = str(period_value).strip()
    if not raw or raw.lower() == "none":
        return None

    patterns = [
        (r"^(\d{4})-Q([1-4])$", "quarter"),
        (r"^(\d{4})-T([1-4])$", "quarter"),
        (r"^T([1-4])\s+(\d{4})$", "quarter_reverse"),
        (r"^(\d{4})-(\d{2})$", "month"),
        (r"^(\d{4})-(\d{2})-(\d{2})$", "day"),
        (r"^(\d{4})$", "year"),
    ]

    for pattern, kind in patterns:
        match = re.match(pattern, raw)
        if not match:
            continue
        if kind == "quarter":
            year, quarter = match.groups()
            month = {"1": 3, "2": 6, "3": 9, "4": 12}[quarter]
            return pd.Timestamp(int(year), month, 1) + pd.offsets.MonthEnd(0)
        if kind == "quarter_reverse":
            quarter, year = match.groups()
            month = {"1": 3, "2": 6, "3": 9, "4": 12}[quarter]
            return pd.Timestamp(int(year), month, 1) + pd.offsets.MonthEnd(0)
        if kind == "month":
            year, month = match.groups()
            return pd.Timestamp(int(year), int(month), 1) + pd.offsets.MonthEnd(0)
        if kind == "day":
            year, month, day = match.groups()
            return pd.Timestamp(int(year), int(month), int(day))
        if kind == "year":
            return pd.Timestamp(int(match.group(1)), 12, 31)

    try:
        return pd.to_datetime(raw)
    except Exception:
        return None


def _build_series(observations: list[tuple[pd.Timestamp, float]]) -> pd.Series:
    if not observations:
        raise DataLoadError("Aucune observation exploitable n'a ete trouvee dans la reponse.")
    frame = pd.DataFrame(observations, columns=["date", "value"])
    frame = frame.dropna().drop_duplicates(subset="date", keep="last").sort_values("date")
    return pd.Series(frame["value"].to_list(), index=pd.DatetimeIndex(frame["date"]), dtype=float)


def _extract_insee_series(root: ET.Element) -> pd.Series:
    observations: list[tuple[pd.Timestamp, float]] = []

    for obs in root.findall(".//gen:Obs", NS):
        dimension = obs.find("gen:ObsDimension", NS)
        value = obs.find("gen:ObsValue", NS)
        if dimension is None or value is None:
            continue
        date = _parse_period(dimension.attrib.get("value", ""))
        if date is None:
            continue
        try:
            amount = float(value.attrib["value"])
        except (KeyError, ValueError):
            continue
        observations.append((date, amount))

    if observations:
        return _build_series(observations)

    for obs in root.findall(".//Obs"):
        date = _parse_period(obs.attrib.get("TIME_PERIOD") or obs.attrib.get("time_period") or obs.attrib.get("period"))
        if date is None:
            continue
        raw_value = obs.attrib.get("OBS_VALUE") or obs.attrib.get("obs_value") or obs.attrib.get("value")
        try:
            amount = float(raw_value)
        except (TypeError, ValueError):
            continue
        observations.append((date, amount))

    return _build_series(observations)


def fetch_insee_series(series_id: str, token: str = "", config: RequestConfig | None = None) -> pd.Series:
    config = config or RequestConfig()
    headers = {"Accept": "application/xml"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.get(
        INSEE_URL.format(series_id=series_id),
        headers=headers,
        timeout=config.timeout_seconds,
    )
    _raise_for_status(response, "Chargement INSEE")
    root = ET.fromstring(response.content)
    return _extract_insee_series(root)


def _guess_delimiter(sample: str) -> str:
    counts = {
        ';': sample.count(';'),
        ',': sample.count(','),
        '	': sample.count('	'),
        '|': sample.count('|'),
    }
    best = max(counts, key=counts.get)
    if counts[best] > 0:
        return best
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;	|").delimiter
    except Exception:
        return ";"


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized = {col.lower().strip(): col for col in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def read_bdf_export(content: bytes, filename: str) -> pd.Series:
    name = filename.lower()
    if name.endswith('.json'):
        frame = pd.read_json(io.BytesIO(content))
    else:
        text = content.decode('utf-8-sig', errors='replace')
        delimiter = _guess_delimiter(text[:2048])
        frame = pd.read_csv(io.StringIO(text), sep=delimiter)

    columns = [str(col) for col in frame.columns]
    date_col = _find_column(columns, [
        'time_period', 'time_period_start', 'period', 'date', 'date de reference', 'mois'
    ])
    value_col = _find_column(columns, [
        'obs_value', 'observation_value', 'value', 'valeur', 'taux', 'credit', 'production_credit'
    ])

    if date_col is None or value_col is None:
        raise DataLoadError(
            f"Impossible d'identifier les colonnes date/valeur dans {filename}. Colonnes vues: {columns}"
        )

    observations: list[tuple[pd.Timestamp, float]] = []
    for row in frame[[date_col, value_col]].itertuples(index=False):
        date = _parse_period(row[0])
        if date is None:
            continue
        raw = str(row[1]).replace('\u00a0', '').replace(' ', '').replace(',', '.')
        try:
            amount = float(raw)
        except ValueError:
            continue
        observations.append((date, amount))

    return _build_series(observations)


def read_bdf_export_file(path: str | Path) -> pd.Series:
    file_path = Path(path)
    if not file_path.exists():
        raise DataLoadError(f"Fichier BdF introuvable: {file_path}")
    return read_bdf_export(file_path.read_bytes(), file_path.name)


def split_bdf_combined_export(content: bytes, filename: str) -> dict[str, pd.Series]:
    name = filename.lower()
    if name.endswith('.json'):
        frame = pd.read_json(io.BytesIO(content))
    else:
        text = content.decode('utf-8-sig', errors='replace')
        delimiter = _guess_delimiter(text[:2048])
        frame = pd.read_csv(io.StringIO(text), sep=delimiter)

    columns = [str(col) for col in frame.columns]
    series_col = _find_column(columns, ['series_key', 'serie', 'series'])
    date_col = _find_column(columns, ['time_period', 'time_period_start', 'period', 'date'])
    value_col = _find_column(columns, ['obs_value', 'observation_value', 'value', 'valeur'])

    if series_col is None or date_col is None or value_col is None:
        raise DataLoadError(
            f"Impossible d'identifier les colonnes series/date/valeur dans {filename}. Colonnes vues: {columns}"
        )

    outputs: dict[str, list[tuple[pd.Timestamp, float]]] = {}
    for row in frame[[series_col, date_col, value_col]].itertuples(index=False):
        series_key = str(row[0]).strip()
        date = _parse_period(row[1])
        if not series_key or date is None:
            continue
        raw = str(row[2]).replace('\u00a0', '').replace(' ', '').replace(',', '.')
        try:
            amount = float(raw)
        except ValueError:
            continue
        outputs.setdefault(series_key, []).append((date, amount))

    return {key: _build_series(observations) for key, observations in outputs.items() if observations}


def split_bdf_combined_export_file(path: str | Path) -> dict[str, pd.Series]:
    file_path = Path(path)
    if not file_path.exists():
        raise DataLoadError(f"Fichier BdF introuvable: {file_path}")
    return split_bdf_combined_export(file_path.read_bytes(), file_path.name)


def combine_quarterly_view(price: pd.Series, rate: pd.Series, credit: pd.Series) -> pd.DataFrame:
    quarterly_price = price.resample("QE").last() if not price.empty else pd.Series(dtype=float)
    quarterly_rate = rate.resample("QE").mean() if not rate.empty else pd.Series(dtype=float)
    quarterly_credit = credit.resample("QE").sum(min_count=1) if not credit.empty else pd.Series(dtype=float)
    return pd.concat(
        [
            quarterly_price.rename("prix_logements"),
            quarterly_rate.rename("taux"),
            quarterly_credit.rename("production_credit"),
        ],
        axis=1,
    ).sort_index()


def normalize_base_100(series: pd.Series) -> pd.Series:
    clean = series.dropna()
    if clean.empty:
        return series.copy()
    return clean / clean.iloc[0] * 100


def latest_point(series: pd.Series) -> tuple[pd.Timestamp | None, float | None]:
    clean = series.dropna()
    if clean.empty:
        return None, None
    return clean.index[-1], float(clean.iloc[-1])
