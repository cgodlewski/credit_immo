# Tableau de bord immobilier et credit en France

L'app combine:
- les prix des logements anciens via l'API INSEE
- les taux et flux de credits via un export Webstat Banque de France

## Mise a jour mensuelle BdF

1. depuis Webstat, exporter les 3 series en une seule fois (https://webstat.banque-france.fr/fr/selection/5384670/)
- Taux: `MIR1.M.FR.B.A22.A.R.A.2254U6.EUR.N`
- Production credit tous flux: `MIR1.M.FR.B.A22.A.5.A.2254U6.EUR.N`
- Production credit hors renegociations: `MIR1.M.FR.B.A22HR.A.5.A.2254U6.EUR.N`
3. `CSV` et `format long`
4. remplacer le fichier `data/webstat_export_3_series.csv`
5. pousser sur GitHub
L'app lit ce fichier par defaut.
Elle accepte aussi un upload manuel temporaire dans la sidebar.
