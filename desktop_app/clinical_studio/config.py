"""可保存、可复现的应用配置。"""
from copy import deepcopy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLOT_NAMES = {
    "summary": "SHAP 摘要图", "bar": "特征重要性条形图", "force": "单样本力图",
    "waterfall": "单样本瀑布图", "dependence_protective": "保护因素依赖图",
    "dependence_risk": "危险因素依赖图",
}


def default_config():
    return json.loads((ROOT / "defaults.json").read_text(encoding="utf-8"))


def save_config(config, path):
    Path(path).write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(config)
    return config


def validate(config):
    """在创建输出文件和执行计算之前验证所有输入。"""
    def finite(value):
        if isinstance(value, dict):
            for item in value.values(): finite(item)
        elif isinstance(value, (list, tuple)):
            for item in value: finite(item)
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("所有数值参数必须是有限数值，不能填写 NaN 或无穷大。")
    finite(config)
    if config.get("schema_version") != 1:
        raise ValueError("不支持的配置文件版本。")
    data, model, plots = config["data"], config["model"], config["plots"]
    n = data["n_samples"]
    if not isinstance(n, int) or not 10 <= n <= 1_000_000:
        raise ValueError("样本量必须是 10～1,000,000 的整数。")
    if not 0 < data["positive_rate"] < 1:
        raise ValueError("阳性比例必须大于 0 且小于 100%。")
    positive = int(n * data["positive_rate"])
    if positive < 2 or n-positive < 2:
        raise ValueError("阳性和阴性组至少各需要 2 个样本。")
    features = data["features"]
    if not features:
        raise ValueError("至少需要一个输入特征。")
    names = [f["name"].strip() for f in features]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("特征名称不能为空或重复。")
    if data["label_name"] in names or data["id_name"] in names or data["label_name"] == data["id_name"]:
        raise ValueError("特征名称、结局列名、ID 列名必须各不相同。")
    if not data["label_name"].strip() or not data["id_name"].strip():
        raise ValueError("结局列名和 ID 列名不能为空。")
    for feature in features:
        if feature["kind"] == "continuous":
            for group in ("positive", "negative"):
                values = feature[group]
                if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values.values()):
                    raise ValueError(f"{feature['name']} 的分布参数必须是有限数值。")
                if values["std"] < 0 or values["min"] >= values["max"]:
                    raise ValueError(f"{feature['name']}：标准差不能为负，下限必须小于上限。")
            if feature["transform"] not in ("int", "round", "none"):
                raise ValueError("不支持的数值处理方式。")
            if not 0 <= feature["digits"] <= 10:
                raise ValueError("小数位数必须在 0～10 之间。")
        elif feature["kind"] == "binary":
            if len(feature["values"]) != 2 or feature["values"][0] == feature["values"][1]:
                raise ValueError("二分类特征必须设置两个不同的数值编码。")
            if not all(math.isfinite(float(v)) for v in feature["values"]):
                raise ValueError("分类编码必须是有限数值。")
            if not all(0 <= feature[k] <= 1 for k in ("positive_p", "negative_p")):
                raise ValueError("分类变量概率必须在 0%～100% 之间。")
        else:
            raise ValueError("不支持的特征类型。")
    for value in [data["random_seed"], model["split_seed"], model["random_state"], plots["random_seed"], config["explanation"]["background_seed"]]:
        if not isinstance(value, int) or not 0 <= value <= 2**32-1:
            raise ValueError("随机种子必须是 0～4294967295 的整数。")
    if not .01 <= model["test_size"] <= .99:
        raise ValueError("测试集比例必须在 1%～99% 之间。")
    if model["solver"] not in ("lbfgs", "liblinear", "newton-cg", "newton-cholesky", "sag", "saga"):
        raise ValueError("不支持的模型求解器。")
    if model["penalty"] not in ("l1", "l2", "elasticnet", "none"):
        raise ValueError("不支持的正则化方式。")
    if not isinstance(model["max_iter"], int) or model["max_iter"] < 1:
        raise ValueError("最大迭代次数必须是正整数。")
    if model["class_weight"] not in ("none", "balanced"):
        raise ValueError("不支持的类别权重。")
    if not 0 < model["threshold"] < 1 or model["C"] <= 0 or model["tol"] <= 0:
        raise ValueError("分类阈值须在 0～1 之间，C 和收敛容差必须为正。")
    if model["penalty"] in ("l1", "elasticnet") and model["solver"] != "saga":
        if not (model["penalty"] == "l1" and model["solver"] == "liblinear"):
            raise ValueError("L1 请使用 saga/liblinear；ElasticNet 请使用 saga。")
    if model["penalty"] == "none" and model["solver"] == "liblinear":
        raise ValueError("无正则化时不能使用 liblinear 求解器。")
    if not 0 <= model["l1_ratio"] <= 1:
        raise ValueError("L1 混合比例须在 0～1 之间。")
    if config["explanation"]["background_max_samples"] < 1:
        raise ValueError("SHAP 背景样本数至少为 1。")
    if config["explanation"].get("protective_feature") is not None and config["explanation"]["protective_feature"] not in names:
        raise ValueError("默认保护因素展示特征已不存在，请重新选择或选择自动。")
    formats = plots["formats"]
    if not formats or any(f not in ("png", "svg", "pdf") for f in formats):
        raise ValueError("请至少选择一种导出格式：PNG、SVG、PDF。")
    if not 72 <= plots["dpi"] <= 1200:
        raise ValueError("图片 DPI 必须在 72～1200 之间。")
    if not isinstance(plots["sample_index"], int) or plots["sample_index"] < 0:
        raise ValueError("局部解释样本索引必须是非负整数。")
    filenames = []
    for name, overrides in plots["plots"].items():
        if name not in PLOT_NAMES:
            raise ValueError(f"未知图表类型：{name}")
        style = deepcopy(plots["common"])
        style.update(overrides)
        from matplotlib.colors import is_color_like
        for key, value in style.items():
            if key.endswith("color") or key in ("background", "positive_light", "negative_light"):
                if not is_color_like(value): raise ValueError(f"{PLOT_NAMES[name]} 的 {key} 颜色无效。")
        for key in ("font_size", "title_size", "label_size", "tick_size"):
            if style[key] <= 0: raise ValueError("字号必须大于 0。")
        for key in ("axis_width", "tick_width", "tick_length", "line_width", "grid_width", "baseline_width", "point_size", "edge_width", "separator_width"):
            if style[key] < 0: raise ValueError("线宽、刻度长度和散点面积不能为负。")
        if name == "bar":
            if style["bar_height"] <= 0: raise ValueError("条形高度必须大于 0。")
            try: format(0.123, style["value_format"])
            except (ValueError, TypeError) as exc: raise ValueError("条形数值格式无效，例如 .3f。") from exc
        if name == "force" and (style["ylim"][0] >= style["ylim"][1] or not 0 < style["content_top"] <= 1):
            raise ValueError("力图纵向范围必须递增，内容上边界须在 0～1 之间。")
        filename = style["filename"]
        if not filename or any(c in filename for c in '/\\:*?"<>|') or filename in (".", ".."):
            raise ValueError("图片文件名不能为空，也不能包含路径或特殊字符。")
        if filename in filenames:
            raise ValueError("各张图的文件名不能重复。")
        filenames.append(filename)
        if style.get("feature") is not None and style["feature"] not in names:
            raise ValueError(f"{PLOT_NAMES[name]} 所选特征已不存在，请重新选择。")
        if style.get("interaction_feature") is not None and style["interaction_feature"] not in names:
            raise ValueError("交互着色特征已不存在，请重新选择。")
        if len(style["figsize"]) != 2 or not all(2 <= float(v) <= 40 for v in style["figsize"]):
            raise ValueError("图片宽、高须在 2～40 英寸之间。")
        if style["figsize"][0]*plots["dpi"]*style["figsize"][1]*plots["dpi"] > 40_000_000:
            raise ValueError("单张图片超过 4000 万像素，请降低尺寸或 DPI。")
        for k in ("point_alpha", "baseline_alpha"):
            if not 0 <= style[k] <= 1:
                raise ValueError("透明度须在 0～1 之间。")
    return config
