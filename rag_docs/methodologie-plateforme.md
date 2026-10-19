# Méthodologie et architecture — Plateforme Vigie de détection de fraude

## Vue d'ensemble

Vigie est une plateforme d'aide à la décision pour l'analyse de fraude bancaire. Elle combine un pipeline de traitement de données, un modèle de machine learning entraîné, et une interface d'exploration, de simulation et de surveillance.

## Pipeline de données (Apache Airflow)

Un DAG (`pipeline_microservices_fraude`) orchestre quatre étapes séquentielles, chacune exécutée par un microservice indépendant (FastAPI, conteneurisé) :

1. **Extraction** — récupération du jeu de données brut (source Kaggle) et sauvegarde sur un volume partagé.
2. **Transformation** — nettoyage, déduplication, anonymisation des données sensibles (hachage salé des numéros de carte, floutage des coordonnées GPS).
3. **Chargement** — import des données nettoyées dans PostgreSQL, table `bank_transactions_cleaned`.
4. **Entraînement** — entraînement du modèle et enregistrement dans MLflow.

## Modèle de machine learning

- **Algorithme** : XGBoost (gradient boosting sur arbres de décision), adapté à la classification binaire sur données tabulaires déséquilibrées.
- **Déséquilibre des classes** : traité par sur-échantillonnage SMOTE, appliqué uniquement sur les données d'entraînement et imbriqué correctement dans la validation croisée (pour éviter toute fuite de données entre les plis).
- **Recherche d'hyperparamètres** : `RandomizedSearchCV` avec validation croisée à 3 plis, optimisée sur le F1-score de la classe frauduleuse.
- **Seuil de décision** : ajusté après entraînement pour maximiser le F1-score sur un jeu de test indépendant, plutôt que de conserver le seuil par défaut de 0,5.
- **Suivi d'expériences** : chaque entraînement est journalisé dans MLflow (hyperparamètres, métriques, artefacts — matrice de confusion, courbe ROC).

## Métriques de performance (dernier entraînement)

| Métrique | Valeur |
|---|---|
| F1-score | ≈ 0,92 |
| Précision | ≈ 0,95 |
| Rappel | ≈ 0,89 |
| Exactitude | ≈ 0,97 |

## Composants applicatifs

- **Explorateur de transactions** — requêtes en langage naturel traduites en SQL sur la base historique.
- **Simulateur de score de risque** — évaluation manuelle d'une transaction (saisie libre ou chargement d'une transaction réelle), avec comparaison à l'étiquette réelle en base.
- **Surveillance en direct (simulée)** — rejeu automatique de transactions historiques au hasard, scorage automatique par le modèle, création automatique d'alertes pour toute transaction jugée frauduleuse.
- **Indicateurs** — tableau de bord agrégé (volume de transactions, taux de fraude, montant total à risque, répartition par canal et par marchand).
- **Assistant documentaire (RAG)** — répond aux questions en s'appuyant sur les documents indexés et les données transactionnelles.

## Limites connues et axes de prudence

1. **Surveillance "en direct" simulée** — aucune connexion à un système bancaire réel n'existe. Le module rejoue des transactions historiques comme si elles venaient d'être soumises, à des fins de démonstration du principe de détection et de blocage automatique.
2. **Dépendance forte à `channel`/`device`** — la performance élevée du modèle s'explique en grande partie par une corrélation marquée entre le canal de paiement et le type d'appareil dans le jeu de données synthétique, plutôt que par un signal comportemental multivarié généralisable.
3. **`velocity_last_hour`** — absente à la source, recalculée uniquement au moment de l'entraînement ; non disponible en temps réel pour une transaction isolée hors contexte historique complet du client.
4. **Comptes d'authentification de démonstration** — les identifiants actuels sont codés en dur avec des mots de passe en clair, à des fins de démonstration uniquement ; une mise en production réelle nécessiterait une gestion des utilisateurs avec mots de passe hachés en base.
