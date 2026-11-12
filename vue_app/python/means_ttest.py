"""Comparison of two independent means from summary statistics.

This follows the MedCalc comparison-of-means dialog: the primary calculation
is the equal-variance pooled two-sample t test, with Welch's unequal-variance
variant available as an explicit alternative.
"""

from __future__ import annotations

from math import isfinite, sqrt
from typing import Any


def _t_sf(value: float, df: float) -> float:
    try:
        from scipy.stats import t

        return float(t.sf(value, df))
    except ImportError as exc:  # pragma: no cover - packaged builds include scipy
        raise RuntimeError("均值 t 检验需要 scipy，请先安装科学计算依赖。") from exc


def _t_ppf(probability: float, df: float) -> float:
    try:
        from scipy.stats import t

        return float(t.ppf(probability, df))
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("均值 t 检验需要 scipy，请先安装科学计算依赖。") from exc


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)


def _sample(name: str, value: Any) -> tuple[float, float, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} 数据无效。")
    try:
        mean = float(value["mean"])
        sd = float(value["sd"])
        n_float = float(value["n"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} 需要填写均值、标准差和例数。") from exc
    if not isfinite(mean) or not isfinite(sd) or not isfinite(n_float):
        raise ValueError(f"{name} 只能填写有限数值。")
    if sd < 0:
        raise ValueError(f"{name} 标准差不能为负数。")
    if n_float < 2 or n_float != round(n_float):
        raise ValueError(f"{name} 例数必须是不小于 2 的整数。")
    return mean, sd, int(n_float)


def _test_result(
    *,
    method: str,
    difference: float,
    standard_error: float,
    df: float,
    pooled_sd: float | None,
    sd1: float,
    sd2: float,
    n1: int,
    n2: int,
) -> dict[str, Any]:
    if standard_error == 0:
        statistic = 0.0 if difference == 0 else (float("inf") if difference > 0 else float("-inf"))
        p = 1.0 if difference == 0 else 0.0
        critical = 0.0
        ci_low, ci_high = difference, difference
    else:
        statistic = difference / standard_error
        p = min(1.0, max(0.0, 2.0 * _t_sf(abs(statistic), df)))
        critical = _t_ppf(0.975, df)
        ci_low, ci_high = difference - critical * standard_error, difference + critical * standard_error
    result = {
        "method": method,
        "difference": _round(difference),
        "pooled_sd": _round(pooled_sd),
        "standard_error": _round(standard_error),
        "ci": {"level": 0.95, "low": _round(ci_low), "high": _round(ci_high)},
        "t": _round(statistic),
        "df": _round(df, 4),
        "p": _round(p),
        "significant_0_05": p < 0.05,
        "critical_t_95": _round(critical),
        "cohens_d": _round(difference / pooled_sd) if pooled_sd and pooled_sd > 0 else None,
        "standard_error_mean_1": _round(sd1 / sqrt(n1)),
        "standard_error_mean_2": _round(sd2 / sqrt(n2)),
    }
    return result


def analyze(
    group1: dict[str, Any],
    group2: dict[str, Any],
    *,
    method: str = "pooled",
    group_labels: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Compare two independent means entered as mean, SD and sample size."""
    mean1, sd1, n1 = _sample("第1组", group1)
    mean2, sd2, n2 = _sample("第2组", group2)
    if method not in ("pooled", "welch"):
        raise ValueError("检验方法必须是 pooled 或 welch。")
    # MedCalc displays the comparison as Sample 2 minus Sample 1.  This is
    # why the screenshot with 12.47 in group 1 and 11.00 in group 2 reports
    # -1.47 and a negative t statistic.
    difference = mean2 - mean1
    pooled_variance = ((n1 - 1) * sd1**2 + (n2 - 1) * sd2**2) / (n1 + n2 - 2)
    pooled_sd = sqrt(pooled_variance)
    if method == "pooled":
        standard_error = pooled_sd * sqrt(1.0 / n1 + 1.0 / n2)
        df = n1 + n2 - 2
    else:
        variance_1, variance_2 = sd1**2 / n1, sd2**2 / n2
        standard_error = sqrt(variance_1 + variance_2)
        denominator = variance_1**2 / (n1 - 1) + variance_2**2 / (n2 - 1)
        df = (variance_1 + variance_2) ** 2 / denominator if denominator else n1 + n2 - 2
    result = _test_result(
        method=method,
        difference=difference,
        standard_error=standard_error,
        df=df,
        pooled_sd=pooled_sd if method == "pooled" else None,
        sd1=sd1,
        sd2=sd2,
        n1=n1,
        n2=n2,
    )
    result.update(
        {
            "group1": {"mean": _round(mean1), "sd": _round(sd1), "n": n1},
            "group2": {"mean": _round(mean2), "sd": _round(sd2), "n": n2},
            "group_labels": list(group_labels or ("第1组", "第2组")),
            "total_n": n1 + n2,
            "assumptions": {
                "independent_samples": True,
                "equal_variances": method == "pooled",
                "normality": "两组总体近似正态，或样本量足够大。",
            },
        }
    )
    return result

