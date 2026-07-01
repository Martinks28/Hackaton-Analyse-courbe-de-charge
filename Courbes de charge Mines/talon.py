"""
Identification du TALON (puissance de base) sur une semaine.

Le talon est le plancher de la courbe de charge : la puissance presente en
permanence, meme la nuit et le week-end. On l'estime par un percentile bas
(P5 par defaut) plutot que par le minimum brut, qui serait fausse par le
moindre trou de mesure.

Sortie : la courbe de la semaine avec le talon trace en ligne, la zone sous
le talon (base permanente) ombree, et deux chiffres cles :
  - la valeur du talon
  - la part de l'energie qui passe sous le talon (talon / moyenne)

S'appuie sur le chargeur de visu_brute.py (les deux fichiers doivent etre
dans le meme dossier).

Exemples :
    python talon.py Argile.xlsx
    python talon.py Argile.xlsx --debut 2022-03-07
    python talon.py Diamant.xlsx --debut 2024-02-05 --out talon.png
    python talon.py Jade.xlsx --percentile 10
"""

from pathlib import Path
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from visu_brute import charger, fenetre


def calculer_talon(serie, percentile=5):
    """Estime le talon par un percentile bas, robuste aux trous de mesure.

    Renvoie aussi un estimateur de controle (mediane des minimums journaliers)
    et la moyenne, pour calculer la part d'energie sous le talon.
    """
    talon = serie.quantile(percentile / 100)
    talon_controle = serie.resample("1D").min().median()
    moyenne = serie.mean()
    return talon, talon_controle, moyenne


def tracer_talon(path, debut=None, percentile=5, out=None):
    data = charger(path)
    sous, t0, t1 = fenetre(data, "semaine", debut)
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    # courbe totale (somme des sous-compteurs s'il y en a plusieurs)
    charge = sous.sum(axis=1)
    talon, talon_ctrl, moyenne = calculer_talon(charge, percentile)
    part = 100 * talon / moyenne if moyenne else float("nan")

    nom = Path(path).stem
    print(f"{nom} | semaine {t0.date()} -> {t1.date()}")
    print(f"  talon (P{percentile})         : {talon:.4g}")
    print(f"  controle (min/jour median): {talon_ctrl:.4g}")
    print(f"  moyenne                   : {moyenne:.4g}")
    print(f"  part d'energie sous talon : {part:.0f} %")

    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.plot(charge.index, charge.values, lw=0.8, color="#1f4e79", label="charge")
    ax.fill_between(charge.index, 0, talon, color="#c55a11", alpha=0.18,
                    label=f"talon = {talon:.3g}")
    ax.axhline(talon, color="#c55a11", lw=1.5, ls="--")

    ax.set_title(f"{nom} - talon sur la semaine du {t0.date()}  "
                 f"(part sous talon : {part:.0f} %)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("puissance brute")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        print(f"  figure : {out}")
    else:
        plt.show()


tracer_talon("Charbon.xlsx")


def tracer_talon_annuel_dynamique(path, fenetre_jours=30, percentile=5, out=None):
    data = charger(path)
    if data.empty:
        raise ValueError("Le fichier de données est vide.")

    charge = data.sum(axis=1)
    
    # 144 points par jour (pas de temps 10 min)
    taille_fenetre = fenetre_jours * 144
    
    # Calcul du talon glissant (centré pour éviter le déphasage)
    talon_dynamique = charge.rolling(window=taille_fenetre, center=True, min_periods=144).quantile(percentile/100)
    
    # Pour les statistiques globales
    moyenne_annuelle = charge.mean()
    talon_moyen = talon_dynamique.mean()
    part = 100 * talon_moyen / moyenne_annuelle if moyenne_annuelle else float("nan")

    nom = Path(path).stem
    fig, ax = plt.subplots(figsize=(14, 5.5))
    
    # Charge brute en bleu très léger
    ax.plot(charge.index, charge.values, lw=0.2, color="#1f4e79", alpha=0.4, label="charge brute")
    
    # Courbe du talon dynamique (qui évolue selon les mois)
    ax.plot(talon_dynamique.index, talon_dynamique.values, color="#c55a11", lw=2, label="talon glissant")
    ax.fill_between(talon_dynamique.index, 0, talon_dynamique.values, color="#c55a11", alpha=0.12)

    ax.set_title(f"{nom} - Évolution du talon sur l'année (Fenêtre : {fenetre_jours}j, part moyenne : {part:.0f} %)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("puissance brute (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()


tracer_talon_annuel_dynamique("Houille.xlsx", fenetre_jours=30, percentile=10, out=None)




