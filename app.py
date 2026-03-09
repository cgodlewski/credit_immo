"""
Tableau de bord : Marché immobilier français
Sources : INSEE–Notaires (prix logements anciens) + Banque de France (taux & production crédits habitat)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import os

# ─────────────────────────────────────────────
# CONFIGURATION GÉNÉRALE
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Marché immobilier français",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Couleurs
C_TAUX_HR   = "#0A66C2"   # taux hors renégo
C_TAUX_YC   = "#E8612C"   # taux y compris renégo
C_INDEX     = "#003366"   # indice de prix
C_CREDIT    = "#4C9BE8"   # production crédit (barres)
C_GA        = "#0A66C2"   # glissement annuel
C_GT        = "#5DA9FF"   # glissement trimestriel

# ─────────────────────────────────────────────
# IDENTIFIANTS SÉRIES
# ─────────────────────────────────────────────

# INSEE — Indices Notaires-INSEE prix logements anciens
# France entière, ensemble, CVS, base 2015
INSEE_IDBANK_PRIX      = "010567059"   # série principale (indice niveau)

# INSEE — Glissements (annuel et trimestriel) pour la série France entière CVS
# Ces idbanks correspondent aux glissements de la même série
INSEE_IDBANK_GA        = "010567060"   # glissement annuel
INSEE_IDBANK_GT        = "010567061"   # glissement trimestriel

# BdF MIR1 — taux crédits habitat
BDF_SERIES_HR  = "MIR1.M.FR.B.A22.A.R.A.2254U6.EUR.N"   # hors renégociations
BDF_SERIES_YC  = "MIR1.M.FR.B.A22.A.R.A.2254U6.EUR.Y"   # y compris renégociations
# (si la clé YC n'existe pas, on tente une variante courante)

# BdF MIR1 — production mensuelle crédits habitat (encours nouveaux)
# Crédit à l'habitat total : production brute mensuelle en Mds EUR
BDF_SERIES_CRED = "MIR1.M.FR.B.A22.A.S.A.2254U6.EUR.N"   # flux totaux

# ─────────────────────────────────────────────
# FONCTIONS DE RÉCUPÉRATION
# ─────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)   # cache 24h
def fetch_insee_series(*idbanks: str) -> pd.DataFrame:
    """
    Récupère une ou plusieurs séries BDM INSEE par idbank.
    Retourne un DataFrame avec une colonne par série, indexé par date (fin de période).
    """
    ids = "+".join(idbanks)
    url = f"https://api.insee.fr/series/BDM/V1/data/SERIES_BDM/{ids}"
    headers = {"Accept": "application/xml"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    # Parsing SDMX-ML 2.1
    root = ET.fromstring(resp.content)
    ns = {
        "mes": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
        "gen": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic",
        "com": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
    }

    records: dict[str, dict] = {}   # idbank -> {period: value}

    for series in root.findall(".//gen:Series", ns):
        # Identifier: IDBANK is a SeriesKey value
        idbank_val = None
        for key_val in series.findall("gen:SeriesKey/gen:Value", ns):
            if key_val.attrib.get("id") == "IDBANK":
                idbank_val = key_val.attrib.get("value")
        if idbank_val is None:
            # fallback: take first series in order
            idbank_val = str(len(records))

        obs_dict = {}
        for obs in series.findall("gen:Obs", ns):
            period = obs.find("gen:ObsDimension", ns)
            value  = obs.find("gen:ObsValue", ns)
            if period is not None and value is not None:
                p = period.attrib.get("value", "")
                v = value.attrib.get("value", "")
                try:
                    obs_dict[p] = float(v)
                except ValueError:
                    pass
        records[idbank_val] = obs_dict

    # Construire un DataFrame commun
    dfs = []
    for idbank_val, obs in records.items():
        s = pd.Series(obs, name=idbank_val)
        s.index = pd.PeriodIndex(s.index).to_timestamp("Q")   # gère T1 1996, etc.
        dfs.append(s.sort_index())

    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, axis=1)
    df.index.name = "date"
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_bdf_series(series_key: str, api_key: str) -> pd.Series:
    """
    Récupère une série BdF Webstat via l'API SDMX.
    Retourne une pd.Series indexée par date (fin de mois).
    """
    dataset, key = series_key.split(".", 1)
    url = (
        f"https://api.webstat.banque-france.fr/webstat-fr/v1/data/{dataset}/{key}"
        f"?format=application/xml&detail=dataonly"
    )
    headers = {
        "Accept": "application/xml",
        "Authorization": f"Bearer {api_key}",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    # Namespace SDMX générique 2.1
    ns_gen = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic"
    ns = {"gen": ns_gen}

    periods, values = [], []
    for obs in root.findall(f".//{{{ns_gen}}}Obs"):
        dim = obs.find(f"{{{ns_gen}}}ObsDimension")
        val = obs.find(f"{{{ns_gen}}}ObsValue")
        if dim is not None and val is not None:
            try:
                # Format période : "2024-03" (YYYY-MM)
                p = pd.Period(dim.attrib["value"], freq="M").to_timestamp("M")
                v = float(val.attrib["value"])
                periods.append(p)
                values.append(v)
            except (ValueError, KeyError):
                pass

    s = pd.Series(values, index=periods, name=series_key).sort_index()
    return s


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.title("🏠 Marché immobilier")
    st.markdown("**Sources :** INSEE–Notaires · Banque de France")
    st.divider()

    # Clé API BdF
    bdf_key_env = os.environ.get("BDF_API_KEY", "")
    bdf_api_key = st.text_input(
        "Clé API Banque de France",
        value=bdf_key_env,
        type="password",
        help="Compte gratuit sur developer.webstat.banque-france.fr",
    )

    st.divider()

    # Onglet / vue
    vue = st.radio(
        "Vue",
        ["📈 Prix & taux", "💶 Crédit & taux", "📊 Prix — détail"],
        index=0,
    )

    st.divider()

    # Choix du taux
    taux_choice = st.radio(
        "Taux à afficher",
        ["Hors renégociations", "Y compris renégociations", "Les deux"],
        index=2,
    )

    # Période
    st.subheader("Période")
    year_start = st.slider("Depuis", 1990, datetime.now().year - 1, 2003)

    st.divider()
    st.caption(
        "Mise à jour automatique des données à chaque rechargement "
        "(cache 24 h). Les données INSEE sont mensuellement révisées."
    )

# ─────────────────────────────────────────────
# CHARGEMENT DES DONNÉES
# ─────────────────────────────────────────────

bdf_ok = bool(bdf_api_key.strip())

# --- INSEE ---
with st.spinner("Chargement des données INSEE…"):
    try:
        df_insee = fetch_insee_series(
            INSEE_IDBANK_PRIX, INSEE_IDBANK_GA, INSEE_IDBANK_GT
        )
        df_insee = df_insee.rename(columns={
            INSEE_IDBANK_PRIX: "index_prix",
            INSEE_IDBANK_GA:   "gliss_annuel",
            INSEE_IDBANK_GT:   "gliss_trim",
        })
        insee_ok = True
    except Exception as e:
        st.error(f"Erreur INSEE : {e}")
        df_insee = pd.DataFrame()
        insee_ok = False

# --- BdF taux & crédit ---
df_taux_hr = pd.Series(dtype=float, name="taux_hr")
df_taux_yc = pd.Series(dtype=float, name="taux_yc")
df_credit  = pd.Series(dtype=float, name="credit")

if bdf_ok:
    with st.spinner("Chargement des données Banque de France…"):
        try:
            df_taux_hr = fetch_bdf_series(BDF_SERIES_HR, bdf_api_key)
            df_taux_hr.name = "taux_hr"
        except Exception as e:
            st.warning(f"BdF taux hors renégo : {e}")

        try:
            df_taux_yc = fetch_bdf_series(BDF_SERIES_YC, bdf_api_key)
            df_taux_yc.name = "taux_yc"
        except Exception as e:
            st.warning(f"BdF taux y.c. renégo : {e}")

        try:
            df_credit = fetch_bdf_series(BDF_SERIES_CRED, bdf_api_key)
            df_credit.name = "credit"
        except Exception as e:
            st.warning(f"BdF production crédit : {e}")
else:
    st.info(
        "💡 Entrez votre clé API Banque de France dans la barre latérale "
        "pour afficher les données de taux et de production de crédits. "
        "Compte gratuit : developer.webstat.banque-france.fr"
    )

# Filtrer sur la période sélectionnée
start_ts = pd.Timestamp(year_start, 1, 1)

if not df_insee.empty:
    df_insee = df_insee[df_insee.index >= start_ts]

for s in (df_taux_hr, df_taux_yc, df_credit):
    s.drop(s.index[s.index < start_ts], inplace=True)


# ─────────────────────────────────────────────
# HELPERS GRAPHIQUES
# ─────────────────────────────────────────────

def add_recession_bands(fig, row=1, col=1):
    """Ajoute des bandes grises pour les crises notables."""
    crises = [
        ("2008-09-01", "2009-06-30", "Crise financière"),
        ("2020-03-01", "2020-06-30", "COVID-19"),
    ]
    for start, end, label in crises:
        fig.add_vrect(
            x0=start, x1=end,
            fillcolor="grey", opacity=0.12, line_width=0,
            annotation_text=label, annotation_position="top left",
            annotation_font_size=9,
            row=row, col=col,
        )

def last_obs_annotation(fig, series: pd.Series, row=1, col=1, color="grey"):
    """Ajoute une annotation sur le dernier point disponible."""
    if series.empty:
        return
    last_date = series.dropna().index[-1]
    last_val  = series.dropna().iloc[-1]
    fig.add_annotation(
        x=last_date, y=last_val,
        text=f"  {last_val:.2f}",
        showarrow=False, xanchor="left",
        font=dict(size=10, color=color),
        row=row, col=col,
    )


# ─────────────────────────────────────────────
# VUE 1 : PRIX & TAUX
# ─────────────────────────────────────────────

if vue == "📈 Prix & taux":
    st.header("Prix des logements anciens & taux des crédits habitat")
    st.caption(
        "Indice Notaires-INSEE (France entière, CVS, base 2015=100) — "
        "Taux BdF MIR (crédits nouveaux à l'habitat, ménages)"
    )

    if df_insee.empty:
        st.warning("Données INSEE non disponibles.")
    else:
        # Agréger le taux mensuel en moyenne trimestrielle
        def to_quarterly_mean(s: pd.Series) -> pd.Series:
            return s.resample("QE").mean()

        taux_hr_q = to_quarterly_mean(df_taux_hr) if not df_taux_hr.empty else pd.Series(dtype=float)
        taux_yc_q = to_quarterly_mean(df_taux_yc) if not df_taux_yc.empty else pd.Series(dtype=float)

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # — Indice de prix (axe droit) —
        if "index_prix" in df_insee.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_insee.index, y=df_insee["index_prix"],
                    name="Indice des prix (base 2015=100)",
                    line=dict(color=C_INDEX, width=2.5),
                    hovertemplate="%{x|%Y-T%q}<br>Indice : %{y:.1f}<extra></extra>",
                ),
                secondary_y=True,
            )

        # — Taux (axe gauche) —
        if taux_choice in ("Hors renégociations", "Les deux") and not taux_hr_q.empty:
            fig.add_trace(
                go.Scatter(
                    x=taux_hr_q.index, y=taux_hr_q,
                    name="Taux hors renégociations (%)",
                    line=dict(color=C_TAUX_HR, width=2),
                    hovertemplate="%{x|%Y-T%q}<br>Taux : %{y:.2f}%<extra></extra>",
                ),
                secondary_y=False,
            )
        if taux_choice in ("Y compris renégociations", "Les deux") and not taux_yc_q.empty:
            fig.add_trace(
                go.Scatter(
                    x=taux_yc_q.index, y=taux_yc_q,
                    name="Taux y.c. renégociations (%)",
                    line=dict(color=C_TAUX_YC, width=2, dash="dot"),
                    hovertemplate="%{x|%Y-T%q}<br>Taux : %{y:.2f}%<extra></extra>",
                ),
                secondary_y=False,
            )

        add_recession_bands(fig)

        fig.update_layout(
            title=dict(
                text="Marché du logement ancien en France : prix et conditions de crédit",
                font=dict(size=17),
            ),
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.15),
            height=520,
            margin=dict(t=70, b=60),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        fig.update_xaxes(showgrid=True, gridcolor="#eee", title_text="")
        fig.update_yaxes(title_text="Taux des crédits (%)", secondary_y=False,
                         showgrid=True, gridcolor="#eee", zeroline=True,
                         zerolinecolor="#bbb")
        fig.update_yaxes(title_text="Indice des prix (2015=100)", secondary_y=True,
                         showgrid=False)

        st.plotly_chart(fig, use_container_width=True)

        # Métriques rapides
        col1, col2, col3 = st.columns(3)
        if "index_prix" in df_insee.columns and not df_insee["index_prix"].dropna().empty:
            last_idx = df_insee["index_prix"].dropna().iloc[-1]
            prev_idx = df_insee["index_prix"].dropna().iloc[-5] if len(df_insee["index_prix"].dropna()) >= 5 else None
            delta_str = f"{(last_idx/prev_idx - 1)*100:+.1f}% (1 an)" if prev_idx else None
            col1.metric("Indice des prix (dernier)", f"{last_idx:.1f}", delta_str)

        if not taux_hr_q.empty:
            last_t = taux_hr_q.dropna().iloc[-1]
            prev_t = taux_hr_q.dropna().iloc[-4] if len(taux_hr_q.dropna()) >= 4 else None
            d = f"{last_t - prev_t:+.2f}pp (1 an)" if prev_t else None
            col2.metric("Taux hors renégo (dernier)", f"{last_t:.2f}%", d)

        if not taux_yc_q.empty:
            last_t2 = taux_yc_q.dropna().iloc[-1]
            prev_t2 = taux_yc_q.dropna().iloc[-4] if len(taux_yc_q.dropna()) >= 4 else None
            d2 = f"{last_t2 - prev_t2:+.2f}pp (1 an)" if prev_t2 else None
            col3.metric("Taux y.c. renégo (dernier)", f"{last_t2:.2f}%", d2)


# ─────────────────────────────────────────────
# VUE 2 : CRÉDIT & TAUX
# ─────────────────────────────────────────────

elif vue == "💶 Crédit & taux":
    st.header("Production de crédits à l'habitat & taux")
    st.caption(
        "Production mensuelle de crédits nouveaux à l'habitat (Mds €) — "
        "Taux BdF MIR (crédits nouveaux, ménages)"
    )

    if not bdf_ok:
        st.warning("Clé API BdF requise pour cette vue.")
    elif df_taux_hr.empty and df_taux_yc.empty:
        st.warning("Données BdF de taux non disponibles.")
    else:
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # — Barres : production crédit (axe droit) —
        if not df_credit.empty:
            fig.add_trace(
                go.Bar(
                    x=df_credit.index, y=df_credit,
                    name="Production crédits (Mds €)",
                    marker_color=C_CREDIT, opacity=0.45,
                    hovertemplate="%{x|%b %Y}<br>Production : %{y:.1f} Mds €<extra></extra>",
                ),
                secondary_y=True,
            )

        # — Taux (axe gauche) —
        if taux_choice in ("Hors renégociations", "Les deux") and not df_taux_hr.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_taux_hr.index, y=df_taux_hr,
                    name="Taux hors renégociations (%)",
                    line=dict(color=C_TAUX_HR, width=2),
                    hovertemplate="%{x|%b %Y}<br>Taux : %{y:.2f}%<extra></extra>",
                ),
                secondary_y=False,
            )
        if taux_choice in ("Y compris renégociations", "Les deux") and not df_taux_yc.empty:
            fig.add_trace(
                go.Scatter(
                    x=df_taux_yc.index, y=df_taux_yc,
                    name="Taux y.c. renégociations (%)",
                    line=dict(color=C_TAUX_YC, width=2, dash="dot"),
                    hovertemplate="%{x|%b %Y}<br>Taux : %{y:.2f}%<extra></extra>",
                ),
                secondary_y=False,
            )

        add_recession_bands(fig)

        fig.update_layout(
            title=dict(
                text="Crédits à l'habitat : taux et production mensuelle",
                font=dict(size=17),
            ),
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.15),
            height=520,
            barmode="overlay",
            margin=dict(t=70, b=60),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        fig.update_xaxes(showgrid=True, gridcolor="#eee")
        fig.update_yaxes(title_text="Taux (%)", secondary_y=False,
                         showgrid=True, gridcolor="#eee", zeroline=True,
                         zerolinecolor="#bbb")
        fig.update_yaxes(title_text="Production mensuelle (Mds €)", secondary_y=True,
                         showgrid=False)

        st.plotly_chart(fig, use_container_width=True)

        # Métriques
        col1, col2, col3 = st.columns(3)
        if not df_credit.empty:
            last_c = df_credit.dropna().iloc[-1]
            prev_c = df_credit.dropna().iloc[-12] if len(df_credit.dropna()) >= 12 else None
            d = f"{last_c - prev_c:+.1f} Mds€ (1 an)" if prev_c else None
            col1.metric("Production mensuelle (dernier)", f"{last_c:.1f} Mds €", d)

        if not df_taux_hr.empty:
            last_t = df_taux_hr.dropna().iloc[-1]
            col2.metric("Taux hors renégo (dernier mois)", f"{last_t:.2f}%")

        if not df_taux_yc.empty:
            last_t2 = df_taux_yc.dropna().iloc[-1]
            col3.metric("Taux y.c. renégo (dernier mois)", f"{last_t2:.2f}%")


# ─────────────────────────────────────────────
# VUE 3 : PRIX — DÉTAIL
# ─────────────────────────────────────────────

elif vue == "📊 Prix — détail":
    st.header("Indices Notaires-INSEE — Prix des logements anciens (détail)")
    st.caption(
        "France entière · CVS · Base 2015=100 · "
        "Glissements annuel et trimestriel"
    )

    if df_insee.empty:
        st.warning("Données INSEE non disponibles.")
    else:
        df_plot = df_insee.dropna(subset=["index_prix"])

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Glissement annuel (axe gauche)
        if "gliss_annuel" in df_plot.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_plot.index, y=df_plot["gliss_annuel"],
                    name="Glissement annuel (%)",
                    line=dict(color=C_GA, width=2),
                    hovertemplate="%{x|%Y-T%q}<br>Var. annuelle : %{y:.1f}%<extra></extra>",
                ),
                secondary_y=False,
            )
        # Glissement trimestriel (axe gauche)
        if "gliss_trim" in df_plot.columns:
            fig.add_trace(
                go.Scatter(
                    x=df_plot.index, y=df_plot["gliss_trim"],
                    name="Glissement trimestriel (%)",
                    line=dict(color=C_GT, width=1.5, dash="dash"),
                    hovertemplate="%{x|%Y-T%q}<br>Var. trim. : %{y:.1f}%<extra></extra>",
                ),
                secondary_y=False,
            )
        # Zéro
        fig.add_hline(y=0, line_width=1, line_dash="dot", line_color="#777")

        # Indice de niveau (axe droit)
        fig.add_trace(
            go.Scatter(
                x=df_plot.index, y=df_plot["index_prix"],
                name="Indice (base 2015=100)",
                line=dict(color=C_INDEX, width=2.5),
                hovertemplate="%{x|%Y-T%q}<br>Indice : %{y:.1f}<extra></extra>",
            ),
            secondary_y=True,
        )

        add_recession_bands(fig)

        fig.update_layout(
            title=dict(
                text="Indices Notaires-INSEE des prix des logements anciens",
                font=dict(size=17),
            ),
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.15),
            height=530,
            margin=dict(t=70, b=60),
            plot_bgcolor="white",
            paper_bgcolor="white",
        )
        fig.update_xaxes(showgrid=True, gridcolor="#eee",
                         tickformat="%Y", dtick="M12")
        fig.update_yaxes(title_text="Variation des prix (%)", secondary_y=False,
                         showgrid=True, gridcolor="#eee")
        fig.update_yaxes(title_text="Indice des prix (2015=100)", secondary_y=True,
                         showgrid=False)

        st.plotly_chart(fig, use_container_width=True)

        # Métriques
        if not df_plot.empty:
            col1, col2, col3 = st.columns(3)
            last_row = df_plot.dropna(subset=["index_prix"]).iloc[-1]
            col1.metric("Indice (dernier trimestre)", f"{last_row['index_prix']:.1f}")
            if "gliss_annuel" in df_plot.columns:
                col2.metric("Glissement annuel", f"{last_row['gliss_annuel']:.1f}%")
            if "gliss_trim" in df_plot.columns:
                col3.metric("Glissement trimestriel", f"{last_row['gliss_trim']:.1f}%")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────

st.divider()
st.caption(
    "**Sources :** INSEE–Notaires (*Indices des prix des logements anciens*, "
    "série 010567059, France entière CVS base 2015) · "
    "Banque de France (*MIR1 – Taux des crédits nouveaux à l'habitat des particuliers*, "
    "séries MIR1.M.FR.B.A22…) · "
    f"Extraction : {datetime.now().strftime('%d/%m/%Y %H:%M')}"
)
