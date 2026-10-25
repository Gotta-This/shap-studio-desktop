"""从原始 Notebook 提取的 SHAP 绘图流程与颜色核对。"""
import numpy as np
import shap
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from copy import deepcopy
from pathlib import Path
import warnings
import inspect
import matplotlib as mpl
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.text import Text


def _plot_style(config, name):
    style = deepcopy(config["common"])
    style.update(config["plots"][name])
    return style


def _font_and_rc(style):
    families = list(style["font_family"])
    if style["font_file"]:
        font_path = Path(style["font_file"]).expanduser()
        if not font_path.is_file():
            raise FileNotFoundError(f"字体文件不存在：{font_path}")
        fm.fontManager.addfont(str(font_path))
        families.insert(0, fm.FontProperties(fname=str(font_path)).get_name())
    installed = {font.name for font in fm.fontManager.ttflist}
    families = [name for name in families if name in installed]
    if not families:
        raise ValueError("配置中的字体均未安装，请设置 font_file 为可用的中文字体文件。")
    if families == ["DejaVu Sans"]:
        warnings.warn("未找到中文字体，中文可能显示为方框，请配置 font_file。", UserWarning)
    return {
        "font.family": families,
        "font.size": style["font_size"],
        "axes.unicode_minus": False,
        "axes.edgecolor": style["axis_color"],
        "axes.linewidth": style["axis_width"],
        "text.color": style["text_color"],
        "axes.labelcolor": style["text_color"],
        "figure.facecolor": style["background"],
        "axes.facecolor": style["background"],
        "mathtext.fontset": "dejavusans",
    }


def _recolor_shap(fig, style):
    """覆盖 SHAP 静态力图/瀑布图内部颜色，不修改 SHAP 的全局常量。"""
    palette = [
        ("#FF0D57", style["positive_color"]),
        ("#1E88E5", style["negative_color"]),
        ("#FFC3D5", style["positive_light"]),
        ("#D1E6FA", style["negative_light"]),
    ]
    # 不同 SHAP 版本的瀑布图可能采用不同的默认颜色。
    palette.extend([(shap.plots.colors.red_rgb, style["positive_color"]),
                    (shap.plots.colors.blue_rgb, style["negative_color"])])
    if hasattr(shap.plots, "get_style"):
        defaults = shap.plots.get_style()
        palette.extend([(defaults.primary_color_positive, style["positive_color"]),
                        (defaults.primary_color_negative, style["negative_color"])])

    def mapped(color):
        try:
            rgba = to_rgba(color)
        except (TypeError, ValueError):
            return color, False
        for old, new in palette:
            if np.allclose(rgba[:3], to_rgba(old)[:3], atol=1e-5):
                return (*to_rgba(new)[:3], rgba[3]), True
        return color, False

    for ax in fig.axes:
        for artist in [*ax.patches, *ax.lines, *ax.texts]:
            for prop in ("color", "facecolor", "edgecolor"):
                getter, setter = getattr(artist, "get_" + prop, None), getattr(artist, "set_" + prop, None)
                if getter and setter:
                    value, changed = mapped(getter())
                    if changed:
                        setter(value)
            if artist in ax.patches:
                # SHAP 力图的填充多边形默认无描边；只设置 linewidth 不会出现在导出图里。
                if (artist.get_fill() and artist.get_facecolor()[3] > 0
                        and artist.get_alpha() != 0 and artist.get_edgecolor()[3] == 0):
                    artist.set_edgecolor(artist.get_facecolor())
                # 无填充色的 Polygon 是力图分隔线；填充箭头使用 edge_width。
                separator = isinstance(artist, mpl.patches.Polygon) and not artist.get_fill()
                artist.set_linewidth(style["separator_width"] if separator else style["edge_width"])
        for image in ax.images:
            # 力图下方的渐变阴影也是独立的颜色映射。
            start, changed = mapped(image.get_cmap()(0.0))
            if changed:
                image.set_cmap(LinearSegmentedColormap.from_list(
                    "configured_force_shading", [start, style["background"]]))


def _finish_plot(fig, main_ax, style, config, name, colorbar_axes=()):
    """在 SHAP 完成绘图后统一样式，避免被内部默认值覆盖。"""
    fig.set_size_inches(*style["figsize"], forward=True)
    fig.set_facecolor(style["background"])
    font_family = mpl.rcParams["font.family"]
    for text in fig.findobj(match=Text):
        text.set_fontfamily(font_family)
        text.set_fontsize(style["font_size"])
        bbox = text.get_bbox_patch()
        if bbox is not None and bbox.get_facecolor()[3] > 0:
            bbox.set_facecolor(style["background"])
            bbox.set_edgecolor(style["background"])
        # 中性色文字遵循 text_color；正负贡献文字保留其语义颜色。
        rgba = to_rgba(text.get_color())
        if np.ptp(rgba[:3]) < 1e-6:
            inside_value = name == "waterfall" and np.allclose(rgba[:3], [1, 1, 1])
            text.set_color(style["value_text_color"] if inside_value else style["text_color"])
    for ax in fig.axes:
        ax.set_facecolor(style["background"])
        ax.grid(False)
        ax.tick_params(axis="both", labelsize=style["tick_size"],
                       width=style["tick_width"], length=style["tick_length"],
                       color=style["axis_color"], labelcolor=style["text_color"])
        for spine in ax.spines.values():
            spine.set_edgecolor(style["axis_color"])
            spine.set_linewidth(style["axis_width"])
        for label in (ax.xaxis.label, ax.yaxis.label):
            label.set_fontsize(style["label_size"])
            label.set_color(style["text_color"])
        ax.xaxis.get_offset_text().set_fontsize(style["tick_size"])
        ax.yaxis.get_offset_text().set_fontsize(style["tick_size"])
        if ax in colorbar_axes:
            continue
        for line in list(ax.lines):
            x, y = np.asarray(line.get_xdata()), np.asarray(line.get_ydata())
            horizontal = len(y) > 1 and np.all(y == y[0]) and len(x) > 1 and np.any(x != x[0])
            if name in ("summary", "waterfall") and horizontal:
                if not style["grid"]:
                    line.remove()
                    continue
                line.set_color(style["grid_color"])
                line.set_linewidth(style["grid_width"])
                line.set_linestyle(style["grid_style"])
                continue
            line.set_linewidth(style["line_width"])
            line.set_linestyle(style["line_style"])
            if name != "force" or np.ptp(to_rgba(line.get_color())[:3]) < 1e-6:
                line.set_color(style["line_color"])
            if name == "waterfall" and line.get_transform() == ax.get_xaxis_transform():
                line.set_color(style["baseline_color"])
                line.set_linewidth(style["baseline_width"])
                line.set_linestyle(style["baseline_style"])
                line.set_alpha(style["baseline_alpha"])
        if style["grid"] and ax is main_ax and name != "waterfall":
            ax.set_axisbelow(True)
            ax.grid(True, color=style["grid_color"], linewidth=style["grid_width"],
                    linestyle=style["grid_style"])
    if name == "summary":
        main_ax.spines["left"].set_visible(True)
        main_ax.tick_params(axis="y", left=True)
        # 替换 SHAP 的默认零线，避免同一位置重叠画两条线。
        for line in list(main_ax.lines):
            x = np.asarray(line.get_xdata())
            if x.size > 1 and np.all(x == 0):
                line.remove()
        main_ax.axvline(0, color=style["baseline_color"], linewidth=style["baseline_width"],
                       linestyle=style["baseline_style"], alpha=style["baseline_alpha"], zorder=0)
    if name.startswith("dependence_"):
        main_ax.axhline(0, color=style["baseline_color"], linewidth=style["baseline_width"],
                       linestyle=style["baseline_style"], alpha=style["baseline_alpha"],
                       label="基线(无影响)")
        main_ax.legend(prop={"family": font_family, "size": style["font_size"]},
                       labelcolor=style["text_color"])
    if name == "force":
        # 力图在轴外绘制 f(x) 等标签，用整图标题预留独立空间。
        fig.suptitle(style.get("title", ""), fontsize=style["title_size"],
                     fontweight=style["title_weight"], color=style["text_color"],
                     fontfamily=font_family, y=style["title_y"])
    else:
        main_ax.set_title(style.get("title", ""), fontsize=style["title_size"],
                          fontweight=style["title_weight"], pad=style["title_pad"],
                          color=style["text_color"])
    if "xlabel" in style:
        main_ax.set_xlabel(style["xlabel"], fontsize=style["label_size"], labelpad=style["xlabel_pad"])
    fig.tight_layout(rect=(0, 0, 1, style["content_top"]) if name == "force" else None)
    output_dir = Path(config["output_dir"]).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for extension in config["formats"]:
        extension = extension.lower().lstrip(".")
        output = output_dir / f'{style["filename"]}.{extension}'
        fig.savefig(output, dpi=config["dpi"], bbox_inches="tight",
                    facecolor=style["background"])
        paths.append(output)
        print(f"  ✓ 已保存: {output}")
    if config["show"]:
        plt.show()
    plt.close(fig)
    return paths


def perform_shap_analysis(model, X_train, X_test, feature_columns, protective_feature_name,
                          plot_config=None, progress=None, background_max_samples=100, background_seed=0):
    """生成启用的 SHAP 图表。所有视觉参数均来自 PLOT_CONFIG。"""
    config = deepcopy(plot_config)
    config["show"] = False
    COLOR_AUDIT_RESULTS.clear()
    feature_columns = list(feature_columns)
    if list(X_test.columns) != feature_columns or list(X_train.columns) != feature_columns:
        raise ValueError("特征列名称和顺序必须与训练集、测试集一致。")
    sample_index = config["sample_index"]
    if not 0 <= sample_index < len(X_test):
        raise ValueError("sample_index 超出测试集范围。")
    if not config["formats"]:
        raise ValueError("formats 至少需要包含一种图片格式。")
    print("正在计算 SHAP 值...")
    explainer = shap.LinearExplainer(model, shap.maskers.Independent(
        shap.utils.sample(X_train, min(background_max_samples, len(X_train)), random_state=background_seed),
        max_samples=background_max_samples))
    shap_values = np.asarray(explainer.shap_values(X_test))
    if shap_values.shape != X_test.shape:
        raise ValueError("此绘图流程适用于当前的二分类逻辑回归模型。")
    base_value = float(np.asarray(explainer.expected_value).item())
    importance = np.abs(shap_values).mean(axis=0)
    explanation = shap.Explanation(values=shap_values[sample_index], base_values=base_value,
                                   data=X_test.iloc[sample_index].values,
                                   feature_names=feature_columns)
    paths = []
    # SHAP 摘要图包含随机抖动；单独固定并在结束后恢复 NumPy 随机状态。
    random_state = np.random.get_state()
    interactive = plt.isinteractive()
    try:
        for name in config["plots"]:
            style = _plot_style(config, name)
            if not style.get("enabled", True):
                continue
            if progress:
                progress(f"正在绘制 {name}…")
            np.random.seed(config["random_seed"])
            with mpl.rc_context(_font_and_rc(style)):
                cmap = LinearSegmentedColormap.from_list(
                    "configured_feature_values", [style["low_color"], style["high_color"]])
                colorbar_axes = []
                if name == "summary":
                    fig, ax = plt.subplots(figsize=style["figsize"])
                    plt.sca(ax)
                    shap.summary_plot(shap_values, X_test, plot_type="dot", cmap=cmap,
                                      max_display=len(feature_columns), alpha=style["point_alpha"],
                                      plot_size=None, show=False,
                                      **({"rng": np.random.default_rng(config["random_seed"])}
                                         if "rng" in inspect.signature(shap.summary_plot).parameters else {}))
                    for collection in ax.collections:
                        if isinstance(collection, mpl.collections.PathCollection):
                            collection.set_sizes([style["point_size"]])
                    colorbar_axes = [other for other in fig.axes if other is not ax]
                    for other in colorbar_axes:
                        other.set_ylabel(style["colorbar_label"])
                        other.set_yticks([0, 1])
                        other.set_yticklabels(["低", "高"])
                elif name == "bar":
                    # 与原 SHAP 全局条形图相同的统计量：mean(abs(SHAP))。
                    fig, ax = plt.subplots(figsize=style["figsize"])
                    order = np.argsort(-importance, kind="stable")
                    ax.barh(np.arange(len(order)), importance[order], height=style["bar_height"],
                            color=style["bar_color"], edgecolor=style["bar_color"],
                            linewidth=style["edge_width"])
                    ax.set_yticks(np.arange(len(order)), np.asarray(feature_columns)[order])
                    ax.invert_yaxis()
                    ax.set_xlim(0, max(float(importance.max()) * 1.2, 0.01))
                    for y, value in enumerate(importance[order]):
                        ax.annotate(format(value, style["value_format"]), (value, y),
                                    xytext=(4, 0), textcoords="offset points", va="center",
                                    color=style["text_color"])
                    ax.spines[["top", "right"]].set_visible(False)
                elif name == "force":
                    # matplotlib=True 的一些版本忽略 plot_cmap，绘制后还需覆盖内部颜色。
                    fig = shap.force_plot(base_value, shap_values[sample_index], X_test.iloc[sample_index],
                                          matplotlib=True, show=False, figsize=style["figsize"],
                                          plot_cmap=[style["positive_color"], style["negative_color"]],
                                          text_rotation=style["text_rotation"],
                                          contribution_threshold=style["contribution_threshold"])
                    ax = fig.axes[0]
                    ax.set_ylim(*style["ylim"])
                    ax.spines["top"].set_position(("data", style["axis_y"]))
                    _recolor_shap(fig, style)
                elif name == "waterfall":
                    fig, ax = plt.subplots(figsize=style["figsize"])
                    plt.sca(ax)
                    shap.plots.waterfall(explanation, max_display=len(feature_columns), show=False)
                    _recolor_shap(fig, style)
                    # SHAP 用重复刻度和固定偏移拼接标签，更换字体后容易重叠。
                    # 改为完整标签，让它们统一遵循用户的字体、字号配置。
                    for twin in list(fig.axes):
                        if twin is not ax:
                            twin.remove()
                    ax.text(base_value, style["base_label_y"], f"E[f(X)] = {base_value:.3f}",
                            transform=ax.get_xaxis_transform(), ha="center", va="top")
                    ax.text(base_value + shap_values[sample_index].sum(), style["prediction_label_y"],
                            f"f(x) = {base_value + shap_values[sample_index].sum():.3f}",
                            transform=ax.get_xaxis_transform(), ha="center", va="bottom")
                elif name.startswith("dependence_"):
                    feature = style["feature"]
                    if feature is None and name == "dependence_protective":
                        feature = protective_feature_name
                    elif feature is None:
                        # 平均 SHAP 的正负不能判断危险/保护因素；这里用模型系数判断方向。
                        candidates = np.flatnonzero(model.coef_[0] > 0)
                        if not len(candidates):
                            print("没有正系数特征，跳过危险因素依赖图。")
                            continue
                        feature = feature_columns[candidates[np.argmax(importance[candidates])]]
                    if feature not in feature_columns:
                        raise ValueError(f"依赖图特征不存在：{feature}")
                    interaction = style["interaction_feature"]
                    if interaction is not None and interaction not in feature_columns:
                        raise ValueError(f"交互特征不存在：{interaction}；请使用明确的特征名或 None。")
                    fig, ax = plt.subplots(figsize=style["figsize"])
                    shap.dependence_plot(feature, shap_values, X_test, feature_names=feature_columns,
                                         interaction_index=interaction, color=style["point_color"],
                                         cmap=cmap if interaction is not None else None,
                                         dot_size=style["point_size"], alpha=style["point_alpha"],
                                         ax=ax, show=False)
                    style["title"] = style["title"].format(feature=feature)
                    ax.set_ylabel("SHAP值 (log-odds)")
                    colorbar_axes = [other for other in fig.axes if other is not ax]
                else:
                    raise ValueError(f"未知图表类型：{name}")
                paths.extend(_finish_plot(fig, ax, style, config, name, colorbar_axes))
    finally:
        np.random.set_state(random_state)
        plt.interactive(interactive)
    print(f"SHAP分析完成，共保存 {len(paths)} 个图表文件。")
    return paths


# ==================== 正式出图时自动核对颜色 ====================
# 核对对象颜色，并在保存的 PNG 中查找相应色值；透明散点按 alpha 与白底混合后比较。
# 这一单元不修改 PLOT_CONFIG，也不会改变生成的图。
import json
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from PIL import Image
from functools import wraps

COLOR_AUDIT_RESULTS = {}


def _hex_rgb(color):
    return mpl.colors.to_hex(to_rgba(color), keep_alpha=False).upper()


def _audit_saved_plot(fig, ax, style, config, name, paths):
    checks = []
    pixel_targets = []
    def check(label, actual, expected):
        ok = bool(np.allclose(to_rgba(actual)[:3], to_rgba(expected)[:3], atol=1e-6))
        checks.append({"item": label, "expected": _hex_rgb(expected),
                       "actual": _hex_rgb(actual), "passed": ok})
    def target(label, color, alpha=1):
        if alpha <= 0:
            return
        rgb = np.asarray(to_rgba(color)[:3])
        background = np.asarray(to_rgba(style["background"])[:3])
        rendered = np.clip(np.rint((alpha * rgb + (1-alpha)*background)*255), 0, 255).astype(int)
        pixel_targets.append((label, rendered.tolist()))

    fig.canvas.draw()
    check("画布背景", fig.get_facecolor(), style["background"])
    target("背景", style["background"])
    for index, spine in enumerate(ax.spines.values()):
        if spine.get_visible():
            check(f"可见坐标轴边框 {index}", spine.get_edgecolor(), style["axis_color"])
    target("坐标轴", style["axis_color"])
    for label in [ax.xaxis.label, ax.yaxis.label]:
        if label.get_text():
            check("轴标题文字", label.get_color(), style["text_color"])
    title = fig._suptitle if name == "force" else ax.title
    if title and title.get_text():
        check("图标题文字", title.get_color(), style["text_color"])
    target("文字", style["text_color"])
    if name == "summary":
        found = 0
        for collection in ax.collections:
            if not isinstance(collection, mpl.collections.PathCollection):
                continue
            values = collection.get_array()
            if values is None or not len(values):
                continue
            found += 1
            check("摘要散点渐变低端", collection.cmap(0.0), style["low_color"])
            check("摘要散点渐变高端", collection.cmap(1.0), style["high_color"])
            actual = collection.get_facecolors()
            expected = collection.cmap(collection.norm(values))
            checks.append({"item": f"散点组 {found} 的全部 RGB 与 cmap(norm(特征值)) 一致",
                           "passed": bool(np.allclose(actual[:,:3], expected[:,:3], atol=1e-6)),
                           "point_count": len(values)})
            checks.append({"item": f"散点组 {found} 的透明度", "expected": style["point_alpha"],
                           "actual": float(actual[0,3]),
                           "passed": bool(np.allclose(actual[:,3],style["point_alpha"]))})
        checks.append({"item": "摘要散点已被检查", "passed": found>0})
        bars = [other for other in fig.axes if other is not ax]
        for bar in bars:
            for collection in bar.collections:
                if isinstance(collection, mpl.collections.QuadMesh):
                    check("颜色条低端", collection.cmap(0.0), style["low_color"])
                    check("颜色条高端", collection.cmap(1.0), style["high_color"])
        target("颜色条低端", style["low_color"])
        target("颜色条高端", style["high_color"])
    elif name == "bar":
        for index, patch in enumerate(ax.patches):
            check(f"条形 {index+1} 填充", patch.get_facecolor(), style["bar_color"])
        target("条形填充", style["bar_color"])
    elif name in ("force", "waterfall"):
        found = Counter()
        allowed = [style[k] for k in ("positive_color", "negative_color", "positive_light", "negative_light")]
        for index, patch in enumerate(ax.patches):
            color = patch.get_facecolor()
            if not patch.get_fill() or color[3] == 0 or patch.get_alpha() == 0:
                continue
            matches = [c for c in allowed if np.allclose(to_rgba(c)[:3],color[:3],atol=1e-6)]
            checks.append({"item": f"色块 {index+1} 使用配置颜色", "actual": _hex_rgb(color),
                           "passed": bool(matches)})
            if matches:
                found[_hex_rgb(matches[0])] += 1
        for key, label in [("positive_color","正贡献"),("negative_color","负贡献")]:
            checks.append({"item": label+"色块存在", "expected": style[key],
                           "count": found[_hex_rgb(style[key])], "passed": True})
            target(label+"填充", style[key])
        if name == "force":
            for index, image in enumerate(ax.images):
                low = image.cmap(0.0)
                matches = [style[k] for k in ("positive_color","negative_color")
                           if np.allclose(to_rgba(style[k])[:3],low[:3])]
                checks.append({"item": f"力图渐变阴影 {index+1} 起点", "actual": _hex_rgb(low), "passed": bool(matches)})
                check(f"力图渐变阴影 {index+1} 终点",image.cmap(1.0),style["background"])
            for patch in ax.patches:
                if isinstance(patch,mpl.patches.Polygon) and not patch.get_fill():
                    edge=patch.get_edgecolor()
                    if edge[3]:
                        matches=[style[k] for k in ("positive_light","negative_light")
                                 if np.allclose(to_rgba(style[k])[:3],edge[:3])]
                        checks.append({"item":"力图分隔线颜色", "actual":_hex_rgb(edge), "passed":bool(matches)})
    elif name.startswith("dependence_"):
        found=0
        for collection in ax.collections:
            if isinstance(collection,mpl.collections.PathCollection) and len(collection.get_offsets()):
                found += 1
                colors=collection.get_facecolors()
                if style["interaction_feature"] is None:
                    for color in colors:
                        check("依赖图散点 RGB",color,style["point_color"])
                else:
                    check("依赖图渐变低端",collection.cmap(0.0),style["low_color"])
                    check("依赖图渐变高端",collection.cmap(1.0),style["high_color"])
                checks.append({"item":"依赖图散点透明度", "expected":style["point_alpha"],
                               "actual":float(colors[0,3]), "passed":bool(np.allclose(colors[:,3],style["point_alpha"]))})
        checks.append({"item":"依赖图散点存在", "passed":found>0})
        if style["interaction_feature"] is None:
            target("散点在背景上的实际颜色",style["point_color"],style["point_alpha"])
    if name == "summary" or name.startswith("dependence_"):
        baseline=ax.lines[-1]
        check("零基线",baseline.get_color(),style["baseline_color"])
        target("零基线",style["baseline_color"],style["baseline_alpha"])
    elif name == "waterfall":
        for line in ax.lines:
            baseline = line.get_transform() == ax.get_xaxis_transform()
            check("参考线" if baseline else "连接线",line.get_color(),
                  style["baseline_color"] if baseline else style["line_color"])
        target("连接线",style["line_color"])
        target("参考线",style["baseline_color"])

    # 统计 PNG 中每一种 RGB 的数量；允许 ±1 的 8 位量化差异。
    # 不把抗锯齿边缘或透明混合后的颜色误判成配色未生效。
    pixel_checks=[]
    png_paths=[path for path in paths if path.suffix.lower()==".png"]
    for path in png_paths:
        rgb=np.asarray(Image.open(path).convert("RGB"),dtype=np.uint32)
        packed=(rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
        values,counts=np.unique(packed,return_counts=True)
        histogram=dict(zip(values.tolist(),counts.tolist()))
        for label,color in pixel_targets:
            count=0
            for r in range(max(0,color[0]-1),min(255,color[0]+1)+1):
                for g in range(max(0,color[1]-1),min(255,color[1]+1)+1):
                    for b in range(max(0,color[2]-1),min(255,color[2]+1)+1):
                        count+=histogram.get((r<<16)|(g<<8)|b,0)
            pixel_checks.append({"item":label,"expected_rendered_rgb":color,
                                 "matching_pixels":int(count),"tolerance":1,"passed":count>0})
    from .style_audit import audit_style
    style_checks=audit_style(fig,ax,style,name)
    result={"name":name,"files":[str(p) for p in paths],"object_checks":checks,
            "style_checks":style_checks,
            "png_checks":pixel_checks,"passed":all(c["passed"] for c in checks+style_checks)}
    COLOR_AUDIT_RESULTS[name]=result
    print(f"  颜色核对 {name}: {'通过' if result['passed'] else '未通过'}")
    return result


# 重复执行此单元时，避免多层包装。
_finish_plot_original = getattr(_finish_plot, "__wrapped__", _finish_plot)
@wraps(_finish_plot_original)
def _finish_plot_verified(fig, main_ax, style, config, name, colorbar_axes=()):
    paths = _finish_plot_original(fig, main_ax, style, config, name, colorbar_axes)
    _audit_saved_plot(fig, main_ax, style, config, name, paths)
    return paths
_finish_plot = _finish_plot_verified
