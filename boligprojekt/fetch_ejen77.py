"""Henter udvalgte data fra DST-tabellen EJEN77 og gemmer som ejen77.csv.

Kør:  pip install requests pandas
      python fetch_ejen77.py
"""
import io
import requests
import pandas as pd

API = "https://api.statbank.dk/v1"
TABLE = "EJEN77"

r = requests.get(f"{API}/tableinfo",
                 params={"id": TABLE, "format": "JSON", "lang": "da"}, timeout=60)
r.raise_for_status()
info = r.json()


def var(var_id):
    return next(v for v in info["variables"] if v["id"].upper() == var_id.upper())


def pick(var_id, wanted):
    """Returnerer koder for værdier, hvis tekst indeholder et af ordene i wanted."""
    ids = []
    for x in var(var_id)["values"]:
        if any(w.lower() in x["text"].lower() for w in wanted):
            ids.append(x["id"])
            print(f"  valgt {var_id}: {x['text']}")
    if not ids:
        raise SystemExit(f"Ingen match for {var_id} med {wanted}")
    return ids


print("Alle ejendomskategorier i tabellen:")
for x in var("EJENDOMSKATE")["values"]:
    print("  -", x["text"])
print()

print("Valg:")
body = {
    "table": TABLE,
    "format": "CSV",
    "lang": "da",
    "valuePresentation": "Value",
    "delimiter": "Semicolon",
    "variables": [
        {"code": "OMRÅDE", "values": ["*"]},
        {"code": "EJENDOMSKATE", "values": pick("EJENDOMSKATE", ["Enfamiliehuse", "Ejerlejlighed"])},
        {"code": "BNØGLE", "values": pick("BNØGLE", ["Gennemsnitlig pris", "Salg ved prisberegning"])},
        {"code": "OVERDRAG", "values": pick("OVERDRAG", ["Almindelig fri handel"])},
        {"code": "Tid", "values": ["*"]},
    ],
}
print()

r = requests.post(f"{API}/data", json=body, timeout=180)
if r.status_code != 200:
    print("FEJL fra DST:", r.status_code)
    print(r.text[:1000])
    raise SystemExit(1)

with open("ejen77.csv", "w", encoding="utf-8") as f:
    f.write(r.text)

df = pd.read_csv(io.StringIO(r.text), sep=";")
print("Gemt som ejen77.csv")
print("Dimensioner:", df.shape)
print("Kolonner:", list(df.columns))
print(df.head(10).to_string())
print()
print("Manglende værdier pr. kolonne:")
print(df.isna().sum())
