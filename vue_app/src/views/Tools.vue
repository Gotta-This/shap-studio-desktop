<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import {
  Plus,
  Trash2,
  Play,
  Download,
  Copy,
  ChartNoAxesCombined,
  LoaderCircle,
  Settings2,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import PageHeading from "@/components/PageHeading.vue";
import EmptyState from "@/components/EmptyState.vue";
import SelectField from "@/components/SelectField.vue";
import DistributionChart from "@/components/DistributionChart.vue";
import { notify, download } from "@/lib/api";
import { startJob, cancelJob, jobFor, clone } from "@/lib/scientific";
const route = useRoute(),
  tool = computed(() => String(route.params.tool)),
  busy = ref(false),
  runningTool = ref(""),
  generationCopied = ref(false),
  errors = reactive<Record<string, string>>({}),
  error = computed(() => errors[tool.value] || "");
let generationCopiedTimer: ReturnType<typeof setTimeout> | undefined;
const titles: Record<string, { name: string; desc: string }> = {
  category: {
    name: "自定义类别数列",
    desc: "设置每一类的数量，按随机种子生成数列。",
  },
  numeric: {
    name: "均数 / 标准差模拟数据",
    desc: "根据汇总统计近似生成模拟数值，核对实际均数与标准差。",
  },
};
const current = computed(() => titles[tool.value] || titles.category);
const categories = ref([
    { value: 1, count: 28 },
    { value: 0, count: 93 },
  ]),
  seed = ref(12),
  categoryResult = ref<any>(null),
  numericResult = ref<any>(null),
  format = ref("line");
const numeric = reactive({
  n: 70,
  mean: 27.92,
  sd: 14.87,
  digits: 0,
  lower: null as number | null,
  upper: null as number | null,
  mode: "target",
  seed: 12,
});
const numericValues = computed(() => {
  const result =
    tool.value === "category" ? categoryResult.value : numericResult.value;
  if (!result) return "";
  const list = result.values.map((n: number) =>
    tool.value === "numeric"
      ? n.toFixed(result.params?.digits ?? 0)
      : String(n),
  );
  return format.value === "comma"
    ? list.join(", ")
    : format.value === "space"
      ? list.join(" ")
      : format.value === "r"
        ? "c(" + list.join(", ") + ")"
        : list.join("\n");
});
const categoryCounts = computed(() => {
  const counts = new Map<number, number>();
  for (const n of categoryResult.value?.values || [])
    counts.set(n, (counts.get(n) || 0) + 1);
  return [...counts].map(([value, count]) => ({ value, count }));
});
async function run(method: string, params: any, callback: (r: any) => void) {
  const kind = method === "tool.numeric" ? "numeric" : "category";
  busy.value = true;
  runningTool.value = tool.value;
  errors[kind] = "";
  try {
    const job = jobFor(kind);
    await startJob(kind, clone(params));
    if (job.error) throw Error(job.error);
    if (job.message.includes("完成")) {
      callback(job.result);
      await autoCopy(job.result, kind);
    } else notify(job.message);
  } catch (e) {
    errors[kind] = (e as Error).message;
  } finally {
    busy.value = false;
    runningTool.value = "";
  }
}
function resultText(result: any, kind: string) {
  const list = result.values.map((n: number) => kind === "numeric" ? n.toFixed(result.params?.digits ?? 0) : String(n));
  return format.value === "comma" ? list.join(", ") : format.value === "space" ? list.join(" ") : format.value === "r" ? "c(" + list.join(", ") + ")" : list.join("\n");
}
async function autoCopy(result: any, kind: string) {
  try {
    await navigator.clipboard.writeText(resultText(result, kind));
    generationCopied.value = true;
    if (generationCopiedTimer) clearTimeout(generationCopiedTimer);
    generationCopiedTimer = setTimeout(() => { generationCopied.value = false; }, 1600);
  } catch {
    errors[kind] = "数据已生成，但自动复制到剪贴板失败。";
  }
}
function csvDownload(result: any, name: string) {
  download(name, "\uFEFF" + result.csv, "text/csv;charset=utf-8");
}
async function copy() {
  try {
    await navigator.clipboard.writeText(numericValues.value);
    notify("全部数值已复制。");
  } catch {
    notify("复制失败，可以从结果框中选取文字。", true);
  }
}
onUnmounted(() => { if (generationCopiedTimer) clearTimeout(generationCopiedTimer); });
</script>
<template>
  <section class="tools-page">
    <PageHeading :title="current.name" :subtitle="current.desc"
      ><Badge variant="secondary">本机计算 · 可复现</Badge></PageHeading
    >
    <div class="tool-layout">
      <div class="panel">
        <div class="panel-heading">
          <h2>生成参数</h2>
          <Settings2 :size="16" class="muted" />
        </div>
        <div class="tool-form">
          <template v-if="tool === 'category'"
            ><div class="category-row-label">
              <span>类别数值</span><span>数量</span><span />
            </div>
            <div
              v-for="(row, index) in categories"
              :key="index"
              class="category-row"
            >
              <Input
                v-model.number="row.value"
                type="number"
                step="any"
                :aria-label="'类别数值 ' + (index + 1)"
              /><Input
                v-model.number="row.count"
                type="number"
                min="0"
                step="1"
                :aria-label="'类别数量 ' + (index + 1)"
              /><Button
                size="icon"
                variant="outline"
                :disabled="categories.length < 2"
                :aria-label="'删除类别 ' + (index + 1)"
                @click="categories.splice(index, 1)"
                ><Trash2 :size="14"
              /></Button>
            </div>
            <Button
              variant="outline"
              class="w-full"
              @click="categories.push({ value: categories.length, count: 10 })"
              ><Plus :size="14" />添加类别</Button
            >
            <div class="form-field">
              <Label for="category-seed">随机种子</Label
              ><Input
                id="category-seed"
                v-model.number="seed"
                type="number"
              /><small
                >相同设置和随机种子生成相同数列，兼容现有 R 抽样规则。</small
              >
            </div>
            <div class="generation-summary">
              <span>{{ categories.length }} 个类别</span
              ><strong
                >合计
                {{ categories.reduce((n, r) => n + Number(r.count || 0), 0) }}
                个数值</strong
              >
            </div>
            <Button
              :disabled="busy"
              @click="
                run(
                  'tool.category',
                  { rows: categories, seed },
                  (r) => (categoryResult = r),
                )
              "
              ><Play :size="14" />{{
                busy ? "正在生成…" : generationCopied ? "已自动复制" : "生成随机数列"
              }}</Button
            ><Button
              v-if="busy && runningTool === 'numeric'"
              variant="outline"
              @click="cancelJob('numeric')"
              >停止生成</Button
            ></template
          ><template v-else
            ><div class="form-field">
              <Label>生成模式</Label
              ><SelectField
                v-model="numeric.mode"
                :options="[
                  { value: 'target', label: '按均数 / 标准差近似生成' },
                  { value: 'range', label: '按上下限均匀随机生成' },
                ]"
                label="生成模式"
              />
            </div>
            <div class="two-columns">
              <div class="form-field">
                <Label for="number-n">例数</Label
                ><Input
                  id="number-n"
                  v-model.number="numeric.n"
                  type="number"
                  min="2"
                  max="5000"
                />
              </div>
              <div class="form-field">
                <Label>小数位数</Label
                ><SelectField
                  :model-value="String(numeric.digits)"
                  :options="['0', '1', '2', '3', '4']"
                  label="小数位数"
                  @update:model-value="(v) => (numeric.digits = Number(v))"
                />
              </div>
            </div>
            <div v-if="numeric.mode === 'target'" class="two-columns">
              <div class="form-field">
                <Label for="target-mean">目标均数</Label
                ><Input
                  id="target-mean"
                  v-model.number="numeric.mean"
                  type="number"
                  step="any"
                />
              </div>
              <div class="form-field">
                <Label for="target-sd">目标标准差</Label
                ><Input
                  id="target-sd"
                  v-model.number="numeric.sd"
                  type="number"
                  step="any"
                  min="0"
                />
              </div>
            </div>
            <div class="two-columns">
              <div class="form-field">
                <Label>下限（可选）</Label
                ><Input
                  :model-value="numeric.lower ?? ''"
                  type="number"
                  step="any"
                  aria-label="数值下限"
                  placeholder="不限制"
                  @update:model-value="
                    (v) => (numeric.lower = v === '' ? null : Number(v))
                  "
                />
              </div>
              <div class="form-field">
                <Label>上限（可选）</Label
                ><Input
                  :model-value="numeric.upper ?? ''"
                  type="number"
                  step="any"
                  aria-label="数值上限"
                  placeholder="不限制"
                  @update:model-value="
                    (v) => (numeric.upper = v === '' ? null : Number(v))
                  "
                />
              </div>
            </div>
            <div class="form-field">
              <Label for="numeric-seed">随机种子</Label
              ><Input
                id="numeric-seed"
                v-model.number="numeric.seed"
                type="number"
              />
            </div>
            <p class="tool-note">
              生成结果为模拟数据。均数与标准差为近似匹配，不保证正态分布。
            </p>
            <Button
              :disabled="busy"
              @click="run('tool.numeric', numeric, (r) => (numericResult = r))"
              ><Play :size="14" />{{
                busy ? "正在生成…" : generationCopied ? "已自动复制" : "生成模拟数据"
              }}</Button
            ><Button
              v-if="busy && runningTool === 'numeric'"
              variant="outline"
              @click="cancelJob('numeric')"
              >停止生成</Button
            ></template
          >
        </div>
      </div>
      <div class="panel result-panel">
        <div class="panel-heading">
          <h2>生成结果</h2>
          <Badge
            v-if="tool === 'category' ? categoryResult : numericResult"
            variant="secondary"
            >{{
              (tool === "category" ? categoryResult : numericResult).values
                .length
            }}
            个数值</Badge
          >
        </div>
        <template v-if="tool === 'category' ? categoryResult : numericResult"
          ><div class="result-metrics">
            <div>
              <small>实际均数</small
              ><strong>{{
                (tool === "category"
                  ? categoryResult
                  : numericResult
                ).mean.toFixed(4)
              }}</strong>
            </div>
            <div>
              <small>实际标准差</small
              ><strong>{{
                (tool === "category"
                  ? categoryResult
                  : numericResult
                ).sd.toFixed(4)
              }}</strong>
            </div>
          </div>
          <details v-if="tool === 'category'" class="tool-note">
            <summary>类别计数与前 10 行</summary>
            <table class="data-table">
              <thead>
                <tr>
                  <th>类别</th>
                  <th>实际数量</th>
                  <th>实际占比</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in categoryCounts" :key="c.value">
                  <td>{{ c.value }}</td>
                  <td>{{ c.count }}</td>
                  <td>
                    {{
                      ((c.count / categoryResult.values.length) * 100).toFixed(
                        1,
                      )
                    }}%
                  </td>
                </tr>
              </tbody>
            </table>
            <pre>{{
              categoryResult.values
                .slice(0, 10)
                .map((v: number, i: number) => i + 1 + "  " + v)
                .join("\n")
            }}</pre>
          </details>
          <details v-if="tool === 'numeric'" class="tool-note">
            <summary>目标与实际（上次生成参数）</summary>
            <table class="data-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>目标值</th>
                  <th>实际值</th>
                  <th>偏差</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>例数</td>
                  <td>{{ numericResult.params.n }}</td>
                  <td>{{ numericResult.values.length }}</td>
                  <td>
                    {{ numericResult.values.length - numericResult.params.n }}
                  </td>
                </tr>
                <tr>
                  <td>均数</td>
                  <td>
                    {{
                      numericResult.params.mode === "range"
                        ? "—"
                        : numericResult.params.mean
                    }}
                  </td>
                  <td>{{ numericResult.mean.toFixed(4) }}</td>
                  <td>
                    {{
                      numericResult.params.mode === "range"
                        ? "—"
                        : (
                            numericResult.mean - numericResult.params.mean
                          ).toFixed(4)
                    }}
                  </td>
                </tr>
                <tr>
                  <td>标准差</td>
                  <td>
                    {{
                      numericResult.params.mode === "range"
                        ? "—"
                        : numericResult.params.sd
                    }}
                  </td>
                  <td>{{ numericResult.sd.toFixed(4) }}</td>
                  <td>
                    {{
                      numericResult.params.mode === "range"
                        ? "—"
                        : (numericResult.sd - numericResult.params.sd).toFixed(
                            4,
                          )
                    }}
                  </td>
                </tr>
              </tbody>
            </table>
          </details>
          <p
            v-if="tool === 'numeric' && numericResult.params.mode === 'range'"
            class="tool-note"
          >
            按上下限均匀随机生成，不约束均数和标准差。
          </p>
          <DistributionChart
            v-if="tool === 'numeric'"
            :values="numericResult.values"
          />
          <div class="result-toolbar">
            <SelectField
              v-model="format"
              :options="[
                { value: 'line', label: '每行一个' },
                { value: 'comma', label: '逗号分隔' },
                { value: 'space', label: '空格分隔' },
                { value: 'r', label: 'R 向量' },
              ]"
              label="复制格式"
            /><Button size="sm" variant="outline" @click="copy"
              ><Copy :size="13" />复制</Button
            ><Button
              size="sm"
              variant="outline"
              @click="
                csvDownload(
                  tool === 'category' ? categoryResult : numericResult,
                  tool + '-simulated.csv',
                )
              "
              ><Download :size="13" />导出 CSV</Button
            >
          </div>
          <textarea
            readonly
            :value="numericValues"
            aria-label="全部生成数值"
            class="values-result"
          /></template
        ><EmptyState
          v-else
          title="等待生成第一组数据"
          description="设置左侧参数，生成后在这里查看、复制和导出。"
          ><template #icon><ChartNoAxesCombined :size="26" /></template
        ></EmptyState>
      </div>
    </div>
    <div v-if="busy" class="running-banner" role="status">
      <LoaderCircle :size="17" class="animate-spin" /><span
        >{{ titles[runningTool]?.name }}正在本机计算，请保持应用打开。</span
      >
    </div>
    <div v-if="error" role="alert" class="error-banner">{{ error }}</div>
  </section>
</template>
