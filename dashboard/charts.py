from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _base_layout(title: str) -> dict:
    return {
        "title": {"text": title},
        "hovermode": "x unified",
        "height": 520,
        "legend": {"orientation": "h", "y": -0.18},
        "plot_bgcolor": "white",
        "paper_bgcolor": "white",
        "margin": {"t": 70, "b": 60},
    }


def build_price_rate_figure(price: pd.Series, rate: pd.Series, rate_name: str) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Scatter(
            x=rate.index,
            y=rate.values,
            name=rate_name,
            line={"color": "#0A66C2", "width": 2},
            hovertemplate="%{x|%Y-%m}<br>Taux: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=price.index,
            y=price.values,
            name="Prix logements anciens",
            line={"color": "#003366", "width": 2.5},
            hovertemplate="%{x|%Y-%m}<br>Indice: %{y:.1f}<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.update_layout(**_base_layout("Prix des logements anciens et taux de credit"))
    figure.update_xaxes(showgrid=True, gridcolor="#EAEAEA")
    figure.update_yaxes(title_text="Taux (%)", secondary_y=False, showgrid=True, gridcolor="#EAEAEA")
    figure.update_yaxes(title_text="Indice de prix", secondary_y=True, showgrid=False)
    return figure


def build_credit_rate_figure(credit: pd.Series, rate: pd.Series, rate_name: str) -> go.Figure:
    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Bar(
            x=credit.index,
            y=credit.values,
            name="Production de credit",
            marker_color="#9CC5E9",
            opacity=0.7,
            hovertemplate="%{x|%Y-%m}<br>Credit: %{y:.1f}<extra></extra>",
        ),
        secondary_y=True,
    )
    figure.add_trace(
        go.Scatter(
            x=rate.index,
            y=rate.values,
            name=rate_name,
            line={"color": "#E8612C", "width": 2},
            hovertemplate="%{x|%Y-%m}<br>Taux: %{y:.2f}%<extra></extra>",
        ),
        secondary_y=False,
    )
    figure.update_layout(**_base_layout("Production de credit et taux"))
    figure.update_xaxes(showgrid=True, gridcolor="#EAEAEA")
    figure.update_yaxes(title_text="Taux (%)", secondary_y=False, showgrid=True, gridcolor="#EAEAEA")
    figure.update_yaxes(title_text="Production de credit", secondary_y=True, showgrid=False)
    return figure


def build_normalized_figure(data: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    palette = ["#003366", "#0A66C2", "#E8612C"]
    for color, column in zip(palette, data.columns):
        figure.add_trace(
            go.Scatter(
                x=data.index,
                y=data[column],
                name=column,
                line={"width": 2, "color": color},
                hovertemplate="%{x|%Y-%m}<br>%{y:.1f}<extra></extra>",
            )
        )
    figure.update_layout(**_base_layout("Prix, taux et credit en base 100"))
    figure.update_xaxes(showgrid=True, gridcolor="#EAEAEA")
    figure.update_yaxes(title_text="Base 100", showgrid=True, gridcolor="#EAEAEA")
    return figure
