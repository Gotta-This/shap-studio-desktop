<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import PredictionPlotSettings from "@/components/PredictionPlotSettings.vue";
import plotDefaults from "../../python/prediction_plot_defaults.json";
import DocumentDrop from "@/components/DocumentDrop.vue";
import {
  documentError,
  documentPayload,
  type ImportDocument,
} from "@/lib/documentImport";
import PageHeading from "@/components/PageHeading.vue";
import NumberField from "@/components/NumberField.vue";
import SelectField from "@/components/SelectField.vue";
import { api, download, notify } from "@/lib/api";
import { jobFor, startJob, cancelJob, clone } from "@/lib/scientific";
const file = ref<HTMLInputElement>(),
  data = ref<any>(null),
  busy = ref(false),
  error = ref(""),
  step = ref(0);
const idColumn = ref("编号"),
  target = ref("分组"),
  positive = ref(""),
  features = ref<any[]>([]);
const splitMode = ref("ratio"),
  trainRatio = ref(0.7),
  trainCount = ref(233),
  seed = ref(20261102),
  threshold = ref(0.5);
const optional = ref<any>({
  lasso: {
    enabled: false,
    lambda_min: 0.0001,
    lambda_max: 1,
    lambda_count: 24,
    rule: "min",
    max_features: 10,
    max_iter: 10000,
    tol: 0.0001,
  },
  shap: {
    enabled: false,
    model: "XGB",
    dataset: "validation",
    max_samples: 500,
    case_id: "",
  },
});
watch(
  () => optional.value.lasso.enabled,
  (enabled) => {
    plotConfig.value.plots.lasso.enabled = enabled;
  },
);
watch(
  () => optional.value.shap.enabled,
  (enabled) => {
    plotConfig.value.plots.shap.enabled = enabled;
  },
);
const models = ref(["LR", "RF", "XGB", "SVM"]),
  grids = ref(""),
  advanced = ref(false),
  selectedImage = ref(0),
  exporting = ref(false);
const plotConfig = ref<any>(clone(plotDefaults)),
  plotSettingsOpen = ref(false),
  styleLoading = ref(true);
onMounted(async () => {
  try {
    const stored = await api("tool.prediction.plot.defaults");
    plotConfig.value = stored.config;
  } catch (e) {
    notify(
      "默认图表样式读取失败，已使用初始样式：" + (e as Error).message,
      true,
    );
  } finally {
    styleLoading.value = false;
  }
});
const styleJob = jobFor("prediction-style");
const job = jobFor("prediction"),
  result = computed(() => job.result),
  locked = computed(() => busy.value || job.busy || styleJob.busy);
const columns = computed(
  () => data.value?.columns.map((c: any) => c.name) || [],
);
const levels = computed(
  () =>
    data.value?.columns.find((c: any) => c.name === target.value)?.values || [],
);
const available = computed(() =>
  features.value.filter(
    (f) => f.name !== idColumn.value && f.name !== target.value,
  ),
);
const selected = computed(() => available.value.filter((f) => f.selected));
const count = computed(() =>
  splitMode.value === "count"
    ? Number(trainCount.value)
    : Math.floor((data.value?.rows || 0) * Number(trainRatio.value)),
);
const labels = ["导入数据", "核对变量", "设置模型", "运行分析", "结果与导出"];
const metricLabels: Record<string, string> = {
  auc: "AUC",
  accuracy: "准确率",
  sensitivity: "灵敏度",
  specificity: "特异度",
  ppv: "PPV",
  npv: "NPV",
  f1: "F1",
  brier: "Brier",
  HL_chi2: "H-L χ²",
  HL_P: "H-L P",
};
watch(target, () => {
  positive.value = levels.value.includes("1")
    ? "1"
    : levels.value[levels.value.length - 1] || "";
});
function applyData(value: any) {
  data.value = value;
  features.value = clone(value.columns);
  idColumn.value = value.columns.some((c: any) => c.name === "编号")
    ? "编号"
    : value.columns[0]?.name;
  target.value = value.columns.some((c: any) => c.name === "分组")
    ? "分组"
    : value.columns[1]?.name;
  positive.value = levels.value.includes("1")
    ? "1"
    : levels.value[levels.value.length - 1] || "";
  grids.value = JSON.stringify(value.grids, null, 2);
  job.result = null;
  job.error = "";
  error.value = "";
  step.value = 1;
}
async function importFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const f = input.files?.[0];
  input.value = "";
  if (f) await importDocument(f);
}
async function importDocument(f: ImportDocument) {
  if (locked.value) {
    notify("请等待当前任务完成后再导入。", true);
    return;
  }
  const problem = documentError([f], ["xlsx", "csv"]);
  if (problem) {
    notify(problem, true);
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    applyData(await api("tool.prediction.inspect", await documentPayload(f)));
    notify("已导入，请核对结局与指标。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function changeSheet(sheet: any) {
  busy.value = true;
  error.value = "";
  try {
    applyData(
      await api("tool.prediction.inspect", { dataset: data.value.id, sheet }),
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function run() {
  error.value = "";
  styleJob.error = "";
  try {
    if (!selected.value.length) throw new Error("请至少选择一个预测指标。");
    if (levels.value.length !== 2)
      throw new Error("请选择恰好包含两类的结局列。");
    const grid = JSON.parse(grids.value);
    const params = {
      dataset: data.value.id,
      sheet: data.value.sheet,
      id_column: idColumn.value,
      target: target.value,
      positive: positive.value,
      features: selected.value.map((f) => ({ name: f.name, kind: f.kind })),
      split_mode: splitMode.value,
      train_ratio: Number(trainRatio.value),
      train_count: Number(trainCount.value),
      seed: Number(seed.value),
      threshold: Number(threshold.value),
      models: models.value,
      grids: grid,
      plot_config: clone(plotConfig.value),
      optional: clone(optional.value),
    };
    step.value = 3;
    job.result = null;
    await startJob("prediction", params);
    if (job.result) {
      selectedImage.value = 0;
      step.value = 4;
      notify("预测模型分析完成。");
    }
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function save(format: string) {
  exporting.value = true;
  error.value = "";
  try {
    const r = await api("tool.prediction.export", {
      id: result.value.id,
      format,
    });
    await download(r.name, r.content, "application/octet-stream", true);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    exporting.value = false;
  }
}
async function redraw() {
  if (!result.value || locked.value) return;
  styleJob.result = null;
  await startJob(
    "prediction_plot",
    { id: result.value.id, plot_config: clone(plotConfig.value) },
    "prediction-style",
  );
  if (styleJob.result && !styleJob.error) {
    job.result = styleJob.result;
    selectedImage.value = 0;
    plotConfig.value = clone(styleJob.result.plot_config);
    notify("已重新绘图，模型与统计结果保持一致。");
  }
}
async function applyPlotSettings(config: any, redrawNow: boolean) {
  plotConfig.value = config;
  if (redrawNow) await redraw();
}
const plotFeatures = computed(
  () =>
    result.value?.plot_features ||
    selected.value.map((f) => ({
      name: f.name,
      kind: f.kind,
      values: f.values,
    })),
);
function number(v: any) {
  return v == null ? "—" : Number(v).toFixed(3);
}
</script>
<template>
  <DocumentDrop
    class="prediction-tool"
    route="/tools/prediction"
    :extensions="['xlsx', 'csv']"
    label="Excel / CSV 数据"
    :disabled="locked"
    @import="importDocument"
  >
    <PageHeading
      title="临床二分类预测模型分析"
      subtitle="导入病例级数据，比较四类模型，生成 ROC、校准图与 LR 列线图 · 可拖入 XLSX / CSV"
    >
      <Button
        variant="outline"
        :disabled="locked || styleLoading"
        @click="plotSettingsOpen = true"
        >图表设置</Button
      >
      <Button variant="outline" :disabled="locked" @click="file?.click()">{{
        data ? "重新导入" : "导入 Excel / CSV"
      }}</Button>
      <input
        ref="file"
        type="file"
        aria-label="导入预测数据"
        accept=".xlsx,.csv"
        hidden
        @change="importFile"
      />
    </PageHeading>
    <nav class="prediction-steps" aria-label="分析步骤">
      <Button
        v-for="(label, i) in labels"
        :key="label"
        :variant="step === i ? 'default' : 'outline'"
        :disabled="locked || (!data && i > 0) || (i === 4 && !result)"
        @click="step = i"
        >{{ i + 1 }} · {{ label }}</Button
      >
    </nav>
    <p
      v-if="error || job.error || styleJob.error"
      role="alert"
      class="prediction-error"
    >
      {{ error || job.error || styleJob.error }}
    </p>
    <p v-if="busy" role="status">正在读取并检查数据…</p>
    <section v-if="step === 0" class="panel prediction-panel">
      <h2>一行一名病例，一列一个指标</h2>
      <p>
        支持 XLSX /
        CSV。编号用于核对病例，分组表示要预测的二分类结局，其他列为候选指标。
      </p>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>编号</th>
              <th>分组</th>
              <th>年龄</th>
              <th>白蛋白</th>
              <th>是否吸烟</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>001</td>
              <td>1</td>
              <td>65</td>
              <td>32</td>
              <td>是</td>
            </tr>
            <tr>
              <td>002</td>
              <td>0</td>
              <td>48</td>
              <td>41</td>
              <td>否</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="prediction-note">
        可以映射不同列名。分组若是治疗组／对照组，请另外选择真正要预测的结局列。
      </p>
      <Button :disabled="locked" @click="file?.click()">选择数据文件</Button>
    </section>
    <template v-if="data">
      <div class="prediction-source">
        <strong>{{ data.name }}</strong
        ><span
          >{{ data.rows }} 例 · {{ data.columns.length }} 列 · 已选
          {{ selected.length }} 项指标</span
        ><SelectField
          v-if="data.sheets.length > 1"
          aria-label="工作表"
          :model-value="data.sheet"
          :options="data.sheets"
          :disabled="locked"
          @update:model-value="changeSheet"
        />
      </div>
      <section v-if="step === 1" class="panel prediction-panel">
        <h2>确认结局与预测指标</h2>
        <div class="prediction-grid">
          <label
            >编号列<SelectField
              v-model="idColumn"
              :options="columns"
              :disabled="locked" /></label
          ><label
            >结局列<SelectField
              v-model="target"
              :options="columns"
              :disabled="locked" /></label
          ><label
            >阳性结局（编码为 1）<SelectField
              v-model="positive"
              :options="levels"
              :disabled="locked"
          /></label>
        </div>
        <p v-if="levels.length !== 2" class="prediction-error">
          当前结局列有 {{ levels.length }} 类，需要恰好两类。
        </p>
        <p class="prediction-note">
          取消不应参与预测的列，例如结局发生后的检查、其他结局或身份信息。自动识别的变量类型可修改；缺失指标在训练折内填补。
        </p>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>使用</th>
                <th>指标名</th>
                <th>变量类型</th>
                <th>缺失数</th>
                <th>不同取值数</th>
                <th>取值示例</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in available" :key="f.name">
                <td>
                  <Checkbox
                    v-model="f.selected"
                    :aria-label="'使用 ' + f.name"
                    :disabled="locked"
                  />
                </td>
                <td>{{ f.name }}</td>
                <td>
                  <SelectField
                    v-model="f.kind"
                    :options="[
                      { value: 'continuous', label: '连续数值' },
                      { value: 'categorical', label: '分类变量' },
                    ]"
                    :aria-label="f.name + ' 类型'"
                    :disabled="locked"
                  />
                </td>
                <td>{{ f.missing }}</td>
                <td>{{ f.unique }}</td>
                <td>{{ f.values.slice(0, 5).join("、") }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <details class="prediction-preview">
          <summary>查看前 8 行原始数据</summary>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th v-for="c in columns" :key="c">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, i) in data.preview" :key="i">
                  <td v-for="(value, j) in row" :key="j">
                    {{ value ?? "缺失" }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
        <div class="prediction-actions">
          <Button
            :disabled="
              !selected.length || levels.length !== 2 || idColumn === target
            "
            @click="step = 2"
            >下一步：设置模型</Button
          >
        </div>
      </section>
      <section v-if="step === 2" class="panel prediction-panel">
        <h2>划分数据与模型设置</h2>
        <div class="prediction-grid">
          <label
            >划分方式<SelectField
              v-model="splitMode"
              :options="[
                { value: 'ratio', label: '按训练比例' },
                { value: 'count', label: '指定训练例数' },
              ]" /></label
          ><label v-if="splitMode === 'ratio'"
            >训练比例<Input
              v-model="trainRatio"
              type="number"
              min="0.5"
              max="0.9"
              step="0.05" /></label
          ><label v-else
            >训练例数<Input
              v-model="trainCount"
              type="number"
              min="5"
              :max="data.rows - 2" /></label
          ><label
            >随机种子<Input
              v-model="seed"
              type="number"
              min="0"
              max="4294967295" /></label
          ><label
            >分类阈值<Input
              v-model="threshold"
              type="number"
              min="0.01"
              max="0.99"
              step="0.01"
          /></label>
        </div>
        <p class="prediction-note">
          预计训练 {{ count }} 例／验证 {{ data.rows - count }} 例（训练占
          {{
            ((count / data.rows) * 100).toFixed(1)
          }}%）。按结局分层随机划分，训练集内进行分层 5 折交叉验证，以 AUC
          网格搜索选参。
        </p>
        <div class="prediction-models">
          <label v-for="m in ['LR', 'RF', 'XGB', 'SVM']" :key="m"
            ><input type="checkbox" :value="m" v-model="models" />
            {{
              (
                {
                  LR: "Logistic 回归",
                  RF: "随机森林",
                  XGB: "XGBoost",
                  SVM: "支持向量机",
                } as any
              )[m]
            }}（{{ m }}）</label
          >
        </div>
        <p class="prediction-note">
          连续变量中位数填补并标准化，分类变量众数填补并独热编码；全部处理仅在训练折拟合。训练集每类至少
          5 例。未选 LR 时不生成列线图。
        </p>
        <section class="prediction-optionals">
          <h3>可选分析</h3>
          <p class="prediction-note">
            默认关闭。LASSO 仅在训练集上诊断；SHAP
            解释本次已拟合模型。勾选后不会自动改变四模型的输入指标。
          </p>
          <label class="prediction-optional-check"
            ><Checkbox
              v-model="optional.lasso.enabled"
              aria-label="启用 LASSO 筛选诊断"
            />启用 LASSO 筛选诊断</label
          >
          <div v-if="optional.lasso.enabled" class="prediction-grid">
            <NumberField
              v-model="optional.lasso.lambda_min"
              label="λ 下限"
              :min="0.0000001"
              :max="10"
            /><NumberField
              v-model="optional.lasso.lambda_max"
              label="λ 上限"
              :min="0.000001"
              :max="100"
            /><NumberField
              v-model="optional.lasso.lambda_count"
              label="λ 网格数量"
              :integer="true"
              :min="8"
              :max="260"
            /><label
              >保留指标建议规则<SelectField
                v-model="optional.lasso.rule"
                label="LASSO 建议规则"
                :options="[
                  { value: 'min', label: '交叉验证误差最小' },
                  { value: '1se', label: '一个标准误规则' },
                  { value: 'count', label: '最多保留指定数量' },
                ]" /></label
            ><NumberField
              v-if="optional.lasso.rule === 'count'"
              v-model="optional.lasso.max_features"
              label="最多保留指标数"
              :integer="true"
              :min="1"
              :max="60"
            /><NumberField
              v-model="optional.lasso.max_iter"
              label="LASSO 最大迭代数"
              :integer="true"
              :min="100"
              :max="50000"
            /><NumberField
              v-model="optional.lasso.tol"
              label="LASSO 收敛容差"
              :min="0.0000001"
              :max="0.01"
            />
          </div>
          <label class="prediction-optional-check"
            ><Checkbox
              v-model="optional.shap.enabled"
              aria-label="启用 SHAP 模型解释"
            />启用 SHAP 模型解释</label
          >
          <div v-if="optional.shap.enabled" class="prediction-grid">
            <label
              >解释模型<SelectField
                v-model="optional.shap.model"
                label="SHAP 解释模型"
                :options="['XGB', 'RF', 'LR']" /></label
            ><label
              >汇总图样本范围<SelectField
                v-model="optional.shap.dataset"
                label="SHAP 样本范围"
                :options="[
                  { value: 'validation', label: '验证集' },
                  { value: 'train', label: '训练集' },
                  { value: 'all', label: '全量数据' },
                ]" /></label
            ><NumberField
              v-model="optional.shap.max_samples"
              label="SHAP 最多解释样本数"
              :integer="true"
              :min="10"
              :max="500"
            /><label
              >单病例编号<Input
                v-model="optional.shap.case_id"
                aria-label="SHAP 单病例编号"
                placeholder="留空使用首个验证病例"
            /></label>
          </div>
          <p v-if="optional.shap.enabled" class="prediction-note">
            需同时勾选所解释的模型。XGB / LR 图使用对数优势，RF
            图使用概率贡献；分类哑变量贡献按原始指标相加。全量汇总包含训练病例，会在图注中注明。
          </p>
          <Button
            v-if="optional.lasso.enabled || optional.shap.enabled"
            variant="outline"
            @click="plotSettingsOpen = true"
            >配置 LASSO / SHAP 图件样式</Button
          >
        </section>
        <Button variant="outline" @click="advanced = !advanced"
          >{{ advanced ? "收起" : "编辑" }}超参数网格</Button
        >
        <label v-if="advanced" class="prediction-grid-editor"
          >参数取值采用 JSON 数组；每模型最多 50 组组合<textarea
            v-model="grids"
            rows="16"
            aria-label="超参数网格"
            spellcheck="false"
          />
        </label>
        <div class="prediction-actions">
          <Button variant="outline" @click="step = 1">返回核对</Button
          ><Button :disabled="!models.length || locked" @click="run"
            >开始分析</Button
          >
        </div>
      </section>
      <section
        v-if="step === 3"
        class="panel prediction-panel"
        aria-live="polite"
      >
        <h2>{{ job.busy ? "正在本机计算" : "分析任务" }}</h2>
        <p>{{ job.message || "准备就绪，点击开始分析。" }}</p>
        <p class="prediction-note">
          模型依次训练，完成后生成高清图表与结果表。数据不会上传到网络。
        </p>
        <div class="prediction-actions">
          <Button
            v-if="job.busy"
            variant="outline"
            :disabled="job.cancelRequested"
            @click="cancelJob('prediction')"
            >{{ job.cancelRequested ? "正在取消…" : "取消分析" }}</Button
          ><Button v-else @click="step = 2">返回设置</Button>
        </div>
      </section>
      <section v-if="step === 4 && result" class="prediction-results">
        <div v-if="styleJob.busy" class="prediction-note" role="status">
          {{ styleJob.message }}
          <Button
            variant="outline"
            size="sm"
            :disabled="styleJob.cancelRequested"
            @click="cancelJob('prediction-style')"
            >取消重新绘图</Button
          >
        </div>
        <div class="panel prediction-panel">
          <div class="prediction-result-heading">
            <div>
              <h2>分析完成</h2>
              <p>
                {{ result.source }} · 阳性结局：{{ result.positive }} ·
                分类阈值：{{ result.threshold }}
              </p>
              <p>
                训练 {{ result.split.train }} 例／验证
                {{ result.split.validation }} 例，实际比例
                {{ (result.split.train_ratio * 100).toFixed(1) }}%／{{
                  ((1 - result.split.train_ratio) * 100).toFixed(1)
                }}%
              </p>
            </div>
            <div class="prediction-actions">
              <Button variant="outline" :disabled="locked" @click="redraw"
                >仅重新绘图</Button
              >
              <Button
                variant="outline"
                :disabled="exporting || locked"
                @click="save('xlsx')"
                >导出结果 Excel</Button
              ><Button :disabled="exporting || locked" @click="save('zip')"
                >导出完整结果 ZIP</Button
              >
            </div>
          </div>
        </div>
        <div class="panel prediction-panel">
          <h2>模型性能</h2>
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>数据集</th>
                  <th>例数／阳性</th>
                  <th v-for="(label, key) in metricLabels" :key="key">
                    {{ label }}
                  </th>
                  <th>AUC 95%CI</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in result.metrics" :key="r.model + r.dataset">
                  <td>
                    <strong>{{ r.model }}</strong>
                  </td>
                  <td>{{ r.dataset }}</td>
                  <td>{{ r.n }}／{{ r.events }}</td>
                  <td v-for="(_, key) in metricLabels" :key="key">
                    {{
                      key === "HL_P" && r[key] != null && r[key] < 0.001
                        ? "<0.001"
                        : number(r[key])
                    }}
                  </td>
                  <td>{{ number(r.ci_low) }}–{{ number(r.ci_high) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="panel prediction-panel">
          <div class="prediction-actions">
            <Button
              v-for="(image, i) in result.images"
              :key="image.name"
              :variant="selectedImage === i ? 'default' : 'outline'"
              @click="selectedImage = Number(i)"
              >{{ image.name }}</Button
            >
          </div>
          <img
            v-if="result.images[selectedImage]"
            class="prediction-chart"
            :src="result.images[selectedImage].url"
            :alt="result.images[selectedImage].name"
          />
          <p class="prediction-note">
            当前图：{{ result.images[selectedImage]?.width_inches || "—" }} ×
            {{ result.images[selectedImage]?.height_inches || "—" }} 英寸；预览
            {{ result.images[selectedImage]?.preview_dpi || 110 }} DPI。
            <template
              v-if="result.images[selectedImage]?.formats?.includes('png')"
              >PNG 实际导出 {{ result.images[selectedImage]?.dpi }} DPI<span
                v-if="
                  result.images[selectedImage]?.dpi <
                  result.images[selectedImage]?.requested_dpi
                "
                >（画布较大，已从
                {{ result.images[selectedImage]?.requested_dpi }} DPI
                自动调整）</span
              >。</template
            >
            公共导出 DPI 为 {{ result.plot_config?.common.dpi || 650 }}；PDF /
            SVG 保持矢量输出，完整 ZIP 同时记录实际导出参数。
          </p>
        </div>
        <div
          v-if="result.optional?.lasso || result.optional?.shap"
          class="panel prediction-panel"
        >
          <h2>可选分析结果</h2>
          <template v-if="result.optional?.lasso"
            ><h3>LASSO 筛选建议</h3>
            <p>
              训练 {{ result.optional.lasso.train_n }} 例 · λ={{
                Number(result.optional.lasso.lambda_selected).toPrecision(5)
              }}
              · 规则 {{ result.optional.lasso.rule }} · 建议保留
              {{ result.optional.lasso.selected_features.length }} 项
            </p>
            <p>
              {{
                result.optional.lasso.selected_features.join("、") ||
                "所选规则未保留指标；四模型原输入未改变。"
              }}
            </p></template
          ><template v-if="result.optional?.shap"
            ><h3>{{ result.optional.shap.model }} · SHAP 解释</h3>
            <p>
              实际汇总 {{ result.optional.shap.sample_n }} 例 · 单病例编号
              {{ result.optional.shap.case.id }}（{{
                result.optional.shap.case.dataset
              }}） · 预测概率
              {{ (result.optional.shap.case.probability * 100).toFixed(1) }}%
            </p>
            <p>
              加和校验最大误差：{{
                Number(result.optional.shap.max_additivity_error).toExponential(
                  2,
                )
              }}。贡献单位：{{
                result.optional.shap.unit === "log_odds"
                  ? "对数优势"
                  : "概率贡献"
              }}。
            </p></template
          >
        </div>
        <div class="panel prediction-panel">
          <h2>分析记录与说明</h2>
          <p v-for="(v, m) in result.best" :key="m">
            {{ m }}：交叉验证 AUC {{ number((v as any).cv_auc) }} ·
            {{ JSON.stringify((v as any).params) }}
          </p>
          <ul>
            <li v-for="note in result.warnings" :key="note">{{ note }}</li>
          </ul>
        </div>
      </section>
    </template>
    <PredictionPlotSettings
      :open="plotSettingsOpen"
      :config="plotConfig"
      :factory="plotDefaults"
      :features="plotFeatures"
      :has-result="!!result"
      @update:open="plotSettingsOpen = $event"
      @apply="applyPlotSettings"
    />
  </DocumentDrop>
</template>
<style scoped>
.prediction-steps,
.prediction-actions,
.prediction-models,
.prediction-source {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.prediction-steps {
  margin-bottom: 18px;
}
.prediction-panel {
  padding: 20px;
  margin-bottom: 18px;
}
.prediction-panel h2 {
  font-size: 17px;
  font-weight: 650;
  margin-bottom: 12px;
}
.prediction-panel p {
  font-size: 13px;
  line-height: 1.7;
  margin-bottom: 12px;
}
.prediction-source {
  padding: 10px 0 18px;
  font-size: 13px;
}
.prediction-source span {
  color: var(--muted-foreground);
}
.prediction-source :deep(button) {
  max-width: 240px;
}
.prediction-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin: 16px 0;
}
.prediction-grid label {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 13px;
}
.prediction-note {
  background: var(--muted);
  border-radius: 8px;
  padding: 12px;
  color: var(--muted-foreground);
}
.prediction-actions {
  margin-top: 16px;
}
.prediction-models {
  gap: 20px;
  padding: 14px 0;
}
.prediction-models label {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.prediction-models input {
  accent-color: var(--primary);
}
.prediction-error {
  color: #b93838;
  background: #fff0f0;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 16px;
}
.prediction-grid-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12px;
  margin-top: 12px;
}
.prediction-grid-editor textarea {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  font-family: monospace;
  width: 100%;
}
.prediction-tool .data-table td {
  padding: 9px 12px;
}
.prediction-tool .data-table th {
  padding: 10px 12px;
}
.prediction-tool .data-table {
  min-width: 740px;
}
.prediction-chart {
  width: 100%;
  height: auto;
  margin: 16px 0;
}
.prediction-result-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.prediction-results ul {
  font-size: 13px;
  line-height: 1.9;
  padding-left: 20px;
  list-style: disc;
}
@media (max-width: 1000px) {
  .prediction-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .prediction-grid {
    grid-template-columns: 1fr;
  }
  .prediction-panel {
    padding: 14px;
  }
  .prediction-steps {
    gap: 6px;
  }
  .prediction-steps button {
    font-size: 11px;
  }
}
</style>

<style scoped>
.prediction-optionals {
  padding: 16px;
  margin: 16px 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fbfdfb;
}
.prediction-optionals h3 {
  font-size: 14px;
  font-weight: 650;
  margin-bottom: 12px;
}
.prediction-optional-check {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin: 14px 0;
}
</style>
