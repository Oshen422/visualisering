"""Boligpriser for førstegangskøbere, Dash-skelet.

Kræver ejen77.csv i samme mappe (fra fetch_ejen77.py).
Kør:  python app.py   og åbn 127.0.0.1:8003 i browseren.
"""
import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output

# Lånelogik (skal verificeres, se projektplanen)
GAELDSFAKTOR = 4
MIN_EGENBETALING = 0.05

# ---------- Data ----------
df = pd.read_csv("ejen77.csv", sep=";")
df["INDHOLD"] = pd.to_numeric(df["INDHOLD"], errors="coerce")
df = df[
    (df["BNØGLE"] == "Gennemsnitlig pris pr. ejendom (1000 kr)")
    & (df["OMRÅDE"].str.startswith("Landsdel"))
    & (df["EJENDOMSKATE"].isin(["Enfamiliehuse", "Ejerlejligheder, i alt"]))
].dropna(subset=["INDHOLD"]).copy()
df["pris"] = df["INDHOLD"] * 1000
df["år"] = df["TID"].str[:4].astype(int)
df["OMRÅDE"] = df["OMRÅDE"].str.replace("Landsdel ", "", regex=False)

# Seneste kvartal for hvert år (til slideren)
df_aar = (df.sort_values("TID")
            .groupby(["OMRÅDE", "EJENDOMSKATE", "år"])
            .tail(1))

aar_liste = sorted(df["år"].unique())
omraader = sorted(df["OMRÅDE"].unique())


# ---------- Layout ----------
app = Dash(__name__)

app.layout = html.Div(style={"maxWidth": "1100px", "margin": "auto", "fontFamily": "sans-serif"}, children=[
    html.H1("Hvor kan en førstegangskøber have råd til at købe?"),

    html.Div(style={"display": "flex", "gap": "16px", "flexWrap": "wrap"}, children=[
        html.Div([html.Label("Husstandens bruttoindkomst (kr./år)"),
                  dcc.Input(id="indkomst", type="number", value=600000, step=10000)]),
        html.Div([html.Label("Opsparing til udbetaling (kr.)"),
                  dcc.Input(id="opsparing", type="number", value=200000, step=10000)]),
        html.Div([html.Label("Anden gæld (kr.)"),
                  dcc.Input(id="gaeld", type="number", value=0, step=10000)]),
        html.Div(style={"minWidth": "260px"}, children=[
            html.Label("Boligtype"),
            dcc.Dropdown(id="boligtype", clearable=False, value="Enfamiliehuse",
                         options=["Enfamiliehuse", "Ejerlejligheder, i alt"])]),
    ]),

    html.H3(id="maks-pris"),

    dcc.Graph(id="bar"),
    dcc.Slider(id="aar", min=aar_liste[0], max=aar_liste[-1], step=1,
               value=aar_liste[-1], marks={a: str(a) for a in aar_liste[::5]}),

    dcc.Graph(id="linje"),
])


# ---------- Callback ----------
@app.callback(
    Output("maks-pris", "children"),
    Output("bar", "figure"),
    Output("linje", "figure"),
    Input("indkomst", "value"),
    Input("opsparing", "value"),
    Input("gaeld", "value"),
    Input("boligtype", "value"),
    Input("aar", "value"),
    Input("bar", "clickData"),
)
def opdater(indkomst, opsparing, gaeld, boligtype, aar, klik):
    indkomst, opsparing, gaeld = indkomst or 0, opsparing or 0, gaeld or 0

    # Lånelogik
    maks_laan = max(0, indkomst * GAELDSFAKTOR - gaeld)
    maks_pris = min(maks_laan + opsparing, opsparing / MIN_EGENBETALING)

    # Søjlediagram: pris pr. landsdel i valgt år
    d = df_aar[(df_aar["EJENDOMSKATE"] == boligtype) & (df_aar["år"] == aar)].copy()
    d["status"] = d["pris"].apply(lambda p: "Inden for budget" if p <= maks_pris else "Over budget")
    d = d.sort_values("pris")
    bar = px.bar(
        d, x="OMRÅDE", y="pris", color="status",
        color_discrete_map={"Inden for budget": "#2E7D32", "Over budget": "#C62828"},
        title=f"Gennemsnitlig salgspris pr. landsdel, {aar}",
        labels={"pris": "Pris (kr.)", "OMRÅDE": "Landsdel", "status": ""},
    )
    bar.add_hline(y=maks_pris, line_dash="dash",
                  annotation_text="Din maks. købspris", annotation_position="top left")

    # Linjediagram: udvikling for klikket landsdel
    valgt = klik["points"][0]["x"] if klik else omraader[0]
    t = df[(df["EJENDOMSKATE"] == boligtype) & (df["OMRÅDE"] == valgt)].sort_values("TID")
    linje = px.line(t, x="TID", y="pris", title=f"Prisudvikling: {valgt} (klik på en søjle for at skifte)",
                    labels={"pris": "Pris (kr.)", "TID": "Kvartal"})
    linje.add_hline(y=maks_pris, line_dash="dash", annotation_text="Din maks. købspris")

    tekst = f"Din maks. købspris: {maks_pris:,.0f} kr.".replace(",", ".")
    return tekst, bar, linje


if __name__ == "__main__":
    app.run(debug=True, port=8003)
