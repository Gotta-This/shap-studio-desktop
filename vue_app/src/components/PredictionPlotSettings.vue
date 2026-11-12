<script setup lang="ts">
import SelectionActions from "@/components/SelectionActions.vue";
import { ref, watch, computed } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import PredictionPlotFields from "./PredictionPlotFields.vue";
import {
  commonGroups,
  seriesFields,
  canvasFields,
  textFields,
  axisGroups,
  nomogramGroups,
  optionalPlotGroups,
} from "@/lib/predictionPlotFields";
import { api, download, notify } from "@/lib/api";
import { clone } from "@/lib/scientific";
import {
  predictionPlotDocuments,
  type FigureExport,
} from "@/lib/predictionPlotDocuments";
const props = defineProps<{
  open: boolean;
  config: any;
  factory: any;
  features: { name: string; kind: string; values?: string[] }[];
  hasResult: boolean;
  figureExports?: FigureExport[];
}>();
const emit = defineEmits<{
  "update:open": [boolean];
  apply: [config: any, redraw: boolean];
}>();
const draft = ref<any>(null),
  tab = ref("common"),
  error = ref(""),
  message = ref(""),
  busy = ref(false),
  file = ref<HTMLInputElement>(),
  json = ref("");
const tabs = [
  { id: "common", name: "公共样式" },
  { id: "models", name: "模型与图例顺序" },
  { id: "roc", name: "ROC 曲线" },
  { id: "calibration", name: "校准曲线" },
  { id: "nomogram", name: "LR 列线图" },
  { id: "lasso", name: "LASSO 筛选图" },
  { id: "shap", name: "SHAP 解释图" },
  { id: "features", name: "指标顺序与颜色" },
  { id: "json", name: "完整配置 JSON" },
];
const shareFormat = ref<"json" | "description" | "prompt">("json");
const shareOptions = [
  { id: "json", label: "JSON 配置" },
  { id: "description", label: "中文参数说明" },
  { id: "prompt", label: "AI 作图提示词" },
] as const;
const sharing = computed(() => {
  try {
    return {
      documents: predictionPlotDocuments(
        JSON.parse(json.value),
        props.figureExports || [],
      ),
      error: "",
    };
  } catch {
    return {
      documents: null,
      error: "请先修正 JSON，再生成中文参数说明和 AI 提示词。",
    };
  }
});
async function copyShare() {
  busy.value = true;
  error.value = "";
  try {
    const config = await validated();
    const docs = predictionPlotDocuments(config, props.figureExports || []);
    json.value = docs.json;
    draft.value = config;
    const text = docs[shareFormat.value];
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const focused = document.activeElement as HTMLElement | null;
      const node = document.createElement("textarea");
      node.value = text;
      node.style.cssText = "position:fixed;opacity:0;pointer-events:none;";
      (document.querySelector("[role=dialog]") || document.body).appendChild(
        node,
      );
      node.select();
      const copied = document.execCommand("copy");
      node.remove();
      focused?.focus({ preventScroll: true });
      if (!copied) throw Error("未能访问剪贴板，请在下方文本框中全选后复制。");
    }
    message.value =
      "已复制" +
      shareOptions.find((o) => o.id === shareFormat.value)!.label +
      "。";
    notify(message.value);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
const plot = computed(() => draft.value?.plots[tab.value]);
const overrideGroups = computed(() =>
  tab.value === "nomogram"
    ? commonGroups.slice(0, 2).map((g) => ({
        ...g,
        fields: g.fields.filter(
          (f) =>
            ![
              "panel_title_size",
              "label_size",
              "tick_size",
              "legend_size",
            ].includes(f.key),
        ),
      }))
    : commonGroups,
);
const orderedFeatures = computed(() => {
  const names = props.features.map((f) => f.name);
  return [
    ...draft.value.plots.nomogram.feature_order.filter((n: string) =>
      names.includes(n),
    ),
    ...names.filter(
      (n) => !draft.value.plots.nomogram.feature_order.includes(n),
    ),
  ];
});
function normalizeDraftStyles() {
  if (!draft.value?.common || !draft.value?.plots) return;
  for (const item of Object.values(draft.value.plots) as any[]) {
    if (item?.style && Object.keys(item.style).length) {
      item.style = clone({ ...draft.value.common, ...item.style });
    }
  }
}
watch(
  () => props.open,
  (open) => {
    if (open) {
      draft.value = clone(props.config);
      normalizeDraftStyles();
      error.value = "";
      message.value = "";
      json.value = JSON.stringify(draft.value, null, 2);
    }
  },
);
function selectTab(next: string) {
  if (tab.value === "json") {
    try {
      draft.value = JSON.parse(json.value);
      normalizeDraftStyles();
      error.value = "";
    } catch {
      error.value = "JSON 格式错误，请先修正。";
      return;
    }
  }
  if (next === "json") json.value = JSON.stringify(draft.value, null, 2);
  tab.value = next;
}
function move(list: string[], i: number, delta: number) {
  if (i + delta < 0 || i + delta >= list.length) return;
  [list[i], list[i + delta]] = [list[i + delta], list[i]];
}
function moveFeature(i: number, delta: number) {
  const order = [...orderedFeatures.value];
  move(order, i, delta);
  draft.value.plots.nomogram.feature_order = order;
}
function featureStyle(name: string) {
  return (draft.value.plots.nomogram.features[name] ||= {
    label: "",
    color: draft.value.plots.nomogram.line_color,
    ticks: [],
    category_labels: {},
  });
}
function override(value: boolean) {
  plot.value.style = value ? clone(draft.value.common) : {};
}
function seriesOverride(model: string, value: boolean) {
  if (value)
    plot.value.series[model] = {
      ...clone(draft.value.models[model]),
      visible: true,
    };
  else delete plot.value.series[model];
}
async function validated() {
  const config = tab.value === "json" ? JSON.parse(json.value) : draft.value;
  return api("tool.prediction.plot.validate", { config });
}
async function apply(redraw: boolean) {
  busy.value = true;
  error.value = "";
  try {
    const config = await validated();
    emit("apply", config, redraw);
    emit("update:open", false);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function preset() {
  busy.value = true;
  error.value = "";
  try {
    const config = await validated();
    await api("tool.prediction.plot.save", { config });
    message.value = "已保存为第五个工具的默认图表样式。";
    notify(message.value);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function exportConfig() {
  error.value = "";
  try {
    await download(
      "预测模型图表设置.json",
      JSON.stringify(await validated(), null, 2),
    );
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function importConfig(e: Event) {
  const input = e.target as HTMLInputElement,
    f = input.files?.[0];
  input.value = "";
  if (!f) return;
  error.value = "";
  try {
    if (f.size > 1024 * 1024) throw Error("图表配置文件最多 1 MB。");
    draft.value = await api("tool.prediction.plot.validate", {
      config: JSON.parse(await f.text()),
    });
    json.value = JSON.stringify(draft.value, null, 2);
    notify("已载入图表设置，应用后生效。");
  } catch (e) {
    error.value = (e as Error).message;
  }
}
function selectOptionalStyles(names: string[]) {
  for (const feature of props.features) {
    if (
      names.includes(feature.name) &&
      !plot.value.feature_styles[feature.name]
    )
      toggleOptionalFeature(feature.name, true);
    else if (!names.includes(feature.name))
      delete plot.value.feature_styles[feature.name];
  }
}
function selectVisibleModels(names: string[]) {
  for (const model of draft.value.model_order) {
    if (!plot.value.series[model]) seriesOverride(model, true);
    plot.value.series[model].visible = names.includes(model);
  }
}
function selectModelStyles(names: string[]) {
  for (const model of draft.value.model_order) {
    if (names.includes(model) && !plot.value.series[model])
      seriesOverride(model, true);
    else if (!names.includes(model)) delete plot.value.series[model];
  }
}
function toggleOptionalFeature(name: string, value: boolean) {
  if (value)
    plot.value.feature_styles[name] = {
      label: name,
      color: tab.value === "shap" ? plot.value.bar_color : "#477eb2",
    };
  else delete plot.value.feature_styles[name];
}
function moveOptionalFeature(name: string, delta: number) {
  const order = [
    ...plot.value.feature_order.filter((n: string) =>
      props.features.some((f) => f.name === n),
    ),
    ...props.features
      .map((f) => f.name)
      .filter((n) => !plot.value.feature_order.includes(n)),
  ];
  move(order, order.indexOf(name), delta);
  plot.value.feature_order = order;
  plot.value.order = "custom";
}
function referenceNomogram() {
  const current = draft.value.plots.nomogram;
  draft.value.plots.nomogram = {
    ...clone(props.factory.plots.nomogram),
    enabled: current.enabled,
    filename: current.filename,
    title: current.title,
    note: current.note,
    feature_order: current.feature_order,
    features: Object.fromEntries(
      Object.entries(current.features || {}).map(
        ([name, value]: [string, any]) => [
          name,
          { ...value, color: "#000000" },
        ],
      ),
    ),
  };
  message.value = "已应用参考图版式；积分和风险刻度仍按本次 LR 模型计算。";
  error.value = "";
}
function referenceShap() {
  const current = draft.value.plots.shap;
  draft.value.plots.shap = {
    ...clone(props.factory.plots.shap),
    enabled: current.enabled,
    filename: current.filename,
    max_display: current.max_display,
    max_single: current.max_single,
    order: current.order,
    feature_order: clone(current.feature_order),
    feature_styles: Object.fromEntries(
      Object.entries(current.feature_styles || {}).map(
        ([name, value]: [string, any]) => [
          name,
          { ...value, color: props.factory.plots.shap.bar_color },
        ],
      ),
    ),
  };
  normalizeDraftStyles();
  message.value =
    "已应用最终 SHAP 参考脚本版式；病例、指标选择和已计算结果保持不变。";
  error.value = "";
}
function reset() {
  const extraEnabled = {
    lasso: draft.value?.plots?.lasso?.enabled,
    shap: draft.value?.plots?.shap?.enabled,
  };
  draft.value = clone(props.factory);
  normalizeDraftStyles();
  for (const name of ["lasso", "shap"] as const)
    if (extraEnabled[name] !== undefined)
      draft.value.plots[name].enabled = extraEnabled[name];
  json.value = JSON.stringify(draft.value, null, 2);
  error.value = "";
}
</script>
<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)"
    ><DialogContent
      class="sm:max-w-[1200px] h-[90vh] p-0 gap-0 overflow-hidden flex flex-col"
      ><DialogHeader class="px-6 pt-5 pb-4"
        ><DialogTitle>预测模型图表设置</DialogTitle
        ><DialogDescription
          >公共设置统一生效；单图可独立覆盖。修改外观可直接重新绘图，复用本次模型和预测概率。</DialogDescription
        ></DialogHeader
      >
      <div v-if="draft" class="plot-settings-body">
        <nav aria-label="图表设置分类">
          <Button
            v-for="t in tabs"
            :key="t.id"
            :variant="tab === t.id ? 'default' : 'outline'"
            @click="selectTab(t.id)"
            >{{ t.name }}</Button
          >
        </nav>
        <div class="plot-settings-scroll">
          <p v-if="message" role="status" class="plot-hint">{{ message }}</p>
          <p v-if="error" role="alert" class="plot-settings-error">
            {{ error }}
          </p>
          <template v-if="tab === 'common'">
            <section v-for="g in commonGroups" :key="g.title">
              <h3>{{ g.title }}</h3>
              <PredictionPlotFields :value="draft.common" :fields="g.fields" />
            </section>
            <section>
              <h3>导出格式</h3>
              <SelectionActions
                label="公共导出格式"
                :items="['png', 'pdf', 'svg']"
                v-model="draft.common.formats"
              />
              <div class="plot-format">
                <label v-for="format in ['png', 'pdf', 'svg']" :key="format"
                  ><input
                    type="checkbox"
                    :value="format"
                    v-model="draft.common.formats"
                  />{{ format.toUpperCase() }}</label
                >
              </div>
              <p>
                PNG 使用指定 DPI；PDF / SVG 为矢量图。预览使用较低
                DPI，内容与导出一致。
              </p>
              <p>
                字体可填 auto、已安装字体名称，例如 SimSun、Songti SC、Noto Sans
                CJK SC；西文字体可用 Times New Roman 或 DejaVu Serif。
              </p>
            </section>
          </template>
          <template v-else-if="tab === 'models'"
            ><p class="plot-hint">
              ROC
              和校准图中的曲线代表模型。这里统一设置模型名称、颜色和图例顺序，不改变训练结果。
            </p>
            <section v-for="(model, i) in draft.model_order" :key="model">
              <div class="plot-section-title">
                <h3>{{ Number(i) + 1 }} · {{ model }}</h3>
                <div>
                  <Button
                    variant="outline"
                    size="sm"
                    :aria-label="model + ' 上移'"
                    :disabled="i === 0"
                    @click="move(draft.model_order, Number(i), -1)"
                    >上移</Button
                  ><Button
                    variant="outline"
                    size="sm"
                    :aria-label="model + ' 下移'"
                    :disabled="i === draft.model_order.length - 1"
                    @click="move(draft.model_order, Number(i), 1)"
                    >下移</Button
                  >
                </div>
              </div>
              <PredictionPlotFields
                :value="draft.models[model]"
                :fields="seriesFields"
                :prefix="model + ' · '"
              /></section
          ></template>
          <template v-else-if="plot">
            <section v-if="tab === 'nomogram'">
              <Button variant="outline" @click="referenceNomogram"
                >应用参考图版式</Button
              >
              <p>
                全宽 Points 与 Total Points，指标轴按贡献比例绘制，Risk
                轴仅连接可见概率刻度；恢复黑色线条和参考图间距。
              </p>
            </section>
            <section v-if="tab === 'shap'">
              <Button variant="outline" @click="referenceShap"
                >应用最终 SHAP 参考版式</Button
              >
              <p>
                采用 shap_reference_style.py 的 12 × 10.4
                英寸画布、细小散点、瀑布连接线和力图引导标注；指标较多时自动增加必要空间。
              </p>
            </section>
            <section>
              <h3>画布与导出</h3>
              <PredictionPlotFields
                :value="plot"
                :fields="canvasFields"
                :prefix="tab + ' · '"
              />
            </section>
            <section>
              <h3>总标题与图注</h3>
              <PredictionPlotFields
                :value="plot"
                :fields="textFields"
                :prefix="tab + ' · '"
              />
            </section>
            <template v-if="['roc', 'calibration'].includes(tab)"
              ><section v-for="g in axisGroups" :key="g.title">
                <h3>{{ g.title }}</h3>
                <PredictionPlotFields
                  :value="plot"
                  :fields="g.fields"
                  :prefix="tab + ' · '"
                />
                <p v-if="g.title === '图例位置与排版'">
                  模板占位符：{label} 模型显示名、{model}
                  模型编号、{auc}、{ci_low}、{ci_high}、{chi2}、{p}、{brier}、{n}。面板标题可用
                  {n} 表示样本数。
                </p>
              </section>
              <section>
                <h3>本图各模型独立样式</h3>
                <SelectionActions
                  label="本图显示曲线"
                  :items="draft.model_order"
                  :model-value="
                    draft.model_order.filter(
                      (m: string) => plot.series[m]?.visible !== false,
                    )
                  "
                  @update:model-value="selectVisibleModels"
                />
                <SelectionActions
                  label="本图模型样式覆盖"
                  :items="draft.model_order"
                  :model-value="
                    draft.model_order.filter((m: string) => !!plot.series[m])
                  "
                  @update:model-value="selectModelStyles"
                />
                <div
                  v-for="model in draft.model_order"
                  :key="model"
                  class="plot-series"
                >
                  <label
                    ><Checkbox
                      :model-value="!!plot.series[model]"
                      @update:model-value="seriesOverride(model, !!$event)"
                    />覆盖 {{ model }} 的公共模型样式</label
                  ><template v-if="plot.series[model]"
                    ><label
                      ><Checkbox v-model="plot.series[model].visible" />显示
                      {{ model }} 曲线</label
                    ><PredictionPlotFields
                      :value="plot.series[model]"
                      :fields="seriesFields"
                      :prefix="tab + ' ' + model + ' · '"
                  /></template>
                </div></section
            ></template>
            <template v-else-if="tab === 'nomogram'"
              ><section v-for="g in nomogramGroups" :key="g.title">
                <h3>{{ g.title }}</h3>
                <PredictionPlotFields
                  :value="plot"
                  :fields="g.fields"
                  :prefix="'列线图 · '"
                />
              </section>
              <p class="plot-hint">
                连续指标范围与 LR
                系数取自本次训练模型。风险刻度不在实际范围内会省略；可开关“刻度不足时自动补充”。指标顺序、颜色与显示名称可在“指标顺序与颜色”中设置。
              </p></template
            >
            <template v-if="optionalPlotGroups[tab]">
              <p class="plot-hint">
                需先在“设置模型”中启用对应可选分析并运行。仅重新绘图会复用已经计算的
                LASSO / SHAP 快照。
              </p>
              <section v-for="g in optionalPlotGroups[tab]" :key="g.title">
                <h3>{{ g.title }}</h3>
                <PredictionPlotFields
                  :value="plot"
                  :fields="g.fields"
                  :prefix="tab + ' · '"
                />
              </section>
              <section>
                <h3>指标显示名称与颜色</h3>
                <SelectionActions
                  label="指标独立样式"
                  :items="features.map((f) => f.name)"
                  :model-value="
                    features
                      .filter((f) => !!plot.feature_styles[f.name])
                      .map((f) => f.name)
                  "
                  @update:model-value="selectOptionalStyles"
                />
                <p>
                  LASSO 的保留指标曲线、SHAP
                  的重要性条形可分别改色；蜂群颜色始终表示特征值高低。
                </p>
                <div v-for="f in features" :key="f.name" class="plot-series">
                  <h4>{{ f.name }}</h4>
                  <label class="plot-check"
                    ><Checkbox
                      :model-value="!!plot.feature_styles[f.name]"
                      @update:model-value="
                        toggleOptionalFeature(f.name, !!$event)
                      "
                    />单独设置此指标</label
                  ><PredictionPlotFields
                    v-if="plot.feature_styles[f.name]"
                    :value="plot.feature_styles[f.name]"
                    :fields="[
                      { key: 'label', label: '显示名称' },
                      { key: 'color', label: '指标颜色', kind: 'color' },
                    ]"
                    :prefix="tab + ' ' + f.name + ' · '"
                  />
                  <div v-if="tab === 'shap'" class="plot-section-title">
                    <span>{{ f.name }}</span
                    ><Button
                      variant="outline"
                      size="sm"
                      @click="moveOptionalFeature(f.name, -1)"
                      >上移</Button
                    ><Button
                      variant="outline"
                      size="sm"
                      @click="moveOptionalFeature(f.name, 1)"
                      >下移</Button
                    >
                  </div>
                </div>
                <p v-if="tab === 'shap'">
                  自定义顺序：{{
                    plot.feature_order.join(" → ") ||
                    "尚未指定，当前按重要性排序"
                  }}
                </p>
              </section>
            </template>
            <section>
              <h3>本图公共样式覆盖</h3>
              <label class="plot-check"
                ><Checkbox
                  :model-value="Object.keys(plot.style).length > 0"
                  @update:model-value="override(!!$event)"
                />本图独立设置 DPI、字体、背景与公共样式</label
              >
              <p>关闭时跟随公共设置；开启时复制当前公共设置，之后独立调整。</p>
              <template v-if="Object.keys(plot.style).length"
                ><div v-for="g in overrideGroups" :key="g.title">
                  <h4>{{ g.title }}</h4>
                  <PredictionPlotFields
                    :value="plot.style"
                    :fields="g.fields"
                    :prefix="tab + ' 独立 · '"
                  />
                </div>
                <SelectionActions
                  label="本图独立导出格式"
                  :items="['png', 'pdf', 'svg']"
                  v-model="plot.style.formats"
                />
                <div class="plot-format">
                  <label v-for="format in ['png', 'pdf', 'svg']" :key="format"
                    ><input
                      type="checkbox"
                      :value="format"
                      v-model="plot.style.formats"
                    />{{ format.toUpperCase() }}</label
                  >
                </div></template
              >
            </section>
          </template>
          <template v-else-if="tab === 'features'"
            ><p class="plot-hint">
              这里设置列线图的临床指标轴；指标名称只改变显示，不修改原始列名和模型。全部指标仍参与总积分计算。
            </p>
            <p v-if="!orderedFeatures.length">
              导入数据并选择预测指标后，可设置每项指标的顺序、颜色、刻度和分类显示名称。
            </p>
            <section v-for="(name, i) in orderedFeatures" :key="name">
              <div class="plot-section-title">
                <h3>{{ Number(i) + 1 }} · {{ name }}</h3>
                <div>
                  <Button
                    variant="outline"
                    size="sm"
                    :aria-label="name + ' 指标上移'"
                    :disabled="i === 0"
                    @click="moveFeature(i, -1)"
                    >上移</Button
                  ><Button
                    variant="outline"
                    size="sm"
                    :aria-label="name + ' 指标下移'"
                    :disabled="i === orderedFeatures.length - 1"
                    @click="moveFeature(i, 1)"
                    >下移</Button
                  >
                </div>
              </div>
              <PredictionPlotFields
                :value="featureStyle(name)"
                :fields="[
                  { key: 'label', label: '显示名称（留空使用原名）' },
                  { key: 'color', label: '指标颜色', kind: 'color' },
                  ...(features.find((f) => f.name === name)?.kind ===
                  'continuous'
                    ? [
                        {
                          key: 'ticks',
                          label: '自定义刻度（留空自动）',
                          kind: 'list' as const,
                        },
                      ]
                    : []),
                ]"
                :prefix="name + ' · '"
              />
              <div
                v-if="
                  features.find((f) => f.name === name)?.kind === 'categorical'
                "
                class="plot-category-labels"
              >
                <label
                  v-for="v in features.find((f) => f.name === name)?.values ||
                  []"
                  :key="v"
                  >{{ v }} 显示为<Input
                    v-model="featureStyle(name).category_labels[v]"
                    :placeholder="v"
                    :aria-label="name + ' ' + v + ' 显示名称'"
                /></label>
              </div></section
          ></template>
          <section v-else-if="tab === 'json'">
            <h3>完整图表配置</h3>
            <p>
              三种格式来自同一份当前配置。JSON
              可编辑；中文说明和提示词自动生成，复制前统一校验。复制不会应用设置或重新训练模型。
            </p>
            <div class="plot-share-controls">
              <div role="group" aria-label="配置内容格式">
                <Button
                  v-for="option in shareOptions"
                  :key="option.id"
                  :variant="shareFormat === option.id ? 'default' : 'outline'"
                  :aria-pressed="shareFormat === option.id"
                  @click="
                    shareFormat = option.id;
                    error = '';
                  "
                  >{{ option.label }}</Button
                >
              </div>
              <Button
                variant="outline"
                :disabled="busy || !!sharing.error"
                @click="copyShare"
                >复制{{
                  shareOptions.find((o) => o.id === shareFormat)?.label
                }}</Button
              >
            </div>
            <p v-if="sharing.error && !error" role="alert">
              {{ sharing.error }}
            </p>
            <textarea
              v-if="shareFormat === 'json'"
              class="plot-json"
              v-model="json"
              aria-label="完整图表配置 JSON"
              spellcheck="false"
            />
            <textarea
              v-else
              class="plot-json plot-readable"
              readonly
              :value="sharing.documents?.[shareFormat] || ''"
              :aria-label="
                shareFormat === 'description' ? '中文参数说明' : 'AI 作图提示词'
              "
              spellcheck="false"
            />
          </section>
        </div>
      </div>
      <footer class="plot-settings-footer">
        <div>
          <Button variant="outline" :disabled="busy" @click="file?.click()"
            >载入样式</Button
          ><Button variant="outline" :disabled="busy" @click="exportConfig"
            >导出样式</Button
          ><Button variant="outline" :disabled="busy" @click="preset"
            >保存为默认</Button
          ><Button variant="outline" :disabled="busy" @click="reset"
            >恢复初始样式</Button
          ><input
            ref="file"
            type="file"
            accept=".json"
            hidden
            @change="importConfig"
          />
        </div>
        <div>
          <Button
            variant="outline"
            :disabled="busy"
            @click="emit('update:open', false)"
            >取消</Button
          ><Button :disabled="busy" @click="apply(hasResult)">{{
            hasResult ? "应用并重新绘图" : "应用设置"
          }}</Button>
        </div>
      </footer>
    </DialogContent></Dialog
  >
</template>
<style scoped>
.plot-share-controls,
.plot-share-controls > div {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.plot-share-controls {
  justify-content: space-between;
  margin: 12px 0;
}
.plot-readable {
  line-height: 1.7;
}

.plot-settings-body {
  display: grid;
  grid-template-columns: 170px minmax(0, 1fr);
  min-height: 0;
  flex: 1;
  min-height: 0;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.plot-settings-body > nav {
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  background: var(--muted);
}
.plot-settings-body > nav button {
  justify-content: flex-start;
  font-size: 12px;
}
.plot-settings-scroll {
  overflow: auto;
  padding: 18px 22px;
  min-width: 0;
}
.plot-settings-scroll section {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}
.plot-settings-scroll h3 {
  font-size: 15px;
  font-weight: 650;
  margin-bottom: 15px;
}
.plot-settings-scroll h4 {
  font-size: 13px;
  font-weight: 600;
  margin: 16px 0;
}
.plot-settings-scroll p {
  font-size: 12px;
  line-height: 1.7;
  color: var(--muted-foreground);
  margin: 10px 0;
}
.plot-settings-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px 20px;
}
.plot-settings-footer > div,
.plot-section-title,
.plot-format {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.plot-section-title {
  justify-content: space-between;
  margin-bottom: 12px;
}
.plot-section-title h3 {
  margin: 0;
}
.plot-section-title > div {
  display: flex;
  gap: 6px;
}
.plot-format {
  gap: 20px;
}
.plot-format label,
.plot-check,
.plot-series > label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.plot-series {
  border-top: 1px solid var(--border);
  padding: 14px 0;
}
.plot-series > label {
  margin-bottom: 12px;
}
.plot-settings-error {
  padding: 12px;
  background: #fff0f0;
  color: #b93838 !important;
  border-radius: 7px;
}
.plot-json {
  font: 12px/1.6 monospace;
  min-height: 42vh;
  width: 100%;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  resize: vertical;
}
.plot-category-labels {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}
.plot-category-labels label {
  display: grid;
  gap: 5px;
  font-size: 12px;
}
@media (max-width: 780px) {
  .plot-settings-body {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }
  .plot-settings-body > nav {
    flex-direction: row;
    border-right: 0;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
    padding: 8px;
  }
  .plot-settings-body > nav button {
    flex-shrink: 0;
  }
  .plot-settings-scroll {
    padding: 12px;
  }
  .plot-settings-footer {
    padding: 10px;
  }
  .plot-settings-footer button {
    font-size: 11px;
    padding: 6px 8px;
  }
  .plot-category-labels {
    grid-template-columns: 1fr;
  }
}
</style>
