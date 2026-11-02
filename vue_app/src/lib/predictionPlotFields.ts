export interface PlotField {
  key: string;
  label: string;
  kind?:
    "text" | "number" | "color" | "boolean" | "select" | "list" | "textarea";
  min?: number;
  max?: number;
  integer?: boolean;
  options?: (string | { value: string; label: string })[];
}
export const lineOptions = [
  { value: "-", label: "实线" },
  { value: "--", label: "虚线" },
  { value: "-.", label: "点划线" },
  { value: ":", label: "点线" },
];
export const markerOptions = [
  { value: "o", label: "圆点" },
  { value: "s", label: "方形" },
  { value: "^", label: "上三角" },
  { value: "v", label: "下三角" },
  { value: "D", label: "菱形" },
  { value: "+", label: "加号" },
  { value: "x", label: "叉号" },
  { value: "*", label: "星号" },
  { value: ".", label: "小点" },
  { value: "", label: "无" },
];
const n = (
  key: string,
  label: string,
  min = 0,
  max = 100,
  integer = false,
): PlotField => ({ key, label, kind: "number", min, max, integer });
const t = (key: string, label: string): PlotField => ({ key, label });
const b = (key: string, label: string): PlotField => ({
  key,
  label,
  kind: "boolean",
});
const color = (key: string, label: string): PlotField => ({
  key,
  label,
  kind: "color",
});
const select = (
  key: string,
  label: string,
  options: PlotField["options"],
): PlotField => ({ key, label, kind: "select", options });
export const commonGroups: { title: string; fields: PlotField[] }[] = [
  {
    title: "分辨率与背景",
    fields: [
      n("dpi", "导出 DPI", 50, 1200, true),
      n("preview_dpi", "预览 DPI", 50, 180, true),
      color("background", "背景颜色"),
      b("transparent", "透明背景"),
    ],
  },
  {
    title: "字体与字号",
    fields: [
      t("font_family", "中文字体（auto 为自动）"),
      t("latin_font", "西文字体（auto 为自动）"),
      n("font_size", "基础字号", 4, 60),
      n("title_size", "总标题字号", 4, 60),
      n("panel_title_size", "面板标题字号", 4, 60),
      n("label_size", "坐标标题字号", 4, 60),
      n("tick_size", "坐标刻度字号", 4, 60),
      n("legend_size", "图例字号", 4, 60),
      n("note_size", "图注字号", 4, 60),
      color("text_color", "文字颜色"),
      select("title_weight", "标题字重", [
        { value: "normal", label: "常规" },
        { value: "bold", label: "加粗" },
      ]),
    ],
  },
  {
    title: "坐标刻度与网格",
    fields: [
      n("axis_width", "坐标轴线宽", 0.1, 10),
      n("tick_length", "刻度线长度", 0, 20),
      n("tick_width", "刻度线宽", 0.1, 10),
      select("tick_direction", "刻度方向", [
        { value: "out", label: "向外" },
        { value: "in", label: "向内" },
        { value: "inout", label: "双向" },
      ]),
      b("grid", "显示网格"),
      color("grid_color", "网格颜色"),
      select("grid_style", "网格线型", lineOptions),
      n("grid_width", "网格线宽", 0.1, 10),
      n("grid_alpha", "网格不透明度", 0, 1),
    ],
  },
];
export const seriesFields: PlotField[] = [
  t("label", "显示名称"),
  color("color", "颜色"),
  n("line_width", "曲线线宽", 0.1, 10),
  select("line_style", "曲线线型", lineOptions),
  select("marker", "标记形状", markerOptions),
  n("marker_size", "标记尺寸", 0, 20),
  n("alpha", "不透明度", 0, 1),
];
export const canvasFields: PlotField[] = [
  b("enabled", "生成这张图"),
  t("filename", "导出文件名（不含扩展名）"),
  n("width", "画布宽度（英寸）", 4, 24),
  n("height", "画布高度（英寸）", 3, 40),
  n("left", "左边界比例", 0, 1),
  n("right", "右边界比例", 0, 1),
  n("top", "上边界比例", 0, 1),
  n("bottom", "下边界比例", 0, 1),
];
export const textFields: PlotField[] = [
  t("title", "总标题"),
  n("title_x", "总标题 X", -0.5, 1.5),
  n("title_y", "总标题 Y", -0.5, 1.5),
  { key: "note", label: "图注", kind: "textarea" },
  n("note_x", "图注 X", -0.5, 1.5),
  n("note_y", "图注 Y", -0.5, 1.5),
];
export const axisGroups: { title: string; fields: PlotField[] }[] = [
  {
    title: "面板与标题",
    fields: [
      select("layout", "面板布局", [
        { value: "horizontal", label: "左右双面板" },
        { value: "vertical", label: "上下双面板" },
        { value: "separate", label: "训练／验证分别导出" },
      ]),
      n("wspace", "面板水平间距", 0, 2),
      n("hspace", "面板垂直间距", 0, 2),
      t("train_title", "训练面板标题"),
      t("validation_title", "验证面板标题"),
      b("panel_labels", "显示面板编号"),
      t("panel_a", "训练面板编号"),
      t("panel_b", "验证面板编号"),
      n("panel_x", "面板编号 X", -2, 3),
      n("panel_y", "面板编号 Y", -2, 3),
      n("panel_size", "面板编号字号", 4, 50),
      n("title_pad", "面板标题间距", 0, 50),
    ],
  },
  {
    title: "坐标轴与刻度",
    fields: [
      t("x_label", "X 轴标题"),
      t("y_label", "Y 轴标题"),
      n("x_min", "X 轴最小值", -10, 10),
      n("x_max", "X 轴最大值", -10, 10),
      n("y_min", "Y 轴最小值", -10, 10),
      n("y_max", "Y 轴最大值", -10, 10),
      { key: "x_ticks", label: "X 轴刻度（逗号分隔）", kind: "list" },
      { key: "y_ticks", label: "Y 轴刻度（逗号分隔）", kind: "list" },
      n("tick_digits", "坐标刻度小数位", 0, 8, true),
      n("x_rotation", "X 轴刻度旋转", -180, 180),
      n("y_rotation", "Y 轴刻度旋转", -180, 180),
      n("label_pad", "坐标标题间距", 0, 50),
      n("tick_pad", "刻度文字间距", 0, 50),
      select("aspect", "坐标轴比例", [
        { value: "equal", label: "等比例" },
        { value: "auto", label: "填充画布" },
      ]),
      b("spine_left", "显示左轴框"),
      b("spine_bottom", "显示下轴框"),
      b("spine_top", "显示上轴框"),
      b("spine_right", "显示右轴框"),
    ],
  },
  {
    title: "图例位置与排版",
    fields: [
      b("legend", "显示图例"),
      t("legend_title", "图例标题"),
      select("legend_location", "图例对齐位置", [
        { value: "best", label: "自动避让" },
        { value: "upper left", label: "左上角" },
        { value: "upper right", label: "右上角" },
        { value: "lower left", label: "左下角" },
        { value: "lower right", label: "右下角" },
        { value: "upper center", label: "上方居中" },
        { value: "lower center", label: "下方居中" },
        { value: "center left", label: "左侧居中" },
        { value: "center right", label: "右侧居中" },
        { value: "center", label: "正中" },
      ]),
      b("legend_anchor", "启用自定义图例锚点"),
      n("legend_x", "图例锚点 X", -2, 3),
      n("legend_y", "图例锚点 Y", -2, 3),
      n("legend_columns", "图例列数", 1, 4, true),
      b("legend_frame", "显示图例边框"),
      color("legend_face", "图例底色"),
      color("legend_edge", "图例边框颜色"),
      n("legend_alpha", "图例底色不透明度", 0, 1),
      n("legend_labelspacing", "图例行间距", 0, 10),
      n("legend_columnspacing", "图例列间距", 0, 10),
      n("legend_handlelength", "图例示例线长度", 0, 10),
      { key: "legend_template", label: "图例内容模板", kind: "textarea" },
      n("auc_digits", "AUC 与置信区间小数位", 0, 8, true),
      n("stat_digits", "χ² 小数位", 0, 8, true),
      n("p_digits", "P 值小数位", 1, 8, true),
      n("brier_digits", "Brier 小数位", 0, 8, true),
    ],
  },
  {
    title: "曲线与参考线",
    fields: [
      b("connect", "连接曲线"),
      b("markers", "显示数据点标记"),
      select("drawstyle", "连线绘制方式", [
        { value: "default", label: "直线连接" },
        { value: "steps-post", label: "后阶梯" },
        { value: "steps-pre", label: "前阶梯" },
        { value: "steps-mid", label: "中阶梯" },
      ]),
      b("reference", "显示理想／参考线"),
      color("reference_color", "参考线颜色"),
      select("reference_style", "参考线型", lineOptions),
      n("reference_width", "参考线宽", 0.1, 10),
    ],
  },
];
export const nomogramGroups: { title: string; fields: PlotField[] }[] = [
  {
    title: "行距与积分轴",
    fields: [
      b("auto_height", "按指标数自动计算高度"),
      n("row_height", "每项指标增加高度（英寸）", 0.3, 2),
      n("base_height", "自动高度基础值（英寸）", 1, 10),
      t("points_label", "顶部积分轴标题"),
      t("total_label", "总积分轴标题"),
      t("risk_label", "风险轴标题"),
      n("points_max", "顶部积分最大值", 10, 1000),
      n("points_ticks", "顶部积分刻度数", 2, 15, true),
      n("total_ticks", "总积分刻度数", 2, 15, true),
      select("variable_tick_mode", "指标刻度方式", [
        { value: "nice", label: "整洁刻度，短轴只标端点" },
        { value: "even", label: "按指定数量均匀分布" },
      ]),
      select("total_tick_mode", "总积分刻度方式", [
        { value: "nice", label: "整洁刻度并保留总分终点" },
        { value: "count", label: "按指定数量均匀分布" },
      ]),
      n("variable_ticks", "连续指标默认刻度数", 2, 15, true),
      { key: "risk_ticks", label: "风险概率刻度（逗号分隔）", kind: "list" },
      b("auto_risk_ticks", "可见风险刻度不足时自动补充"),
      n("risk_digits", "风险概率小数位", 0, 8, true),
      n("variable_digits", "指标有效数字位数", 1, 8, true),
      n("total_digits", "总积分小数位", 0, 8, true),
    ],
  },
  {
    title: "轴线、标签与刻度样式",
    fields: [
      color("line_color", "默认指标轴颜色"),
      color("points_color", "顶部积分轴颜色"),
      color("total_color", "总积分轴颜色"),
      color("risk_color", "风险轴颜色"),
      select("line_style", "列线图轴线型", lineOptions),
      n("line_width", "列线图轴线宽", 0.1, 8),
      n("tick_width", "列线图刻度线宽", 0.1, 8),
      n("tick_length", "刻度线半长（行单位）", 0.01, 0.3),
      n("tick_offset", "刻度标签下移（行单位）", 0.05, 0.4),
      n("label_offset", "左侧标签距离比例", 0.005, 0.3),
      n("label_size", "指标及积分轴标签字号", 4, 40),
      n("tick_size", "列线图刻度字号", 4, 40),
      n("label_rotation", "列线图标签旋转", -180, 180),
      n("tick_rotation", "列线图刻度旋转", -180, 180),
    ],
  },
];

export const optionalPlotGroups: Record<
  string,
  { title: string; fields: PlotField[] }[]
> = {
  lasso: [
    {
      title: "面板标题与坐标",
      fields: [
        t("path_title", "系数轨迹标题"),
        t("cv_title", "交叉验证标题"),
        t("x_label", "横轴标题"),
        t("path_y_label", "系数纵轴标题"),
        t("cv_y_label", "误差纵轴标题"),
        t("top_label", "顶部计数标题"),
        n("wspace", "面板水平间距", 0, 2),
        n("top_ticks", "顶部刻度数", 2, 12, true),
        b("show_top_counts", "显示非零原始变量数"),
        b("show_zero_line", "显示零系数参考线"),
        b("panel_labels", "显示 A / B 编号"),
        b("auto_note", "自动生成分析说明"),
      ],
    },
    {
      title: "曲线、误差线与规则颜色",
      fields: [
        n("path_line_width", "保留指标线宽", 0.1, 8),
        color("inactive_color", "未保留指标颜色"),
        n("inactive_width", "未保留指标线宽", 0.1, 8),
        color("cv_color", "CV 均值点颜色"),
        select(
          "cv_marker",
          "CV 点形状",
          markerOptions.filter((x) =>
            ["o", "s", "^", "D", ".", "x"].includes(x.value),
          ),
        ),
        n("cv_marker_size", "CV 点尺寸", 1, 15),
        color("error_color", "标准误差线颜色"),
        n("error_width", "误差线宽", 0.1, 8),
        n("error_capsize", "误差线端帽", 0, 10),
        color("minimum_color", "最小误差规则颜色"),
        color("one_se_color", "一个标准误规则颜色"),
        color("constraint_color", "数量约束规则颜色"),
        n("reference_width", "选择规则参考线宽", 0.1, 8),
      ],
    },
    {
      title: "保留指标图例",
      fields: [
        b("legend", "显示保留指标图例"),
        t("legend_title", "图例标题"),
        n("legend_columns", "图例列数", 1, 4, true),
        n("legend_x", "图例 X", -2, 3),
        n("legend_y", "图例 Y", -2, 3),
        b("legend_frame", "显示图例边框"),
      ],
    },
  ],
  shap: [
    {
      title: "面板内容与排序",
      fields: [
        b("auto_layout", "按指标数自动排版（长标签换行）"),
        n("row_height", "自动排版最小行高（英寸）", 0.22, 1),
        n("label_width", "自动排版标签宽度（英寸）", 1, 4),
        select("title_weight", "总标题与分图标题字重", [
          { value: "normal", label: "常规" }, { value: "bold", label: "加粗" },
        ]),
        select("label_weight", "坐标轴及色条标题字重", [
          { value: "normal", label: "常规" }, { value: "bold", label: "加粗" },
        ]),
        select("feature_weight", "指标名称字重", [
          { value: "normal", label: "常规" }, { value: "bold", label: "加粗" },
        ]),
        t("summary_title", "蜂群图标题"),
        t("importance_title", "重要性图标题"),
        t("waterfall_title", "瀑布图标题"),
        t("force_title", "力图标题"),
        n("max_display", "汇总图最多显示指标数", 1, 60, true),
        n("max_single", "单病例最多单列指标数", 1, 60, true),
        select("order", "指标排序", [
          { value: "importance", label: "按平均绝对贡献降序" },
          { value: "custom", label: "按自定义顺序" },
        ]),
        b("panel_labels", "显示 A / B / C / D 编号"),
        b("auto_note", "自动生成分析说明"),
      ],
    },
    {
      title: "颜色、标记与标注",
      fields: [
        color("low_color", "低特征值颜色"),
        color("neutral_color", "中间／缺失值颜色"),
        color("high_color", "高特征值颜色"),
        color("positive_color", "正贡献颜色"),
        color("negative_color", "负贡献颜色"),
        color("bar_color", "默认重要性条形颜色"),
        n("point_size", "蜂群点大小", 1, 100),
        n("point_alpha", "蜂群点不透明度", 0, 1),
        n("jitter", "蜂群抖动半宽", 0, 0.45),
        n("bar_height", "条形高度", 0.1, 0.9),
        n("value_digits", "贡献值小数位", 0, 6, true),
        b("show_values", "显示贡献数值"),
        b("show_grid", "显示水平网格"),
        b("colorbar", "显示特征值色条"),
        n("force_label_min", "力图标签最小贡献比例", 0, 1),
      ],
    },
  ],
};

optionalPlotGroups.lasso[2].fields.push(
  {
    key: "legend_max",
    label: "最多显示图例数",
    kind: "number",
    min: 1,
    max: 60,
    integer: true,
  },
  { key: "annotation_x", label: "规则说明 X", kind: "number", min: 0, max: 1 },
  { key: "annotation_y", label: "规则说明 Y", kind: "number", min: 0, max: 1 },
  {
    key: "annotation_gap",
    label: "规则说明行距",
    kind: "number",
    min: 0.02,
    max: 0.15,
  },
);
optionalPlotGroups.shap[0].fields.push(
  { key: "wspace", label: "面板水平间距", kind: "number", min: 0, max: 2 },
  { key: "hspace", label: "面板垂直间距", kind: "number", min: 0, max: 2 },
  {
    key: "summary_height",
    label: "汇总图行高比例",
    kind: "number",
    min: 0.2,
    max: 4,
  },
  {
    key: "waterfall_height",
    label: "瀑布图行高比例",
    kind: "number",
    min: 0.2,
    max: 4,
  },
  {
    key: "force_height",
    label: "力图行高比例",
    kind: "number",
    min: 0.2,
    max: 4,
  },
);
