<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  Plus,
  Trash2,
  Play,
  Download,
  Copy,
  FileUp,
  FolderOpen,
  ArrowRight,
  Check,
  ChartNoAxesCombined,
  LoaderCircle,
  FileSpreadsheet,
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
import ConfigEditor from "@/components/ConfigEditor.vue";
import { api, notify, download, upload, openPath } from "@/lib/api";
const route = useRoute(),
  tool = computed(() => String(route.params.tool)),
  busy = ref(false),
  runningTool = ref(""),
  error = ref(""),
  step = ref(0);
const titles: Record<string, { name: string; desc: string }> = {
  category: {
    name: "自定义类别数列",
    desc: "设置每一类的数量，按随机种子生成数列。",
  },
  numeric: {
    name: "均数 / 标准差模拟数据",
    desc: "根据汇总统计近似生成模拟数值，核对实际均数与标准差。",
  },
  word: {
    name: "Word 一键生成 Excel",
    desc: "导入汇总表，核对分组与指标，再生成明确标记的模拟数据。",
  },
  shap: {
    name: "模拟数据生图",
    desc: "从模拟数据到模型解释，在同一工作流中完成。",
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
const wordConfig = ref<any>(null),
  shapConfig = ref<any>(null),
  wordResult = ref<any>(null),
  shapResult = ref<any>(null),
  wordImport = ref<any>(null),
  groupA = ref("对照组"),
  groupB = ref("中药组"),
  wordFile = ref<HTMLInputElement>(),
  configFile = ref<HTMLInputElement>();
const numericValues = computed(() => {
  const result =
    tool.value === "category" ? categoryResult.value : numericResult.value;
  if (!result) return "";
  const list = result.values.map((n: number) =>
    tool.value === "numeric" ? n.toFixed(numeric.digits) : String(n),
  );
  return format.value === "comma"
    ? list.join(", ")
    : format.value === "space"
      ? list.join(" ")
      : format.value === "r"
        ? "c(" + list.join(", ") + ")"
        : list.join("\n");
});
const histogram = computed(() => {
  if (!numericResult.value) return [];
  const a = numericResult.value.values as number[];
  const lo = Math.min(...a),
    hi = Math.max(...a);
  const bins = Array(16).fill(0);
  for (const x of a)
    bins[Math.min(15, Math.floor(((x - lo) / (hi - lo || 1)) * 16))]++;
  const max = Math.max(...bins);
  return bins.map((v) => Math.max(2, (v / max) * 100));
});
const steps = computed(() =>
  tool.value === "word"
    ? ["导入与分组", "核对资料与指标", "生成与导出"]
    : ["数据参数", "模型与 SHAP", "图表样式", "生成与导出"],
);
watch(
  tool,
  async () => {
    step.value = 0;
    error.value = "";
    try {
      if (tool.value === "word" && !wordConfig.value)
        wordConfig.value = await api("tool.word.defaults");
      if (tool.value === "shap" && !shapConfig.value)
        shapConfig.value = await api("tool.shap.defaults");
    } catch (e) {
      error.value = (e as Error).message;
    }
  },
  { immediate: true },
);
async function run(method: string, params: any, callback: (r: any) => void) {
  busy.value = true;
  runningTool.value = tool.value;
  error.value = "";
  try {
    callback(await api(method, params));
    notify("已生成模拟数据，原文件保持不变。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
    runningTool.value = "";
  }
}
async function readWord(e: Event) {
  const files = (e.target as HTMLInputElement).files;
  if (!files?.length) return;
  await run(
    "tool.word.read",
    {
      uploads: await upload(Array.from(files)),
      groups: [groupA.value, groupB.value],
    },
    (r) => {
      wordImport.value = r.imported;
      wordConfig.value = r.config;
      step.value = 1;
    },
  );
}
function csvDownload(result: any, name: string) {
  download(name, "\uFEFF" + result.csv, "text/csv;charset=utf-8");
}
function configSave() {
  download(
    tool.value + "-parameters.json",
    JSON.stringify(
      tool.value === "word" ? wordConfig.value : shapConfig.value,
      null,
      2,
    ),
    "application/json",
  );
}
async function configLoad(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (tool.value === "word") {
      if (data.version !== 1) throw Error("请选择有效的 Word 工具配置。");
      wordConfig.value = data;
    } else {
      if (data.schema_version !== 1) throw Error("请选择有效的生图配置。");
      shapConfig.value = data;
    }
    notify("配置已载入，请核对后生成。");
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function copy() {
  try {
    await navigator.clipboard.writeText(numericValues.value);
    notify("全部数值已复制。");
  } catch {
    notify("复制失败，可以从结果框中选取文字。", true);
  }
}
</script>
<template>
  <section class="tools-page">
    <PageHeading :title="current.name" :subtitle="current.desc"
      ><template v-if="tool === 'word' || tool === 'shap'"
        ><input
          ref="configFile"
          type="file"
          accept=".json"
          class="hidden"
          @change="configLoad"
        /><Button variant="outline" @click="configFile?.click()"
          ><FileUp :size="15" />载入配置</Button
        ><Button variant="outline" @click="configSave"
          ><Download :size="15" />保存配置</Button
        ></template
      ><Badge v-else variant="secondary">本机计算 · 可复现</Badge></PageHeading
    >
    <div v-if="tool === 'category' || tool === 'numeric'" class="tool-layout">
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
                variant="ghost"
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
                {{
                  categories.reduce((n, r) => n + Number(r.count || 0), 0)
                }}
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
                busy ? "正在生成…" : "生成随机数列"
              }}</Button
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
                busy ? "正在生成…" : "生成模拟数据"
              }}</Button
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
          <div
            v-if="tool === 'numeric'"
            class="histogram"
            aria-label="模拟数据分布预览"
          >
            <span
              v-for="(h, i) in histogram"
              :key="i"
              :style="{ height: h + '%' }"
            />
          </div>
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
    <template v-else
      ><div class="stepper">
        <button
          v-for="(name, index) in steps"
          :key="name"
          :class="{ selected: step === index, finished: step > index }"
          @click="step = index"
        >
          <span
            ><Check v-if="step > index" :size="12" /><template v-else>{{
              index + 1
            }}</template></span
          >{{ name }}<ArrowRight v-if="index < steps.length - 1" :size="13" />
        </button>
      </div>
      <template v-if="tool === 'word'"
        ><div v-if="step === 0" class="panel word-import-panel">
          <div class="panel-heading">
            <h2>导入 Word 汇总表</h2>
            <Badge variant="secondary">DOCX</Badge>
          </div>
          <div class="tool-form">
            <div class="two-columns">
              <div class="form-field">
                <Label for="word-group-a">第一组名称</Label
                ><Input id="word-group-a" v-model="groupA" />
              </div>
              <div class="form-field">
                <Label for="word-group-b">第二组名称</Label
                ><Input id="word-group-b" v-model="groupB" />
              </div>
            </div>
            <input
              ref="wordFile"
              type="file"
              accept=".docx"
              class="hidden"
              aria-label="导入 DOCX 汇总表"
              @change="readWord"
            />
            <div class="upload-zone">
              <FileSpreadsheet :size="30" /><strong
                >选择含有汇总表的 Word 文档</strong
              ><span>原文件保持不变；旧版 DOC 请先另存为 DOCX。</span
              ><Button :disabled="busy" @click="wordFile?.click()"
                ><FileUp :size="15" />{{
                  busy ? "正在识别…" : "选择 Word 文档"
                }}</Button
              >
            </div>
            <p class="tool-note">
              先填写文档中的分组名称，再导入。识别后逐项核对例数、指标、均数、标准差和缺失内容。
            </p>
          </div>
        </div>
        <div v-if="step === 1 && wordConfig" class="panel">
          <div class="panel-heading">
            <h2>核对基本资料与指标</h2>
            <Button size="sm" variant="outline" @click="step = 2"
              >下一步<ArrowRight :size="13"
            /></Button>
          </div>
          <div v-if="wordImport" class="import-summary">
            <Badge variant="secondary">{{ wordImport.table_count }} 张表</Badge
            ><Badge variant="secondary"
              >{{ wordImport.indicators.length }} 个分组指标</Badge
            >
            <p v-for="message in wordImport.messages" :key="message">
              {{ message }}
            </p>
          </div>
          <div class="tool-form"><ConfigEditor v-model="wordConfig" /></div>
        </div>
        <div v-if="step === 2" class="panel">
          <div class="panel-heading">
            <h2>生成与导出</h2>
            <Button
              :disabled="busy || !wordConfig"
              @click="
                run(
                  'tool.word.generate',
                  { config: wordConfig },
                  (r) => (wordResult = r),
                )
              "
              ><Play :size="14" />{{
                busy ? "正在生成…" : "生成模拟数据"
              }}</Button
            >
          </div>
          <div class="tool-note mx-5 mb-5">
            基于汇总统计生成的模拟数据，不是原始病例还原。指标独立近似匹配，不保证重现原文
            P 值。
          </div>
          <template v-if="wordResult"
            ><div class="result-toolbar">
              <Badge variant="secondary"
                >共 {{ wordResult.total }} 行 · 预览前 200 行</Badge
              ><Button
                size="sm"
                variant="outline"
                @click="
                  download(
                    wordResult.name,
                    wordResult.base64,
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    true,
                  )
                "
                ><Download :size="13" />导出完整 Excel</Button
              >
            </div>
            <div class="table-scroll results-table">
              <table class="data-table">
                <thead>
                  <tr>
                    <th v-for="c in wordResult.columns" :key="c">{{ c }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in wordResult.rows" :key="index">
                    <td v-for="(value, c) in row" :key="c">{{ value }}</td>
                  </tr>
                </tbody>
              </table>
            </div></template
          ><EmptyState
            v-else
            title="等待生成模拟病例数据"
            description="核对所有参数后，再生成并导出完整 Excel。"
          /></div></template
      ><template v-if="tool === 'shap' && shapConfig"
        ><div v-if="step < 3" class="panel">
          <div class="panel-heading">
            <h2>{{ steps[step] }}</h2>
            <Button size="sm" variant="outline" @click="step++"
              >下一步<ArrowRight :size="13"
            /></Button>
          </div>
          <div class="tool-form">
            <ConfigEditor
              v-if="step === 0"
              v-model="shapConfig.data"
            /><template v-if="step === 1"
              ><h3>逻辑回归</h3>
              <ConfigEditor v-model="shapConfig.model" />
              <h3>SHAP 解释</h3>
              <ConfigEditor v-model="shapConfig.explanation" /></template
            ><ConfigEditor v-if="step === 2" v-model="shapConfig.plots" />
          </div>
        </div>
        <div v-else class="panel">
          <div class="panel-heading">
            <h2>生成与导出</h2>
            <div class="flex gap-2">
              <Button
                variant="outline"
                :disabled="busy"
                @click="
                  run(
                    'tool.shap.run',
                    { config: shapConfig, data_only: true },
                    (r) => (shapResult = r),
                  )
                "
                >仅生成数据</Button
              ><Button
                :disabled="busy"
                @click="
                  run(
                    'tool.shap.run',
                    { config: shapConfig },
                    (r) => (shapResult = r),
                  )
                "
                ><Play :size="14" />{{
                  busy ? "正在计算与绘图…" : "生成数据并分析"
                }}</Button
              >
            </div>
          </div>
          <p class="tool-note mx-5 mb-5">
            数据为模拟值；SHAP 解释模型的
            log-odds。结果写入独立目录，不覆盖之前的输出。
          </p>
          <template v-if="shapResult"
            ><div class="result-toolbar">
              <span class="muted">{{ shapResult.folder }}</span
              ><Button
                size="sm"
                variant="outline"
                @click="openPath(shapResult.folder)"
                ><FolderOpen :size="13" />结果文件夹</Button
              >
            </div>
            <div v-if="shapResult.metrics" class="result-metrics">
              <div v-for="(value, key) in shapResult.metrics" :key="key">
                <template v-if="typeof value === 'number'"
                  ><small>{{ key }}</small
                  ><strong>{{ value.toFixed(4) }}</strong></template
                >
              </div>
            </div>
            <div class="plot-gallery">
              <div v-for="image in shapResult.images" :key="image.name">
                <img :src="image.url" :alt="image.name" />
                <div>
                  <span>{{ image.name }}</span
                  ><Button
                    size="sm"
                    variant="ghost"
                    @click="
                      download(
                        image.name,
                        image.url.split(',')[1],
                        'image/png',
                        true,
                      )
                    "
                    ><Download :size="13" />保存图表</Button
                  >
                </div>
              </div>
            </div>
            <div class="table-scroll results-table">
              <table class="data-table">
                <thead>
                  <tr>
                    <th v-for="c in shapResult.columns" :key="c">{{ c }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in shapResult.rows" :key="index">
                    <td v-for="(value, c) in row" :key="c">{{ value }}</td>
                  </tr>
                </tbody>
              </table>
            </div></template
          ><EmptyState
            v-else
            title="准备好生成结果了吗"
            description="先核对数据、模型与图表设置，再开始计算。"
          /></div></template
    ></template>
    <div v-if="busy" class="running-banner" role="status">
      <LoaderCircle :size="17" class="animate-spin" /><span
        >{{ titles[runningTool]?.name }}正在本机计算，请保持应用打开。</span
      >
    </div>
    <div v-if="error" role="alert" class="error-banner">{{ error }}</div>
  </section>
</template>
