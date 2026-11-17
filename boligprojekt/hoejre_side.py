"""Højre side af dashboardet: låneberegner + kort over kommuner med regionsvalg.

Kræver i samme mappe:
  priser_kommuner.csv  (fra fetch_finansdk.py, Finans Danmark BM010, kr. pr. m2)
  kommuner.geojson     (kommunegrænser, forenklet fra DAGI)

Kør alene:      python hoejre_side.py   og åbn 127.0.0.1:8004
Brug i app.py:  import hoejre_side
                app.layout = html.Div([..., hoejre_side.layout()])
                hoejre_side.register_callbacks(app)
"""
import json
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html

MAPPE = Path(__file__).parent

# Lånelogik (samme antagelser som app.py, skal verificeres)
GAELDSFAKTOR = 4
MIN_EGENBETALING = 0.05

# Farver: én farve lys til mørk for pris, orange kant for "inden for budget"
PRISSKALA = "Blues"
BUDGETFARVE = "#E66101"
INGEN_DATA = "#DDDDDD"

KBH = "København og omegn"
KBH_LANDSDELE = ["Landsdel København by", "Landsdel Københavns omegn"]

# ---------- Data ----------
with open(MAPPE / "kommuner.geojson", encoding="utf-8") as f:
    GEO = json.load(f)

raa = pd.read_csv(MAPPE / "priser_kommuner.csv")

# Filen er sorteret hierarkisk: Region, Landsdel, kommuner. Brug rækkefølgen til at finde region.
region_for, landsdel_for, region, landsdel = {}, {}, None, None
for kode, navn in raa[["kode", "navn"]].drop_duplicates().itertuples(index=False):
    if navn.startswith("Region"):
        region = navn
    elif navn.startswith("Landsdel"):
        landsdel = navn
    elif navn != "Hele landet":
        region_for[kode], landsdel_for[kode] = region, landsdel

# Gennemsnit af de seneste 4 kvartaler (små kommuner har få handler pr. kvartal)
seneste = sorted(raa["tid"].unique())[-4:]
PERIODE = f"{seneste[0]} til {seneste[-1]}"
priser = (raa[raa["tid"].isin(seneste) & raa["kode"].isin(region_for)]
          .groupby(["kode", "navn", "kategori"], as_index=False)["kr_pr_m2"].mean())
priser["region"] = priser["kode"].map(region_for)
priser["landsdel"] = priser["kode"].map(landsdel_for)

KATEGORIER = sorted(priser["kategori"].unique(), reverse=True)  # Parcel-/rækkehus først
REGIONER = ["Hele landet"] + sorted(set(region_for.values())) + [KBH]


def _punkter(coords):
    if isinstance(coords[0], (int, float)):
        yield coords
    else:
        for c in coords:
            yield from _punkter(c)


GRAENSER = {}  # kode -> (lon_min, lat_min, lon_max, lat_max)
for feat in GEO["features"]:
    pts = list(_punkter(feat["geometry"]["coordinates"]))
    GRAENSER[feat["id"]] = (min(p[0] for p in pts), min(p[1] for p in pts),
                            max(p[0] for p in pts), max(p[1] for p in pts))


def koder_i(region):
    if region == "Hele landet":
        return list(region_for)
    if region == KBH:
        return [k for k, l in landsdel_for.items() if l in KBH_LANDSDELE]
    return [k for k, r in region_for.items() if r == region]


def udsnit(koder, bredde=560, hoejde=480):
    """Center og zoom, så de valgte kommuner fylder kortet."""
    b = [GRAENSER[k] for k in koder if k in GRAENSER]
    lon0, lat0 = min(x[0] for x in b), min(x[1] for x in b)
    lon1, lat1 = max(x[2] for x in b), max(x[3] for x in b)

    def merc(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    zoom_lon = math.log2(bredde * 360 / (512 * (lon1 - lon0)))
    zoom_lat = math.log2(hoejde * 2 * math.pi / (512 * (merc(lat1) - merc(lat0))))
    return {"lon": (lon0 + lon1) / 2, "lat": (lat0 + lat1) / 2}, min(zoom_lon, zoom_lat) - 0.3


def kr(x):
    return f"{x:,.0f}".replace(",", ".") + " kr."


def maks_koebspris(indkomst, opsparing, gaeld):
    maks_laan = max(0, indkomst * GAELDSFAKTOR - gaeld)
    return min(maks_laan + opsparing, opsparing / MIN_EGENBETALING)


# ---------- Figur ----------
# Virker både med ny plotly (Choroplethmap) og ældre (Choroplethmapbox)
NY = hasattr(go, "Choroplethmap")
Choro = go.Choroplethmap if NY else go.Choroplethmapbox
KORT = "map" if NY else "mapbox"
# "white-bg" virker uden internet. Skift til "carto-positron" for baggrundskort med bynavne.
KORTSTIL = "white-bg"


def lav_kort(region, kategori, m2, maks_pris):
    d = priser[(priser["kategori"] == kategori) & priser["kode"].isin(koder_i(region))].copy()
    d["pris"] = d["kr_pr_m2"] * m2
    d["budget"] = d["pris"] <= maks_pris
    alle = priser.loc[priser["kategori"] == kategori, "kr_pr_m2"] * m2  # fast skala for hele landet

    har = d.dropna(subset=["pris"])
    mangler = d[d["pris"].isna()]
    inden = har[har["budget"]]

    fig = go.Figure()
    if len(mangler):
        fig.add_trace(Choro(
            geojson=GEO, locations=mangler["kode"], z=[0] * len(mangler),
            colorscale=[[0, INGEN_DATA], [1, INGEN_DATA]], showscale=False,
            marker_line_color="white", marker_line_width=0.5,
            text=mangler["navn"], hovertemplate="<b>%{text}</b><br>Ingen handler i perioden<extra></extra>"))
    fig.add_trace(Choro(
        geojson=GEO, locations=har["kode"], z=har["pris"] / 1e6,
        zmin=0, zmax=float(alle.max()) / 1e6, colorscale=PRISSKALA,
        marker_line_color="white", marker_line_width=0.5,
        colorbar={"title": {"text": f"Pris for {m2} m²<br>(mio. kr.)"}, "thickness": 12, "len": 0.8},
        text=har["navn"],
        customdata=list(zip(har["kr_pr_m2"].map(kr), har["pris"].map(kr),
                            har["budget"].map({True: "Inden for budget", False: "Over budget"}))),
        hovertemplate="<b>%{text}</b><br>%{customdata[0]} pr. m²<br>"
                      f"{m2} m²: " + "%{customdata[1]}<br>%{customdata[2]}<extra></extra>"))
    if len(inden):  # orange kant = inden for budget (kan også ses i sort/hvid)
        fig.add_trace(Choro(
            geojson=GEO, locations=inden["kode"], z=[0] * len(inden),
            colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
            marker_line_color=BUDGETFARVE, marker_line_width=1.5 if region == "Hele landet" else 2.5, hoverinfo="skip"))

    center, zoom = udsnit(list(d["kode"]))
    fig.update_layout(**{KORT: {"style": KORTSTIL, "center": center, "zoom": zoom}},
                      margin={"l": 0, "r": 0, "t": 0, "b": 0}, height=480, uirevision=region)
    return fig, len(inden), len(har), len(mangler)


# ---------- Layout ----------
FELT = {"display": "flex", "flexDirection": "column", "gap": "4px", "fontSize": "14px"}
INPUT = {"padding": "6px", "fontSize": "15px", "width": "100%", "boxSizing": "border-box"}


def layout():
    return html.Div(style={"fontFamily": "sans-serif", "maxWidth": "640px"}, children=[
        html.H3("Låneberegner", style={"margin": "0 0 8px"}),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr", "gap": "12px"}, children=[
            html.Div(style=FELT, children=[
                html.Label("Bruttoindkomst (kr./år)"),
                dcc.Input(id="hs-indkomst", type="number", value=600000, step=10000, min=0, style=INPUT)]),
            html.Div(style=FELT, children=[
                html.Label("Opsparing (kr.)"),
                dcc.Input(id="hs-opsparing", type="number", value=200000, step=10000, min=0, style=INPUT)]),
            html.Div(style=FELT, children=[
                html.Label("Anden gæld (kr.)"),
                dcc.Input(id="hs-gaeld", type="number", value=0, step=10000, min=0, style=INPUT)]),
        ]),
        html.Div(id="hs-resultat", style={"margin": "12px 0", "padding": "10px 12px",
                                          "background": "#F3F6FA", "borderRadius": "6px"}),

        html.H3("Kort", style={"margin": "16px 0 8px"}),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "12px"}, children=[
            html.Div(style=FELT, children=[
                html.Label("Region"),
                dcc.Dropdown(id="hs-region", options=REGIONER, value="Hele landet", clearable=False)]),
            html.Div(style=FELT, children=[
                html.Label("Boligtype"),
                dcc.Dropdown(id="hs-kategori", options=KATEGORIER, value=KATEGORIER[0], clearable=False)]),
        ]),
        html.Div(style={**FELT, "marginTop": "12px"}, children=[
            html.Label("Boligstørrelse (m²)"),
            dcc.Slider(id="hs-m2", min=40, max=200, step=10, value=80,
                       marks={m: str(m) for m in range(40, 201, 40)})]),
        html.Div(id="hs-status", style={"margin": "16px 0 6px", "fontSize": "14px"}),
        dcc.Graph(id="hs-kort", config={"displayModeBar": False, "scrollZoom": True}),
        html.Div(f"Kilde: Finans Danmark (BM010), realiseret handelspris pr. m², gennemsnit {PERIODE}. "
                 f"Lånegrænse: {GAELDSFAKTOR} x indkomst og mindst {MIN_EGENBETALING:.0%} egenbetaling (antagelse).",
                 style={"fontSize": "12px", "color": "#666", "marginTop": "6px"}),
    ])


# ---------- Callback ----------
def register_callbacks(app):
    @app.callback(
        Output("hs-resultat", "children"),
        Output("hs-status", "children"),
        Output("hs-kort", "figure"),
        Input("hs-indkomst", "value"),
        Input("hs-opsparing", "value"),
        Input("hs-gaeld", "value"),
        Input("hs-region", "value"),
        Input("hs-kategori", "value"),
        Input("hs-m2", "value"),
    )
    def opdater(indkomst, opsparing, gaeld, region, kategori, m2):
        indkomst, opsparing, gaeld = indkomst or 0, opsparing or 0, gaeld or 0
        maks = maks_koebspris(indkomst, opsparing, gaeld)
        laan = max(0, maks - opsparing)
        resultat = [
            html.Div("Din maks. købspris", style={"fontSize": "13px", "color": "#555"}),
            html.Div(kr(maks), style={"fontSize": "26px", "fontWeight": "bold"}),
            html.Div(f"Lån: {kr(laan)}  |  Egenbetaling: {kr(min(opsparing, maks))}",
                     style={"fontSize": "13px", "color": "#555"}),
        ]
        fig, inden, med_data, mangler = lav_kort(region, kategori, m2, maks)
        status = [
            html.Span("▢ ", style={"color": BUDGETFARVE, "fontWeight": "bold", "fontSize": "18px"}),
            html.B(f"{inden} af {med_data} kommuner"),
            f" er inden for budget ({kategori.lower()}, {m2} m²).",
            f" {mangler} uden handler (grå)." if mangler else "",
        ]
        return resultat, status, fig

    return opdater


if __name__ == "__main__":
    app = Dash(__name__)
    app.layout = html.Div(style={"padding": "16px"}, children=[layout()])
    register_callbacks(app)
    app.run(debug=True, port=8004)
