# Supervisor report — deterministic/offline

Pipeline completed; Astra role reviews were not called.

| Model | Log loss | Brier | Accuracy | Matches |
|---|---:|---:|---:|---:|
| elo_k20_d0.24 | 1.0027 | 0.5999 | 52.9% | 380 |
| elo_k20_d0.3 | 1.0043 | 0.6013 | 52.9% | 380 |
| elo_k40_d0.24 | 0.9945 | 0.5949 | 53.2% | 380 |
| elo_k40_d0.3 | 0.9933 | 0.5937 | 53.2% | 380 |
| attack_defense_decay0.9_C0.1 | 1.0263 | 0.6147 | 49.2% | 380 |
| attack_defense_decay0.9_C1.0 | 1.0311 | 0.6176 | 49.2% | 380 |
| attack_defense_decay0.97_C0.1 | 1.0400 | 0.6244 | 48.2% | 380 |
| attack_defense_decay0.97_C1.0 | 1.0466 | 0.6285 | 48.2% | 380 |
| historical_frequencies | 1.0834 | 0.6572 | 40.8% | 380 |

Validation-selected candidate: elo_k40_d0.3.

Lower log loss and Brier are better. Selection is conditional on this validation season; the test season has not been evaluated.

See experiment_summary.json for measured validation performance, data_audit.json for coverage, validation_tests.txt for checks, and change_log.json for executed changes.

2025–26 remains unexamined. Model selection is provisional, not evidence of trading profitability.
