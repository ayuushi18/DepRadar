DepRadar

This project forecasts which popular Python packages will go quiet in the next 12 months, built
as a lakehouse pipeline on Databricks (Spark, Delta Lake, Unity Catalog, Jobs, MLflow).

Most software depends on open-source packages run by one or two volunteers. When
maintainers stop, dependents get no fixes and no support. Existing tools mostly score a
package today; DepRadar asks which ones are likely to go silent soon, and measures how
well that works with a time-based backtest.

"Silent" means no release and no human commit for 12 months. It is not the same as dead:
a hand check of 30 sampled labels found 37% (95% range 22 to 54%) were dead today and
60% were stable or active.

## Data

| Source | Used for | Size |
|---|---|---|
| GH Archive via BigQuery | monthly GitHub activity, Nov 2021 to Apr 2025 | 2.16M aggregated rows |
| PyPI simple API | release history | 228,131 releases |
| GitHub API | recent activity for the live-scoring features | 200,425 commits, 2,128 repos |

2,713 of the top 3,000 PyPI packages map to a GitHub repo. After excluding forks and
unavailable repos, 2,667 packages (2,128 unique repos) are analysed. Packages hosted
elsewhere are out of scope.

**Source problem found:** per-event-type checks showed GH Archive capture degraded from
about June 2025 (stars, PRs and comments collapse while pushes continue). The backtest
therefore uses only pre-June-2025 data, and the live features use the GitHub API.

## Pipeline

```
BigQuery / PyPI / GitHub API
        -> Volume (files)
        -> bronze  (Auto Loader into Delta, nothing altered)
        -> silver  (typed, deduplicated, usernames hashed, 16 quality checks)
        -> gold    (star schema, labels, features)
        -> MLflow  (backtest runs, registered model)
        -> risk scores and tiers
```

Two Databricks Jobs: `depradar_pipeline` (bronze, silver, gold, features, with quality
gates that stop the run on failure) and `depradar_training` (backtest, evaluation, final
model, scoring; manual).

Engineering checks:
- Spark-computed labels reconcile exactly with an independent pandas implementation:
  50,673 rows, 0 differences.
- Silver checks caught 74 duplicate keys (usernames differing only by case); fixed and
  verified that total event counts still equal bronze.
- Leakage test: scrambling every month from the snapshot onward changes no feature.

## Method

- Snapshot dates: monthly, Nov 2022 to May 2024. A package is "alive" if it had a release
  or human push in the prior 12 months.
- Features use only months before the snapshot. The deployable set has 11 portable
  features (activity months, months since last activity and release, release counts and
  trends, package age) that can also be computed from the GitHub API.
- Walk-forward backtest, test months Nov 2023 to May 2024: each month trains only on
  snapshots whose outcome was already known (at least 12 months earlier).
- Uncertainty comes from resampling whole packages, because the same packages recur
  across months.

## Results

Base rate: 6.4% of alive packages went silent.

| Model | Precision@100 | PR-AUC | ROC-AUC |
|---|---|---|---|
| Rule: fewest active months | 0.344 | 0.286 | 0.884 |
| Rule: longest since last release | 0.307 | 0.217 | 0.774 |
| Logistic regression (portable features) | 0.370 | 0.306 | 0.892 |
| Gradient boosting (portable features) | 0.369 | 0.344 | 0.886 |
| Gradient boosting (portable + research features) | 0.359 | 0.346 | 0.889 |

- Boosting beats the simple activity rule on PR-AUC by +0.058 (95% range +0.016 to
  +0.099). On precision at 100 the difference is not clear.
- The extra research features add nothing (+0.002, range -0.029 to +0.031).
- Most of the signal is persistence: 85% of packages that went silent were already
  active in 3 or fewer of the previous 12 months.

Risk tiers, measured out of sample (percentile within each month):

| Tier | Went silent | 95% range | Share of all silent packages |
|---|---|---|---|
| Top 5% | 37.0% | 30 to 44% | 28.6% |
| Next 5% | 24.4% | 19 to 30% | 19.0% |
| Next 10% | 17.4% | 14 to 21% | 27.0% |
| Rest | 2.1% | 2 to 3% | 25.5% |

Predicted probabilities are mis-calibrated at the extremes (low-risk bands under-predict,
the top band over-predicts), so tiers are reported instead of probabilities.

Feature robustness: an API-versus-archive check on 300 repos (1,743 repo-months) found
92.8% agreement on "active this month" (kappa 0.86). Adding that level of noise to the
backtest lowered PR-AUC from 0.342 to 0.320 (0.294 at twice the noise).

Scoring as of October 2026 (2,667 packages): 410 already silent, 226 High, 226 Elevated,
1,805 Lower. Of 60 packages archived by their owners, 42 are already silent.

## Limitations

- Silent is not dead; the label includes finished, stable libraries.
- 60 of the top 100 flagged packages in one test month did not go silent; occasional
  maintenance releases reset the label.
- The model cannot see announced deprecations or replacements.
- The same packages recur across test months, so the monthly results are not independent.
- The live features count default-branch commits; the training data counts pushes.
- Packages on GitLab or other hosts, and the 6% repos that moved or split, are not covered.

## Layout

```
src/         extraction and local analysis scripts
databricks/  notebooks 01 to 09 (bronze through export)
app/         core logic and tests for the dependency checker
docs/        screenshots
```

Raw data is not included: it contains real GitHub usernames (hashed in the lakehouse).

## Status

Pipeline, backtest, model registry and scoring are complete. The dependency-checker
interface is in progress.
