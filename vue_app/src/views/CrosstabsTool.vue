<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { Calculator, Copy, Download, Minus, Plus, RotateCcw } from "lucide-vue-next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import PageHeading from "@/components/PageHeading.vue";
import { api, download, notify } from "@/lib/api";

const DEFAULT_TABLE = [
  [21, 50],
  [40, 116],
];
const matrix = ref<number[][]>(DEFAULT_TABLE.map((row) => [...row]));
const rowLabels = ref(["行1", "行2"]);
const columnLabels = ref(["列1", "列2"]);
const options = reactive({
  descriptive: true,
  fisher: true,
  pairwise: true,
  kappa: false,
  paired: false,
});
const result = ref<any>(null);
const busy = ref(false);
const error = ref("");

const rowCount = computed(() => matrix.value.length);
const columnCount = computed(() => matrix.value[0]?.length || 0);
const total = computed(() =>
  matrix.value.reduce((sum, row) => sum + row.reduce((r, value) => r + Number(value || 0), 0), 0),
);

function addRow() {
  const next = Array.from({ length: columnCount.value }, () => 0);
  matrix.value.push(next);
  rowLabels.value.push(`行${rowCount.value}`);
}
function removeRow() {
  if (rowCount.value <= 2) return;
  matrix.value.pop();
  rowLabels.value.pop();
}
function addColumn() {
  matrix.value.forEach((row) => row.push(0));
  columnLabels.value.push(`列${columnCount.value}`);
}
function removeColumn() {
  if (columnCount.value <= 2) return;
  matrix.value.forEach((row) => row.pop());
  columnLabels.value.pop();
}
function reset() {
  matrix.value = DEFAULT_TABLE.map((row) => [...row]);
  rowLabels.value = ["行1", "行2"];
  columnLabels.value = ["列1", "列2"];
  result.value = null;
  error.value = "";
}
function finiteCounts() {
  return matrix.value.every((row) =>
    row.every((value) => Number.isFinite(Number(value)) && Number(value) >= 0),
  );
}
async function run() {
  error.value = "";
  if (!finiteCounts() || total.value <= 0) {
    error.value = "频数必须是非负数，且总频数必须大于 0。";
    return;
  }
  busy.value = true;
  try {
    result.value = await api("tool.crosstabs.analyze", {
      table: matrix.value.map((row) => row.map((value) => Number(value || 0))),
      row_labels: rowLabels.value,
      column_labels: columnLabels.value,
      options: { ...options },
    });
    notify("列联表分析已完成。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function fmt(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : Number(value).toFixed(digits);
}
function cellText(row: number, col: number) {
  if (!result.value) return "";
  return `${result.value.table[row][col]}\n行 ${fmt(result.value.row_percent[row][col])}% · 列 ${fmt(result.value.column_percent[row][col])}%`;
}
async function copyResult() {
  if (!result.value) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2));
    notify("分析结果已复制。");
  } catch {
    notify("复制失败，请使用保存文件。", true);
  }
}
function saveResult() {
  if (!result.value) return;
  download("列联表分析结果.json", JSON.stringify(result.value, null, 2), "application/json;charset=utf-8");
}
</script>

<template>
  <section class="scientific-page crosstabs-page">
    <PageHeading title="列联表统计分析" subtitle="按照 SPSS CROSSTABS 标准分析频数列联表">
      <Badge variant="secondary">本机计算 · SPSS 口径</Badge>
    </PageHeading>

    <div class="crosstabs-grid">
      <section class="scientific-section surface">
        <div class="section-heading">
          <div>
            <h2>第一步：数据输入</h2>
            <p>输入各行各列的频数。支持非负整数或加权后的非负频数。</p>
          </div>
          <Button size="sm" variant="outline" @click="reset"><RotateCcw :size="14" />重置</Button>
        </div>
        <div class="crosstabs-actions">
          <Button size="sm" variant="outline" @click="addRow"><Plus :size="14" />添加行</Button>
          <Button size="sm" variant="outline" :disabled="rowCount <= 2" @click="removeRow"><Minus :size="14" />删除行</Button>
          <Button size="sm" variant="outline" @click="addColumn"><Plus :size="14" />添加列</Button>
          <Button size="sm" variant="outline" :disabled="columnCount <= 2" @click="removeColumn"><Minus :size="14" />删除列</Button>
        </div>
        <div class="table-scroll crosstabs-table-scroll">
          <table class="data-table editable-table crosstabs-input-table">
            <thead>
              <tr>
                <th>行 / 列</th>
                <th v-for="(label, col) in columnLabels" :key="`label-${col}`">
                  <Input v-model="columnLabels[col]" :aria-label="`列标签 ${col + 1}`" />
                </th>
                <th>行合计</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in matrix" :key="`row-${rowIndex}`">
                <th><Input v-model="rowLabels[rowIndex]" :aria-label="`行标签 ${rowIndex + 1}`" /></th>
                <td v-for="(value, colIndex) in row" :key="`${rowIndex}-${colIndex}`">
                  <Input v-model.number="matrix[rowIndex][colIndex]" type="number" min="0" step="any" :aria-label="`${rowLabels[rowIndex]} ${columnLabels[colIndex]}`" />
                </td>
                <td class="table-total">{{ row.reduce((sum, n) => sum + Number(n || 0), 0) }}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <th>列合计</th>
                <td v-for="(_, colIndex) in columnLabels" :key="`total-${colIndex}`">{{ matrix.reduce((sum, row) => sum + Number(row[colIndex] || 0), 0) }}</td>
                <td class="table-total">{{ total }}</td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div class="subsection">
          <h3>分析选项</h3>
          <div class="crosstabs-options">
            <label><Checkbox v-model="options.descriptive" />描述性统计（行 / 列百分比）</label>
            <label><Checkbox v-model="options.fisher" />Fisher 精确概率（仅 2×2）</label>
            <label><Checkbox v-model="options.pairwise" />列比例两两比较（Bonferroni）</label>
            <label><Checkbox v-model="options.kappa" />Kappa 一致性</label>
            <label><Checkbox v-model="options.paired" />配对卡方（McNemar / Bowker）</label>
          </div>
        </div>
        <p v-if="error" class="field-error">{{ error }}</p>
        <Button class="crosstabs-run" :disabled="busy" @click="run"><Calculator :size="15" />{{ busy ? "正在计算…" : "计算" }}</Button>
      </section>

      <section class="scientific-section surface crosstabs-results">
        <div class="section-heading">
          <div>
            <h2>第二步：结果输出</h2>
            <p v-if="result">总样本量 {{ result.total }}，最小期望频数 {{ fmt(result.assumption.min_expected) }}</p>
            <p v-else>输入频数后点击“计算”。</p>
          </div>
          <div v-if="result" class="heading-actions">
            <Button size="sm" variant="outline" @click="copyResult"><Copy :size="14" />复制</Button>
            <Button size="sm" variant="outline" @click="saveResult"><Download :size="14" />保存</Button>
          </div>
        </div>
        <template v-if="result">
          <div class="crosstabs-result-table table-scroll">
            <table class="data-table">
              <thead><tr><th>行百分比 / 列百分比</th><th v-for="label in result.column_labels" :key="label">{{ label }}</th><th>合计</th></tr></thead>
              <tbody>
                <tr v-for="(label, row) in result.row_labels" :key="label">
                  <th>{{ label }}</th>
                  <td v-for="(_, col) in result.column_labels" :key="`${row}-${col}`" class="crosstabs-cell"><strong>{{ result.table[row][col] }}</strong><small v-if="options.descriptive">{{ cellText(Number(row), Number(col)).split('\n')[1] }}</small></td>
                  <td>{{ result.row_totals[row] }}</td>
                </tr>
              </tbody>
              <tfoot><tr><th>合计</th><td v-for="value in result.column_totals" :key="value">{{ value }}</td><td>{{ result.total }}</td></tr></tfoot>
            </table>
          </div>

          <div class="crosstabs-test-grid">
            <div class="crosstabs-test-card"><span>Pearson 卡方</span><strong>χ² = {{ fmt(result.pearson.statistic, 3) }}</strong><small>df = {{ result.pearson.df }} · P = {{ fmt(result.pearson.p, 3) }}</small></div>
            <div class="crosstabs-test-card"><span>似然比卡方</span><strong>G² = {{ fmt(result.likelihood_ratio.statistic, 3) }}</strong><small>df = {{ result.likelihood_ratio.df }} · P = {{ fmt(result.likelihood_ratio.p, 3) }}</small></div>
            <div v-if="result.fisher.available" class="crosstabs-test-card"><span>Fisher 精确概率</span><strong>P = {{ fmt(result.fisher.p, 3) }}</strong><small>OR = {{ fmt(result.fisher.odds_ratio, 3) }}</small></div>
            <div v-if="result.yates.available" class="crosstabs-test-card"><span>Yates 连续性校正</span><strong>χ² = {{ fmt(result.yates.statistic, 3) }}</strong><small>P = {{ fmt(result.yates.p, 3) }}</small></div>
            <div v-if="result.kappa.available" class="crosstabs-test-card"><span>Cohen’s Kappa</span><strong>κ = {{ fmt(result.kappa.kappa, 3) }}</strong><small>观察一致率 {{ fmt(result.kappa.observed_agreement * 100) }}%</small></div>
            <div v-if="result.paired.available" class="crosstabs-test-card"><span>{{ result.paired.test }}</span><strong>χ² = {{ fmt(result.paired.statistic, 3) }}</strong><small>df = {{ result.paired.df }} · P = {{ fmt(result.paired.p, 3) }}</small></div>
          </div>
          <div class="tool-note">{{ result.assumption.small_expected_count }} 个单元格期望频数小于 5（{{ result.assumption.small_expected_percent }}%）。{{ result.assumption.small_expected_count ? "请结合 Fisher 精确概率或谨慎解释卡方结果。" : "满足常规 Pearson 卡方的期望频数条件。" }}</div>
          <div v-if="result.pairwise.length" class="subsection crosstabs-pairwise">
            <h3>列比例两两比较（Bonferroni 校正）</h3>
            <div class="table-scroll"><table class="data-table"><thead><tr><th>行</th><th>比较</th><th>z</th><th>校正 P 值</th><th>结论</th></tr></thead><tbody><tr v-for="pair in result.pairwise" :key="`${pair.row}-${pair.left}-${pair.right}`"><td>{{ result.row_labels[pair.row] }}</td><td>{{ result.column_labels[pair.left] }} vs {{ result.column_labels[pair.right] }}</td><td>{{ fmt(pair.z, 3) }}</td><td>{{ fmt(pair.p_bonferroni, 3) }}</td><td>{{ pair.significant ? "差异显著" : "差异不显著" }}</td></tr></tbody></table></div>
          </div>
        </template>
        <div v-else class="empty-state"><Calculator :size="28" /><strong>等待计算</strong><span>结果会显示在这里。</span></div>
      </section>
    </div>
  </section>
</template>
