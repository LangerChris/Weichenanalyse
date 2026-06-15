"""Weichenanalyse — Zustandsüberwachung von Eisenbahn-Weichen über den Motorstrom.

Wiederverwendbare Pipeline-Module für Laden, Vorverarbeitung, Feature-Extraktion,
Modellierung und Evaluation. Siehe docs/MODELLING_PLAN.md.
"""

from weichenanalyse.data import Turn, load_dataset

__all__ = ["Turn", "load_dataset"]
