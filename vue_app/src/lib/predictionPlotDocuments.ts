import {
  commonGroups,
  seriesFields,
  canvasFields,
  textFields,
  axisGroups,
  nomogramGroups,
  optionalPlotGroups,
  type PlotField,
} from "./predictionPlotFields";

type Config = Record<string, any>;
export interface FigureExport {
  name: string;
  dpi?: number;
  requested_dpi?: number;
  preview_dpi?: number;
  width_inches?: number;
  height_inches?: number;
  formats?: string[];
  png_pixels?: number[] | null;
}
const plotNames: Record<string, string> = {
  roc: "ROC 曲线",
  calibration: "H-L 校准曲线",
  nomogram: "LR 列线图",
  lasso: "LASSO 筛选图",
  shap: "SHAP 解释组合图",
};
const fields = [
  ...commonGroups.flatMap((g) => g.fields),
  ...seriesFields,
  ...canvasFields,
  ...textFields,
  ...axisGroups.flatMap((g) => g.fields),
  ...nomogramGroups.flatMap((g) => g.fields),
  ...Object.values(optionalPlotGroups).flatMap((groups) =>
    groups.flatMap((g) => g.fields),
  ),
];
const fieldMap = new Map(fields.map((f) => [f.key, f]));
const labels: Record<string, string> = {
  panel_labels: "显示分图编号",
  label_size: "坐标标题字号",
  tick_size: "刻度字号",
  enabled: "是否启用",
  formats: "输出格式",
  feature_order: "自定义指标顺序",
  feature_styles: "指标显示名及颜色",
  features: "指标独立设置",
  category_labels: "分类显示名称",
  label: "显示名称",
  color: "颜色",
  ticks: "自定义刻度",
  visible: "是否显示",
  title_weight: "总标题及分图标题字重",
  label_weight: "坐标轴及色条标题字重",
  feature_weight: "指标名称字重",
};
function number(v: number) {
  return Number(v.toFixed(5)).toString();
}
function value(v: any, field?: PlotField): string {
  if (v === null || v === undefined) return "未设置";
  if (typeof v === "boolean") return v ? "开启" : "关闭";
  if (typeof v === "number") return number(v);
  if (Array.isArray(v))
    return v.length ? v.map((x) => value(x)).join(" → ") : "自动／未指定";
  if (typeof v === "object")
    return Object.keys(v).length
      ? Object.entries(v)
          .map(([k, x]) => `${labels[k] || k}：${value(x, fieldMap.get(k))}`)
          .join("；")
      : "未设置独立覆盖";
  const option = field?.options?.find(
    (o) => (typeof o === "string" ? o : o.value) === v,
  );
  if (option) return typeof option === "string" ? option : option.label;
  if (v === "auto")
    return "自动（按本机可用字体选择，跨电脑需安装相同字体才能严格复现）";
  return String(v) || "留空";
}
function lines(object: Config, excluded: string[] = []): string[] {
  return Object.entries(object)
    .filter(([k]) => !excluded.includes(k))
    .map(([key, v]) => {
      const field = fieldMap.get(key);
      return `${labels[key] || field?.label || key}：${value(v, field)}`;
    });
}
function fontSummary(s: Config, kind = "common"): string[] {
  if (kind === "nomogram")
    return [
      `中文字体：${value(s.font_family)}；英文及数字字体：${value(s.latin_font)}`,
      `总标题：${s.title_size} pt；变量及轴名称：${s.label_size} pt；数值刻度：${s.tick_size} pt；图注：${s.note_size} pt`,
      `文字颜色：${s.text_color}；标题字重：${value(s.title_weight, fieldMap.get("title_weight"))}`,
    ];
  return [
    `中文字体：${value(s.font_family)}；英文及数字字体：${value(s.latin_font)}`,
    `基础字号：${s.font_size} pt；总标题：${s.title_size} pt；分图标题：${s.panel_title_size} pt`,
    `坐标轴标题：${s.label_size} pt；刻度：${s.tick_size} pt；${kind === "shap" ? "数值与色条" : "图例"}：${s.legend_size} pt；图注：${s.note_size} pt`,
    `文字颜色：${s.text_color}；标题字重：${value(s.title_weight, fieldMap.get("title_weight"))}`,
  ];
}
function exportLines(exports: FigureExport[]): string[] {
  if (!exports.length)
    return [
      "最近实际导出：尚无记录。自动画布的最终尺寸与 PNG 实际 DPI 需在生成后确认，不以草稿值冒充实际值。",
    ];
  return [
    "【最近一次已生成图片的实际参数】",
    "以下是上一次导出记录；修改草稿后，须重新绘图才会更新，不能视为当前草稿的实际输出。",
    ...exports.map((e) => {
      const size =
        e.width_inches && e.height_inches
          ? `${number(e.width_inches)} × ${number(e.height_inches)} 英寸`
          : "尺寸未记录";
      const png = e.formats?.includes("png")
        ? `PNG 实际 ${e.dpi ?? "未记录"} DPI（请求 ${e.requested_dpi ?? "未记录"} DPI）${e.png_pixels ? `，${e.png_pixels.join(" × ")} 像素` : ""}`
        : "未导出 PNG";
      return `${e.name}：${size}；${png}；预览 ${e.preview_dpi ?? "未记录"} DPI；格式 ${(e.formats || []).map((f) => f.toUpperCase()).join(" / ") || "未记录"}`;
    }),
  ];
}
/** All three representations come from the same live config, never a canned template. */
export function predictionPlotDocuments(
  config: Config,
  exports: FigureExport[] = [],
) {
  if (
    !config?.common ||
    !config?.plots ||
    !Array.isArray(config?.model_order) ||
    !config?.models
  ) {
    throw Error("配置缺少公共样式、模型或图表设置，请先修正 JSON。");
  }
  const c = config.common;
  const result: string[] = [
    "预测模型图表参数说明（当前草稿）",
    "",
    `全图请求导出 DPI：${c.dpi}（各图独立覆盖时以各图设置为准）`,
    `全图预览 DPI：${c.preview_dpi}；公共输出格式：${(c.formats || []).map((f: string) => f.toUpperCase()).join(" / ")}`,
    "字号单位为 pt；画布宽高单位为英寸；边距和标题位置为相对坐标；颜色使用十六进制色值。PNG 像素预算为 6400 万，预览像素预算为 800 万；超出时按实际画布计算允许的整数 DPI，PDF / SVG 保留矢量。",
    "【公共字体与样式】",
    ...fontSummary(c),
    ...lines(c),
    "",
    "【模型、图例颜色与顺序】",
    `绘图顺序：${config.model_order.join(" → ")}（只绘制本次分析中实际存在的模型）`,
  ];
  for (const model of config.model_order)
    result.push(`${model}：${lines(config.models[model] || {}).join("；")}`);
  for (const [key, p] of Object.entries(config.plots) as [string, Config][]) {
    const s = { ...c, ...p.style };
    if (key === "nomogram") {
      s.label_size = p.label_size;
      s.tick_size = p.tick_size;
    }
    if (key === "shap") s.title_weight = p.title_weight;
    result.push(
      "",
      `【${plotNames[key] || key}】${p.enabled ? "已启用" : "未启用（以下配置保留，启用后生效）"}`,
      `本图请求导出 DPI：${s.dpi}；本图预览 DPI：${s.preview_dpi}；输出格式：${(s.formats || []).map((f: string) => f.toUpperCase()).join(" / ")}`,
      `配置画布：${p.width} × ${p.height} 英寸${p.auto_height || p.auto_layout ? "（启用自动适配，实际尺寸以导出记录为准）" : ""}`,
      "本图实际生效的字体：",
      ...fontSummary(s, key),
      "本图公共配置（已合并单图覆盖及图件专用字号）：",
      ...lines(s),
      "本图独立参数：",
      ...lines(p, ["style", "series", "reference_version"]),
    );
    if (p.series && Object.keys(p.series).length) {
      result.push("本图各模型覆盖后的实际样式：");
      for (const model of config.model_order)
        result.push(
          `${model}：${lines({ ...config.models[model], ...p.series[model] }).join("；")}`,
        );
    }
    if (key === "nomogram")
      result.push(
        `列线图变量名和轴名称实际字号：${p.label_size} pt；数值刻度：${p.tick_size} pt（以列线图独立参数为准）`,
        `自动画布高度：max(5, ${p.base_height} + ${p.row_height} × 实际指标数) 英寸；关闭自动高度时使用配置高度。`,
        "Points 和 Total Points 均为全宽轴；变量轴长按 LR 系数及训练集范围计算；负系数可使刻度方向递减，Risk 由同一次 LR 模型换算，不照抄示例积分或概率。",
      );
    if (key === "lasso")
      result.push(
        "LASSO 系数路径、交叉验证均值与标准误取自已计算快照；颜色按原始指标归组，所选变量保留颜色，其余使用未选颜色；仅展示诊断，不擅自改变四模型输入指标。",
      );
    if (key === "shap")
      result.push(
        "SHAP 字体与标注位置细节：",
        `总标题：${s.title_size} pt，${value(p.title_weight, fieldMap.get("title_weight"))}；分图标题：${s.panel_title_size} pt，左对齐；指标名：${s.tick_size} pt，${value(p.feature_weight, fieldMap.get("feature_weight"))}。`,
        `坐标轴标题：${s.label_size} pt，${value(p.label_weight, fieldMap.get("label_weight"))}；重要性数值和瀑布贡献：${s.legend_size} pt，数值加粗；力图箭头文字和逐项引导标注：${Math.max(6, s.legend_size - 1)} pt。`,
        `色条标题及高低标签：${s.legend_size} pt；样本数：${Math.max(6, s.note_size - 0.5)} pt；底部首行说明：${s.legend_size} pt，后两行：${s.note_size} pt。`,
        `散点面积：${p.point_size} pt²；透明度：${p.point_alpha}；低值 ${p.low_color} → 高值 ${p.high_color} 两色连续渐变，缺失值 ${p.neutral_color}；水平显示抖动最多为 SHAP 极差的 ${number(p.horizontal_jitter * 100)}%，固定种子 ${p.scatter_seed}，不修改分析数值。`,
        `重要性条形边框：#2F6080，0.5 pt；瀑布连接线：#CCCCCC，0.6 pt；小贡献数值在条外标注，零贡献保留；力图引导线：0.55 pt，正贡献 ${p.positive_color}，负贡献 ${p.negative_color}。`,
        "多指标和长名称只增加必要空间及标注行；所有已选指标、正负贡献与零贡献按实际计算保留。模型名、样本数、病例编号和输出单位由本次结果填充，不写死参考图数值。",
      );
  }
  result.push("", ...exportLines(exports));
  const description = result.join("\n");
  const json = JSON.stringify(config, null, 2);
  const prompt = [
    "请根据我提供的病例级数据或已计算绘图快照，用 Python / Matplotlib 生成临床二分类预测模型图，严格采用以下配置与版式。",
    "若提供绘图快照，复用该快照，不重新训练或修改预测概率、SHAP、LASSO、AUC、置信区间、H-L、Brier 等结果。若仅提供原始表格且缺少已确认的模型或划分方案，先明确结局、阳性编码、预测指标和建模设置，再计算，不能从参考图反推数值。",
    "编号只作身份核查；结局和预测指标按我明确的映射选择，不把编号或结局纳入特征。模型、病例数、病例编号、指标名称和单位必须来自本次数据。不要照抄示例的六个指标、119例、病例002或任何统计值。",
    "只输出已启用的图。逐图合并公共设置与独立覆盖，覆盖项优先；保留自定义模型标签、颜色和顺序。不要把所有文字统一加粗。自动画布应避免标签、色条、图例和图注重叠或裁切，保留 PNG 及配置中的矢量格式。",
    "若 PNG 触及像素预算，记录请求 DPI、实际 DPI、最终画布和像素；不以降低 DPI 代替修复排版。最近导出记录只用于对照，不能替代新图的实际记录。字体设为自动时，请报告实际选用的字体，跨系统尽量安装相同字体。",
    "输出图片、可编辑代码、同一配置 JSON 和实际导出参数；确认图例数值与结果表一致，SHAP 基准值加贡献之和等于模型输出，概率与模型输出单位一致。",
    "",
    description,
    "",
    "以下 JSON 是可导入 App 的完整图表配置；数值配置为唯一参数来源：",
    "```json",
    json,
    "```",
  ].join("\n");
  return { description, json, prompt };
}
