"""Henter kvadratmeterpriser fra Finans Danmarks boligmarkedsstatistik
(rkr.statistikbank.dk) og gemmer dem som CSV.

  BM010: realiseret handelspris pr. m2 for alle kommuner   -> priser_kommuner.csv
  BM011: realiseret handelspris pr. m2 for alle postnumre  -> priser_postnumre.csv

DST's EJEN77 går kun ned til landsdele, derfor denne kilde.

Kør:  pip install requests pandas
      python fetch_finansdk.py
"""
import html
import re

import pandas as pd
import requests

BASE = "https://rkr.statistikbank.dk/statbank5a/SelectVarVal/"
KATEGORIER = {"1": "Parcel-/rækkehus", "2": "Ejerlejlighed"}
ANTAL_KVARTALER = 8


def options(side, var):
    blok = re.search(rf'NAME="{var}".*?</select>', side, re.S | re.I).group(0)
    return re.findall(r'(?i)<option value="([^"]*)"[^>]*>([^<]*)', blok)


def hent(tabel):
    s = requests.Session()
    side = s.get(BASE + f"Define.asp?MainTable={tabel}&PLanguage=0&PXSId=0&wsid=cftree",
                 timeout=60).content.decode("latin1")
    form = re.search(r'(?is)<FORM name="main".*?</FORM>', side).group(0)
    skjult = []
    for tag in re.findall(r'(?i)<input[^>]*type="?hidden"?[^>]*>', form):
        navn = re.search(r'(?i)name="([^"]*)"', tag).group(1)
        vaerdi = re.search(r'(?i)value="([^"]*)"', tag)
        if navn != "TS":
            skjult.append((navn, vaerdi.group(1) if vaerdi else ""))

    omraader = options(side, "var1")
    kvartaler = [k for k, _ in options(side, "var4")][:ANTAL_KVARTALER]
    print(f"{tabel}: {len(omraader)} områder, kvartaler {kvartaler[-1]}-{kvartaler[0]}")

    rows = []
    for kat_kode, kat_navn in KATEGORIER.items():
        data = skjult + [("TS", "ShowTable"), ("var2", kat_kode), ("var3", "REAL")]
        data += [("var1", k) for k, _ in omraader] + [("var4", k) for k in kvartaler]
        t = s.post(BASE + "saveselections.asp", data=data, timeout=180).content.decode("latin1")
        tabel_html = re.search(r'(?is)<table id="pxtable".*?</table>', t).group(0)

        # Siden lægger den største dimension i rækkerne, så tjek om kolonnerne er kvartaler
        kode_for = {html.unescape(n).strip(): k for k, n in omraader}
        hoved = [html.unescape(h).strip()
                 for h in re.findall(r'(?i)<th class="headfirst" colspan="1">([^<]*)<', tabel_html)]
        tid_i_kolonner = all(re.fullmatch(r"\d{4}K\d", h) for h in hoved)
        for r in re.findall(r'(?is)<tr>(.*?)</tr>', tabel_html):
            stub = re.search(r'class="stub3"[^>]*>([^<]*)<', r)
            if not stub:
                continue
            stub = html.unescape(stub.group(1)).strip()
            celler = re.findall(r'(?i)<td class=N\w*>([^<]*)<', r)
            for h, v in zip(hoved, celler):
                tid, navn = (h, stub) if tid_i_kolonner else (stub, h)
                v = html.unescape(v).replace(" ", "").replace("\xa0", "")
                rows.append({"kode": kode_for[navn], "navn": navn, "kategori": kat_navn,
                             "tid": tid, "kr_pr_m2": pd.to_numeric(v, errors="coerce")})
    df = pd.DataFrame(rows)
    df.loc[df["kr_pr_m2"] == 0, "kr_pr_m2"] = None   # 0 = ingen handler i kvartalet
    return df


if __name__ == "__main__":
    kom = hent("BM010")
    kom.to_csv("priser_kommuner.csv", index=False, encoding="utf-8")
    print("Gemt priser_kommuner.csv", kom.shape)

    post = hent("BM011")
    post.to_csv("priser_postnumre.csv", index=False, encoding="utf-8")
    print("Gemt priser_postnumre.csv", post.shape)
