<script setup lang="ts">
import { computed } from "vue";
import { Plus, Trash2 } from "lucide-vue-next";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import SelectField from "./SelectField.vue";
const props = withDefaults(
    defineProps<{ modelValue: any; depth?: number; exclude?: string[] }>(),
    { depth: 0, exclude: () => [] },
  ),
  emit = defineEmits<{ "update:modelValue": [value: any] }>();
const labels: Record<string, string> = {
  n_samples: "样本量",
  positive_rate: "阳性比例（0～1）",
  random_seed: "数据随机种子",
  label_name: "结局列名",
  positive_name: "阳性组名称",
  negative_name: "阴性组名称",
  id_name: "编号列名",
  id_prefix: "编号前缀",
  id_width: "编号位数",
  id_start: "起始编号",
  features: "输入特征",
  name: "名称",
  kind: "变量类型",
  positive: "阳性组",
  negative: "阴性组",
  mean: "均数",
  std: "标准差",
  sd: "标准差",
  min: "最小值",
  max: "最大值",
  transform: "数值处理",
  digits: "小数位数",
  values: "分类编码",
  positive_p: "阳性组取第二编码概率",
  negative_p: "阴性组取第二编码概率",
  test_size: "测试集比例",
  split_seed: "划分种子",
  random_state: "模型随机种子",
  solver: "求解器",
  penalty: "正则化方式",
  C: "正则化强度 C",
  max_iter: "最大迭代次数",
  tol: "收敛容差",
  class_weight: "类别权重",
  l1_ratio: "L1 混合比例",
  threshold: "分类阈值",
  background_max_samples: "SHAP 背景样本数",
  background_seed: "背景抽样种子",
  protective_feature: "保护因素特征",
  dpi: "图像 DPI",
  formats: "导出格式",
  sample_index: "解释样本索引",
  font_family: "字体",
  font_size: "字号",
  title_size: "标题字号",
  label_size: "标签字号",
  tick_size: "刻度字号",
  line_width: "线宽",
  line_style: "线型",
  grid: "网格",
  grid_color: "网格颜色",
  grid_width: "网格线宽",
  grid_style: "网格线型",
  baseline_color: "基线颜色",
  baseline_width: "基线线宽",
  baseline_style: "基线线型",
  baseline_alpha: "基线透明度",
  point_size: "散点大小",
  point_alpha: "散点透明度",
  point_color: "散点颜色",
  low_color: "低值颜色",
  high_color: "高值颜色",
  positive_color: "正向贡献颜色",
  negative_color: "负向贡献颜色",
  positive_light: "正向浅色",
  negative_light: "负向浅色",
  edge_width: "边框线宽",
  separator_width: "分隔线宽",
  bar_color: "条形颜色",
  figsize: "图像宽高（英寸）",
  plots: "单图设置",
  summary: "SHAP 摘要图",
  bar: "特征重要性",
  force: "单样本力图",
  waterfall: "单样本瀑布图",
  dependence_protective: "保护因素依赖图",
  dependence_risk: "危险因素依赖图",
  enabled: "启用图表",
  filename: "导出文件名",
  title: "图表标题",
  xlabel: "横坐标标题",
  colorbar_label: "色条标题",
  bar_height: "条形高度",
  value_format: "数值格式",
  text_rotation: "文字旋转角度",
  contribution_threshold: "贡献阈值",
  title_y: "标题纵向位置",
  content_top: "内容顶边",
  ylim: "纵轴范围",
  axis_y: "坐标轴位置",
  base_label_y: "基线标签位置",
  prediction_label_y: "预测标签位置",
  xlabel_pad: "横轴标题间距",
  feature: "展示特征（留空自动）",
  interaction_feature: "交互着色特征（留空自动）",
  seed: "随机种子",
  course_unit: "病程单位",
  groups: "分组基本资料",
  n: "例数",
  male: "男性比例（%）",
  severity: "轻、中、重比例（%）",
  effective: "有效比例（%）",
  recurrence: "复发比例（%）",
  age: "年龄区间",
  course: "病程区间",
  lower: "下限",
  upper: "上限",
  percent: "比例（%）",
  course_digits: "病程小数位",
  extent_mode: "病变范围模式",
  recurrence_scope: "复发分母",
  extent: "病变分类",
  extent_ranges: "病变数值区间",
  extent_digits: "病变小数位",
  label: "类别名称",
  indicators: "指标设置",
  group: "所属分组",
  parity: "奇偶限制",
  raw: "原始统计值",
  table: "来源表序号",
  typed_fields: "识别字段",
  include_basics: "包含基本资料",
  style: "公共图表样式",
  styles: "单独图表样式",
  layout: "布局",
  font_weight: "字重",
  confirmed: "已核对字段含义",
  labels: "类别名称",
  weights: "类别比例（%）",
  q1: "第一四分位数",
  q3: "第三四分位数",
  median: "中位数",
  aggregate_pending: "汇总规则待确认",
  from_field: "来源字段",
  positive_labels: "有效类别",
};
const options: Record<string, string[]> = {
  kind: [
    "continuous",
    "binary",
    "mean_sd",
    "quantile",
    "category",
    "gender",
    "yesno",
    "binary01",
    "derived",
    "excluded",
  ],
  transform: ["int", "round", "none"],
  solver: ["lbfgs", "liblinear", "newton-cg", "newton-cholesky", "sag", "saga"],
  penalty: ["l1", "l2", "elasticnet", "none"],
  class_weight: ["none", "balanced"],
  parity: ["any", "odd", "even"],
  extent_mode: ["blank", "category", "range"],
  recurrence_scope: ["all", "effective"],
};
const numericNull = new Set([
  "mean",
  "sd",
  "lower",
  "upper",
  "median",
  "q1",
  "q3",
]);
const keys = computed(() =>
  Object.keys(props.modelValue || {}).filter(
    (k) =>
      !["key", "schema_version", "version", "source"].includes(k) &&
      !props.exclude.includes(k),
  ),
);
const kindOptions = computed(() =>
  "key" in (props.modelValue || {})
    ? ["continuous", "binary"]
    : [
        "mean_sd",
        "quantile",
        "binary",
        "gender",
        "yesno",
        "binary01",
        "category",
        "derived",
        "excluded",
      ],
);
const nullableStrings = new Set([
  "feature",
  "interaction_feature",
  "protective_feature",
]);
const nested = (v: any) => v !== null && typeof v === "object";
function update(k: string, value: any) {
  if (nullableStrings.has(k) && value === "") value = null;
  if (
    k === "kind" &&
    ["continuous", "binary"].includes(props.modelValue.kind) &&
    ["continuous", "binary"].includes(value)
  ) {
    const next = JSON.parse(JSON.stringify(props.modelValue));
    next.kind = value;
    if (value === "binary") {
      next.values = [0, 1];
      next.positive_p = 0.6;
      next.negative_p = 0.3;
      delete next.positive;
      delete next.negative;
      delete next.transform;
      delete next.digits;
    } else {
      next.positive = { mean: 10, std: 2, min: 0, max: 30 };
      next.negative = { mean: 8, std: 2, min: 0, max: 30 };
      next.transform = "round";
      next.digits = 2;
      delete next.values;
      delete next.positive_p;
      delete next.negative_p;
    }
    emit("update:modelValue", next);
    return;
  }
  emit("update:modelValue", { ...props.modelValue, [k]: value });
}
function number(k: string, value: string) {
  update(k, value === "" ? null : Number(value));
}
function arrayValue(k: string, index: number, value: any) {
  const list = [...props.modelValue[k]];
  list[index] = value;
  update(k, list);
}
function remove(k: string, index: number) {
  update(
    k,
    props.modelValue[k].filter((_: any, i: number) => i !== index),
  );
}
function add(k: string) {
  const original = props.modelValue[k];
  let next = original.length
    ? JSON.parse(JSON.stringify(original[original.length - 1]))
    : "";
  if (next && typeof next === "object") {
    if ("name" in next) next.name = "新项目 " + (original.length + 1);
    if ("key" in next) next.key = crypto.randomUUID();
  }
  update(k, [...original, next]);
}
</script>
<template>
  <div :class="['config-editor', { 'config-nested': depth > 0 }]">
    <template v-for="key in keys" :key="key"
      ><details
        v-if="nested(modelValue[key]) && !Array.isArray(modelValue[key])"
        class="config-group"
        :open="depth === 0"
      >
        <summary>{{ labels[key] || key }}</summary>
        <ConfigEditor
          :model-value="modelValue[key]"
          :depth="depth + 1"
          @update:model-value="(v) => update(key, v)"
        />
      </details>
      <details
        v-else-if="Array.isArray(modelValue[key])"
        class="config-group config-array"
        :open="depth < 1"
      >
        <summary>
          {{ labels[key] || key }}
          <small>{{ modelValue[key].length }} 项</small>
        </summary>
        <div
          v-for="(value, index) in modelValue[key]"
          :key="index"
          class="config-array-item"
        >
          <div v-if="nested(value)" class="config-array-heading">
            <span>{{
              value.name ||
              value.label ||
              value.group ||
              "第 " + (index + 1) + " 项"
            }}</span
            ><Button
              type="button"
              variant="outline"
              size="icon"
              :aria-label="'删除 ' + (value.name || key) + ' ' + index"
              @click="remove(key, index)"
              ><Trash2 :size="13"
            /></Button>
          </div>
          <ConfigEditor
            v-if="nested(value)"
            :model-value="value"
            :depth="depth + 1"
            @update:model-value="(v) => arrayValue(key, index, v)"
          />
          <div v-else class="config-array-value">
            <Input
              :model-value="value"
              :type="typeof value === 'number' ? 'number' : 'text'"
              :aria-label="(labels[key] || key) + ' ' + (index + 1)"
              @update:model-value="
                (v) =>
                  arrayValue(
                    key,
                    index,
                    typeof value === 'number' ? Number(v) : String(v),
                  )
              "
            /><Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="删除此项"
              @click="remove(key, index)"
              ><Trash2 :size="13"
            /></Button>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          class="add-config"
          @click="add(key)"
          ><Plus :size="12" />添加一项</Button
        >
      </details>
      <div v-else class="config-field">
        <label>{{ labels[key] || key }}</label
        ><Checkbox
          v-if="typeof modelValue[key] === 'boolean'"
          :model-value="modelValue[key]"
          :aria-label="labels[key] || key"
          @update:model-value="(v) => update(key, !!v)"
        /><SelectField
          v-else-if="options[key]"
          :model-value="modelValue[key]"
          :options="key === 'kind' ? kindOptions : options[key]"
          :label="labels[key] || key"
          @update:model-value="(v) => update(key, v)"
        />
        <div
          v-else-if="
            key.includes('color') ||
            /^#[a-f0-9]{6}$/i.test(String(modelValue[key]))
          "
          class="color-field"
        >
          <input
            type="color"
            :value="modelValue[key] || '#234734'"
            :aria-label="labels[key] || key"
            @input="(e) => update(key, (e.target as HTMLInputElement).value)"
          /><Input
            :model-value="modelValue[key]"
            :aria-label="(labels[key] || key) + ' 色值'"
            @update:model-value="(v) => update(key, String(v))"
          />
        </div>
        <Input
          v-else
          :model-value="modelValue[key] ?? ''"
          :type="
            typeof modelValue[key] === 'number' || numericNull.has(key)
              ? 'number'
              : 'text'
          "
          :step="typeof modelValue[key] === 'number' ? 'any' : undefined"
          :aria-label="labels[key] || key"
          @update:model-value="
            (v) =>
              typeof modelValue[key] === 'number' || numericNull.has(key)
                ? number(key, String(v))
                : update(
                    key,
                    v === '' && modelValue[key] === null ? null : String(v),
                  )
          "
        /></div
    ></template>
  </div>
</template>
