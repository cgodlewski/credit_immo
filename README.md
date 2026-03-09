# 🏠 Tableau de bord immobilier français

Appli **Streamlit** visualisant en temps réel les données du marché immobilier français à partir des APIs publiques INSEE et Banque de France.

## Ce que ça fait

Trois vues interactives, toutes avec zoom, hover et sélection de période :

| Vue | Contenu |
|-----|---------|
| 📈 Prix & taux | Indice Notaires-INSEE des prix des logements anciens (base 2015) croisé avec les taux de crédit habitat BdF |
| 💶 Crédit & taux | Production mensuelle de crédits à l'habitat (Mds €) en barres + taux en courbe |
| 📊 Prix — détail | Indice de niveau + glissements annuel et trimestriel (INSEE) |

**Choix du taux :** hors renégociations / y compris renégociations / les deux.  
**Mise à jour :** automatique à chaque chargement (cache 24 h). Aucun fichier à télécharger.

---

## Sources de données

### INSEE — API BDM (gratuite, sans clé)
- Indice Notaires-INSEE des prix des logements anciens  
  `idbank : 010567059` — France entière, CVS, base 2015=100  
- Glissement annuel : `010567060`  
- Glissement trimestriel : `010567061`  
- Endpoint : `https://api.insee.fr/series/BDM/V1/data/SERIES_BDM/{idbanks}`

### Banque de France — API Webstat (gratuite, clé requise)
- Taux crédits habitat hors renégo : `MIR1.M.FR.B.A22.A.R.A.2254U6.EUR.N`  
- Taux y compris renégo : `MIR1.M.FR.B.A22.A.R.A.2254U6.EUR.Y`  
- Production mensuelle crédits : `MIR1.M.FR.B.A22.A.S.A.2254U6.EUR.N`  
- Endpoint : `https://api.webstat.banque-france.fr/webstat-fr/v1/data/{dataset}/{key}`

---

## Installation locale

```bash
# Cloner le dépôt
git clone https://github.com/<ton-pseudo>/immo-dashboard.git
cd immo-dashboard

# Environnement virtuel (recommandé)
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate

# Dépendances
pip install -r requirements.txt

# Lancer
streamlit run app.py
```

### Clé API Banque de France

1. Créer un compte gratuit sur [developer.webstat.banque-france.fr](https://developer.webstat.banque-france.fr)
2. S'abonner au produit **WEBSTAT Banque de France FR V1**
3. Copier la clé Bearer générée

Deux façons de l'utiliser :
- **Directement dans l'appli** : champ « Clé API Banque de France » dans la barre latérale
- **Variable d'environnement** (recommandé en production) :
  ```bash
  export BDF_API_KEY="votre_cle_ici"
  streamlit run app.py
  ```

---

## Déploiement sur Streamlit Cloud

1. Pousser ce dépôt sur GitHub (public ou privé)
2. Aller sur [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Sélectionner le dépôt, branche `main`, fichier `app.py`
4. Dans **Advanced settings → Secrets**, ajouter :
   ```toml
   BDF_API_KEY = "votre_cle_ici"
   ```
5. Cliquer **Deploy**

L'appli sera disponible à `https://<nom>.streamlit.app`.

> **Note :** si tu préfères ne pas exposer la clé BdF, tu peux laisser les utilisateurs la saisir eux-mêmes dans la sidebar — c'est ce que fait l'appli par défaut quand `BDF_API_KEY` n'est pas définie.

---

## Structure du projet

```
immo-dashboard/
├── app.py              # Application Streamlit principale
├── requirements.txt    # Dépendances Python
└── README.md
```

---

## Notes techniques

- Les données INSEE (trimestrielles) sont agrégées en moyenne trimestrielle pour être alignées avec les données BdF (mensuelles → Q).
- Le cache Streamlit (`@st.cache_data(ttl=86400)`) évite de rappeler les APIs à chaque interaction utilisateur.
- Les identifiants de séries BdF à vérifier : si la série taux y.c. renégo `EUR.Y` n'existe pas pour ce code MIR1, remplacer par `EUR.T` dans `app.py` (ligne `BDF_SERIES_YC`).

---

## Ajouter d'autres séries

Pour ajouter une zone géographique (Île-de-France, Province…) ou un type de bien (appartements, maisons) :
1. Récupérer l'`idbank` sur [insee.fr](https://www.insee.fr/fr/statistiques/serie/010567059)
2. Ajouter la constante dans `app.py` sous `# IDENTIFIANTS SÉRIES`
3. Passer l'idbank à `fetch_insee_series()`

---

*Sources : INSEE–Notaires · Banque de France · Mise à jour mensuelle automatique*
