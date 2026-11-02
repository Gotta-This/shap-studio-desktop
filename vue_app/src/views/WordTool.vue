<script setup lang="ts">
import {
  ref,
  reactive,
  computed,
  onMounted,
  onUnmounted,
  watch,
  nextTick,
} from "vue";
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
import RowsEditor from "@/components/RowsEditor.vue";
import FieldRuleDialog from "@/components/FieldRuleDialog.vue";
import ProseMatching from "@/components/ProseMatching.vue";
import { api, upload, download, notify } from "@/lib/api";
import {
  clone,
  fieldTypes,
  ruleSummary,
  ruleLines,
  jobFor,
  startJob,
  cancelJob,
} from "@/lib/scientific";
const sourceLabels: Record<string, string> = {
  column: "输出列名",
  group: "组别 / 数据集",
  source: "参数来源",
  rule: "生成规则",
  original: "原文依据",
};
const tabs = [
    "基础资料",
    "表格匹配",
    "文字匹配",
    "全部字段以及来源",
    "生成与导出",
  ],
  tab = ref(0),
  config = ref<any>(null),
  inventory = ref<any>(null),
  draft = ref<any>(null),
  session = ref(""),
  groupsConfirmed = ref(true),
  names = ref<string[]>([]),
  ungrouped = ref(false),
  ungroupedN = ref<number | null>(70),
  error = ref(""),
  busy = ref(false),
  preview = ref(false),
  previewTab = ref(0),
  editing = ref<any>(null),
  editingDraft = ref(false),
  groupIndex = ref("0"),
  prose = ref<any>(null),
  proseStale = ref(false),
  proseActive = ref(true),
  studyIndex = ref(0),
  editorRevision = ref(0),
  restoring = ref(false),
  sources = ref<any>(null),
  matches = ref<any>(null),
  auditResult = ref<any>(null),
  auditing = ref(false),
  file = ref<HTMLInputElement>(),
  configFile = ref<HTMLInputElement>(),
  confirmImport = ref<File | null>(null),
  job = jobFor("word");
const options = reactive({
    sizes: false,
    rates: false,
    prose: false,
    leave_unknown_blank: false,
    decimal_mode: "zero",
  }),
  group = computed(
    () =>
      config.value?.groups?.[Number(groupIndex.value)] ||
      config.value?.groups?.[0],
  ),
  fields = computed(() =>
    config.value
      ? [
          ...(config.value.indicators || []),
          ...(config.value.typed_fields || []),
          ...(config.value.categoricals || []),
        ]
      : [],
  ),
  blocks = computed(() =>
    Object.entries(
      fields.value.reduce((r: Record<string, any[]>, f: any) => {
        (r[String(f.table || "手工添加")] ||= []).push(f);
        return r;
      }, {}),
    ),
  ),
  rangeColumns = [
    { key: "lower", label: "下限" },
    { key: "upper", label: "上限" },
    { key: "percent", label: "占比 %" },
  ];
onMounted(async () => {
  try {
    const initial = await api("tool.word.defaults");
    if (config.value) return;
    config.value = initial;
    config.value.same_group_size = true;
    config.value.shared_basics = true;
    config.value.include_basics = true;
    config.value.typed_fields = [];
  } catch (e) {
    error.value = (e as Error).message;
  }
});
async function guard(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function requestImport(f?: File) {
  if (!f) return;
  if (busy.value || job.busy) {
    notify("请等待当前任务完成后再导入。", true);
    return;
  }
  if (session.value || job.result) confirmImport.value = f;
  else read(f);
}
async function read(f: File) {
  confirmImport.value = null;
  await guard(async () => {
    const r = await api("tool.word.scan", {
      uploads: await upload([f]),
      decimal_mode: options.decimal_mode,
    });
    groupsConfirmed.value = false;
    session.value = r.session;
    inventory.value = r.scan;
    draft.value = r.draft;
    names.value = [...r.scan.candidates];
    ungrouped.value = r.scan.has_ungrouped && !names.value.length;
    ungroupedN.value = r.scan.ungrouped_n ?? null;
    matches.value = null;
    auditResult.value = null;
    sources.value = null;
    prose.value = null;
    proseStale.value = false;
    job.result = null;
    config.value = {
      ...config.value,
      source: f.name,
      indicators: [],
      typed_fields: [],
      categoricals: [],
    };
    tab.value = 0;
    await nextTick();
    if (ungrouped.value) {
      if (ungroupedN.value && ungroupedN.value >= 2) {
        await applyCurrent();
        tab.value = 1;
      } else notify("已读取无分组表，请补充例数后确认。");
    } else if (names.value.length) {
      matches.value = await api("tool.word.match", {
        session: session.value,
        groups: names.value,
      });
      if (matches.value.groups.every((g: any) => g.tables || g.paragraphs)) {
        await applyCurrent();
        tab.value = 1;
      } else notify("已自动核对组别，存在未匹配组别，请调整后重新确认。", true);
    } else notify("未识别到明确组别，请补充组别后确认。", true);
  });
}
async function matchGroups() {
  await guard(async () => {
    matches.value = await api("tool.word.match", {
      session: session.value,
      groups: names.value,
    });
  });
}
async function applyCurrent() {
  const r = await api("tool.word.apply", {
    session: session.value,
    draft: draft.value,
    options,
    groups: names.value,
    ungrouped: ungrouped.value,
    n: ungroupedN.value,
    previous: config.value,
  });
  config.value = r.config;
  prose.value = r.prose_document;
  proseStale.value = false;
  groupIndex.value = "0";
  job.result = null;
  await nextTick();
  groupsConfirmed.value = true;
  await nextTick();
  clearTimeout(auditTimer);
  await auditCurrent(++auditVersion);
  notify(
    auditResult.value?.pending
      ? `已自动匹配并核对，${auditResult.value.pending} 项规则待人工确认。`
      : "已自动匹配并完成参数核对。",
  );
}
async function apply() {
  await guard(async () => {
    if (!ungrouped.value && names.value.length)
      matches.value = await api("tool.word.match", {
        session: session.value,
        groups: names.value,
      });
    await applyCurrent();
  });
}
let auditTimer: ReturnType<typeof setTimeout> | undefined;
let auditVersion = 0;
function ruleKey(f: any) {
  return JSON.stringify([f.table ?? null, f.group, f.name]);
}
const auditIssues = computed(
  () =>
    new Map(
      (auditResult.value?.issues || []).map((f: any) => [
        ruleKey(f),
        f.message,
      ]),
    ),
);
function pendingRule(f: any) {
  return (
    f.kind !== "excluded" &&
    (f.confirmed === false ||
      f.kind === "unknown" ||
      auditIssues.value.has(ruleKey(f)))
  );
}
async function auditCurrent(version: number) {
  auditing.value = true;
  try {
    const result = await api("tool.word.audit", clone(payload()));
    if (version === auditVersion) auditResult.value = result;
  } catch (e) {
    if (version === auditVersion)
      auditResult.value = {
        total: fields.value.length,
        pending: 0,
        issues: [],
        global_error: (e as Error).message,
        valid: false,
      };
  } finally {
    if (version === auditVersion) auditing.value = false;
  }
}
watch(
  [config, prose, proseStale, proseActive, studyIndex, groupsConfirmed],
  () => {
    clearTimeout(auditTimer);
    const version = ++auditVersion;
    if (
      !config.value ||
      !groupsConfirmed.value ||
      (!inventory.value && !fields.value.length && !prose.value)
    ) {
      auditing.value = false;
      auditResult.value = null;
      return;
    }
    auditing.value = true;
    auditTimer = setTimeout(() => void auditCurrent(version), 150);
  },
  { deep: true },
);
onUnmounted(() => {
  clearTimeout(auditTimer);
  auditVersion++;
});
function locatePending() {
  document
    .querySelector(".word-fields-table .rule-pending")
    ?.scrollIntoView({ block: "center", behavior: "smooth" });
}
function payload() {
  return {
    config: { ...config.value, import_options: clone(options) },
    prose_document: prose.value,
    prose_active: proseActive.value,
    prose_stale: proseStale.value,
    study_index: studyIndex.value,
  };
}
watch([prose, studyIndex, proseActive], ([doc]) => {
  if (doc && proseActive.value && !restoring.value) {
    config.value.include_basics = false;
    config.value.same_group_size = false;
    config.value.shared_basics = false;
    if (!inventory.value && !fields.value.length) {
      const study = doc.studies?.[studyIndex.value];
      if (study)
        config.value.groups = study.groups.map((g: any) => ({
          ...clone(config.value.groups[0]),
          name: g.name,
          n: g.n || 70,
        }));
    }
  }
});
watch(
  () => [
    names.value.join("\0"),
    ungrouped.value,
    ungroupedN.value,
    options.sizes,
    options.rates,
    options.prose,
    options.decimal_mode,
  ],
  () => {
    if (inventory.value) groupsConfirmed.value = false;
  },
);
watch(tab, async (v) => {
  if (v === 3) await review();
});
async function review() {
  await guard(async () => {
    sources.value = await api("tool.word.review", payload());
  });
}
function locate(f: any) {
  for (const key of ["indicators", "typed_fields", "categoricals"]) {
    const i = (config.value[key] || []).indexOf(f);
    if (i >= 0) return { key, i };
  }
  return null;
}
const fieldPeers = computed(() => {
  const old = editing.value;
  if (!old) return [];
  return (editingDraft.value ? draft.value.fields : fields.value).filter(
    (f: any) => f !== old && f.table === old.table && f.name === old.name,
  );
});
function saveField(value: any, sync: boolean, updatedPeers: any[]) {
  const old = editing.value,
    preview = editingDraft.value,
    peers = sync ? fieldPeers.value : [];
  const replace = (before: any, after: any) => {
    if (preview) {
      const i = draft.value.fields.indexOf(before);
      if (i >= 0) draft.value.fields[i] = after;
      return;
    }
    const pos = locate(before);
    if (!pos) return;
    if (
      pos.key === "typed_fields" ||
      (pos.key === "indicators" && after.kind === "mean_sd") ||
      (pos.key === "categoricals" && after.kind === "category")
    )
      config.value[pos.key][pos.i] = after;
    else {
      config.value[pos.key].splice(pos.i, 1);
      (config.value.typed_fields ||= []).push(after);
    }
  };
  replace(old, value);
  peers.forEach((f: any, i: number) => replace(f, updatedPeers[i]));
  error.value = "";
}
function rename(f: any, v: any) {
  error.value = "";
  const name = f.name;
  for (const a of fields.value)
    if (a.table === f.table && a.name === name) a.name = String(v);
  for (const a of fields.value)
    if (a.from_field === name) a.from_field = String(v);
}
function remove(f: any) {
  error.value = "";
  for (const key of ["indicators", "typed_fields", "categoricals"])
    config.value[key] = (config.value[key] || []).filter(
      (a: any) =>
        !(a.table === f.table && a.name === f.name) && a.from_field !== f.name,
    );
}
function add(table: any) {
  const name = "新指标 " + (fields.value.length + 1);
  config.value.typed_fields ||= [];
  for (const g of config.value.groups)
    config.value.typed_fields.push({
      table: table === "手工添加" ? null : Number(table),
      name,
      group: g.name,
      kind: "mean_sd",
      mean: 0,
      sd: 1,
      digits: 0,
      parity: "any",
      confirmed: true,
      raw: "手工添加",
    });
}
async function load(e: Event) {
  await guard(async () => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    const c = await api("tool.word.configuration", {
      config: JSON.parse(await f.text()),
    });
    if (!Array.isArray(c.groups) || !c.groups.length)
      throw Error("不是有效的 Word 生成配置。");
    if (c.table_match) {
      Object.assign(c, clone(c.table_match));
      delete c.table_match;
    }
    inventory.value = null;
    draft.value = null;
    session.value = "";
    matches.value = null;
    groupsConfirmed.value = true;
    config.value = c;
    Object.assign(options, c.import_options || {});
    restoring.value = true;
    prose.value = c.prose_document || null;
    proseStale.value = !!c.prose_stale;
    proseActive.value = c.prose_active !== false;
    studyIndex.value = c.study_index || 0;
    groupIndex.value = "0";
    names.value = c.groups.map((g: any) => g.name);
    job.result = null;
    editorRevision.value++;
    await nextTick();
    restoring.value = false;
  });
}
function save() {
  const c = clone(config.value);
  c.table_match = Object.fromEntries(
    ["indicators", "typed_fields", "categoricals"].map((k) => [
      k,
      clone(c[k] || []),
    ]),
  );
  c.prose_document = prose.value;
  c.prose_stale = proseStale.value;
  c.prose_active = proseActive.value;
  c.study_index = studyIndex.value;
  c.import_options = clone(options);
  download("Word模拟配置.json", JSON.stringify(c, null, 2), "application/json");
}
async function copyResult() {
  await navigator.clipboard.writeText(job.result.text);
  notify("已复制完整模拟数据。");
}
async function generate() {
  if (!groupsConfirmed.value) {
    error.value = "当前 Word 尚未确认组别，请先匹配并确认。";
    return;
  }
  await startJob("word", payload());
  if (job.result && !job.error && job.message.includes("完成"))
    notify("已生成完整 Excel，表格预览最多显示 200 行。");
}
function sameN(v: any) {
  if (config.value.same_group_size)
    for (const g of config.value.groups) g.n = v;
}
</script>
<template>
  <div
    class="scientific-page word-page"
    @dragover.prevent
    @drop.prevent="(e) => requestImport(e.dataTransfer?.files[0])"
  >
    <PageHeading
      title="Word 一键生成 Excel"
      subtitle="核对原文与生成规则，导出带有来源记录的模拟病例表"
      ><Button variant="outline" @click="tab = 2">正文转竖表</Button
      ><Button
        variant="outline"
        :disabled="busy || job.busy"
        @click="configFile?.click()"
        >载入配置</Button
      ><Button variant="outline" :disabled="!config" @click="save"
        >保存配置</Button
      ><Button :disabled="busy || job.busy" @click="file?.click()"
        >导入 Word</Button
      ></PageHeading
    ><input
      ref="file"
      hidden
      type="file"
      accept=".doc,.docx"
      aria-label="导入 Word 文档"
      @change="
        (e) => {
          requestImport((e.target as HTMLInputElement).files?.[0]);
          (e.target as HTMLInputElement).value = '';
        }
      "
    /><input
      ref="configFile"
      hidden
      type="file"
      accept=".json"
      @change="load"
    />
    <section class="surface scientific-section word-import-controls">
      <div class="toolbar">
        <label class="file-check"
          ><Checkbox v-model="options.sizes" />采用 Word 中的例数</label
        ><label class="file-check"
          ><Checkbox v-model="options.rates" />采用 Word
          表中的有效／复发比例</label
        ><label class="file-check"
          ><Checkbox v-model="options.prose" />采用正文一般资料</label
        ><label class="file-check"
          ><Checkbox
            v-model="options.leave_unknown_blank"
          />未识别的基础字段留空</label
        ><SelectField
          v-model="options.decimal_mode"
          label="导入小数精度"
          :options="[
            { value: 'zero', label: '默认整数（0 位）' },
            { value: 'source', label: '沿用原文精度' },
          ]"
        />
      </div>
      <div v-if="inventory" class="import-summary">
        <div>
          <strong>{{
            inventory.source_name || inventory.source.split(/[\\/]/).pop()
          }}</strong>
          <p>
            {{ inventory.tables.length }} 个原表 ·
            {{ inventory.fields.length }} 条识别草稿 ·
            {{ groupsConfirmed ? "已确认组别" : "尚未确认组别" }} ·
            导入选项在确认组别时生效
          </p>
        </div>
        <Button variant="outline" @click="preview = true"
          >查看原表与识别草稿</Button
        >
      </div>
      <template v-if="inventory"
        ><div class="toolbar">
          <label v-if="inventory.has_ungrouped" class="file-check"
            ><Checkbox v-model="ungrouped" />无分组竖表</label
          ><template v-if="!ungrouped"
            ><div v-for="(_, i) in names" :key="i" class="inline-field">
              <Input
                v-model="names[i]"
                :disabled="busy || job.busy"
                :aria-label="'匹配组别 ' + (i + 1)"
              /><Button
                variant="outline"
                :aria-label="'删除组别 ' + (i + 1)"
                :disabled="busy || job.busy"
                @click="names.splice(i, 1)"
                >×</Button
              >
            </div>
            <Button
              variant="outline"
              :disabled="busy || job.busy || names.length >= 20"
              @click="names.push('新组别')"
              >添加组别</Button
            ></template
          ><NumberField
            v-else
            v-model="ungroupedN"
            label="无分组生成例数"
            integer
            :min="2"
            :max="5000"
          /><Button
            v-if="!ungrouped"
            variant="outline"
            :disabled="busy || job.busy"
            @click="matchGroups"
            >核对组别匹配</Button
          ><Button :disabled="busy || job.busy" @click="apply"
            >匹配并确认组别</Button
          >
        </div></template
      >
      <div v-if="matches" class="tool-note">
        <p v-for="g in matches.groups" :key="g.name">
          {{ g.name }}：{{ g.tables }} 张表、{{ g.paragraphs }} 处正文 ·
          {{ g.n == null ? "原文例数未识别" : g.n + " 例"
          }}<strong v-if="!g.tables && !g.paragraphs"
            >（未匹配，请修改或移除）</strong
          >
        </p>
      </div>
      <p v-if="!inventory" class="tool-note">
        导入 .doc /
        .docx，或拖入文档。先核对原表、方向、候选组别与识别草稿，再应用。
      </p>
    </section>
    <div class="workflow-tabs" role="tablist" aria-label="Word 工作步骤">
      <button
        v-for="(name, i) in tabs"
        :key="name"
        :aria-selected="tab === i"
        role="tab"
        :class="{ active: tab === i }"
        @click="tab = i"
      >
        <span>{{ i + 1 }}</span
        >{{ name }}
      </button>
    </div>
    <p v-if="error || job.error" class="field-error" role="alert">
      {{ error || job.error }}
    </p>
    <template v-if="config && group"
      ><section v-if="tab === 0" class="surface scientific-section">
        <div class="section-heading">
          <div>
            <h2>基础资料</h2>
            <p>
              例数默认 70；只有显式勾选才采用 Word
              中的例数。各组有效率、复发率独立配置。
            </p>
          </div>
          <SelectField
            v-model="groupIndex"
            :options="
              config.groups.map((g: any, i: number) => ({
                value: String(i),
                label: g.name,
              }))
            "
            label="当前基础资料组别"
          />
        </div>
        <div class="toolbar">
          <label class="file-check"
            ><Checkbox
              v-model="config.include_basics"
              :disabled="config.ungrouped || (!!prose && proseActive)"
            />包含基础资料与结局列</label
          ><label class="file-check"
            ><Checkbox
              v-model="config.same_group_size"
              @update:model-value="() => sameN(group.n)"
            />各组例数相同</label
          ><label class="file-check"
            ><Checkbox
              v-model="config.shared_basics"
            />共用基础分布（结局各组独立）</label
          >
        </div>
        <div class="form-grid">
          <NumberField
            v-model="group.n"
            label="当前组生成例数"
            integer
            :min="2"
            :max="5000"
            @update:model-value="sameN"
          /><NumberField v-model="config.seed" label="随机种子" integer />
          <div class="form-field">
            <label>病程单位</label
            ><Input v-model="config.course_unit" aria-label="病程单位" />
          </div>
        </div>
        <template v-if="config.include_basics"
          ><p
            v-if="config.shared_basics && Number(groupIndex) > 0"
            class="tool-note"
          >
            基础分布共用第一组的设置；有效率、复发率仍可在下方独立修改。
          </p>
          <fieldset
            :disabled="config.shared_basics && Number(groupIndex) > 0"
            class="basics-distributions"
          >
            <div class="subsection">
              <h3>性别与病情</h3>
              <div class="form-grid">
                <NumberField
                  v-model="group.male"
                  label="男性占比 %"
                /><NumberField
                  v-model="group.severity[0]"
                  label="轻度占比 %"
                /><NumberField
                  v-model="group.severity[1]"
                  label="中度占比 %"
                /><NumberField v-model="group.severity[2]" label="重度占比 %" />
              </div>
            </div>
            <div class="subsection">
              <RowsEditor
                v-model="group.age"
                :columns="rangeColumns"
                title="年龄区间"
              /><label class="file-check"
                ><Checkbox
                  :model-value="!!group.age_stats"
                  @update:model-value="
                    (v) => (group.age_stats = v ? { mean: 50, sd: 10 } : null)
                  "
                />同时约束年龄均数与标准差</label
              >
              <div v-if="group.age_stats" class="two-columns">
                <NumberField
                  v-model="group.age_stats.mean"
                  label="年龄均数"
                /><NumberField
                  v-model="group.age_stats.sd"
                  label="年龄标准差"
                />
              </div>
            </div>
            <div class="subsection">
              <RowsEditor
                v-model="group.course"
                :columns="rangeColumns"
                title="病程区间"
              /><NumberField
                v-model="group.course_digits"
                label="病程小数位"
                integer
                :min="0"
                :max="4"
              />
            </div>
            <div class="subsection">
              <h3>病变范围</h3>
              <SelectField
                v-model="group.extent_mode"
                :options="[
                  { value: 'blank', label: '留空' },
                  { value: 'category', label: '分类比例' },
                  { value: 'range', label: '连续区间' },
                ]"
                label="病变范围模式"
              /><RowsEditor
                v-if="group.extent_mode === 'category'"
                v-model="group.extent"
                :columns="[
                  { key: 'label', label: '类别', text: true },
                  { key: 'percent', label: '占比 %' },
                ]"
              /><template v-if="group.extent_mode === 'range'"
                ><RowsEditor
                  v-model="group.extent_ranges"
                  :columns="rangeColumns" /><NumberField
                  v-model="group.extent_digits"
                  label="病变范围小数位"
                  integer
              /></template>
            </div>
          </fieldset>
          <div class="subsection">
            <h3>{{ group.name }} · 有效与复发</h3>
            <div class="form-grid">
              <NumberField
                v-model="group.effective"
                label="总有效率 %"
              /><NumberField
                v-model="group.recurrence"
                label="复发率 %"
              /><SelectField
                v-model="group.recurrence_scope"
                :options="[
                  { value: 'all', label: '全部病例为分母' },
                  { value: 'effective', label: '仅有效病例为分母' },
                ]"
                label="复发率分母"
              />
            </div></div
        ></template>
      </section>
      <section
        v-if="tab === 1"
        class="surface scientific-section word-matching"
      >
        <div class="section-heading">
          <div>
            <h2>表格匹配</h2>
            <p>按原表分块；同表同指标名称跨组同步，数值与确认状态逐组独立。</p>
          </div>
          <Button variant="outline" @click="add('手工添加')"
            >添加指标（全部组）</Button
          >
        </div>
        <div v-if="auditing || auditResult" class="rule-audit" role="status">
          <span v-if="auditing">正在自动核对参数…</span>
          <span v-else
            >已自动核对 {{ auditResult.total }} 项规则：{{
              auditResult.pending
            }}
            项待人工确认{{ auditResult.valid ? "，参数核对通过" : "" }}。</span
          >
          <Button
            v-if="auditResult?.pending"
            variant="outline"
            size="sm"
            @click="locatePending"
            >定位待确认</Button
          >
          <p v-if="auditResult?.global_error" class="field-error" role="alert">
            {{ auditResult.global_error }}
          </p>
        </div>
        <div v-for="[table, rows] in blocks" :key="table" class="subsection">
          <div class="section-heading">
            <h3>{{ config.table_titles?.[table] || "手工添加指标" }}</h3>
            <Button variant="outline" size="sm" @click="add(table)"
              >本表添加指标</Button
            >
          </div>
          <div class="table-scroll">
            <table class="data-table editable-table word-fields-table">
              <colgroup>
                <col style="width: 18%" />
                <col style="width: 10%" />
                <col style="width: 10%" />
                <col style="width: 34%" />
                <col style="width: 14%" />
                <col style="width: 14%" />
              </colgroup>
              <thead>
                <tr>
                  <th>输出列名</th>
                  <th>组别 / 数据集</th>
                  <th>数据类型</th>
                  <th>生成规则</th>
                  <th>Word 原文</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="f in rows"
                  :key="f.group + f.name"
                  :class="{ 'rule-pending': pendingRule(f) }"
                  :aria-label="
                    pendingRule(f)
                      ? f.name + ' / ' + f.group + '：待人工确认'
                      : undefined
                  "
                >
                  <td>
                    <Input
                      :model-value="f.name"
                      aria-label="输出列名"
                      @update:model-value="(v) => rename(f, v)"
                    />
                  </td>
                  <td>{{ f.group }}</td>
                  <td>
                    {{
                      fieldTypes.find((x) => x.value === (f.kind || "mean_sd"))
                        ?.label
                    }}<small
                      v-if="pendingRule(f)"
                      :title="
                        String(auditIssues.get(ruleKey(f)) || '待人工确认')
                      "
                      >待人工确认</small
                    >
                  </td>
                  <td>
                    <div class="word-rule-cell">
                      <div class="word-rule-lines">
                        <span v-for="(line, i) in ruleLines(f)" :key="i">{{
                          line
                        }}</span>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        :aria-label="
                          '编辑规则：' +
                          f.name +
                          '，' +
                          f.group +
                          '，' +
                          ruleSummary(f)
                        "
                        @click="
                          editing = f;
                          editingDraft = false;
                        "
                        >编辑规则</Button
                      >
                    </div>
                  </td>
                  <td class="source-cell">{{ f.raw }}</td>
                  <td>
                    <Button
                      variant="outline"
                      size="sm"
                      class="remove-indicator"
                      @click="remove(f)"
                      >移除同名指标</Button
                    >
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <p v-if="!fields.length" class="tool-note">
          尚未确认导入组别，或没有可识别字段。可先检查原表草稿，也可手工添加指标。
        </p>
      </section>
      <div v-if="tab === 2">
        <label class="file-check"
          ><Checkbox v-model="proseActive" />生成时采用文字匹配数据</label
        ><ProseMatching
          :key="session + '-' + editorRevision"
          :study-index="studyIndex"
          v-model="prose"
          :groups="config.groups.map((g: any) => g.name)"
          :mode="options.decimal_mode"
          :fields="fields"
          @stale="(v) => (proseStale = v)"
          @study="(v) => (studyIndex = v)"
        />
      </div>
      <section v-if="tab === 3" class="surface scientific-section">
        <div class="section-heading">
          <h2>全部字段以及来源</h2>
          <Button variant="outline" @click="review">刷新字段来源</Button>
        </div>
        <p v-if="sources?.error" role="alert" class="field-error">
          {{ sources.error }}（仍显示独立表格来源）
        </p>
        <div v-if="sources?.rows?.length" class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th v-for="key in Object.keys(sources.rows[0])" :key="key">
                  {{ sourceLabels[key] || key }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in sources.rows" :key="i">
                <td v-for="(v, k) in r" :key="k">{{ v }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section v-if="tab === 4" class="surface scientific-section">
        <div class="section-heading">
          <div>
            <h2>生成与导出</h2>
            <p>输出为模拟病例；完整 Excel 含参数、字段来源和生成校验。</p>
          </div>
          <div class="toolbar">
            <Button
              :disabled="busy || job.busy || !groupsConfirmed"
              @click="generate"
              >生成模拟数据</Button
            ><Button
              v-if="job.busy"
              variant="outline"
              @click="cancelJob('word')"
              >取消生成</Button
            >
          </div>
        </div>
        <p role="status">{{ job.message }}</p>
        <template v-if="job.result"
          ><div class="toolbar">
            <strong
              >共 {{ job.result.total }} 行 · 预览前
              {{ job.result.rows.length }} 行</strong
            ><Button
              @click="
                download(
                  job.result.name,
                  job.result.base64,
                  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                  true,
                )
              "
              >导出完整 Excel</Button
            ><Button variant="outline" @click="copyResult()"
              >复制完整数据</Button
            >
          </div>
          <div class="table-scroll result-table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th v-for="c in job.result.columns" :key="c">{{ c }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in job.result.rows" :key="i">
                  <td v-for="(v, j) in r" :key="j">{{ v }}</td>
                </tr>
              </tbody>
            </table>
          </div></template
        >
      </section></template
    >
    <div v-if="tab !== 4" class="workflow-footer">
      <span>{{ job.busy ? job.message : "配置会在页面之间保留" }}</span
      ><Button variant="outline" @click="tab = Math.max(0, tab - 1)"
        >上一步</Button
      ><Button @click="tab = Math.min(4, tab + 1)">下一步</Button>
    </div>
    <FieldRuleDialog
      :field="editing"
      :peers="fieldPeers"
      @close="editing = null"
      @save="saveField"
    /><Dialog :open="preview" @update:open="(v) => (preview = v)"
      ><DialogContent class="sm:max-w-6xl max-h-[90vh] overflow-y-auto"
        ><DialogHeader
          ><DialogTitle>Word 原表与识别草稿</DialogTitle
          ><DialogDescription
            >这里的修改将在“匹配并确认组别”后应用。</DialogDescription
          ></DialogHeader
        >
        <div class="workflow-tabs">
          <button
            v-for="(t, i) in [
              '表名与原表',
              '表格识别草稿',
              '文字识别草稿',
              '完整正文',
            ]"
            :key="t"
            :class="{ active: previewTab === i }"
            @click="previewTab = i"
          >
            {{ t }}
          </button>
        </div>
        <template v-if="draft"
          ><template v-if="previewTab === 0"
            ><div v-for="t in draft.tables" :key="t.table" class="subsection">
              <Input
                v-model="t.title"
                :aria-label="'原表 ' + t.table + ' 标题'"
              />
              <p>{{ t.orientation }} · {{ t.groups.join("、") }}</p>
              <div class="table-scroll">
                <table class="data-table">
                  <tbody>
                    <tr v-for="(r, i) in t.rows" :key="i">
                      <td v-for="(c, j) in r" :key="j">{{ c }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div></template
          >
          <div v-if="previewTab === 1" class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>原表</th>
                  <th>字段</th>
                  <th>组别</th>
                  <th>识别草稿</th>
                  <th>原文</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="f in draft.fields" :key="f._preview_key">
                  <td>{{ f.table_title }}</td>
                  <td>{{ f.name }}</td>
                  <td>{{ f.group }}</td>
                  <td>
                    <Button
                      variant="outline"
                      @click="
                        editing = f;
                        editingDraft = true;
                      "
                      >{{ ruleSummary(f) }}</Button
                    >
                  </td>
                  <td>{{ f.raw }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <ProseMatching
            v-if="previewTab === 2"
            v-model="draft.prose_document"
            :groups="names"
            :mode="options.decimal_mode"
            :fields="draft.fields"
            @stale="(v) => (draft.prose_stale = v)"
          />
          <pre v-if="previewTab === 3" class="source-prose">{{
            draft.prose_text
          }}</pre>
        </template></DialogContent
      ></Dialog
    ><Dialog
      :open="!!confirmImport"
      @update:open="
        (v) => {
          if (!v) confirmImport = null;
        }
      "
      ><DialogContent
        ><DialogHeader
          ><DialogTitle>替换当前 Word 导入？</DialogTitle
          ><DialogDescription
            >新的原表和草稿会替换当前导入会话，请先保存需要保留的配置。</DialogDescription
          ></DialogHeader
        >
        <div class="toolbar">
          <Button variant="outline" @click="confirmImport = null">取消</Button
          ><Button @click="read(confirmImport!)">替换导入</Button>
        </div></DialogContent
      ></Dialog
    >
  </div>
</template>
