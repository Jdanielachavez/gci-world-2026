# Final Assignment — Turning Customer Data into Retained Revenue
### A Data-Driven Churn-Reduction Proposal for Company A (Telecom)
**GCI World 2026 April · University of Tokyo (Matsuo-Iwasawa Lab)**
Author: **Josseline Daniela Chávez Carpio**

---

## Objective
Build an end-to-end, business-oriented data-science case for an anonymized telecom operator
("Company A"): use customer and usage data to **predict churn** and turn that model into a
**concrete, quantified retention strategy** — not just a prediction, but a revenue decision.

## What I did
- **Market & industry analysis** — framed the problem with telecom churn benchmarks
  (20–30% annual churn) and the economics of retention vs. acquisition.
- **Exploratory data analysis** on the Client and Record datasets to surface churn drivers.
- **Feature engineering & preprocessing** — cleaned identifiers, imputed missing values,
  encoded categoricals, and engineered tenure / usage features.
- **Model comparison** — benchmarked **Logistic Regression**, **Decision Tree**, and
  **Gradient Boosting**; selected Gradient Boosting on ROC-AUC.
- **Business translation** — instead of a yes/no flag, I **ranked** customers by churn risk,
  targeted the **top 20%** for retention, and quantified the financial impact.
- **Executive report** — distilled everything into a 14-slide decision deck.

## Result
| Metric | Value |
|---|---|
| Best model | Gradient Boosting |
| ROC-AUC | 0.69 |
| Top-20% targeting precision | 73% |
| Lift vs. random | 1.47× |
| **Projected net benefit** | **$6.06M** (+$1.97M vs. random targeting) |

## Key files
| File | Description |
|---|---|
| `JosselineDanielaChavezCarpio.ipynb` | Full analysis notebook: market → EDA → models → business impact |
| `JosselineDanielaChavezCarpio.pdf` | 14-slide executive report |
| `references.txt` | Sources cited |

> Datasets (`Client.csv`, `Record.csv`) are course-provided and excluded from the repository (>25 MB).
