"""Regime engine (TDS §11, E5.3). 60-day: manual analyst tag (the human action).
90-day: rule engine proposes, a principal confirms. No regime is ever asserted
without a human; transitions preserve the prior row via superseded_by.
"""
