"""SPSS CROSSTABS-compatible calculations for frequency tables.

The public entry point is :func:`analyze`.  It accepts a rectangular matrix of
non-negative frequencies and returns JSON-serialisable dictionaries so the
Vue/Tauri bridge can use the same engine in development and in packaged builds.

The implementation follows the standard SPSS CROSSTABS conventions:

* row, column and total percentages are calculated from the observed counts;
* Pearson and likelihood-ratio chi-square tests use asymptotic chi-square
  probabilities;
* Fisher's exact test and Yates' correction are available for 2x2 tables;
* pairwise column-proportion tests use Bonferroni adjustment;
* Cohen's kappa is restricted to square tables;
* McNemar / McNemar-Bowker are available for paired square tables.
"""

from __future__ import annotations

from math import erf, exp, isfinite, lgamma, log, sqrt
from typing import Any, Sequence


def _chi2_sf(value: float, df: int) -> float:
    """Return a chi-square survival probability using SciPy when available."""
    if df <= 0 or not isfinite(value):
        return None  # type: ignore[return-value]
    try:
        from scipy.stats import chi2

        return float(chi2.sf(value, df))
    except ImportError as exc:  # pragma: no cover - packaged builds include scipy
        raise RuntimeError("列联表分析需要 scipy，请先安装科学计算依赖。") from exc


def _normal_two_sided_p(z: float) -> float:
    return float(2.0 * (1.0 - 0.5 * (1.0 + erf(abs(z) / sqrt(2.0)))))


def _as_matrix(table: Sequence[Sequence[Any]]) -> list[list[float]]:
    if not isinstance(table, (list, tuple)) or not table:
        raise ValueError("请输入至少一行列联表频数。")
    rows: list[list[float]] = []
    width = None
    for row in table:
        if not isinstance(row, (list, tuple)) or not row:
            raise ValueError("列联表每一行都必须包含至少一个频数。")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError("列联表各行的列数必须一致。")
        values: list[float] = []
        for value in row:
            if isinstance(value, bool):
                raise ValueError("频数必须是非负数。")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("频数必须是非负数。") from exc
            if not isfinite(number) or number < 0:
                raise ValueError("频数必须是非负数。")
            # SPSS can carry weighted/fractional counts, so do not force int.
            values.append(number)
        rows.append(values)
    if len(rows) < 2 or (width or 0) < 2:
        raise ValueError("列联表至少需要 2 行 × 2 列。")
    if sum(sum(row) for row in rows) <= 0:
        raise ValueError("列联表总频数必须大于 0。")
    if any(sum(row) <= 0 for row in rows) or any(sum(row[c] for row in rows) <= 0 for c in range(width or 0)):
        raise ValueError("不能包含总频数为 0 的空行或空列，请删除后再计算。")
    return rows


def _fmt(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _fisher_2x2(table: list[list[float]]) -> dict[str, float | None]:
    try:
        from scipy.stats import fisher_exact
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Fisher 精确概率需要 scipy，请先安装科学计算依赖。") from exc
    # scipy's exact test requires integral counts.  SPSS frequency data are
    # normally integer counts; give a clear message for fractional input.
    if any(abs(value - round(value)) > 1e-10 for row in table for value in row):
        return {"odds_ratio": None, "p": None, "available": False}
    odds, p = fisher_exact([[int(round(v)) for v in row] for row in table], alternative="two-sided")
    return {"odds_ratio": _fmt(odds), "p": _fmt(p), "available": True}


def _pairwise_columns(table: list[list[float]], col_totals: list[float]) -> list[dict[str, Any]]:
    """SPSS-style pairwise column-proportion tests with Bonferroni adjustment."""
    columns = len(col_totals)
    pairs_per_row = columns * (columns - 1) // 2
    results: list[dict[str, Any]] = []
    for i, row in enumerate(table):
        for left in range(columns):
            for right in range(left + 1, columns):
                n_left, n_right = col_totals[left], col_totals[right]
                if n_left <= 0 or n_right <= 0:
                    results.append({"row": i, "left": left, "right": right, "z": None, "p": None, "p_bonferroni": None, "significant": False})
                    continue
                p_left, p_right = row[left] / n_left, row[right] / n_right
                pooled_n = n_left + n_right
                pooled = (row[left] + row[right]) / pooled_n
                variance = pooled * (1.0 - pooled) * (1.0 / n_left + 1.0 / n_right)
                z = (p_left - p_right) / sqrt(variance) if variance > 0 else 0.0
                p = _normal_two_sided_p(z)
                adjusted = min(1.0, p * pairs_per_row)
                results.append({
                    "row": i,
                    "left": left,
                    "right": right,
                    "left_proportion": _fmt(p_left),
                    "right_proportion": _fmt(p_right),
                    "z": _fmt(z),
                    "p": _fmt(p),
                    "p_bonferroni": _fmt(adjusted),
                    "significant": adjusted < 0.05,
                })
    return results


def _kappa(table: list[list[float]], total: float) -> dict[str, float | None]:
    size = len(table)
    if size != len(table[0]):
        return {"available": False, "kappa": None, "observed_agreement": None, "expected_agreement": None}
    row_totals = [sum(row) for row in table]
    col_totals = [sum(table[r][c] for r in range(size)) for c in range(size)]
    observed = sum(table[i][i] for i in range(size)) / total
    expected = sum(row_totals[i] * col_totals[i] for i in range(size)) / (total * total)
    kappa = (observed - expected) / (1.0 - expected) if expected < 1.0 else None
    return {"available": True, "kappa": _fmt(kappa), "observed_agreement": _fmt(observed), "expected_agreement": _fmt(expected)}


def _paired(table: list[list[float]]) -> dict[str, Any]:
    size = len(table)
    if size != len(table[0]):
        return {"available": False, "test": None}
    if size == 2:
        discordant = table[0][1] + table[1][0]
        statistic = ((abs(table[0][1] - table[1][0]) - 1.0) ** 2 / discordant) if discordant > 0 else 0.0
        return {
            "available": True,
            "test": "McNemar",
            "statistic": _fmt(statistic),
            "df": 1,
            "p": _fmt(_chi2_sf(statistic, 1)),
            "discordant": _fmt(discordant),
            "continuity_corrected": True,
        }
    statistic = 0.0
    terms = 0
    for i in range(size):
        for j in range(i + 1, size):
            denominator = table[i][j] + table[j][i]
            if denominator > 0:
                statistic += (table[i][j] - table[j][i]) ** 2 / denominator
            terms += 1
    return {
        "available": True,
        "test": "McNemar-Bowker",
        "statistic": _fmt(statistic),
        "df": terms,
        "p": _fmt(_chi2_sf(statistic, terms)),
        "continuity_corrected": False,
    }


def analyze(
    table: Sequence[Sequence[Any]],
    *,
    row_labels: Sequence[str] | None = None,
    column_labels: Sequence[str] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze a frequency table using SPSS CROSSTABS conventions."""
    matrix = _as_matrix(table)
    options = dict(options or {})
    rows, columns = len(matrix), len(matrix[0])
    total = sum(sum(row) for row in matrix)
    row_totals = [sum(row) for row in matrix]
    col_totals = [sum(matrix[r][c] for r in range(rows)) for c in range(columns)]
    expected = [[row_totals[i] * col_totals[j] / total for j in range(columns)] for i in range(rows)]
    row_percent = [[value / row_totals[i] * 100 if row_totals[i] else None for value in matrix[i]] for i in range(rows)]
    column_percent = [[matrix[i][j] / col_totals[j] * 100 if col_totals[j] else None for j in range(columns)] for i in range(rows)]
    total_percent = [[value / total * 100 for value in row] for row in matrix]
    min_expected = min(value for row in expected for value in row)
    small_expected = sum(value < 5.0 for row in expected for value in row)

    pearson = sum((matrix[i][j] - expected[i][j]) ** 2 / expected[i][j] for i in range(rows) for j in range(columns) if expected[i][j] > 0)
    df = (rows - 1) * (columns - 1)
    likelihood = sum(2.0 * matrix[i][j] * log(matrix[i][j] / expected[i][j]) for i in range(rows) for j in range(columns) if matrix[i][j] > 0 and expected[i][j] > 0)
    yates = None
    if rows == columns == 2:
        yates = sum((abs(matrix[i][j] - expected[i][j]) - 0.5) ** 2 / expected[i][j] for i in range(2) for j in range(2) if expected[i][j] > 0)

    result: dict[str, Any] = {
        "table": matrix,
        "row_labels": list(row_labels or [f"行{i + 1}" for i in range(rows)]),
        "column_labels": list(column_labels or [f"列{i + 1}" for i in range(columns)]),
        "rows": rows,
        "columns": columns,
        "total": _fmt(total),
        "row_totals": [_fmt(v) for v in row_totals],
        "column_totals": [_fmt(v) for v in col_totals],
        "expected": [[_fmt(v) for v in row] for row in expected],
        "row_percent": [[_fmt(v, 2) for v in row] for row in row_percent],
        "column_percent": [[_fmt(v, 2) for v in row] for row in column_percent],
        "total_percent": [[_fmt(v, 2) for v in row] for row in total_percent],
        "assumption": {"min_expected": _fmt(min_expected), "small_expected_count": small_expected, "small_expected_percent": _fmt(small_expected / (rows * columns) * 100, 2)},
        "pearson": {"statistic": _fmt(pearson), "df": df, "p": _fmt(_chi2_sf(pearson, df))},
        "likelihood_ratio": {"statistic": _fmt(likelihood), "df": df, "p": _fmt(_chi2_sf(likelihood, df))},
        "yates": {"available": yates is not None, "statistic": _fmt(yates), "df": 1 if yates is not None else None, "p": _fmt(_chi2_sf(yates, 1)) if yates is not None else None},
        "fisher": {"available": False, "reason": "Fisher 精确检验按 SPSS CROSSTABS 标准仅对 2×2 表计算。"},
        "pairwise": [],
        "kappa": {"available": False, "kappa": None, "observed_agreement": None, "expected_agreement": None},
        "paired": {"available": False, "test": None},
    }
    if rows == columns == 2 and options.get("fisher", True):
        result["fisher"] = _fisher_2x2(matrix)
    if options.get("pairwise", False):
        result["pairwise"] = _pairwise_columns(matrix, col_totals)
    if options.get("kappa", False):
        result["kappa"] = _kappa(matrix, total)
    if options.get("paired", False):
        result["paired"] = _paired(matrix)
    return result

