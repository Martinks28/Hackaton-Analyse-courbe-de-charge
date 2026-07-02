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
def tracer_plateaux(data, echelle="tout", debut=None, type_lissage="ewm", window=15, seuil_derivee=0.01, min_points=6, out=None, nom=None):
    """
    Détecte et affiche les plateaux sur une seule couleur (version d'origine)
    avec le choix du lissage dynamique :
      - type_lissage = "ewm"    -> utilise ewm(span=window)
      - type_lissage = "median" -> utilise rolling(window).median()
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

    charge_brute = sous.sum(axis=1)
    
    # --- CHOIX DU LISSAGE PARAMÉTRABLE ---
    if type_lissage == "ewm":
        charge_lissee = charge_brute.ewm(span=window, adjust=False).mean()
    elif type_lissage == "median":
        charge_lissee = charge_brute.rolling(window=window, center=True, min_periods=1).median()
    else:
        raise ValueError("type_lissage doit être 'ewm' ou 'median'")

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



def tracer_plateaux_regroupes(data, echelle="tout", debut=None, type_lissage="ewm", window=15, seuil_derivee=0.01, min_points=6, marge_pct=0.04, out=None, nom=None):
    """
    Détecte les plateaux avec un choix de lissage dynamique :
      - type_lissage = "ewm"    -> utilise ewm(span=window) [Idéal courbes douces]
      - type_lissage = "median" -> utilise rolling(window).median() [Idéal courbes très bruitées]
    """
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
    
    # --- CHOIX DU LISSAGE PARAMÉTRABLE ---
    if type_lissage == "ewm":
        # window sert ici de 'span'
        charge_lissee = charge_brute.ewm(span=window, adjust=False).mean()
    elif type_lissage == "median":
        # window est le nombre de points de la fenêtre glissante. 
        # min_periods=1 évite d'avoir des NaN au tout début de la courbe
        charge_lissee = charge_brute.rolling(window=window, center=True, min_periods=1).median()
    else:
        raise ValueError("type_lissage doit être 'ewm' ou 'median'")
    
    if echelle == "tout":
        sous = data.copy()
        t0 = data.index.min()
        t1 = data.index.max()
    else:
        sous, t0, t1 = fenetre(data, echelle, debut)
        sous = sous.copy()

    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")


    derivee = charge_lissee.diff().fillna(0)
    amplitude = charge_lissee.max() - charge_lissee.min()
    seuil_abs = seuil_derivee * (amplitude if amplitude > 0 else 1)
    points_stables = derivee.abs() < seuil_abs

    groupes = (points_stables != points_stables.shift()).cumsum()
    plateaux_bruts = []
    
    for g_id, g_df in points_stables.groupby(groupes):
        if g_df.iloc[0] and len(g_df) >= min_points:
            H_moyenne = charge_lissee.loc[g_df.index].mean()
            plateaux_bruts.append({
                't_debut': g_df.index[0],
                't_fin': g_df.index[-1],
                'index': g_df.index, 
                'hauteur': H_moyenne,
                'zone': None,
                'couleur': None
            })

    # --- ÉTAPE DE FUSION DES PLATEAUX ADJACENTS CORROMPUS PAR LE BRUIT ---
    plateaux_detectes = []
    if plateaux_bruts:
        # On trie d'abord par ordre chronologique pour détecter la proximité temporelle
        plateaux_bruts.sort(key=lambda x: x['t_debut'])
        
        p_actuel = plateaux_bruts[0]
        for p_suivant in plateaux_bruts[1:]:
            # Si le plateau suivant est proche dans le temps (moins de 2h) AND a presque la même hauteur
            ecart_temps = (p_suivant['t_debut'] - p_actuel['t_fin']).total_seconds() / 3600
            ecart_hauteur = abs(p_suivant['hauteur'] - p_actuel['hauteur'])
            
            if ecart_temps < 2.0 and ecart_hauteur <= (marge_pct * p_actuel['hauteur']):
                # On fusionne le suivant dans l'actuel
                p_actuel['t_fin'] = p_suivant['t_fin']
                p_actuel['index'] = p_actuel['index'].union(p_suivant['index'])
                # La nouvelle hauteur devient la moyenne pondérée ou simple des deux
                p_actuel['hauteur'] = (p_actuel['hauteur'] + p_suivant['hauteur']) / 2
            else:
                plateaux_detectes.append(p_actuel)
                p_actuel = p_suivant
        plateaux_detectes.append(p_actuel)

    # --- REGROUPEMENT GLOBAL PAR POURCENTAGE ---
    if plateaux_detectes:
        hauteurs_tris = sorted([p['hauteur'] for p in plateaux_detectes])
        plafond_max_acceptable = hauteurs_tris[0] + (0.50 * amplitude)

        niveaux_ref = [hauteurs_tris[0]]
        
        restants_v2 = [h for h in hauteurs_tris if abs(h - niveaux_ref[0]) > (marge_pct * niveaux_ref[0]) and h <= plafond_max_acceptable]
        if restants_v2:
            niveaux_ref.append(restants_v2[0])
            
            restants_v3 = [h for h in hauteurs_tris if all(abs(h - r) > (marge_pct * r) for r in niveaux_ref) and h <= plafond_max_acceptable]
            if restants_v3:
                niveaux_ref.append(restants_v3[0])

        couleurs_zones = {
            0: ('Talon principal', '#2ca02c'),
            1: ('Deuxième Talon', '#ff7f0e'),
            2: ('Troisième Talon', '#9467bd')
        }

        for p in plateaux_detectes:
            if p['hauteur'] > plafond_max_acceptable:
                continue
            idx_proche = np.argmin([abs(p['hauteur'] - ref) for ref in niveaux_ref])
            if abs(p['hauteur'] - niveaux_ref[idx_proche]) <= (marge_pct * niveaux_ref[idx_proche]):
                p['zone'], p['couleur'] = couleurs_zones[idx_proche]

    # --- 3. TRACÉ DU GRAPHIQUE ---
    fig, ax = plt.subplots(figsize=(14, 5.5))
    nom = nom or data.attrs.get("nom", "Courbe")
    
    ax.plot(charge_brute.index, charge_brute.values, lw=0.6, color="#7f7f7f", alpha=0.3, label="Zone sans plateaux / Pics")
    ax.plot(charge_lissee.index, charge_lissee.values, lw=1, color="#1f77b4", alpha=0.7, label="Charge lissée")

    legendes_ajoutees = set()
    for p in plateaux_detectes:
        if p['zone'] is not None:
            lbl = p['zone'] if p['zone'] not in legendes_ajoutees else ""
            legendes_ajoutees.add(p['zone'])
            # Tracé du bloc uni fusionné
            ax.axvspan(p['t_debut'], p['t_fin'], color=p['couleur'], alpha=0.25, label=lbl)
            ax.plot(p['index'], [p['hauteur']] * len(p['index']), color=p['couleur'], lw=2.5)

    ax.set_title(f"{nom} | Regroupement des Plateaux ({int(marge_pct*100)}% de marge) | {t0.date()} -> {t1.date()}", fontsize=13, fontweight="bold")
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
def trouver_semaines_calendaires_extremes(data, out_max=None, out_min=None, nom=None):
    """
    Identifie la semaine calendaire (strictement du Lundi au Dimanche) 
    la plus consommatrice (MAX) et la moins consommatrice (MIN) sur la période.
    """
    nom = nom or data.attrs.get("nom", "Bâtiment")
    
    # 1. Calcul de la charge totale instantanée
    charge_totale = data.sum(axis=1)
    
    # 2. Conversion de la puissance (W) en Énergie (Wh) par point
    pas_temps = pd.Series(charge_totale.index).diff().median()
    facteur_horaire = pas_temps.total_seconds() / 3600  # ex: 10 min = 0.1666 h
    energie_pas = charge_totale * facteur_horaire
    
    # 3. Regroupement par semaine calendaire stricte (Lundi au Dimanche)
    # 'W-MON' agrège les données par semaine se terminant le dimanche soir / lundi 00:00
    # closed='left' et label='left' permettent de marquer la semaine par son LUNDI de départ
    conso_semaines = energie_pas.resample('W-MON', closed='left', label='left').sum()
    
    # Sécurité : On élimine la première et la dernière ligne si elles sont incomplètes 
    # (ex: si ton fichier commence un mercredi, la première "semaine" n'aura que 4 jours)
    if len(conso_semaines) > 2:
        conso_semaines = conso_semaines.iloc[1:-1]
    
    if conso_semaines.empty:
        raise ValueError("Pas assez de données pour extraire une semaine complète.")

    # 4. Extraction des records (Max et Min)
    # idxmax() et idxmin() nous donnent maintenant le LUNDI de début de la semaine
    date_debut_max = conso_semaines.idxmax()
    date_fin_max = date_debut_max + pd.Timedelta(days=6, hours=23, minutes=59)
    
    date_debut_min = conso_semaines.idxmin()
    date_fin_min = date_debut_min + pd.Timedelta(days=6, hours=23, minutes=59)
    
    # Conversion en kWh pour l'affichage
    conso_max_kwh = conso_semaines.max() / 1000
    conso_min_kwh = conso_semaines.min() / 1000

    print(f"=== ANALYSE CALENDAIRE (LUN-DIM) POUR {nom.upper()} ===")
    print(f"Semaine MAX : Du Lundi {date_debut_max.date()} au Dimanche {date_fin_max.date()} | Conso : {conso_max_kwh:.1f} kWh\m²")
    print(f"Semaine MIN : Du Lundi {date_debut_min.date()} au Dimanche {date_fin_min.date()} | Conso : {conso_min_kwh:.1f} kWh\m²\n")
    if conso_min_kwh > 0:
        ratio = conso_max_kwh / conso_min_kwh
        print(f"La consommation est {ratio:.1f} fois plus importante sur la semaine MAX que sur la semaine MIN.\n")
    else :
        print("La consommation minimale est nulle, impossible de calculer un ratio.\n")
    
    # 5. Extraction des sous-ensembles de données pour les graphiques
    df_semaine_max = data.loc[date_debut_max:date_fin_max]
    df_semaine_min = data.loc[date_debut_min:date_fin_min]
    
    # 6. Tracé des graphiques
    for df_semaine, t0, t1, type_ext, conso, path_out in [
        (df_semaine_max, date_debut_max, date_fin_max, "MAX (Plus gourmande)", conso_max_kwh, out_max),
        (df_semaine_min, date_debut_min, date_fin_min, "MIN (Plus sobre)", conso_min_kwh, out_min)
    ]:
        fig, ax = plt.subplots(figsize=(12, 5))
        charge_sub = df_semaine.sum(axis=1)
        
        ax.plot(charge_sub.index, charge_sub.values, color="#1f77b4", lw=1)
        ax.fill_between(charge_sub.index, 0, charge_sub.values, color="#1f77b4", alpha=0.1)
        
        ax.set_title(f"{nom} | Semaine {type_ext} : Lun {t0.date()} -> Dim {t1.date()} ({conso:.1f} kWh)", fontsize=12, fontweight="bold")
        ax.set_ylabel("Puissance (W)")
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        
        fig.tight_layout()
        if path_out:
            fig.savefig(path_out, dpi=110, bbox_inches="tight")
            plt.close(fig)
        else:
            plt.show()
        
    return (date_debut_max, date_fin_max), (date_debut_min, date_fin_min)





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




