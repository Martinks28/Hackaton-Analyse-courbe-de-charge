# Chaine d'analyse automatisée des courbes de charge des bâtiments tertiaires

## Contexte
Le secteur tertiaire représente 33% de la consommation finale d'éléctricité en France en 2024. Il y a donc un réel enjeu écologique (bien que l'éléctricité soit quasiment exclusivement décarbonée) mais également économique lorsqu'il s'agit de réduire la consommation des bâtiments de bureaux et commerciaux. 

<img width="533" height="297" alt="image" src="https://github.com/user-attachments/assets/e5e7778f-71d7-4878-8ab4-bbae5b414ba5" />

A l'échelle d'une période longue et d'une surface alimentée importante, quelques kW/m² d'économisés par jour peuvent représenter un gain d'énergie consommé remarquable. D'autant plus que les leviers pour réduire cette consommation sont souvent plus simple qu'on y pense. C'est justement l'objet du projet : à partir de courbes de charges (ce sont les seules données disponibles lorsqu'il n'y a pas de compteurs spécifiques sur les sites) nous proposons une analyse simplifiée et automatisée afin de mettre en évidence les comportements énergetiques problématiques. 

Cette analyse est particulièrement cruciale en regard de l'objectif de réduction de 40% avant 20230 imposé aux bâtiments concernés par le [*Décret Tertiaire*](https://www.manche.gouv.fr/Actions-de-l-Etat/Amenagement-territoire-energie/Urbanisme/Qualite-de-la-construction/Batiments-tertiaires-le-dispositif-Eco-energie-tertiaire).

### Postes de consommation
La consommation éléctrique d'un bâtiment classique se répartit en différents types d'équipements chacun ayant leurs spécificités.

#### Ventilation
Les équipements de ventilation sont essentiels dans tout lieu occupé pour assurer le renouvellement de l'air en continu. La ventilation peut être dotée d'une batterie chaude et d'une batterie glacée pour amener de l'air à une tempréature proche de celle intérieure. On les appelle centrales de traitement d'air (CTA).

<img width="500" height="281" alt="image" src="https://github.com/user-attachments/assets/f952ecfc-b3b9-4ace-a83f-3ecd4004d4c1" />

#### Chauffage, climatisation
La climatisation et le chauffage regroupent les radiateurs (le plus souvent à eau), les ventilo-convecteurs ou encore des panneaux rayonnants. Ces équipements reposent sur des réseaux de chaleurs/fraicheur alimentés par des pompes de différents tailles selon le mode de distribution. Par exemple CPCU fournit de la vapeur d'eau chaude à de nombreux bâtiments parisiens.

#### Usages courants
Cette dernière catégorie regroupe les éclairages, la bureautique, les prises de courant, et autres appareils auxiliaires

## Objectifs
Les fichiers que nous utilisons sont des tableaux comportant les puissance demandées en fonction du temps sur des périodes diverses. 

La première étape consiste à visualiser les données. Ensuite nous cherchons à déterminer les éléments remarquables sur la courbe : le talon, les programmes horaires des équipements, ainsi que certains motifs périodiques qui mettraient en évidence certains cycles des machines thermiques. Le but final étant de partitionner la courbe de charge en fonction des types de "consommateurs" d'éléctricité. 

## Implémentation
### Visualisation
### Analyse des plateaux
* Méthode centile : on cherche la valeur du 5ème centile sur les valeurs de 1h à 4h du matin (là où elles sont les plus basses)
* Méthode Statmodel
* methode dérivées
* méthodes clustering
* méthode "ruptures"
### Semaines extremes

## Glossaire/Définitions
* **CVC/HVAC :** Chauffage Ventilation Climatisation / Heating Ventilation Air-conditioning
* **CTA :** Centrale de Traitement de l'Air
* **CPCU:** : Chaleur Paris chauffage urbain
* **Courbe de charge :** Puissance appelée par le bâtiment à intervalles réguliers sur une période de temps précise. En abscisse on trouve le temps et en ordonnée la puissance (Wh ou kWh)
* **Talon :** Puisssance minimale reçue (le plus souvent lorsque le bâtiment est innocupé)
<img width="644" height="149" alt="image" src="https://github.com/user-attachments/assets/7530cb92-97d7-4950-b5fa-a180daec3d80" />







