<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
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
import PageHeading from "@/components/PageHeading.vue";
import SelectField from "@/components/SelectField.vue";
import NumberField from "@/components/NumberField.vue";
import ConfigEditor from "@/components/ConfigEditor.vue";
import { api, download, openPath, notify, desktop } from "@/lib/api";
import {
  clone,
  plotNames,
  jobFor,
  startJob,
  cancelJob,
} from "@/lib/scientific";
const config = ref<any>(null),
  defaults = ref<any>(null),
  tab = ref(0),
  dialog = ref(""),
  error = ref(""),
  style = ref("common"),
  resultTab = ref("figures"),
  table = ref<any>(null),
  page = ref(0),
  image = ref(""),
  zoom = ref(false),
  output = ref(""),
  copyTo = ref(""),
  exports = ref(["data", "figures", "config", "reports"]),
  file = ref<HTMLInputElement>(),
  job = jobFor("shap"),
  previewJob = jobFor("shap-preview");
const continuous = computed(
    () =>
      config.value?.data.features.filter((f: any) => f.kind === "continuous") ||
      [],
  ),
  binary = computed(
    () =>
      config.value?.data.features.filter((f: any) => f.kind === "binary") || [],
  ),
  featureNames = computed(() => [
    { value: "", label: "自动选择" },
    ...(config.value?.data.features || []).map((f: any) => f.name),
  ]),
  currentStyle = computed(() =>
    style.value === "common"
      ? config.value.plots.common
      : config.value.plots.plots[style.value],
  ),
  effectiveStyle = computed(() => ({
    ...config.value?.plots.common,
    ...(style.value === "common" ? {} : currentStyle.value),
  })),
  result = computed(() => job.result),
  images = computed(() => result.value?.images || []),
  selectedImage = computed(
    () =>
      images.value.find((x: any) => x.name === image.value) || images.value[0],
  ),
  previewImage = computed(
    () =>
      previewJob.result?.images?.find((x: any) =>
        x.name.includes(config.value.plots.plots[style.value]?.filename),
      ) || previewJob.result?.images?.[0],
  ),
  allBusy = computed(() => job.busy || previewJob.busy);
const mainStyleKeys = [
    "font_size",
    "title_size",
    "label_size",
    "tick_size",
    "line_width",
    "point_size",
  ],
  colorKeys = [
    "background",
    "text_color",
    "positive_color",
    "negative_color",
    "point_color",
    "bar_color",
  ],
  styleLabels: Record<string, string> = {
    font_size: "字号",
    title_size: "标题字号",
    label_size: "标签字号",
    tick_size: "刻度字号",
    line_width: "线宽",
    point_size: "散点大小",
    background: "背景色",
    text_color: "文字颜色",
    positive_color: "正贡献颜色",
    negative_color: "负贡献颜色",
    point_color: "散点颜色",
    bar_color: "条形颜色",
  };
onMounted(async () => {
  try {
    const initial = await api("tool.shap.defaults");
    defaults.value = clone(initial);
    if (!config.value) config.value = initial;
  } catch (e) {
    error.value = (e as Error).message;
  }
});
function rename(f: any, value: any) {
  const old = f.name,
    next = String(value);
  f.name = next;
  if (config.value.explanation.protective_feature === old)
    config.value.explanation.protective_feature = next;
  for (const s of Object.values(config.value.plots.plots) as any[])
    for (const k of ["feature", "interaction_feature"])
      if (s[k] === old) s[k] = next;
}
function add(kind: string) {
  const i = config.value.data.features.length + 1;
  config.value.data.features.push(
    kind === "binary"
      ? {
          key: "feature_" + Date.now(),
          name: "新分类变量 " + i,
          kind,
          values: [0, 1],
          positive_p: 0.7,
          negative_p: 0.5,
        }
      : {
          key: "feature_" + Date.now(),
          name: "新连续变量 " + i,
          kind,
          positive: { mean: 60, std: 10, min: 0, max: 100 },
          negative: { mean: 50, std: 10, min: 0, max: 100 },
          transform: "round",
          digits: 1,
        },
  );
}
function remove(f: any) {
  config.value.data.features = config.value.data.features.filter(
    (a: any) => a !== f,
  );
  if (config.value.explanation.protective_feature === f.name)
    config.value.explanation.protective_feature = null;
  for (const s of Object.values(config.value.plots.plots) as any[])
    for (const k of ["feature", "interaction_feature"])
      if (s[k] === f.name) s[k] = null;
}
function move(f: any, d: number) {
  const a = config.value.data.features,
    i = a.indexOf(f),
    j = i + d;
  if (j >= 0 && j < a.length) {
    a.splice(i, 1);
    a.splice(j, 0, f);
  }
}
function override(k: string, v: any) {
  if (v) currentStyle.value[k] = clone(effectiveStyle.value[k]);
  else delete currentStyle.value[k];
}
function restore() {
  if (style.value === "common")
    config.value.plots.common = clone(defaults.value.plots.common);
  else
    config.value.plots.plots[style.value] = clone(
      defaults.value.plots.plots[style.value],
    );
}
async function run(mode: string) {
  error.value = "";
  if (mode === "redraw" && !result.value?.has_model) {
    error.value = "请先完成一次完整分析，再复用模型重绘。";
    return;
  }
  await startJob("shap", {
    config: clone(config.value),
    output: output.value,
    data_only: mode === "data",
    previous: mode === "redraw" ? result.value.id : undefined,
  });
  if (!job.error) {
    tab.value = 3;
    page.value = 0;
    resultTab.value = mode === "data" ? "data" : "figures";
    await loadTable();
  }
}
async function preview() {
  if (!result.value?.has_model) {
    error.value = "请先生成完整分析，之后可使用同一模型预览当前样式。";
    return;
  }
  const c = clone(config.value);
  c.plots.formats = ["png"];
  for (const [key, s] of Object.entries(c.plots.plots) as [string, any][])
    s.enabled = style.value === "common" || key === style.value;
  await startJob(
    "shap",
    { config: c, previous: result.value.id },
    "shap-preview",
  );
}
async function loadTable() {
  if (!result.value || ["figures", "metrics"].includes(resultTab.value)) {
    table.value = null;
    return;
  }
  try {
    table.value = await api("tool.shap.table", {
      id: result.value.id,
      kind: resultTab.value,
      page: page.value,
    });
  } catch (e) {
    error.value = (e as Error).message;
  }
}
watch([resultTab, page], loadTable);
async function exportResult() {
  try {
    const r = await api("tool.shap.export", {
      id: result.value.id,
      kinds: exports.value,
      destination: copyTo.value,
    });
    if (r.folder) notify("已保存到 " + r.folder);
    else download(r.name, r.base64, "application/zip", true);
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function chooseOutput() {
  if (desktop) {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const dir = await open({ directory: true, multiple: false });
    if (typeof dir === "string") output.value = dir;
  }
}
async function load(e: Event) {
  try {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    const c = JSON.parse(await f.text());
    if (c.schema_version !== 1 || !c.data?.features || !c.plots?.common)
      throw Error("不是有效的模拟生图配置。");
    config.value = c;
    previewJob.result = null;
    notify("已载入参数配置。");
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function copyTable() {
  if (!result.value) return;
  try {
    const first = await api("tool.shap.table", {
        id: result.value.id,
        kind: resultTab.value,
        page: 0,
      }),
      rows = [...first.rows];
    for (let p = 1; p < Math.ceil(first.total / 200); p++)
      rows.push(
        ...(
          await api("tool.shap.table", {
            id: result.value.id,
            kind: resultTab.value,
            page: p,
          })
        ).rows,
      );
    await navigator.clipboard.writeText(
      [first.columns, ...rows].map((r: any[]) => r.join("\t")).join("\n"),
    );
    notify("已复制当前结果表的全部数据。");
  } catch (e) {
    error.value = (e as Error).message;
  }
}
</script>
<template>
  <div class="scientific-page">
    <PageHeading
      title="模拟数据生图"
      subtitle="配置数据分布、模型解释与图表样式，查看并导出完整分析结果"
      ><Button variant="outline" :disabled="allBusy" @click="file?.click()"
        >载入配置</Button
      ><Button
        variant="outline"
        :disabled="!config"
        @click="
          download(
            '模拟生图参数.json',
            JSON.stringify(config, null, 2),
            'application/json',
          )
        "
        >保存配置</Button
      ></PageHeading
    ><input ref="file" type="file" accept=".json" hidden @change="load" />
    <div class="workflow-tabs" role="tablist" aria-label="模拟生图工作步骤">
      <button
        v-for="(name, i) in [
          '数据参数',
          '模型与分类变量',
          '图表样式',
          '结果与导出',
        ]"
        :key="name"
        role="tab"
        :aria-selected="tab === i"
        :class="{ active: tab === i }"
        @click="tab = i"
      >
        <span>{{ i + 1 }}</span
        >{{ name }}
      </button>
    </div>
    <p
      v-if="error || job.error || previewJob.error"
      class="field-error"
      role="alert"
    >
      {{ error || job.error || previewJob.error }}
    </p>
    <template v-if="config"
      ><section v-if="tab === 0" class="surface scientific-section">
        <div class="section-heading">
          <div>
            <h2>数据参数</h2>
            <p>连续变量按组独立设定分布和范围；分类变量在模型页配置。</p>
          </div>
          <Button variant="outline" @click="dialog = 'data'"
            >完整数据与字段参数</Button
          >
        </div>
        <div class="form-grid">
          <NumberField
            v-model="config.data.n_samples"
            label="样本量"
            integer
            :min="10"
          /><NumberField
            v-model="config.data.positive_rate"
            label="阳性比例（0～1）"
          /><NumberField
            v-model="config.data.random_seed"
            label="数据随机种子"
            integer
          />
          <div class="form-field">
            <label>编号列名</label
            ><Input v-model="config.data.id_name" aria-label="编号列名" />
          </div>
        </div>
        <div class="section-heading subsection">
          <h3>连续变量</h3>
          <Button variant="outline" @click="add('continuous')"
            >添加连续变量</Button
          >
        </div>
        <div class="table-scroll">
          <table class="data-table editable-table feature-table">
            <thead>
              <tr>
                <th>变量名称</th>
                <th
                  v-for="label in [
                    '阳性均数',
                    '阳性标准差',
                    '阳性下限',
                    '阳性上限',
                    '阴性均数',
                    '阴性标准差',
                    '阴性下限',
                    '阴性上限',
                  ]"
                  :key="label"
                >
                  {{ label }}
                </th>
                <th>数值处理</th>
                <th>小数位</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in continuous" :key="f.key">
                <td>
                  <Input
                    :model-value="f.name"
                    aria-label="连续变量名称"
                    @update:model-value="(v) => rename(f, v)"
                  />
                </td>
                <template v-for="g in ['positive', 'negative']" :key="g"
                  ><td v-for="k in ['mean', 'std', 'min', 'max']" :key="k">
                    <Input
                      v-model.number="f[g][k]"
                      type="number"
                      step="any"
                      :aria-label="f.name + ' ' + g + ' ' + k"
                    /></td
                ></template>
                <td>
                  <SelectField
                    v-model="f.transform"
                    :options="[
                      { value: 'int', label: '取整数' },
                      { value: 'round', label: '四舍五入' },
                      { value: 'none', label: '保留原值' },
                    ]"
                    label="数值处理"
                  />
                </td>
                <td>
                  <Input
                    v-model.number="f.digits"
                    type="number"
                    :aria-label="f.name + ' 小数位'"
                  />
                </td>
                <td class="row-actions">
                  <Button variant="ghost" @click="move(f, -1)">↑</Button
                  ><Button variant="ghost" @click="move(f, 1)">↓</Button
                  ><Button variant="ghost" @click="remove(f)">删除</Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section v-if="tab === 1" class="surface scientific-section">
        <div class="section-heading">
          <div>
            <h2>模型与分类变量</h2>
            <p>分类概率表示取第二个编码的概率；各变量可使用独立编码。</p>
          </div>
          <Button variant="outline" @click="dialog = 'model'"
            >完整模型与 SHAP 参数</Button
          >
        </div>
        <div class="form-grid">
          <NumberField
            v-model="config.model.test_size"
            label="测试集比例（0～1）"
          /><NumberField
            v-model="config.model.threshold"
            label="分类阈值"
          /><NumberField
            v-model="config.model.max_iter"
            label="最大迭代次数"
            integer
          /><SelectField
            v-model="config.model.solver"
            :options="[
              'lbfgs',
              'liblinear',
              'newton-cg',
              'newton-cholesky',
              'sag',
              'saga',
            ]"
            label="模型求解器"
          />
        </div>
        <div class="section-heading subsection">
          <h3>分类变量</h3>
          <Button variant="outline" @click="add('binary')">添加分类变量</Button>
        </div>
        <div class="table-scroll">
          <table class="data-table editable-table">
            <thead>
              <tr>
                <th>变量名称</th>
                <th>第一编码</th>
                <th>第二编码</th>
                <th>阳性组概率</th>
                <th>阴性组概率</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in binary" :key="f.key">
                <td>
                  <Input
                    :model-value="f.name"
                    aria-label="分类变量名称"
                    @update:model-value="(v) => rename(f, v)"
                  />
                </td>
                <td v-for="i in [0, 1]" :key="i">
                  <Input
                    v-model.number="f.values[i]"
                    type="number"
                    :aria-label="f.name + ' 编码 ' + (i + 1)"
                  />
                </td>
                <td>
                  <Input
                    v-model.number="f.positive_p"
                    type="number"
                    step="0.01"
                    :aria-label="f.name + ' 阳性概率'"
                  />
                </td>
                <td>
                  <Input
                    v-model.number="f.negative_p"
                    type="number"
                    step="0.01"
                    :aria-label="f.name + ' 阴性概率'"
                  />
                </td>
                <td class="row-actions">
                  <Button variant="ghost" @click="move(f, -1)">↑</Button
                  ><Button variant="ghost" @click="move(f, 1)">↓</Button
                  ><Button variant="ghost" @click="remove(f)">删除</Button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section v-if="tab === 2" class="surface scientific-section">
        <div class="section-heading">
          <div>
            <h2>图表样式</h2>
            <p>公共样式应用于全部图；单图勾选“独立设置”后覆盖对应属性。</p>
          </div>
          <Button variant="outline" @click="restore">恢复默认样式</Button>
        </div>
        <div class="style-layout">
          <nav class="style-navigation">
            <button
              v-for="(label, key) in plotNames"
              :key="key"
              :class="{ active: style === key }"
              @click="style = String(key)"
            >
              {{ label }}
            </button>
            <div class="subsection">
              <h3>图片导出</h3>
              <label
                v-for="f in ['png', 'svg', 'pdf']"
                :key="f"
                class="file-check"
                ><Checkbox
                  :model-value="config.plots.formats.includes(f)"
                  @update:model-value="
                    (v) =>
                      (config.plots.formats = v
                        ? [...config.plots.formats, f]
                        : config.plots.formats.filter((x: string) => x !== f))
                  "
                />{{ f.toUpperCase() }}</label
              ><NumberField
                v-model="config.plots.dpi"
                label="图像 DPI"
                integer
              /><NumberField
                v-model="config.plots.random_seed"
                label="绘图随机种子"
                integer
              /><NumberField
                v-model="config.plots.sample_index"
                label="解释样本索引（从 0 开始）"
                integer
              />
            </div>
          </nav>
          <div class="style-properties">
            <template v-if="style !== 'common'"
              ><label class="file-check"
                ><Checkbox v-model="currentStyle.enabled" />生成此图</label
              >
              <div class="form-field">
                <label>图标题</label
                ><Input v-model="currentStyle.title" aria-label="图标题" />
              </div>
              <div class="form-field">
                <label>图片文件名</label
                ><Input
                  v-model="currentStyle.filename"
                  aria-label="图片文件名"
                />
              </div>
              <template v-if="style.startsWith('dependence')"
                ><SelectField
                  :model-value="currentStyle.feature || ''"
                  :options="featureNames"
                  label="依赖图特征"
                  @update:model-value="
                    (v) => (currentStyle.feature = v || null)
                  " /><SelectField
                  :model-value="currentStyle.interaction_feature || ''"
                  :options="featureNames"
                  label="交互着色特征"
                  @update:model-value="
                    (v) => (currentStyle.interaction_feature = v || null)
                  " /></template
            ></template>
            <div class="style-property">
              <label v-if="style !== 'common'" class="file-check"
                ><Checkbox
                  :model-value="Object.hasOwn(currentStyle, 'font_family')"
                  @update:model-value="(v) => override('font_family', v)"
                />独立设置字体</label
              ><label>字体（按顺序回退）</label
              ><Input
                :model-value="effectiveStyle.font_family.join(', ')"
                :disabled="
                  style !== 'common' &&
                  !Object.hasOwn(currentStyle, 'font_family')
                "
                aria-label="字体列表"
                @update:model-value="
                  (v) =>
                    (currentStyle.font_family = String(v)
                      .split(/[,，]/)
                      .map((s) => s.trim())
                      .filter(Boolean))
                "
              />
            </div>
            <div
              v-for="k in [...mainStyleKeys, ...colorKeys]"
              :key="k"
              class="style-property"
            >
              <label v-if="style !== 'common'" class="file-check"
                ><Checkbox
                  :model-value="Object.hasOwn(currentStyle, k)"
                  @update:model-value="(v) => override(k, v)"
                />独立设置 {{ styleLabels[k] }}</label
              ><NumberField
                v-if="mainStyleKeys.includes(k)"
                :label="styleLabels[k]"
                :disabled="
                  style !== 'common' && !Object.hasOwn(currentStyle, k)
                "
                :model-value="effectiveStyle[k]"
                @update:model-value="
                  (v) => {
                    if (style === 'common' || Object.hasOwn(currentStyle, k))
                      currentStyle[k] = v;
                  }
                "
              />
              <div v-else class="form-field">
                <label>{{ styleLabels[k] }}</label>
                <div class="color-input">
                  <input
                    type="color"
                    :aria-label="styleLabels[k] + ' 色板'"
                    :value="effectiveStyle[k]"
                    :disabled="
                      style !== 'common' && !Object.hasOwn(currentStyle, k)
                    "
                    @input="
                      (e) =>
                        (currentStyle[k] = (e.target as HTMLInputElement).value)
                    "
                  /><Input
                    :model-value="effectiveStyle[k]"
                    :aria-label="styleLabels[k]"
                    :disabled="
                      style !== 'common' && !Object.hasOwn(currentStyle, k)
                    "
                    @update:model-value="(v) => (currentStyle[k] = String(v))"
                  />
                </div>
              </div>
              <small
                v-if="style !== 'common' && !Object.hasOwn(currentStyle, k)"
                >继承公共样式</small
              >
            </div>
            <div class="two-columns">
              <NumberField
                :model-value="effectiveStyle.figsize[0]"
                label="图片宽（英寸）"
                @update:model-value="
                  (v) => (currentStyle.figsize = [v, effectiveStyle.figsize[1]])
                "
              /><NumberField
                :model-value="effectiveStyle.figsize[1]"
                label="图片高（英寸）"
                @update:model-value="
                  (v) => (currentStyle.figsize = [effectiveStyle.figsize[0], v])
                "
              />
            </div>
            <Button variant="outline" @click="dialog = 'style'"
              >全部样式与当前图专属参数</Button
            >
          </div>
          <div class="style-preview">
            <div class="section-heading">
              <h3>实际绘图预览</h3>
              <Button
                variant="outline"
                :disabled="allBusy || !result?.has_model"
                @click="preview"
                >{{ previewJob.busy ? "预览生成中…" : "预览当前样式" }}</Button
              >
            </div>
            <p class="tool-note">
              先完成一次完整分析，然后复用模型预览。修改样式后点击预览更新图片。
            </p>
            <img
              v-if="previewImage"
              :src="previewImage.url"
              :alt="previewImage.name"
            />
            <p v-else>尚未生成当前样式预览</p>
          </div>
        </div>
      </section>
      <section v-if="tab === 3" class="surface scientific-section">
        <div class="section-heading">
          <div>
            <h2>结果与导出</h2>
            <p v-if="result">
              共 {{ result.total }} 行 ·
              {{ result.has_model ? "包含模型与 SHAP 分析" : "仅生成数据" }} ·
              参数快照与结果一同保存
            </p>
            <p v-else>完成生成后，可查看全部数据、模型指标与图表。</p>
          </div>
          <Button
            v-if="result"
            variant="outline"
            @click="openPath(result.folder)"
            >结果文件夹</Button
          >
        </div>
        <template v-if="result"
          ><div class="workflow-tabs result-tabs">
            <button
              v-for="[key, label] in [
                ['figures', '图表'],
                ['data', '模拟数据'],
                ['metrics', '模型指标'],
                ['coefficients', '模型系数'],
                ['predictions', '预测结果'],
                ['shap', 'SHAP 数值'],
              ]"
              :key="key"
              :class="{ active: resultTab === key }"
              @click="
                resultTab = key;
                page = 0;
              "
            >
              {{ label }}
            </button>
          </div>
          <div v-if="resultTab === 'figures'">
            <div v-if="images.length" class="toolbar">
              <SelectField
                v-model="image"
                :options="
                  images.map((x: any) => ({ value: x.name, label: x.name }))
                "
                label="结果图选择"
              /><Button variant="outline" @click="zoom = true">放大查看</Button
              ><Button
                variant="outline"
                @click="
                  download(
                    selectedImage.name,
                    selectedImage.url.split(',')[1],
                    'image/png',
                    true,
                  )
                "
                >保存当前图</Button
              >
            </div>
            <img
              v-if="selectedImage"
              class="result-figure"
              :src="selectedImage.url"
              :alt="selectedImage.name"
            />
            <p v-else class="tool-note">
              没有 PNG 预览；SVG / PDF 可从结果文件夹或导出包查看。
            </p>
          </div>
          <div v-else-if="resultTab === 'metrics'" class="metrics-result">
            <p v-if="!result.has_model">本次仅生成数据，尚无模型指标。</p>
            <template v-else
              ><div class="metric-cards">
                <div>
                  <span>准确率</span
                  ><strong
                    >{{ (result.metrics.accuracy * 100).toFixed(2) }}%</strong
                  >
                </div>
                <div>
                  <span>ROC-AUC</span
                  ><strong>{{ result.metrics.auc.toFixed(4) }}</strong>
                </div>
                <div>
                  <span>模型截距</span
                  ><strong>{{ result.metrics.intercept.toFixed(4) }}</strong>
                </div>
              </div>
              <h3>混淆矩阵</h3>
              <table class="data-table">
                <thead>
                  <tr>
                    <th>真实 / 预测</th>
                    <th>预测阴性</th>
                    <th>预测阳性</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(row, i) in result.metrics.confusion_matrix"
                    :key="i"
                  >
                    <th>{{ i === 0 ? "真实阴性" : "真实阳性" }}</th>
                    <td v-for="(v, j) in row" :key="j">{{ v }}</td>
                  </tr>
                </tbody>
              </table>
              <h3>分类报告</h3>
              <div class="table-scroll">
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>类别</th>
                      <th>精确率</th>
                      <th>召回率</th>
                      <th>F1</th>
                      <th>样本数</th>
                    </tr>
                  </thead>
                  <tbody>
                    <template
                      v-for="(r, key) in result.metrics.classification_report"
                      :key="key"
                      ><tr v-if="typeof r === 'object'">
                        <th>{{ key }}</th>
                        <td>{{ r.precision?.toFixed(4) }}</td>
                        <td>{{ r.recall?.toFixed(4) }}</td>
                        <td>{{ r["f1-score"]?.toFixed(4) }}</td>
                        <td>{{ r.support }}</td>
                      </tr></template
                    >
                  </tbody>
                </table>
              </div>
              <h3>局部样本预测</h3>
              <pre>{{
                JSON.stringify(result.metrics.sample_prediction, null, 2)
              }}</pre>
            </template>
          </div>
          <template v-else-if="table"
            ><div class="toolbar">
              <strong
                >共 {{ table.total }} 行 · 第 {{ page + 1 }} /
                {{ Math.max(1, Math.ceil(table.total / 200)) }} 页</strong
              ><Button variant="outline" :disabled="page === 0" @click="page--"
                >上一页</Button
              ><Button
                variant="outline"
                :disabled="(page + 1) * 200 >= table.total"
                @click="page++"
                >下一页</Button
              ><Button
                variant="outline"
                :disabled="!table.total"
                @click="copyTable"
                >复制完整结果表</Button
              >
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead>
                  <tr>
                    <th v-for="c in table.columns" :key="c">{{ c }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(r, i) in table.rows" :key="i">
                    <td v-for="(v, j) in r" :key="j">{{ v }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-if="!table.total" class="tool-note">
              本次结果没有此类数据。
            </p></template
          >
          <div class="subsection">
            <h3>选择保存内容</h3>
            <div class="toolbar">
              <label
                v-for="[key, label] in [
                  ['data', '数据表'],
                  ['figures', '图像'],
                  ['config', '参数配置'],
                  ['reports', '分析报告'],
                ]"
                :key="key"
                class="file-check"
                ><Checkbox
                  :model-value="exports.includes(key)"
                  @update:model-value="
                    (v) =>
                      (exports = v
                        ? [...exports, key]
                        : exports.filter((k) => k !== key))
                  "
                />{{ label }}</label
              >
            </div>
            <div class="toolbar">
              <Input
                v-model="copyTo"
                aria-label="结果复制目标目录"
                placeholder="留空下载 ZIP；填写目录则复制所选内容"
              /><Button :disabled="!exports.length" @click="exportResult"
                >保存所选内容</Button
              >
            </div>
          </div></template
        >
      </section>
      <section class="surface scientific-section generation-bar">
        <div class="toolbar">
          <Input
            v-model="output"
            aria-label="分析输出目录"
            placeholder="输出目录留空使用应用本地目录"
          /><Button v-if="desktop" variant="outline" @click="chooseOutput"
            >选择目录</Button
          ><Button variant="outline" :disabled="allBusy" @click="run('data')"
            >仅生成数据</Button
          ><Button :disabled="allBusy" @click="run('full')">生成完整分析</Button
          ><Button
            variant="outline"
            :disabled="allBusy || !result?.has_model"
            @click="run('redraw')"
            >复用模型重绘</Button
          ><Button
            v-if="allBusy"
            variant="outline"
            @click="cancelJob(job.busy ? 'shap' : 'shap-preview')"
            >取消计算</Button
          >
        </div>
        <p role="status">
          {{
            job.busy
              ? job.message
              : previewJob.busy
                ? previewJob.message
                : job.message || "本机计算 · 可复现参数与随机种子"
          }}
        </p>
      </section></template
    ><Dialog
      :open="!!dialog"
      @update:open="
        (v) => {
          if (!v) dialog = '';
        }
      "
      ><DialogContent class="sm:max-w-5xl max-h-[90vh] overflow-y-auto"
        ><DialogHeader
          ><DialogTitle>{{
            dialog === "data"
              ? "完整数据与字段参数"
              : dialog === "model"
                ? "完整模型与 SHAP 参数"
                : "全部样式与当前图专属参数"
          }}</DialogTitle
          ><DialogDescription
            >修改立即保留在当前配置中。</DialogDescription
          ></DialogHeader
        ><template v-if="config"
          ><ConfigEditor
            v-if="dialog === 'data'"
            v-model="config.data"
            :exclude="['features']"
          /><template v-if="dialog === 'model'"
            ><ConfigEditor v-model="config.model" />
            <h3>SHAP 解释参数</h3>
            <ConfigEditor v-model="config.explanation" /></template
          ><template v-if="dialog === 'style'"
            ><h3>{{ plotNames[style] }}</h3>
            <ConfigEditor
              :model-value="currentStyle"
              @update:model-value="
                (v) => {
                  if (style === 'common') config.plots.common = v;
                  else config.plots.plots[style] = v;
                }
              "
            /><template v-if="style !== 'common'"
              ><h3>更多可继承属性</h3>
              <div class="toolbar">
                <label
                  v-for="k in Object.keys(config.plots.common)"
                  :key="k"
                  class="file-check"
                  ><Checkbox
                    :model-value="Object.hasOwn(currentStyle, k)"
                    @update:model-value="(v) => override(k, v)"
                  />{{ styleLabels[k] || k }}</label
                >
              </div></template
            ></template
          ></template
        ><Button @click="dialog = ''">完成</Button></DialogContent
      ></Dialog
    ><Dialog :open="zoom" @update:open="(v) => (zoom = v)"
      ><DialogContent class="sm:max-w-[95vw] max-h-[95vh] overflow-auto"
        ><DialogHeader
          ><DialogTitle>{{ selectedImage?.name }}</DialogTitle
          ><DialogDescription>完整图像预览</DialogDescription></DialogHeader
        ><img
          v-if="selectedImage"
          :src="selectedImage.url"
          :alt="selectedImage.name" /></DialogContent
    ></Dialog>
  </div>
</template>
