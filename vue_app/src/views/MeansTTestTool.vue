<script setup lang="ts">
import { reactive, ref } from "vue";
import { Calculator, Copy, Download, RotateCcw } from "lucide-vue-next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import PageHeading from "@/components/PageHeading.vue";
import { api, download, notify } from "@/lib/api";

const group1 = reactive({ label: "第1组数据", mean: 12.47, sd: 2.37, n: 71 });
const group2 = reactive({ label: "第2组数据", mean: 11, sd: 1.92, n: 156 });
const method = ref("pooled");
const comment = ref("");
const result = ref<any>(null);
const busy = ref(false);
const error = ref("");

function reset() {
  Object.assign(group1, { label: "第1组数据", mean: 12.47, sd: 2.37, n: 71 });
  Object.assign(group2, { label: "第2组数据", mean: 11, sd: 1.92, n: 156 });
  method.value = "pooled";
  comment.value = "";
  result.value = null;
  error.value = "";
}
function fmt(value: number | null | undefined, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return Number(value).toFixed(digits);
}
function pText(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return Number(value) < 0.0001 ? "P < 0.0001" : `P = ${Number(value).toFixed(4)}`;
}
async function run() {
  error.value = "";
  if (![group1.mean, group1.sd, group1.n, group2.mean, group2.sd, group2.n].every((v) => Number.isFinite(Number(v)))) {
    error.value = "请完整填写两组均值、标准差和例数。";
    return;
  }
  busy.value = true;
  try {
    const output = await api("tool.means_ttest.analyze", {
      group1: { mean: Number(group1.mean), sd: Number(group1.sd), n: Number(group1.n) },
      group2: { mean: Number(group2.mean), sd: Number(group2.sd), n: Number(group2.n) },
      method: method.value,
      group_labels: [group1.label || "第1组", group2.label || "第2组"],
    });
    result.value = { ...output, comment: comment.value };
    notify("平均值对比已完成。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function copyResult() {
  if (!result.value) return;
  try {
    await navigator.clipboard.writeText(JSON.stringify(result.value, null, 2));
    notify("检验结果已复制。");
  } catch {
    notify("复制失败，请使用保存文件。", true);
  }
}
function saveResult() {
  if (result.value) download("平均值对比-t检验结果.json", JSON.stringify(result.value, null, 2), "application/json;charset=utf-8");
}
</script>

<template>
  <section class="scientific-page means-ttest-page">
    <PageHeading title="平均值对比（t 检验）" subtitle="根据两组汇总统计量比较两个独立样本的平均值">
      <Badge variant="secondary">本机计算 · MedCalc 口径</Badge>
    </PageHeading>

    <section class="scientific-section surface">
      <div class="section-heading">
        <div><h2>输入两组数据</h2><p>输入观察到的均值、标准差和案例数量；无需导入原始数据。</p></div>
        <Button size="sm" variant="outline" @click="reset"><RotateCcw :size="14" />重置</Button>
      </div>
      <div class="means-input-grid">
        <div class="means-group-card">
          <h3>{{ group1.label }}</h3>
          <div class="form-field"><label for="means-g1-label">组名</label><Input id="means-g1-label" v-model="group1.label" /></div>
          <div class="form-field"><label for="means-g1-mean">平均值</label><Input id="means-g1-mean" v-model.number="group1.mean" type="number" step="any" /></div>
          <div class="form-field"><label for="means-g1-sd">标准差</label><Input id="means-g1-sd" v-model.number="group1.sd" type="number" min="0" step="any" /></div>
          <div class="form-field"><label for="means-g1-n">案例数量</label><Input id="means-g1-n" v-model.number="group1.n" type="number" min="2" step="1" /></div>
        </div>
        <div class="means-group-card">
          <h3>{{ group2.label }}</h3>
          <div class="form-field"><label for="means-g2-label">组名</label><Input id="means-g2-label" v-model="group2.label" /></div>
          <div class="form-field"><label for="means-g2-mean">平均值</label><Input id="means-g2-mean" v-model.number="group2.mean" type="number" step="any" /></div>
          <div class="form-field"><label for="means-g2-sd">标准差</label><Input id="means-g2-sd" v-model.number="group2.sd" type="number" min="0" step="any" /></div>
          <div class="form-field"><label for="means-g2-n">案例数量</label><Input id="means-g2-n" v-model.number="group2.n" type="number" min="2" step="1" /></div>
        </div>
      </div>
      <div class="means-controls">
        <div class="form-field means-method"><label for="means-method">检验方法</label><select id="means-method" v-model="method"><option value="pooled">等方差 t 检验（合并标准差）</option><option value="welch">不等方差 t 检验（Welch）</option></select></div>
        <div class="form-field means-comment"><label for="means-comment">注释（可选）</label><Input id="means-comment" v-model="comment" placeholder="可填写结论或研究备注" /></div>
      </div>
      <p v-if="error" class="field-error">{{ error }}</p>
      <Button :disabled="busy" @click="run"><Calculator :size="15" />{{ busy ? "正在检验…" : "检验" }}</Button>
    </section>

    <section class="scientific-section surface means-results">
      <div class="section-heading">
        <div><h2>结果</h2><p v-if="result">比较 {{ result.group_labels[0] }} 与 {{ result.group_labels[1] }}，总例数 {{ result.total_n }}。</p><p v-else>输入数据后点击“检验”。</p></div>
        <div v-if="result" class="heading-actions"><Button size="sm" variant="outline" @click="copyResult"><Copy :size="14" />复制</Button><Button size="sm" variant="outline" @click="saveResult"><Download :size="14" />保存</Button></div>
      </div>
      <template v-if="result">
        <div class="means-summary-grid">
          <div><span>Difference</span><strong>{{ fmt(result.difference, 2) }}</strong></div>
          <div><span>Pooled Standard Deviation</span><strong>{{ result.pooled_sd === null ? "—" : fmt(result.pooled_sd, 3) }}</strong></div>
          <div><span>Standard error</span><strong>{{ fmt(result.standard_error, 3) }}</strong></div>
          <div><span>95% CI</span><strong>{{ fmt(result.ci.low, 3) }} to {{ fmt(result.ci.high, 3) }}</strong></div>
          <div><span>Test statistic t</span><strong>{{ fmt(result.t, 3) }}</strong></div>
          <div><span>DF</span><strong>{{ fmt(result.df, 3) }}</strong></div>
          <div><span>Significance level</span><strong>{{ pText(result.p) }}</strong></div>
        </div>
        <div class="tool-note">{{ result.method === "pooled" ? "采用等方差独立样本 t 检验，标准误使用合并标准差。" : "采用 Welch 不等方差独立样本 t 检验，自由度使用 Welch–Satterthwaite 近似。" }} 两组差值按“第2组 − 第1组”计算，与 MedCalc 输出方向一致。</div>
        <div class="means-assumption"><span>假设：两组样本相互独立；{{ result.assumptions.equal_variances ? "两组总体方差相等。" : "不要求两组总体方差相等。" }}</span><span v-if="result.comment">注释：{{ result.comment }}</span></div>
      </template>
      <div v-else class="empty-state"><Calculator :size="28" /><strong>等待检验</strong><span>结果会显示在这里。</span></div>
    </section>
  </section>
</template>
