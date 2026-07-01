from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import plotly.express as px

EXCEL_EPOCH = pd.Timestamp("1899-12-30")
DUREES = {"jour": "1D", "semaine": "7D", "mois": "1MS", "annee": "1YS", "tout": None}


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


