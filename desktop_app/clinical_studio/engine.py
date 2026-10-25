"""无界面分析核心。默认参数与原 Notebook 数值一致。"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import importlib.metadata
import json
import platform
import shutil
import sys
import uuid
import warnings

from .config import validate, save_config


@dataclass
class AnalysisResult:
    config: dict
    folder: Path
    data: object
    features: list
    model: object = None
    train: object = None
    test: object = None
    y_test: object = None
    predictions: object = None
    coefficients: object = None
    metrics: dict = None
    images: list = None
    audit: dict = None
    messages: list = None


def generate_dataset(config):
    import numpy as np
    import pandas as pd
    data = config["data"]
    n = data["n_samples"]
    rng = np.random.RandomState(data["random_seed"])
    count = int(n * data["positive_rate"])
    labels = np.array([1]*count + [0]*(n-count))
    rng.shuffle(labels)
    values = {}
    for feature in data["features"]:
        if feature["kind"] == "continuous":
            groups = []
            for group in ("positive", "negative"):
                params = feature[group]
                groups.append(rng.normal(params["mean"], params["std"], n).clip(params["min"], params["max"]))
            array = np.where(labels == 1, groups[0], groups[1])
            if feature["transform"] == "int":
                array = array.astype(int)  # 与原代码一致：向零截断，不是四舍五入。
            elif feature["transform"] == "round":
                array = array.round(feature["digits"])
        else:
            p, q = feature["positive_p"], feature["negative_p"]
            array = np.where(labels == 1, rng.choice(feature["values"], n, p=[1-p, p]),
                             rng.choice(feature["values"], n, p=[1-q, q]))
        values[feature["name"]] = array
    df = pd.DataFrame(values)
    df[data["label_name"]] = labels
    df.insert(0, data["id_name"], [data["id_prefix"] + str(i+data["id_start"]).zfill(data["id_width"]) for i in range(n)])
    return df, [f["name"] for f in data["features"]]


def _new_folder(root):
    folder = Path(root).expanduser() / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6])
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def _save_data(result):
    result.data.to_csv(result.folder / "data.csv", index=False, encoding="utf-8-sig")
    result.data.to_excel(result.folder / "clinical_prediction_dataset_with_protective.xlsx", index=False)
    save_config(result.config, result.folder / "parameters.json")


def _fit(result):
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report, roc_auc_score, confusion_matrix
    cfg, df, features = result.config, result.data, result.features
    settings, data = cfg["model"], cfg["data"]
    train, test, yt, ytest = train_test_split(df[features], df[data["label_name"]],
        test_size=settings["test_size"], random_state=settings["split_seed"],
        stratify=df[data["label_name"]] if settings["stratify"] else None)
    if yt.nunique() != 2 or ytest.nunique() != 2:
        raise ValueError("训练集和测试集必须各含两种结局，请增加样本量或调整比例。")
    if not 0 <= cfg["plots"]["sample_index"] < len(test):
        raise ValueError(f"局部解释样本索引超出范围，测试集共有 {len(test)} 个样本。")
    params = {k: settings[k] for k in ("max_iter", "solver", "C", "tol", "fit_intercept", "random_state")}
    params["class_weight"] = None if settings["class_weight"] == "none" else "balanced"
    # 新版 sklearn 用 l1_ratio/C 配置正则化；旧版保留 penalty 接口。
    prototype = LogisticRegression().get_params()
    if prototype.get("penalty") == "deprecated":
        params["l1_ratio"] = {"l2": 0., "l1": 1., "none": 0.}.get(settings["penalty"], settings["l1_ratio"])
        if settings["penalty"] == "none":
            params["C"] = float("inf")
    else:
        params["penalty"] = None if settings["penalty"] == "none" else settings["penalty"]
        if settings["penalty"] == "elasticnet":
            params["l1_ratio"] = settings["l1_ratio"]
    model = LogisticRegression(**params).fit(train, yt)
    probability = model.predict_proba(test)[:, 1]
    predicted = (probability > settings["threshold"]).astype(int)
    metrics = dict(accuracy=float(accuracy_score(ytest, predicted)), auc=float(roc_auc_score(ytest, probability)),
        confusion_matrix=confusion_matrix(ytest, predicted, labels=[0, 1]).tolist(),
        classification_report=classification_report(ytest, predicted, labels=[0, 1],
            target_names=[data["negative_name"], data["positive_name"]], zero_division=0, output_dict=True),
        n_train=len(train), n_test=len(test), n_positive=int(df[data["label_name"]].sum()),
        intercept=float(model.intercept_[0]), iterations=int(model.n_iter_[0]))
    coefficients = pd.DataFrame({"特征": features, "系数": model.coef_[0], "OR": np.exp(model.coef_[0]),
        "系数绝对值": np.abs(model.coef_[0]), "作用方向": ["正向" if v > 0 else "负向" if v < 0 else "零" for v in model.coef_[0]]})
    coefficients = coefficients.sort_values("系数绝对值", ascending=False)
    predictions = df.loc[test.index].copy()
    predictions["预测结局"] = predicted
    predictions["阳性预测概率"] = probability
    result.model, result.train, result.test, result.y_test = model, train, test, ytest
    result.predictions, result.coefficients, result.metrics = predictions, coefficients, metrics


def _draw(result, progress):
    import numpy as np
    import pandas as pd
    from . import plotting
    cfg = deepcopy(result.config["plots"])
    cfg["output_dir"] = str(result.folder / "figures")
    cfg["show"] = False
    # PNG 始终作为 App 预览；用户所选格式作为额外导出保留。
    cfg["formats"] = list(dict.fromkeys(["png"]+cfg["formats"]))
    explanation = result.config["explanation"]
    protective = explanation["protective_feature"]
    if protective not in result.features:
        protective_indices = np.flatnonzero(result.model.coef_[0] < 0)
        protective = result.features[protective_indices[0]] if len(protective_indices) else result.features[0]
    result.images = plotting.perform_shap_analysis(result.model, result.train, result.test, result.features,
        protective, plot_config=cfg, progress=progress,
        background_max_samples=explanation["background_max_samples"], background_seed=explanation["background_seed"])
    result.audit = deepcopy(plotting.COLOR_AUDIT_RESULTS)
    explainer = plotting.shap.LinearExplainer(result.model, plotting.shap.maskers.Independent(
        plotting.shap.utils.sample(result.train, min(explanation["background_max_samples"], len(result.train)),
                                  random_state=explanation["background_seed"]),
        max_samples=explanation["background_max_samples"]))
    values = np.asarray(explainer.shap_values(result.test))
    shap_df = pd.DataFrame(values, columns=result.features, index=result.test.index)
    shap_df.index.name = "原数据行号"
    shap_df.to_csv(result.folder / "shap_values.csv", encoding="utf-8-sig")
    importance = pd.DataFrame({"特征": result.features, "平均绝对SHAP值": np.abs(values).mean(axis=0)})
    importance.sort_values("平均绝对SHAP值", ascending=False).to_csv(result.folder / "feature_importance.csv", index=False, encoding="utf-8-sig")
    sample = cfg["sample_index"]
    result.metrics["sample_prediction"] = {"test_index": sample, "dataset_row": int(result.test.index[sample]),
        "true_label": int(result.y_test.iloc[sample]),
        "positive_probability": float(result.model.predict_proba(result.test.iloc[[sample]])[0,1]),
        "predicted_label": int(result.model.predict_proba(result.test.iloc[[sample]])[0,1] > result.config["model"]["threshold"]),
        "feature_values": {name: float(value) for name,value in result.test.iloc[sample].items()},
        "shap_base_log_odds": float(np.asarray(explainer.expected_value).item()),
        "shap_sum": float(values[sample].sum())}


def _save_results(result):
    import pandas as pd
    import numpy as np
    (result.folder / "metrics.json").write_text(json.dumps(result.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (result.folder / "color_verification.json").write_text(json.dumps(result.audit, ensure_ascii=False, indent=2), encoding="utf-8")
    result.coefficients.to_csv(result.folder / "coefficients.csv", index=False, encoding="utf-8-sig")
    result.predictions.to_csv(result.folder / "test_predictions.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(result.folder / "analysis_results.xlsx", engine="openpyxl") as writer:
        result.data.to_excel(writer, sheet_name="模拟数据", index=False)
        result.coefficients.to_excel(writer, sheet_name="模型系数", index=False)
        result.predictions.to_excel(writer, sheet_name="测试集预测", index=False)
        pd.DataFrame(result.metrics["classification_report"]).T.to_excel(writer, sheet_name="分类报告")
        pd.DataFrame(result.metrics["confusion_matrix"], index=["真实阴性", "真实阳性"], columns=["预测阴性", "预测阳性"]).to_excel(writer, sheet_name="混淆矩阵")
    versions = {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "scikit-learn", "shap", "matplotlib", "Pillow", "openpyxl"]}
    versions["python"] = platform.python_version()
    versions["runtime_mode"] = "bundled" if getattr(sys,"frozen",False) else "source"
    versions["executable"] = sys.executable
    (result.folder / "versions.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
    audit_pass = all(item["passed"] for item in result.audit.values())
    lines = ["SHAP 分析工作台 · 运行报告", "", "数据类型：按用户设定的分布生成的模拟数据。",
        f"样本数：{len(result.data)}；训练集：{len(result.train)}；测试集：{len(result.test)}",
        f"准确率：{result.metrics['accuracy']:.6f}", f"ROC-AUC：{result.metrics['auc']:.6f}",
        f"截距：{result.metrics['intercept']:.6f}", "", "模型系数：", result.coefficients.to_string(index=False),
        "", "分类报告：", pd.DataFrame(result.metrics["classification_report"]).T.to_string(),
        "", "局部样本预测：", json.dumps(result.metrics["sample_prediction"], ensure_ascii=False, indent=2),
        "", f"图表对象颜色核对：{'全部通过' if audit_pass else '部分未通过'}"]
    for name, item in result.audit.items():
        pixel_misses = [p["item"] for p in item["png_checks"] if not p["passed"]]
        lines.append(f"{name}: {'通过' if item['passed'] else '未通过'}；对象检查 {len(item['object_checks'])} 项；PNG 像素证据 {len(item['png_checks'])} 项。")
        if pixel_misses:
            lines.append("  像素未命中（可能因透明度、字号或元素不可见）："+"、".join(pixel_misses))
    lines += ["", "颜色对象与配置比较；透明像素按背景混色，抗锯齿和重叠会产生中间色。",
        "SHAP 数值解释的是 log-odds，不是概率百分点。系数方向不代表统计显著性或因果关系。",
        "", "运行提示：", *(result.messages or [])]
    (result.folder / "运行报告.txt").write_text("\n".join(lines), encoding="utf-8")


def run_analysis(config, output_root, progress=lambda message: None, previous=None, data_only=False):
    from .config import ROOT
    from matplotlib import font_manager
    config = deepcopy(config)
    validate(config)
    for font_path in (ROOT / "assets").glob("NotoSansCJKsc-*.otf"):
        font_manager.fontManager.addfont(str(font_path))
    result = AnalysisResult(config=config, folder=_new_folder(output_root), data=None, features=[], messages=[])
    try:
        if previous is not None:
            if any(config[key] != previous.config[key] for key in ("data", "model")):
                raise ValueError("数据或模型参数已经变化，请先运行完整分析，再单独重新绘图。")
            if previous.model is None:
                raise ValueError("尚无已训练的模型，请先运行完整分析。")
            for key in ("data", "features", "model", "train", "test", "y_test", "predictions", "coefficients"):
                setattr(result, key, getattr(previous, key))
            result.metrics = deepcopy(previous.metrics)
        else:
            progress("正在生成模拟数据…")
            result.data, result.features = generate_dataset(config)
        _save_data(result)
        if data_only:
            progress("数据已保存，可查看数据表或继续分析。")
            return result
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            if previous is None:
                progress("正在训练逻辑回归并评估…")
                _fit(result)
            if not 0 <= config["plots"]["sample_index"] < len(result.test):
                raise ValueError(f"样本索引超出范围，测试集共 {len(result.test)} 行。")
            progress("正在计算 SHAP 并生成图表…")
            _draw(result, progress)
            result.messages = list(dict.fromkeys(str(w.message) for w in captured))
        progress("正在保存数据、预测、图表与颜色核对报告…")
        _save_results(result)
        progress("分析完成，全部结果已保存。")
        return result
    except Exception as exc:
        (result.folder / "失败说明.txt").write_text(str(exc), encoding="utf-8")
        raise


def copy_results(result, destination):
    destination = Path(destination).expanduser().resolve()
    if destination == result.folder.resolve():
        return destination
    if result.folder.resolve() in destination.parents:
        raise ValueError("不能将结果目录复制到其自身的子目录。")
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / result.folder.name
    if target.exists():
        target = destination / (result.folder.name+"_"+uuid.uuid4().hex[:4])
    shutil.copytree(result.folder, target)
    return target
