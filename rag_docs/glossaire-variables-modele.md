# Glossaire des variables du modèle de détection de fraude

Ce document définit les 13 variables réellement utilisées par le modèle XGBoost pour évaluer le risque de fraude d'une transaction. Toutes proviennent de la table `bank_transactions_cleaned`.

## Variables numériques

**amount** — Montant de la transaction, dans la devise d'origine (voir `currency`). Variable numérique continue.

**high_risk_merchant** — Indicateur binaire (0 ou 1) signalant si le commerçant est répertorié comme présentant un risque de fraude élevé, selon la classification interne de la base source.

**transaction_hour** — Heure de la journée à laquelle la transaction a eu lieu, entre 0 et 23. Les transactions nocturnes (0h-5h, 22h-23h) sont statistiquement associées à un risque légèrement supérieur.

**weekend_transaction** — Indicateur binaire signalant si la transaction a eu lieu un samedi ou un dimanche.

**velocity_last_hour** — Nombre de transactions effectuées par le même client dans l'heure précédant celle-ci. Signal classique de fraude (une carte compromise est souvent utilisée en rafale).
> **Limite connue** : cette colonne est vide sur 100% des lignes de la table source. Elle est recalculée dynamiquement lors de l'entraînement (fenêtre glissante par client), mais reste à 0 par défaut lors d'une prédiction manuelle isolée dans le simulateur, sauf ajustement volontaire.

**card_present** — Indicateur binaire signalant si la carte physique était présente lors de la transaction (paiement en point de vente avec puce/sans contact) ou non (paiement en ligne, saisie manuelle).

## Variables catégorielles

**merchant_type** — Nature de l'activité du commerçant (`physical`, `online`, `transport`, `medical`, `major`, `airlines`, `casual`, `booking`).

**card_type** — Type de carte bancaire utilisée (`Basic Debit`, `Basic Credit`, `Gold Credit`, `Platinum Credit`, `Premium Debit`).

**device** — Appareil ou terminal utilisé pour la transaction (`Chrome`, `Firefox`, `Safari`, `Edge`, `iOS App`, `Android App`, `Magnetic Stripe`).

**channel** — Canal de la transaction : `web`, `mobile` ou `pos` (point de vente physique).

**country** — Pays où la transaction a été initiée.

**city_size** — Taille de la ville associée à la transaction (`small`, `medium`, `large`).

**currency** — Devise de la transaction (USD, EUR, GBP, AUD, SGD, MXN, NGN, RUB).

## Variable cible

**is_fraud** — Étiquette réelle (0 = légitime, 1 = frauduleuse), utilisée pour entraîner le modèle et comparer ses prédictions à la vérité terrain.

## Décision du modèle

Le modèle produit une **probabilité de fraude** entre 0 et 1. Cette probabilité est comparée à un **seuil de décision optimal**, calculé pendant l'entraînement pour maximiser le F1-score (l'équilibre entre précision et rappel). Au-dessus du seuil, la transaction est classée **FRAUDULEUSE** ; en dessous, **LÉGITIME**.

## Limite méthodologique importante

Une analyse de l'importance des variables a montré que **`channel`** et **`device`** portent à eux seuls plus de 80% du pouvoir prédictif du modèle — une corrélation forte propre au jeu de données synthétique utilisé, plutôt qu'un signal comportemental multivarié généralisable à des données réelles de production.
