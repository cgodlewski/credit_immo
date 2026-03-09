# Tableau de bord immobilier et credit en France

L'app combine:
- les prix des logements anciens via l'API INSEE
- les taux et flux de credits via un export Webstat Banque de France

## Mise a jour mensuelle BdF

Le plus simple pour GitHub et Streamlit Cloud:
1. depuis Webstat, exporte les 3 series en une seule fois
2. choisis `CSV` et `format long`
3. remplace le fichier `data/webstat_export_3_series.csv`
4. pousse le changement sur GitHub

L'app lit ce fichier par defaut.
Elle accepte aussi un upload manuel temporaire dans la sidebar.

## Series attendues dans l'export

- Taux: `MIR1.M.FR.B.A22.A.R.A.2254U6.EUR.N`
- Production credit tous flux: `MIR1.M.FR.B.A22.A.5.A.2254U6.EUR.N`
- Production credit hors renegociations: `MIR1.M.FR.B.A22HR.A.5.A.2254U6.EUR.N`

## Lancement local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```
