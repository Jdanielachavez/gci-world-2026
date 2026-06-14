# Competition — NFL Draft Prediction
**GCI World 2026 April · University of Tokyo (Matsuo-Iwasawa Lab)**
Author: **Josseline Daniela Chávez Carpio**

---

## Objective
A leaderboard-style machine-learning competition. Given physical measurements and combine
performance metrics for college football players, the task is to predict the **probability that
each player is drafted** into the NFL. Submissions are ranked by **ROC-AUC** on a hidden test set.

## What I did
- **Exploratory data analysis** to understand which attributes separate drafted from undrafted players.
- **Feature engineering** — built domain-informed features: BMI, power-to-weight ratio, an
  explosiveness index, and speed–agility combinations.
- **Leakage-safe encoding** — replaced naive target encoding with **out-of-fold target encoding**
  inside a stratified cross-validation loop, removing the data leakage that had inflated early scores.
- **Model ensemble** — combined **LightGBM + XGBoost + CatBoost + Random Forest**, averaging
  calibrated probabilities.
- **Validation** — stratified k-fold cross-validation, tracking ROC-AUC at every step.

## Result
| | ROC-AUC |
|---|---|
| Course baseline | ≈ 0.78 |
| **My ensemble (CV)** | **≈ 0.85** |

## Key files
| File | Description |
|---|---|
| `my_solution.ipynb` | Full competition notebook: EDA → features → ensemble → submission |
| `improve_model.py` / `improve_model_v3.py` | Standalone training scripts with the leakage-safe CV ensemble |
| `submission.csv` (+ `_v2`, `_v3`) | Scored prediction files |
| `danielachavez1.ipynb` / `.pdf` | My written report |

> Datasets (`train.csv`, `test.csv`) are course-provided and excluded from the repository.
