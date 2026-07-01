from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
import plotly.express as px
import ruptures as rpt
from sklearn.cluster import KMeans

EXCEL_EPOCH = pd.Timestamp("1899-12-30")
DUREES = {"jour": "1D", "semaine": "7D", "mois": "1MS", "annee": "1YS", "tout": None}


# **Visualisation**: Affichage des courbes à l'échelle de la journée, du mois, de la semaine et de l'année

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


def tracer(data, echelle="tout", debut=None, titre=None, out=None):
    # 1. Gestion de la nouvelle échelle "tout"
    if echelle == "tout":
        sous = data
        t0 = data.index.min()
        t1 = data.index.max()
    else:
        # On ne fait appel au découpage que si on demande une échelle précise
        sous, t0, t1 = fenetre(data, echelle, debut)
        
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    # 2. Création de la figure
    fig, ax = plt.subplots(figsize=(14, 5))
    for col in sous.columns:
        ax.plot(sous.index, sous[col], lw=0.8, label=str(col))

    # Adaptation du titre par défaut selon l'échelle
    titre_defaut = f"Vue globale : {t0.date()} -> {t1.date()}" if echelle == "tout" else f"{echelle.capitalize()} : {t0.date()} -> {t1.date()}"
    ax.set_title(titre or titre_defaut, fontsize=13, fontweight="bold")
    
    ax.set_ylabel("Puissance en W")
    ax.grid(alpha=0.3)
    if len(sous.columns) > 1:
        ax.legend(fontsize=8, ncol=2)

    # 3. Format de l'axe temps adapté à l'échelle
    if echelle == "jour":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Hh"))
    elif echelle == "semaine":
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m"))
    elif echelle == "tout" or echelle == "annee":
        # Pour une vue globale, afficher "Mois Année" (ex: Jan 2022) évite de surcharger l'axe
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


# **Réalisation de semaine type, mois type, journée type**(qu'on peut filtrer)

def tracer_semaine_type_mois(data, mois, titre=None):
    """
    Calcule et trace (avec Plotly) la semaine type pour un mois donné,
    en se basant sur les 12 derniers mois d'historique du fichier.
    """
    # 1. Définir la fenêtre des 12 derniers mois (année glissante)
    date_fin = data.index.max()
    date_debut = date_fin - pd.DateOffset(years=1)
    
    # 2. Filtrer les données sur cette fenêtre stricte
    df_12_mois = data[(data.index > date_debut) & (data.index <= date_fin)]
    
    # 3. Récupérer uniquement le mois demandé
    df_mois = df_12_mois[df_12_mois.index.month == mois]
    
    if df_mois.empty:
        print(f"Attention : Aucune donnée pour le mois {mois} entre le {date_debut.date()} et le {date_fin.date()}")
        return None
        
    # 4. Calcul de la semaine type (Moyenne)
    df_mois = df_mois.copy()
    df_mois['num_jour'] = df_mois.index.dayofweek
    df_mois['heure_minute'] = df_mois.index.strftime('%H:%M')
    
    semaine_type = df_mois.groupby(['num_jour', 'heure_minute']).mean(numeric_only=True)
    
    # 5. Reconstruire un index textuel propre
    noms_axes = []
    jours_noms = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    
    for (num_jour, hm) in semaine_type.index:
        noms_axes.append(f"{jours_noms[num_jour]} {hm}")
        
    semaine_type.index = noms_axes
    
    # 6. Création du graphique interactif Plotly
    titre_final = titre or f"Semaine type - Mois n°{mois} (Calculée sur les 12 derniers mois)"
    
    # px.line trace automatiquement toutes les colonnes du tableau
    fig = px.line(semaine_type, title=titre_final, 
                  labels={"index": "Jour et Heure", "value": "Puissance (W)", "variable": "Capteur"})
    
    # 7. Nettoyage de l'axe X pour ne pas surcharger l'affichage
    # On force Plotly à ne mettre une graduation que tous les jours à minuit (tous les 144 points)
    positions = np.arange(0, len(semaine_type), 144)
    etiquettes = [semaine_type.index[i] for i in positions]
    
    fig.update_xaxes(
        tickmode='array',
        tickvals=positions,
        ticktext=etiquettes
    )
    
    # 8. Esthétique : un curseur unifié pour comparer tous les capteurs d'un coup
    fig.update_layout(
        hovermode="x unified",
        legend_title_text='Légende'
    )
    
    fig.show()
    
    # On renvoie le tableau de données au cas où tu voudrais faire d'autres calculs avec !
    return semaine_type


def tracer_semaine_type_mois_filtre(data, mois, span=7, titre=None):
    """
    Calcule et trace (avec Plotly) la semaine type pour un mois donné,
    en appliquant d'abord un filtre passe-bas exponentiel pour éliminer le bruit.
    """
    # 1. Définir la fenêtre des 12 derniers mois (année glissante)
    date_fin = data.index.max()
    date_debut = date_fin - pd.DateOffset(years=1)
    
    # 2. Filtrer les données sur cette fenêtre stricte
    df_12_mois = data[(data.index > date_debut) & (data.index <= date_fin)].copy()
    
    # 3. LE FILTRAGE (On le fait sur l'année entière pour éviter les effets de bord)
    # On sélectionne uniquement les colonnes numériques (les Watts)
    cols_num = df_12_mois.select_dtypes(include=[np.number]).columns
    df_12_mois[cols_num] = df_12_mois[cols_num].ewm(span=span, adjust=False).mean()
    
    # 4. Récupérer uniquement le mois demandé après le filtrage
    df_mois = df_12_mois[df_12_mois.index.month == mois]
    
    if df_mois.empty:
        print(f"Attention : Aucune donnée pour le mois {mois} entre le {date_debut.date()} et le {date_fin.date()}")
        return None
        
    # 5. Calcul de la semaine type (Moyenne des semaines filtrées)
    df_mois = df_mois.copy()
    df_mois['num_jour'] = df_mois.index.dayofweek
    df_mois['heure_minute'] = df_mois.index.strftime('%H:%M')
    
    semaine_type = df_mois.groupby(['num_jour', 'heure_minute']).mean(numeric_only=True)
    
    # 6. Reconstruire un index textuel propre
    noms_axes = []
    jours_noms = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    
    for (num_jour, hm) in semaine_type.index:
        noms_axes.append(f"{jours_noms[num_jour]} {hm}")
        
    semaine_type.index = noms_axes
    
    # 7. Création du graphique interactif Plotly
    titre_final = titre or f"Semaine type (Lissée span={span}) - Mois n°{mois}"
    
    fig = px.line(semaine_type, title=titre_final, 
                  labels={"index": "Jour et Heure", "value": "Puissance lissée (W)", "variable": "Capteur"})
    
    # Nettoyage de l'axe X (une graduation tous les minuits = 144 points)
    positions = np.arange(0, len(semaine_type), 144)
    etiquettes = [semaine_type.index[i] for i in positions]
    
    fig.update_xaxes(
        tickmode='array',
        tickvals=positions,
        ticktext=etiquettes
    )
    
    fig.update_layout(
        hovermode="x unified",
        legend_title_text='Légende'
    )
    
    fig.show()
    
    return semaine_type


def tracer_difference_semaine_type_mois(data, mois1, mois2, span=7, titre=None):
    """
    Calcule et trace la différence de consommation entre la semaine type de deux mois distincts (mois1 - mois2).
    Utile pour visualiser l'impact saisonnier (chauffage, climatisation) sur les journées types.
    """
    # 1. Définir la fenêtre des 12 derniers mois
    date_fin = data.index.max()
    date_debut = date_fin - pd.DateOffset(years=1)
    
    # 2. Filtrer les données sur cette fenêtre
    df_12_mois = data[(data.index > date_debut) & (data.index <= date_fin)].copy()
    
    # 3. Lissage global pour éviter les effets de bord
    cols_num = df_12_mois.select_dtypes(include=[np.number]).columns
    df_12_mois[cols_num] = df_12_mois[cols_num].ewm(span=span, adjust=False).mean()
    
    # 4. Extraction et vérification des deux mois
    df_m1 = df_12_mois[df_12_mois.index.month == mois1].copy()
    df_m2 = df_12_mois[df_12_mois.index.month == mois2].copy()
    
    if df_m1.empty or df_m2.empty:
        print(f"Attention : Données manquantes pour le mois {mois1} ou {mois2} sur la période analysée.")
        return None

    # 5. Fonction interne pour calculer la semaine type d'un sous-dataframe
    def calculer_profil(df):
        df['num_jour'] = df.index.dayofweek
        df['heure_minute'] = df.index.strftime('%H:%M')
        return df.groupby(['num_jour', 'heure_minute']).mean(numeric_only=True)

    semaine_type1 = calculer_profil(df_m1)
    semaine_type2 = calculer_profil(df_m2)
    
    # 6. Soustraction des deux semaines types
    # L'alignement se fait automatiquement sur le multi-index (num_jour, heure_minute)
    difference = semaine_type1 - semaine_type2
    
    # 7. Reconstruire un index textuel propre pour l'affichage
    noms_axes = []
    jours_noms = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    
    for (num_jour, hm) in difference.index:
        noms_axes.append(f"{jours_noms[num_jour]} {hm}")
        
    difference.index = noms_axes
    
    # 8. Création du graphique Plotly
    titre_final = titre or f"Différence de profil type : Mois {mois1} moins Mois {mois2} (span={span})"
    
    fig = px.line(difference, title=titre_final, 
                  labels={"index": "Jour et Heure", "value": "Écart de Puissance (W)", "variable": "Capteur"})
    
    # Ajout d'une ligne zéro pour bien repérer qui consomme le plus
    fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
    
    # Nettoyage de l'axe X (une graduation tous les minuits = 144 points)
    positions = np.arange(0, len(difference), 144)
    etiquettes = [difference.index[i] for i in positions]
    
    fig.update_xaxes(tickmode='array', tickvals=positions, ticktext=etiquettes)
    fig.update_layout(hovermode="x unified", legend_title_text='Légende')
    
    fig.show()
    
    return difference


# **Tracer les talons(fixes et dynamiques, semaine, mois, année)**

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


def tracer_talon_semaine_dynamique(path, debut=None, fenetre_heures=3, percentile=50, out=None):
    """
    Calcule et trace les paliers de consommation sur une semaine 
    en utilisant un quantile glissant (médiane par défaut à P50) à l'échelle horaire.
    """
    data = charger(path)
    sous, t0, t1 = fenetre(data, "semaine", debut)
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    charge = sous.sum(axis=1)
    
    # Échelle horaire : 1 heure = 6 points (car pas de temps de 10 min)
    points_par_heure = 6
    taille_fenetre = int(fenetre_heures * points_par_heure)
    
    # Calcul des paliers dynamiques (médiane glissante centrée par défaut)
    # min_periods=3 permet de calculer dès qu'on a 30 min de données aux bords
    paliers_dynamiques = charge.rolling(
        window=taille_fenetre, 
        center=True, 
        min_periods=3
    ).quantile(percentile / 100)
    
    # Statistiques de la semaine
    moyenne_semaine = charge.mean()
    palier_moyen = paliers_dynamiques.mean()
    part = 100 * palier_moyen / moyenne_semaine if moyenne_semaine else float("nan")

    nom = Path(path).stem
    print(f"{nom} | Semaine {t0.date()} -> {t1.date()}")
    print(f"  palier moyen (P{percentile}) : {palier_moyen:.4g}")
    print(f"  part d'énergie sous paliers : {part:.0f} %")

    fig, ax = plt.subplots(figsize=(14, 5.5))
    
    # Charge brute de la semaine (bleu sombre de ta charte)
    ax.plot(charge.index, charge.values, lw=0.8, color="#1f4e79", alpha=0.5, label="charge brute")
    
    # Courbe des paliers (orange de ta charte)
    ax.plot(paliers_dynamiques.index, paliers_dynamiques.values, color="#c55a11", lw=2, 
            label=f"talons glissants ({fenetre_heures}h)")
    ax.fill_between(paliers_dynamiques.index, 0, paliers_dynamiques.values, color="#c55a11", alpha=0.12)

    ax.set_title(f"{nom} - talons sur la semaine du {t0.date()} "
                 f"(Fenêtre : {fenetre_heures}h, part sous talon : {part:.0f} %)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("puissance brute (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # Formatage de l'axe X pour voir les jours et les heures de la semaine
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m\n%H:%M"))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center") # Centré pour l'alignement des heures

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return paliers_dynamiques


def tracer_talon_jour_dynamique(path, debut=None, fenetre_heures=1.0, percentile=50, out=None):
    """
    Calcule et trace les paliers de consommation sur une journée 
    en utilisant un quantile glissant à l'échelle intra-journalière.
    """
    data = charger(path)
    
    # 1. On utilise le mot-clé "jour" (en supposant que ta fonction fenetre le gère)
    sous, t0, t1 = fenetre(data, "jour", debut)
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    charge = sous.sum(axis=1)
    
    # 2. Gestion de la fenêtre (on autorise les fractions d'heure, ex: 0.5 = 30 min)
    points_par_heure = 6
    taille_fenetre = max(1, int(fenetre_heures * points_par_heure))
    
    # Calcul des paliers
    paliers_dynamiques = charge.rolling(
        window=taille_fenetre, 
        center=True, 
        min_periods=1
    ).quantile(percentile / 100)
    
    # Statistiques de la journée
    moyenne_jour = charge.mean()
    palier_moyen = paliers_dynamiques.mean()
    part = 100 * palier_moyen / moyenne_jour if moyenne_jour else float("nan")

    nom = Path(path).stem
    print(f"{nom} | Journée du {t0.date()}")
    print(f"  palier moyen (P{percentile}) : {palier_moyen:.4g}")
    print(f"  part d'énergie sous paliers : {part:.0f} %")

    fig, ax = plt.subplots(figsize=(14, 5.5))
    
    # Trace de la charge brute (j'ai très légèrement épaissi le trait 'lw=1.2' 
    # car on a moins de points sur une journée, c'est plus lisible)
    ax.plot(charge.index, charge.values, lw=1.2, color="#1f4e79", alpha=0.6, label="charge brute")
    
    ax.plot(paliers_dynamiques.index, paliers_dynamiques.values, color="#c55a11", lw=2, 
            label=f"talons glissants ({fenetre_heures}h)")
    ax.fill_between(paliers_dynamiques.index, 0, paliers_dynamiques.values, color="#c55a11", alpha=0.12)

    ax.set_title(f"{nom} - Talons sur la journée du {t0.date()} "
                 f"(Fenêtre : {fenetre_heures}h, part sous talon : {part:.0f} %)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("puissance brute (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # 3. Formatage de l'axe X dédié à la journée (Heure:Minute uniquement)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    
    # Optionnel mais très propre : forcer une graduation toutes les 2 heures
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")

    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return paliers_dynamiques

# **repérer les programmes horaires, les motifs des courbes**

# +
#algo qui itère le talon dynamique pour repérer le deuxième palier. Fonctionne pas très bien


def tracer_couches_un_jour(path, date_cible, fenetre_heures=2.0, p_talon=10, p_palier=50, out=None):
    """
    Extrait et trace les paliers par couches empilées strictement pour UNE seule journée.
    date_cible doit être au format 'YYYY-MM-DD'
    """
    data = charger(path)
    
    # Extraction stricte de la journée demandée via le slicing de l'index DateTime
    df_jour = data.loc[date_cible]
    
    if df_jour.empty:
        raise ValueError(f"Aucune donnée trouvée pour la date : {date_cible}")
        
    # On écrase le DataFrame en une Series 1D propre (somme si multi-colonnes)
    charge = df_jour.sum(axis=1)
    
    # Pas de temps 10 min -> 6 pts/h
    pts_par_heure = 6
    taille_fenetre = max(1, int(fenetre_heures * pts_par_heure))
    
    # ---- COUCHE 1 : Le Talon Fondamental ----
    couche1_talon = charge.rolling(
        window=taille_fenetre, center=True, min_periods=1
    ).quantile(p_talon / 100)
    
    # ---- COUCHE 2 : Le Palier d'Activité ----
    residu_actif = (charge - couche1_talon).clip(lower=0)
    couche2_activite = residu_actif.rolling(
        window=taille_fenetre, center=True, min_periods=1
    ).quantile(p_palier / 100)
    
    # ---- VISUALISATION ----
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Courbe brute de la journée
    ax.plot(charge.index, charge.values, lw=1.2, color="#1f4e79", alpha=0.5, label="Charge brute")
    
    # Zone empilée (Stackplot)
    ax.stackplot(charge.index, 
                 couche1_talon, 
                 couche2_activite, 
                 labels=[f'Couche 1 : Talon Fond (P{p_talon})', 
                         f'Couche 2 : Bloc Activité (P{p_palier})'],
                 colors=['#c55a11', '#2ca02c'], 
                 alpha=0.25)
    
    # Lignes de contour pour la netteté des paliers
    ax.plot(charge.index, couche1_talon, color='#c55a11', lw=1.5, ls="--")
    ax.plot(charge.index, couche1_talon + couche2_activite, color='#2ca02c', lw=2)
    
    # Habillage
    nom = Path(path).stem
    ax.set_title(f"{nom} - Décomposition en couches du {date_cible} (Fenêtre : {fenetre_heures}h)", 
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # Formatage de l'axe X propre pour l'échelle de 24h
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(ticker.MaxNLocator(12)) # 12 graduations max (toutes les 2 heures environ)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    
    fig.tight_layout()
    
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return couche1_talon, couche2_activite


# +
#algo de clustering

def tracer_paliers_kmeans(path, date_cible, nb_etats=3, fenetre_lissage_heures=1.0, out=None):
    """
    Détecte les régimes de fonctionnement d'un bâtiment via l'algorithme K-Means.
    Remplace l'approche par soustraction par une approche de clustering non-supervisé.
    """
    data = charger(path) # Ta fonction habituelle
    df_jour = data.loc[date_cible]
    
    if df_jour.empty:
        raise ValueError(f"Aucune donnée trouvée pour la date : {date_cible}")
        
    charge = df_jour.sum(axis=1)
    
    # 1. PRÉ-TRAITEMENT : Lissage médian pour enlever le bruit "transitoire"
    pts_par_heure = 6
    taille_fenetre = max(1, int(fenetre_lissage_heures * pts_par_heure))
    charge_lissee = charge.rolling(window=taille_fenetre, center=True, min_periods=1).median()
    
    # 2. MACHINE LEARNING : Clustering K-Means
    # On reformate les données pour scikit-learn (qui attend un tableau 2D)
    X = charge_lissee.values.reshape(-1, 1)
    
    # On initialise K-Means (n_init=10 est standard pour la stabilité)
    kmeans = KMeans(n_clusters=nb_etats, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)
    
    # Les "centres" trouvés par K-Means sont nos valeurs de paliers exactes !
    centres = kmeans.cluster_centers_.flatten()
    
    # On reconstruit une courbe "idéale" en remplaçant chaque point par la valeur de son palier
    courbe_etats = np.array([centres[label] for label in labels])
    df_etats = pd.Series(courbe_etats, index=charge.index)
    
    # On trie les centres pour l'affichage (du plus petit au plus grand)
    centres_tries = np.sort(centres)
    
    # 3. VISUALISATION
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Courbe brute en fond
    ax.plot(charge.index, charge.values, lw=1, color="#1f4e79", alpha=0.4, label="Charge brute")
    
    # Superposition des blocs de régime
    ax.plot(df_etats.index, df_etats.values, color="#d62728", lw=3, drawstyle="steps-mid", 
            label="Régimes détectés (K-Means)")
    
    # Ajout de lignes horizontales pour bien montrer les paliers découverts
    couleurs_paliers = ['#2ca02c', '#ff7f0e', '#9467bd', '#8c564b']
    for i, centre in enumerate(centres_tries):
        ax.axhline(centre, color=couleurs_paliers[i % len(couleurs_paliers)], 
                   ls="--", lw=1.5, alpha=0.8, 
                   label=f"État {i+1} : {centre:.4g} W")
    
    nom = Path(path).stem
    ax.set_title(f"{nom} - Détection des régimes (Machine Learning) du {date_cible}", 
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    
    # Légende à l'extérieur pour ne pas cacher les données
    ax.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    
    # Formatage de l'axe X
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(ticker.MaxNLocator(12))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return df_etats, centres_tries


# +
#algo qui utilise la bibliot

def tracer_paliers_ruptures(path, date_cible, penalite=0.0001, out=None):
    """
    Détecte les paliers (régimes) d'une journée avec la librairie ruptures (méthode PELT).
    Pas besoin de connaître le nombre de clusters à l'avance.
    """
    data = charger(path)
    df_jour = data.loc[date_cible]
    
    if df_jour.empty:
        raise ValueError(f"Aucune donnée trouvée pour la date : {date_cible}")
        
    charge = df_jour.sum(axis=1)
    signal = charge.values
    
    # 1. DÉTECTION DES RUPTURES
    # model="l2" : cherche les sauts de moyenne (parfait pour nos paliers)
    # min_size=3 : force un palier à durer au moins 30 minutes (3 points de 10 min) pour ignorer les micro-pics
    algo = rpt.Pelt(model="l2", min_size=3).fit(signal)
    
    # Prédiction : retourne les indices (positions) des ruptures trouvées
    # La pénalité est le paramètre clé à ajuster !
    points_rupture = algo.predict(pen=penalite)
    
    # 2. RECONSTRUCTION DE LA COURBE EN PALIERS
    courbe_paliers = np.zeros_like(signal)
    debut = 0
    
    for fin in points_rupture:
        # On extrait le segment entre deux ruptures
        segment = signal[debut:fin]
        if len(segment) > 0:
            # On attribue à ce segment sa valeur médiane pour créer un palier plat et net
            courbe_paliers[debut:fin] = np.median(segment)
        debut = fin
        
    df_paliers = pd.Series(courbe_paliers, index=charge.index)
    
    # 3. VISUALISATION
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Courbe brute
    ax.plot(charge.index, charge.values, lw=1.2, color="#1f4e79", alpha=0.4, label="Charge brute")
    
    # Courbe des paliers détectés
    ax.plot(df_paliers.index, df_paliers.values, color="#d62728", lw=2.5, drawstyle="steps-post", 
            label="Régimes (Ruptures PELT)")
    
    # Ajout de lignes verticales pour marquer visuellement les instants de rupture
    for p in points_rupture[:-1]: # On ignore le dernier point qui est la fin du signal
        heure_rupture = charge.index[p]
        ax.axvline(heure_rupture, color='black', linestyle='--', alpha=0.3)
        # Petite annotation de l'heure
        ax.text(heure_rupture, ax.get_ylim()[1]*0.95, heure_rupture.strftime('%H:%M'), 
                rotation=90, va='top', ha='right', fontsize=9, alpha=0.7)

    nom = Path(path).stem
    nb_ruptures = len(points_rupture) - 1
    ax.set_title(f"{nom} - Détection chronologique ({nb_ruptures} ruptures trouvées) le {date_cible}", 
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # Formatage de l'axe X
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(ticker.MaxNLocator(12))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return df_paliers, points_rupture


# +
#algo qui utilise la bibliothèque rupture+ coloriage

def tracer_paliers_ruptures_coloriage(path, date_cible, penalite=0.0001, out=None):
    """
    Détecte les paliers (régimes) d'une journée avec la librairie ruptures (méthode PELT).
    Pas besoin de connaître le nombre de clusters à l'avance.
    """
    data = charger(path)
    df_jour = data.loc[date_cible]
    
    if df_jour.empty:
        raise ValueError(f"Aucune donnée trouvée pour la date : {date_cible}")
        
    charge = df_jour.sum(axis=1)
    signal = charge.values
    
    # 1. DÉTECTION DES RUPTURES
    # model="l2" : cherche les sauts de moyenne (parfait pour nos paliers)
    # min_size=3 : force un palier à durer au moins 30 minutes (3 points de 10 min) pour ignorer les micro-pics
    algo = rpt.Pelt(model="l2", min_size=3).fit(signal)
    
    # Prédiction : retourne les indices (positions) des ruptures trouvées
    # La pénalité est le paramètre clé à ajuster !
    points_rupture = algo.predict(pen=penalite)
    
    # 2. RECONSTRUCTION DE LA COURBE EN PALIERS
    courbe_paliers = np.zeros_like(signal)
    debut = 0
    
    for fin in points_rupture:
        # On extrait le segment entre deux ruptures
        segment = signal[debut:fin]
        if len(segment) > 0:
            # On attribue à ce segment sa valeur médiane pour créer un palier plat et net
            courbe_paliers[debut:fin] = np.median(segment)
        debut = fin
        
    df_paliers = pd.Series(courbe_paliers, index=charge.index)
    
    # 3. VISUALISATION
    fig, ax = plt.subplots(figsize=(15, 6))
    
    # Courbe brute en arrière-plan
    ax.plot(charge.index, charge.values, lw=0.8, color="#1f4e79", alpha=0.4, label="Charge brute")
    
    # --- NOUVEAU : COLORIAGE DES RECTANGLES ---
    # On récupère une jolie palette de couleurs intégrée à Matplotlib (ex: 'Set2', 'Pastel1' ou 'tab10')
    import matplotlib.cm as cm
    palette = plt.colormaps['Set2'].colors 
    
    debut_idx = 0
    for i, fin_idx in enumerate(points_rupture):
        # Sécurité pour le tout dernier point de la courbe
        if fin_idx < len(charge):
            x_debut = charge.index[debut_idx]
            x_fin = charge.index[fin_idx]
        else:
            x_debut = charge.index[debut_idx]
            x_fin = charge.index[-1]
            
        # La hauteur du rectangle correspond à la valeur du palier sur ce segment
        valeur_palier = df_paliers.iloc[debut_idx]
        
        # On dessine un rectangle parfait entre x_debut et x_fin
        ax.fill_between([x_debut, x_fin], 0, [valeur_palier, valeur_palier], 
                        color=palette[i % len(palette)], alpha=0.5, 
                        edgecolor='none') # edgecolor='none' enlève les bordures parasites
        
        debut_idx = fin_idx
    # -----------------------------------------
    
    # Superposer la ligne rouge "en escalier" par-dessus pour bien marquer le contour
    ax.plot(df_paliers.index, df_paliers.values, color="#d62728", lw=2, drawstyle="steps-post", 
            label="Régimes (Ruptures PELT)")
    
    # Ajout de lignes verticales pour marquer visuellement les instants de rupture
    for p in points_rupture[:-1]: # On ignore le dernier point qui est la fin du signal
        heure_rupture = charge.index[p]
        ax.axvline(heure_rupture, color='black', linestyle='--', alpha=0.3)
        # Petite annotation de l'heure
        ax.text(heure_rupture, ax.get_ylim()[1]*0.95, heure_rupture.strftime('%H:%M'), 
                rotation=90, va='top', ha='right', fontsize=9, alpha=0.7)

    nom = Path(path).stem
    nb_ruptures = len(points_rupture) - 1
    ax.set_title(f"{nom} - Détection chronologique ({nb_ruptures} ruptures trouvées) le {date_cible}", 
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # Formatage de l'axe X
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(ticker.MaxNLocator(12))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center")
    
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return df_paliers, points_rupture


# -

def tracer_paliers_ruptures_semaine(path, debut=None, penalite=0.001, out=None):
    """
    Détecte et trace les paliers de fonctionnement sur une semaine complète
    via l'algorithme PELT (bibliothèque ruptures).
    """
    data = charger(path)
    
    # 1. Extraction de la semaine via ta fonction dédiée
    sous, t0, t1 = fenetre(data, "semaine", debut)
    if sous.empty:
        raise ValueError(f"Aucune donnee entre {t0.date()} et {t1.date()}")

    charge = sous.sum(axis=1)
    signal = charge.values
    
    # 2. DÉTECTION DES RUPTURES
    # min_size=12 : Un palier doit durer au moins 2 heures (12 pts * 10 min)
    algo = rpt.Pelt(model="l2", min_size=12).fit(signal)
    points_rupture = algo.predict(pen=penalite)
    
    # 3. RECONSTRUCTION DE LA COURBE EN PALIERS
    courbe_paliers = np.zeros_like(signal)
    debut_idx = 0
    
    for fin_idx in points_rupture:
        segment = signal[debut_idx:fin_idx]
        if len(segment) > 0:
            # Utilisation de la médiane sur le segment pour un rendu bien plat
            courbe_paliers[debut_idx:fin_idx] = np.median(segment)
        debut_idx = fin_idx
        
    df_paliers = pd.Series(courbe_paliers, index=charge.index)
    
    # 4. VISUALISATION
    fig, ax = plt.subplots(figsize=(15, 6))
    
    # Courbe brute de la semaine (bleu transparent)
    ax.plot(charge.index, charge.values, lw=0.8, color="#1f4e79", alpha=0.4, label="Charge brute")
    
    # Courbe des paliers (orange de ta charte)
    ax.plot(df_paliers.index, df_paliers.values, color="#c55a11", lw=2.5, drawstyle="steps-post", 
            label="Paliers (Ruptures PELT)")
    
    # Ajout des lignes verticales de rupture (uniquement si elles ne surchargent pas le graphe)
    # On n'affiche le texte de l'heure que pour les grosses ruptures pour garder le graphique lisible
    for p in points_rupture[:-1]:
        heure_rupture = charge.index[p]
        ax.axvline(heure_rupture, color='black', linestyle='--', alpha=0.2, lw=1)
        
    # Habillage
    nom = Path(path).stem
    nb_ruptures = len(points_rupture) - 1
    ax.set_title(f"{nom} - Profil hebdomadaire ({nb_ruptures} paliers détectés) - Semaine du {t0.date()}", 
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Puissance (W)")
    ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    
    # Formatage de l'axe X adapté pour une semaine (Jour de la semaine + Date)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a %d/%m\n%H:%M"))
    # Une graduation majeure toutes les 12 heures pour bien voir les transitions Jour/Nuit
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12]))
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=9)
    
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
        
    return df_paliers, points_rupture


