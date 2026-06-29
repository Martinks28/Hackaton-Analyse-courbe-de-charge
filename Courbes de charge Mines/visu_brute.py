"""
Visualisation des donnees brutes d'un fichier de consommation, sur une fenetre
de duree variable : jour, semaine, mois ou annee.

Les valeurs sont tracees telles qu'elles figurent dans le fichier (unite d'origine,
aucune agregation). Seul le timestamp est decode proprement.

Exemples :
    python visu_brute.py Argile.xlsx --echelle jour    --debut 2022-03-08
    python visu_brute.py Argile.xlsx --echelle semaine  --debut 2022-03-07
    python visu_brute.py Argile.xlsx --echelle annee    --debut 2022-01-01
    python visu_brute.py Diamant.xlsx --echelle semaine --debut 2024-02-05

Sans --debut, la fenetre demarre au tout debut du fichier.
"""

import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

EXCEL_EPOCH = pd.Timestamp("1899-12-30")
DUREES = {"jour": "1D", "semaine": "7D", "mois": "1MS", "annee": "1YS"}


def _to_datetime(s):
    """Le timestamp peut etre une vraie date OU un numero de serie Excel."""
    if np.issubdtype(s.dtype, np.datetime64):
        return pd.to_datetime(s)
    return EXCEL_EPOCH + pd.to_timedelta(s.astype(float), unit="D")


def charger(path):
    """Renvoie un DataFrame indexe par le temps, colonnes = mesures brutes."""
    df = pd.read_excel(path, sheet_name=0)

    # colonne temps : par nom connu, sinon premiere colonne
    tcol = next((c for c in ("Horodate", "timestamp", "Timestamp", "datetime")
                 if c in df.columns), df.columns[0])

    # colonnes de mesure : tout sauf le temps et les colonnes d'unite/texte
    val_cols = [c for c in df.columns
                if c != tcol
                and not str(c).lower().startswith("unit")
                and df[c].dtype != object]

    data = df[val_cols].apply(pd.to_numeric, errors="coerce")
    data.index = _to_datetime(df[tcol])
    data = data[~data.index.isna()].sort_index()
    return data


def fenetre(data, echelle, debut=None):
    """Decoupe la sous-periode demandee."""
    t0 = pd.Timestamp(debut) if debut else data.index.min().normalize()
    if echelle == "jour":
        t1 = t0 + pd.Timedelta(days=1)
    elif echelle == "semaine":
        t1 = t0 + pd.Timedelta(days=7)
    elif echelle == "mois":
        t1 = t0 + pd.DateOffset(months=1)
    elif echelle == "annee":
        t1 = t0 + pd.DateOffset(years=1)
    else:
        raise ValueError(f"echelle inconnue : {echelle}")
    return data.loc[t0:t1], t0, t1


def tracer(data, echelle, debut=None, titre=None, out=None):
    sous, t0, t1 = fenetre(data, echelle, debut)
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    fig, ax = plt.subplots(figsize=(14, 5))
    for col in sous.columns:
        ax.plot(sous.index, sous[col], lw=0.8, label=str(col))

    ax.set_title(titre or f"{echelle.capitalize()} : {t0.date()} -> {t1.date()}",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("valeur brute")
    ax.grid(alpha=0.3)
    if len(sous.columns) > 1:
        ax.legend(fontsize=8, ncol=2)

    # format de l'axe temps adapte a l'echelle
    if echelle == "jour":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
    elif echelle == "semaine":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return out
    plt.show()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Visualisation des donnees brutes")
    ap.add_argument("fichier")
    ap.add_argument("--echelle", choices=list(DUREES), default="semaine")
    ap.add_argument("--debut", default=None, help="AAAA-MM-JJ (defaut : debut du fichier)")
    ap.add_argument("--out", default=None, help="chemin PNG (defaut : affichage ecran)")
    args = ap.parse_args()

    data = charger(args.fichier)
    print(f"{Path(args.fichier).name} : {data.index.min()} -> {data.index.max()}  "
          f"({len(data)} points, colonnes : {list(data.columns)})")
    tracer(data, args.echelle, args.debut, titre=Path(args.fichier).stem + f" - {args.echelle}",
           out=args.out)
