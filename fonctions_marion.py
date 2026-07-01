"""
Bibliotheque commune du projet "Courbes de charge".

Ce fichier regroupe TOUTES les fonctions utilisees dans le projet, qui etaient
auparavant dispersees dans trois fichiers differents (utils_energie.py,
visu_brute.py, talon.py). Il n'y a plus qu'un seul fichier a maintenir : celui-ci.

Sections :
  1. Chargement des fichiers Excel -> DataFrame indexe par le temps
  2. Decoupage en fenetres temporelles (jour / semaine / mois / annee / tout)
  3. Trace de la courbe brute (matplotlib)
  4. Semaine type d'un mois donne (plotly), brute et lissee
  5. Talon (puissance de base) : ponctuel sur une semaine, et glissant sur l'annee

Utilisation dans le notebook :
    from utils_energie import charger, tracer, tracer_semaine_type_mois, \
        tracer_semaine_type_mois_filtre, tracer_talon, tracer_talon_annuel_dynamique
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import plotly.express as px

EXCEL_EPOCH = pd.Timestamp("1899-12-30")
DUREES = {"jour": "1D", "semaine": "7D", "mois": "1MS", "annee": "1YS", "tout": None}


# ---------------------------------------------------------------------------
# 1. Chargement
# ---------------------------------------------------------------------------

def _serie_en_datetime(s):
    """Convertit une colonne en datetime, qu'elle soit deja une date,
    un numero de serie Excel, ou du texte (format jour/mois/annee)."""
    if np.issubdtype(s.dtype, np.datetime64):
        return pd.to_datetime(s)
    if pd.api.types.is_numeric_dtype(s):
        return EXCEL_EPOCH + pd.to_timedelta(s.astype(float), unit="D")
    return pd.to_datetime(s.astype(str), dayfirst=True, errors="coerce")


def _construire_index(df):
    """Construit l'index temporel et renvoie aussi les colonnes consommees.

    Gere trois cas :
      - temps reparti sur deux colonnes 'Date' + 'Time'
      - une seule colonne temps nommee (Horodate / timestamp / ...)
      - a defaut, la premiere colonne
    """
    cols = {str(c).lower(): c for c in df.columns}

    # cas 1 : Date + Time separes
    if "date" in cols and "time" in cols:
        cdate, ctime = cols["date"], cols["time"]
        d = pd.to_datetime(df[cdate].astype(str), dayfirst=True, errors="coerce")
        t = pd.to_timedelta(df[ctime].astype(str), errors="coerce")
        return d + t, [cdate, ctime]

    # cas 2 : une colonne temps nommee, sinon premiere colonne
    tcol = next((c for c in ("Horodate", "timestamp", "Timestamp", "datetime", "Date")
                 if c in df.columns), df.columns[0])
    return _serie_en_datetime(df[tcol]), [tcol]


def charger(path):
    """Renvoie un DataFrame indexe par le temps, colonnes = mesures brutes."""
    df = pd.read_excel(path, sheet_name=0)

    index, cols_temps = _construire_index(df)

    # colonnes de mesure : tout sauf le temps et les colonnes d'unite/texte
    val_cols = [c for c in df.columns
                if c not in cols_temps
                and not str(c).lower().startswith("unit")
                and df[c].dtype != object]

    data = df[val_cols].apply(pd.to_numeric, errors="coerce")
    data.index = index
    data = data[~data.index.isna()].sort_index()
    data.attrs["nom"] = Path(path).stem
    return data


# ---------------------------------------------------------------------------
# 2. Fenetrage
# ---------------------------------------------------------------------------

def fenetre(data, echelle, debut=None):
    """Decoupe la sous-periode demandee."""

    if echelle == "jour":
        if debut :
            t0 = pd.Timestamp(debut) 
            t1 = t0 + pd.Timedelta(days=1)
        else :
            t0 = data.index.max().normalize() - pd.Timedelta(days=1)
            t1 = data.index.max().normalize()
    elif echelle == "semaine":
        if debut :
            t0 = pd.Timestamp(debut) 
            t1 = t0 + pd.Timedelta(days=7)
        else :
            t0 = data.index.max().normalize() - pd.Timedelta(days=7)
            t1 = data.index.max().normalize()
    elif echelle == "mois":
        if debut :
            t0 = pd.Timestamp(debut) 
            t1 = t0 + pd.DateOffset(months=1)
        else :
            t0 = data.index.max().normalize() - pd.DateOffset(months=1)
            t1 = data.index.max().normalize()
    elif echelle == "annee":
        if debut :
            t0 = pd.Timestamp(debut) 
            t1 = t0 + pd.DateOffset(years=1)
        else :
            t0 = data.index.max().normalize() - pd.DateOffset(years=1)
            t1 = data.index.max().normalize()
    else:
        raise ValueError(f"echelle inconnue : {echelle}")
    return data.loc[t0:t1], t0, t1


# ---------------------------------------------------------------------------
# 3. Trace de la courbe brute
# ---------------------------------------------------------------------------

def tracer(data, echelle="tout", debut=None, titre=None, out=None, nom = None):
    # 1. Gestion de l'echelle "tout"
    if echelle == "tout":
        sous = data
        t0 = data.index.min()
        t1 = data.index.max()
    else:
        # On ne fait appel au decoupage que si on demande une echelle precise
        sous, t0, t1 = fenetre(data, echelle, debut)

    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    # 2. Creation de la figure
    fig, ax = plt.subplots(figsize=(14, 5))
    for col in sous.columns:
        ax.plot(sous.index, sous[col], lw=0.8, label=str(col))

    # Adaptation du titre par defaut selon l'echelle
    nom = nom or data.attrs.get("nom", "Courbe")
    titre_defaut = (f"{nom} | Vue globale : {t0.date()} -> {t1.date()}" if echelle == "tout"
                     else f"{nom} | {echelle.capitalize()} : {t0.date()} -> {t1.date()}")
    ax.set_title(titre or titre_defaut, fontsize=13, fontweight="bold")

    ax.set_ylabel("Puissance en W")
    ax.grid(alpha=0.3)
    if len(sous.columns) > 1:
        ax.legend(fontsize=8, ncol=2)

    # 3. Format de l'axe temps adapte a l'echelle
    if echelle == "jour":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
    elif echelle == "semaine":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
    elif echelle == "tout" or echelle == "annee":
        # Pour une vue globale, "Mois Annee" (ex: Jan 2022) evite de surcharger l'axe
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    else:
        # Pour le mois
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return out
    plt.show()


# ---------------------------------------------------------------------------
# 4. Semaine type d'un mois donne
# ---------------------------------------------------------------------------

def _construire_semaine_type(df_mois):
    """Moyenne par (jour de semaine, heure:minute) + index textuel propre."""
    df_mois = df_mois.copy()
    df_mois["num_jour"] = df_mois.index.dayofweek
    df_mois["heure_minute"] = df_mois.index.strftime("%H:%M")

    semaine_type = df_mois.groupby(["num_jour", "heure_minute"]).mean(numeric_only=True)

    jours_noms = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    semaine_type.index = [f"{jours_noms[num_jour]} {hm}" for num_jour, hm in semaine_type.index]
    return semaine_type


def _tracer_semaine_type_plotly(semaine_type, titre, ylabel, out=None):
    fig, ax = plt.subplots(figsize=(14,5))
    x = np.arange(len(semaine_type))
    for col in semaine_type.columns:
        ax.plot(x, semaine_type[col], lw=1, label=str(col))
 
    ax.set_title(titre, fontsize=13, fontweight="bold")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.3)
    if len(semaine_type.columns) > 1:
        ax.legend(fontsize=8, ncol=2)
 
    # Une graduation par minuit (144 points = 1 jour au pas de 10 min)
    positions = np.arange(0, len(semaine_type), 144)
    etiquettes = [semaine_type.index[i] for i in positions]
    ax.set_xticks(positions)
    ax.set_xticklabels(etiquettes, rotation=30, ha="right")
    ax.set_xlim(0, len(semaine_type) - 1)
 
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return out
    plt.show()


def tracer_semaine_type_mois(data, mois, titre=None, nom=None):
    """
    Calcule et trace (avec Plotly) la semaine type pour un mois donne,
    en se basant sur les 12 derniers mois d'historique du fichier.
    """
    date_fin = data.index.max()
    date_debut = date_fin - pd.DateOffset(years=1)

    df_12_mois = data[(data.index > date_debut) & (data.index <= date_fin)]
    df_mois = df_12_mois[df_12_mois.index.month == mois]

    if df_mois.empty:
        print(f"Attention : Aucune donnee pour le mois {mois} entre le {date_debut.date()} et le {date_fin.date()}")
        return None

    semaine_type = _construire_semaine_type(df_mois)
    nom = nom or data.attrs.get("nom", "Courbe")
    titre_final = titre or f"{nom} | Semaine type - Mois n°{mois} (Calculee sur les 12 derniers mois)"
    _tracer_semaine_type_plotly(semaine_type, titre_final, "Puissance (W)")

    return semaine_type


def tracer_semaine_type_mois_filtre(data, mois, span=7, titre=None, nom=None):
    """
    Calcule et trace (avec Plotly) la semaine type pour un mois donne,
    en appliquant d'abord un filtre passe-bas exponentiel pour eliminer le bruit.
    """
    date_fin = data.index.max()
    date_debut = date_fin - pd.DateOffset(years=1)

    df_12_mois = data[(data.index > date_debut) & (data.index <= date_fin)].copy()

    # Filtrage sur l'annee entiere pour eviter les effets de bord, puis extraction du mois
    cols_num = df_12_mois.select_dtypes(include=[np.number]).columns
    df_12_mois[cols_num] = df_12_mois[cols_num].ewm(span=span, adjust=False).mean()
    df_mois = df_12_mois[df_12_mois.index.month == mois]

    if df_mois.empty:
        print(f"Attention : Aucune donnee pour le mois {mois} entre le {date_debut.date()} et le {date_fin.date()}")
        return None

    semaine_type = _construire_semaine_type(df_mois)
    nom = nom or data.attrs.get("nom", "Courbe")
    titre_final = titre or f"{nom} | Semaine type (Lissee span={span}) - Mois n°{mois}"
    _tracer_semaine_type_plotly(semaine_type, titre_final, "Puissance lissee (W)")

    return semaine_type


# ---------------------------------------------------------------------------
# 5. Talon (puissance de base)
# ---------------------------------------------------------------------------

def calculer_talon(serie, percentile=5):
    """Estime le talon par un percentile bas, robuste aux trous de mesure.

    Renvoie aussi un estimateur de controle (mediane des minimums journaliers)
    et la moyenne, pour calculer la part d'energie sous le talon.
    """
    talon = serie.quantile(percentile / 100)
    talon_controle = serie.resample("1D").min().median()
    moyenne = serie.mean()
    return talon, talon_controle, moyenne


def tracer_talon(data, echelle="tout", debut=None, percentile=5, out=None, nom=None):

    sous, t0, t1 = fenetre(data, echelle, debut)
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    # courbe totale (somme des sous-compteurs s'il y en a plusieurs)
    charge = sous.sum(axis=1)
    talon, talon_ctrl, moyenne = calculer_talon(charge, percentile)
    part = 100 * talon / moyenne if moyenne else float("nan")

    nom = nom or data.attrs.get("nom", "Courbe")
    print(f"{nom} | {echelle} {t0.date()} -> {t1.date()}")
    print(f"  talon (P{percentile})         : {talon:.4g}")
    print(f"  part d'energie sous talon : {part:.0f} %")

    fig, ax = plt.subplots(figsize=(14, 5.5))
    ax.plot(charge.index, charge.values, lw=0.8, color="#1f4e79", label="charge")
    ax.fill_between(charge.index, 0, talon, color="#c55a11", alpha=0.18,
                     label=f"talon = {talon:.3g}")
    ax.axhline(talon, color="#c55a11", lw=1.5, ls="--")

    ax.set_title(f"{nom} - talon {echelle} du {t0.date()}  "
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


def tracer_talon_annuel_dynamique(data, fenetre_jours=30, percentile=5, out=None, nom=None):
    """Talon glissant sur l'annee entiere (fenetre centree, en jours)."""
    if data.empty:
        raise ValueError("Le fichier de donnees est vide.")

    charge = data.sum(axis=1)

    # 144 points par jour (pas de temps 10 min)
    taille_fenetre = fenetre_jours * 144

    # Talon glissant (centre pour eviter le dephasage)
    talon_dynamique = charge.rolling(window=taille_fenetre, center=True,
                                      min_periods=144).quantile(percentile / 100)

    moyenne_annuelle = charge.mean()
    talon_moyen = talon_dynamique.mean()
    part = 100 * talon_moyen / moyenne_annuelle if moyenne_annuelle else float("nan")

    nom = nom or data.attrs.get("nom", "Courbe")
    fig, ax = plt.subplots(figsize=(14, 5.5))

    ax.plot(charge.index, charge.values, lw=0.2, color="#1f4e79", alpha=0.4, label="charge brute")
    ax.plot(talon_dynamique.index, talon_dynamique.values, color="#c55a11", lw=2, label="talon glissant")
    ax.fill_between(talon_dynamique.index, 0, talon_dynamique.values, color="#c55a11", alpha=0.12)

    ax.set_title(f"{nom} - Evolution du talon sur l'annee (Fenetre : {fenetre_jours}j, part moyenne : {part:.0f} %)",
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


# ---------------------------------------------------------------------------
# 6. Plateaux méthode dérivée
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 6. Plateaux méthode dérivée
# ---------------------------------------------------------------------------
def tracer_plateaux(data, echelle="tout", debut=None, seuil_derivee=0.01, min_points=6, out=None, nom=None):
    """
    Détecte et met en évidence les plateaux de consommation (zones stables).
    
    Paramètres:
      - span : paramètre de lissage exponentiel (plus il est grand, plus la courbe est lisse).
      - seuil_derivee : seuil en % de l'amplitude max de la courbe en dessous duquel on considère 
                        que la dérivée est "proche de zéro".
      - min_points : nombre de points consécutifs minimum pour valider un plateau (évite les micro-plateaux).
    """
    # 1. Gestion de l'échelle temporelle
    if echelle == "tout":
        sous = data.copy()
        t0 = data.index.min()
        t1 = data.index.max()
    else:
        sous, t0, t1 = fenetre(data, echelle, debut)
        sous = sous.copy()

    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    # Somme des sous-compteurs pour avoir la charge globale
    charge_brute = sous.sum(axis=1)

    # 2. Lissage exponentiel pour éliminer le bruit de fond
    charge_lissee = charge_brute.rolling(window=15, center=True, min_periods=1).median()

    # 3. Calcul de la dérivée numérique (différence point à point)
    derivee = charge_lissee.diff().fillna(0)

    # Définition d'un seuil dynamique adapté à la dynamique du signal
    amplitude = charge_lissee.max() - charge_lissee.min()
    if amplitude == 0:
        amplitude = 1  # Évite une division par zéro si la courbe est plate d'origine
    seuil_abs = seuil_derivee * amplitude

    # Identification des points stables (dérivée proche de zéro)
    points_stables = derivee.abs() < seuil_abs

    # 4. Regroupement des points stables consécutifs en segments (plateaux)
    # Astuce : une rupture (changement d'état) incrémente l'ID du groupe
    groupes = (points_stables != points_stables.shift()).cumsum()
    
    # On ne garde que les groupes qui sont stables ET qui durent assez longtemps
    plateaux_indices = []
    for g_id, g_df in points_stables.groupby(groupes):
        if g_df.iloc[0] and len(g_df) >= min_points:
            plateaux_indices.append(g_df.index)

    # 5. Construction du graphique Matplotlib
    fig, ax = plt.subplots(figsize=(14, 5.5))
    nom = nom or data.attrs.get("nom", "Courbe")
    
    # Tracé de la charge brute (en fond) et lissee (pour l'analyse)
    ax.plot(charge_brute.index, charge_brute.values, lw=0.6, color="#1f4e79", alpha=0.3, label="Charge brute")
    ax.plot(charge_lissee.index, charge_lissee.values, lw=1.2, color="#1f4e79", label="Charge lissée")
    
    # Coloriage des plateaux détectés

    deja_legende = False
    for idx_range in plateaux_indices:
        # On extrait la valeur moyenne lissée sur ce plateau pour l'affichage visuel
        val_moyenne = charge_lissee.loc[idx_range].mean()
        # Optionnel : une petite ligne horizontale verte sur le plateau pour marquer sa hauteur théorique
        ax.plot(idx_range, [val_moyenne] * len(idx_range), color="#2ca02c", lw=2)
        deja_legende = True
    """
        # Colorie la zone temporelle du plateau
        label_text = "Plateaux détectés" if not deja_legende else ""
        ax.axvspan(idx_range[0], idx_range[-1], color="#2ca02c", alpha=0.2, label=label_text)
    """  

    
    # 6. Habillage du graphique
    titre_final = f"{nom} | Détection des plateaux (méthode dérivée) | {t0.date()} -> {t1.date()}"
    ax.set_title(titre_final, fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # Adaptations de l'axe X selon la durée affichée
    if echelle == "jour":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
    elif echelle == "semaine":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
    elif echelle in ("tout", "annee"):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    else:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()

    if out:
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return out
    plt.show()


def tracer_plateaux_histogramme_hauteurs(data, echelle="tout", debut=None, span=12, seuil_derivee=0.01, min_points=6, marge_pct=0.04, out=None, nom=None):
    """
    Détecte les plateaux par dérivée, puis les regroupe par hauteur de plateau 
    en appliquant une marge en % de la hauteur du plateau de référence.
    
    Paramètres:
      - marge_pct : marge d'acceptation (0.10 = +/- 10% de la hauteur du plateau référent).
    """
    # 1. Détection standard des plateaux par la dérivée
    if echelle == "tout":
        sous = data.copy()
        t0 = data.index.min()
        t1 = data.index.max()
    else:
        sous, t0, t1 = fenetre(data, echelle, debut)
        sous = sous.copy()

    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    charge_brute = sous.sum(axis=1)
    charge_lissee = charge_brute.rolling(window=15, center=True, min_periods=1).median()

    derivee = charge_lissee.diff().fillna(0)
    amplitude = charge_lissee.max() - charge_lissee.min()
    seuil_abs = seuil_derivee * (amplitude if amplitude > 0 else 1)
    points_stables = derivee.abs() < seuil_abs

    groupes = (points_stables != points_stables.shift()).cumsum()
    plateaux_detectes = []
    
    for g_id, g_df in points_stables.groupby(groupes):
        if g_df.iloc[0] and len(g_df) >= min_points:
            H_moyenne = charge_brute.loc[g_df.index].mean()
            plateaux_detectes.append({'index': g_df.index, 'hauteur': H_moyenne, 'zone': None, 'couleur': None})

    # 2. REGROUPEMENT PAR PROXIMITÉ DE HAUTEUR (Algorithme Glouton par vagues)
    if plateaux_detectes:
        # On trie les plateaux du plus bas au plus haut
        plateaux_detectes.sort(key=lambda x: x['hauteur'])
        
        # --- VAGUE 1 : TALON PRINCIPAL ---
        # Le premier est forcément le talon principal de référence
        ref_talon_1 = plateaux_detectes[0]['hauteur']
        # Un plateau max acceptable pour éviter d'embarquer des sommets de pics dans le 2ème talon
        plafond_max_acceptable = ref_talon_1 + (0.45 * amplitude) 
        
        for p in plateaux_detectes:
            # Si le plateau est dans la marge (+/- X% de sa propre hauteur de référence)
            if abs(p['hauteur'] - ref_talon_1) <= (marge_pct * ref_talon_1):
                p['zone'] = 'Talon principal'
                p['couleur'] = '#2ca02c'  # Vert

        # --- VAGUE 2 : DEUXIÈME TALON ---
        # On cherche le prochain plateau non classé qui reste sous le plafond max
        plateaux_restants = [p for p in plateaux_detectes if p['zone'] is None and p['hauteur'] <= plafond_max_acceptable]
        
        if plateaux_restants:
            # Le plus bas des restants devient la référence du deuxième talon
            ref_talon_2 = plateaux_restants[0]['hauteur']
            for p in plateaux_detectes:
                if p['zone'] is None and abs(p['hauteur'] - ref_talon_2) <= (marge_pct * ref_talon_2):
                    p['zone'] = 'Deuxième Talon'
                    p['couleur'] = '#ff7f0e'  # Orange

        # --- VAGUE 3 : TROISIEME TALON ---
        # On cherche le prochain plateau non classé qui reste sous le plafond max
        plateaux_restants_v3 = [p for p in plateaux_detectes if p['zone'] is None and p['hauteur'] <= plafond_max_acceptable]
        
        if plateaux_restants_v3:
            # Le plus bas des restants devient la référence du troisième talon
            ref_talon_3 = plateaux_restants_v3[0]['hauteur']
            for p in plateaux_detectes:
                if p['zone'] is None and abs(p['hauteur'] - ref_talon_3) <= (marge_pct * ref_talon_3):
                    p['zone'] = 'Troisième Talon'
                    p['couleur'] = '#9467bd'  # Violet (couleur standard matplotlib agréable)

    # 3. Tracé du graphique
    fig, ax = plt.subplots(figsize=(14, 5.5))
    nom = nom or data.attrs.get("nom", "Courbe")
    
    # Tout ce qui n'a pas été classé reste en "Zone sans plateaux / Pics" (Gris)
    ax.plot(charge_brute.index, charge_brute.values, lw=0.6, color="#7f7f7f", alpha=0.3, label="Zone sans plateaux / Pics")
    ax.plot(charge_lissee.index, charge_lissee.values, lw=1, color="#1f77b4", alpha=0.7, label="Charge lissée")

    legendes_ajoutees = set()
    for p in plateaux_detectes:
        if p['zone'] is not None:  # On ne colore que les talons validés
            lbl = p['zone'] if p['zone'] not in legendes_ajoutees else ""
            legendes_ajoutees.add(p['zone'])
            ax.axvspan(p['index'][0], p['index'][-1], color=p['couleur'], alpha=0.25, label=lbl)
            ax.plot(p['index'], [p['hauteur']] * len(p['index']), color=p['couleur'], lw=2.5)

    ax.set_title(f"{nom} | Regroupement des plateaux par hauteur ({int(marge_pct*100)}% de marge) | {t0.date()} -> {t1.date()}", fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.2)
    ax.legend(loc="upper right")
    
    if echelle == "jour": ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
    elif echelle == "semaine": ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
    else: ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m/%y"))

    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    
    if out:
        fig.savefig(out, dpi=110, bbox_inches="tight")
        plt.close(fig)
        return out
    plt.show()




# ---------------------------------------------------------------------------
# Utilisation en ligne de commande (facultatif)
# Exemple :  python utils_energie.py Argile.xlsx --echelle semaine --debut 2022-03-07
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Visualisation des donnees brutes")
    ap.add_argument("fichier")
    ap.add_argument("--echelle", choices=list(DUREES), default="tout")
    ap.add_argument("--debut", default=None, help="AAAA-MM-JJ (defaut : debut du fichier)")
    ap.add_argument("--out", default=None, help="chemin PNG (defaut : affichage ecran)")
    args = ap.parse_args()

    data = charger(args.fichier)
    print(f"{Path(args.fichier).name} : {data.index.min()} -> {data.index.max()}  "
          f"({len(data)} points, colonnes : {list(data.columns)})")
    tracer(data, args.echelle, args.debut,
           titre=Path(args.fichier).stem + f" - {args.echelle}", out=args.out)




