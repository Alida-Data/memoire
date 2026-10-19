# Procédure de traitement d'une alerte de fraude

Ce document décrit la marche à suivre pour un analyste lorsqu'une alerte apparaît dans l'onglet "Alertes" de la plateforme.

## 1. Réception de l'alerte

Une alerte est créée automatiquement lorsque la surveillance en direct détecte une transaction dont la probabilité de fraude, calculée par le modèle, dépasse le seuil de décision. Elle apparaît avec :
- l'identifiant de la transaction,
- le montant,
- le score de risque (probabilité de fraude),
- une comparaison à l'étiquette réelle en base (si disponible),
- l'horodatage de détection.

## 2. Vérification initiale

1. Noter le score de risque : un score proche de 100% indique une confiance très élevée du modèle ; un score proche du seuil de décision mérite un examen plus attentif.
2. Consulter la mention "vérité terrain" si présente — elle indique si cette transaction est historiquement confirmée frauduleuse ou légitime, utile en contexte de test/validation.
3. Si besoin d'approfondir, utiliser l'explorateur de transactions (langage naturel) pour retrouver le contexte complet de cette transaction ou du client associé.

## 3. Décision

- **Confirmation de fraude** : documenter le cas, escalader selon la procédure interne de l'établissement (hors périmètre de cette plateforme, qui reste un outil d'aide à la décision).
- **Faux positif suspecté** : noter les caractéristiques ayant déclenché l'alerte à tort (utile pour l'amélioration continue du modèle).

## 4. Clôture

Une fois l'alerte traitée (confirmée ou écartée), cliquer sur **"Marquer comme traité"** pour la faire sortir de la liste active. Cette action met à jour le statut en base (`Traitée`) sans supprimer l'historique.

## Rappel important

Cette plateforme est un **outil d'aide à la décision** : elle ne bloque aucune transaction réelle et ne remplace pas le jugement de l'analyste ni les procédures réglementaires en vigueur (LAB/FT, obligations de déclaration de soupçon, etc.). Toute décision finale relève de l'équipe sécurité/conformité.
