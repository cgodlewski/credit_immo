from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard.charts import (
    build_credit_rate_figure,
    build_normalized_figure,
    build_price_rate_figure,
)
from dashboard.config import (
    DEFAULT_BDF_CREDIT_ALL_SERIES,
    DEFAULT_BDF_CREDIT_EXCL_SERIES,
    DEFAULT_BDF_RATE_SERIES,
    DEFAULT_INSEE_PRICE_SERIES,
)
from dashboard.data import (
    DataLoadError,
    combine_quarterly_view,
    fetch_insee_series,
    latest_point,
    normalize_base_100,
    split_bdf_combined_export,
    split_bdf_combined_export_file,
)


st.set_page_config(
    page_title="Immobilier et credit en France",
    page_icon="house",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_BDF_COMBINED_FILE = Path("data/webstat_export_3_series.csv")
LEGACY_BDF_COMBINED_FILE = Path("Webstat_Export_3_series.csv")


def _metric_delta(series: pd.Series, periods_back: int, suffix: str) -> str | None:
    clean = series.dropna()
    if len(clean) <= periods_back:
        return None
    current = clean.iloc[-1]
    previous = clean.iloc[-(periods_back + 1)]
    if previous == 0:
        return None
    if suffix == "%":
        return f"{(current / previous - 1) * 100:+.1f}%"
    return f"{current - previous:+.2f}{suffix}"


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def load_insee_data(insee_series: str) -> pd.Series:
    return fetch_insee_series(insee_series, "").rename("prix_logements")


@st.cache_data(show_spinner=False)
def load_bdf_combined_file(path: str) -> dict[str, pd.Series]:
    return split_bdf_combined_export_file(path)


st.title("Immobilier et credit en France")
st.caption("Prix des logements anciens, taux et production de credits.")

with st.sidebar:
    st.header("Configuration")
    start_year = st.slider("Debut", min_value=1996, max_value=2026, value=2003)
    credit_view = st.radio(
        "Serie de production credit",
        options=["Tous flux", "Hors renegociations"],
        index=0,
    )
    st.subheader("Banque de France")
    st.caption("Fichier recommande: `data/webstat_export_3_series.csv`.")
    upload_bdf = st.file_uploader("Upload export BdF multi-series", type=["csv", "json"], key="bdf_combined")
    with st.expander("Fichier BdF"):
        default_path = DEFAULT_BDF_COMBINED_FILE if DEFAULT_BDF_COMBINED_FILE.exists() else LEGACY_BDF_COMBINED_FILE
        local_bdf_path = st.text_input("Chemin du fichier export", value=str(default_path))
    with st.expander("Series techniques"):
        insee_series = st.text_input("INSEE prix", value=DEFAULT_INSEE_PRICE_SERIES)
        st.text_input("BdF taux", value=DEFAULT_BDF_RATE_SERIES, disabled=True)
        st.text_input("BdF production credit tous flux", value=DEFAULT_BDF_CREDIT_ALL_SERIES, disabled=True)
        st.text_input("BdF production credit hors renegociations", value=DEFAULT_BDF_CREDIT_EXCL_SERIES, disabled=True)

default_start = pd.Timestamp(start_year, 1, 1)

load_errors: list[str] = []
price = pd.Series(dtype=float, name="prix_logements")
rate = pd.Series(dtype=float, name="taux")
credit_all = pd.Series(dtype=float, name="production_credit_all")
credit_excl = pd.Series(dtype=float, name="production_credit_excl")

try:
    with st.spinner("Chargement INSEE..."):
        price = load_insee_data(insee_series=insee_series)
        price = price.loc[lambda s: s.index >= default_start]
except DataLoadError as exc:
    load_errors.append(f"INSEE: {exc}")

try:
    if upload_bdf is not None:
        combined = split_bdf_combined_export(upload_bdf.getvalue(), upload_bdf.name)
    else:
        combined = load_bdf_combined_file(local_bdf_path)

    if DEFAULT_BDF_RATE_SERIES not in combined:
        raise DataLoadError(f"Serie taux absente du fichier BdF: {DEFAULT_BDF_RATE_SERIES}")
    if DEFAULT_BDF_CREDIT_ALL_SERIES not in combined:
        raise DataLoadError(f"Serie credit tous flux absente du fichier BdF: {DEFAULT_BDF_CREDIT_ALL_SERIES}")
    if DEFAULT_BDF_CREDIT_EXCL_SERIES not in combined:
        raise DataLoadError(f"Serie credit hors renegociations absente du fichier BdF: {DEFAULT_BDF_CREDIT_EXCL_SERIES}")

    rate = combined[DEFAULT_BDF_RATE_SERIES].rename("taux").loc[lambda s: s.index >= default_start]
    credit_all = combined[DEFAULT_BDF_CREDIT_ALL_SERIES].rename("production_credit_all").loc[lambda s: s.index >= default_start]
    credit_excl = combined[DEFAULT_BDF_CREDIT_EXCL_SERIES].rename("production_credit_excl").loc[lambda s: s.index >= default_start]
except DataLoadError as exc:
    load_errors.append(f"Banque de France: {exc}")

for error in load_errors:
    st.error(error)

if price.empty and rate.empty and credit_all.empty and credit_excl.empty:
    st.stop()

selected_credit = credit_all if credit_view == "Tous flux" else credit_excl
selected_credit_name = "Production de credit tous flux" if credit_view == "Tous flux" else "Production de credit hors renegociations"

quarterly = combine_quarterly_view(price=price, rate=rate, credit=selected_credit)
normalized_parts: list[pd.Series] = []
if not quarterly["prix_logements"].dropna().empty:
    normalized_parts.append(normalize_base_100(quarterly["prix_logements"]).rename("Prix logements"))
if not quarterly["taux"].dropna().empty:
    normalized_parts.append(normalize_base_100(quarterly["taux"]).rename("Taux"))
if not quarterly["production_credit"].dropna().empty:
    normalized_parts.append(normalize_base_100(quarterly["production_credit"]).rename(selected_credit_name))
normalized = pd.concat(normalized_parts, axis=1).dropna(how="all") if normalized_parts else pd.DataFrame()

latest_price_date, latest_price_value = latest_point(price)
latest_rate_date, latest_rate_value = latest_point(rate)
latest_credit_date, latest_credit_value = latest_point(selected_credit)

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Prix logements", f"{latest_price_value:.1f}" if latest_price_value is not None else "n/a", _metric_delta(price, 4, "%"))
metric_2.metric("Taux", f"{latest_rate_value:.2f}%" if latest_rate_value is not None else "n/a", _metric_delta(rate, 12, " pt"))
metric_3.metric(selected_credit_name, f"{latest_credit_value:.1f}" if latest_credit_value is not None else "n/a", _metric_delta(selected_credit, 12, ""))

tab_1, tab_2, tab_3 = st.tabs(["Prix + taux", "Credit + taux", "Serie normalisee"])

with tab_1:
    if price.dropna().empty:
        st.info("Vue indisponible tant que la serie INSEE n'est pas chargee.")
    elif rate.dropna().empty:
        st.info("Vue indisponible tant que la serie de taux Banque de France n'est pas chargee.")
    else:
        st.plotly_chart(build_price_rate_figure(price=price, rate=rate, rate_name="Taux"), use_container_width=True)

with tab_2:
    if selected_credit.dropna().empty or rate.dropna().empty:
        st.info("Vue indisponible tant que le fichier Banque de France n'est pas charge.")
    else:
        st.plotly_chart(build_credit_rate_figure(credit=selected_credit, rate=rate, rate_name="Taux"), use_container_width=True)

with tab_3:
    if normalized.empty or normalized.shape[1] < 2:
        st.info("Il faut au moins deux series chargees pour afficher la comparaison normalisee.")
    else:
        st.plotly_chart(build_normalized_figure(normalized), use_container_width=True)
        st.caption("Normalisation base 100 sur la premiere date commune disponible apres filtrage.")

st.divider()
st.caption("Sources: INSEE, Banque de France")
