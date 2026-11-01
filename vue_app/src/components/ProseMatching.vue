<script setup lang="ts">
import { computed, ref } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import SelectField from "./SelectField.vue";
import { api, download } from "@/lib/api";
import { clone } from "@/lib/scientific";
const props = defineProps<{
    modelValue: any;
    groups: string[];
    mode: string;
    fields: any[];
  }>(),
  emit = defineEmits<{
    "update:modelValue": [any];
    stale: [boolean];
    study: [number];
  }>();
const autoGroups = ref(true),
  customGroups = ref(props.groups.join("、"));
const text = ref(props.modelValue?.source_text || ""),
  index = ref("0"),
  error = ref(""),
  selected = ref<any>(null),
  busy = ref(false),
  file = ref<HTMLInputElement>();
const study = computed(() => props.modelValue?.studies?.[Number(index.value)]);
async function parse() {
  busy.value = true;
  error.value = "";
  try {
    const doc = await api("tool.word.prose.parse", {
      text: text.value,
      groups: autoGroups.value
        ? undefined
        : customGroups.value
            .split(/[、,，]/)
            .map((x) => x.trim())
            .filter(Boolean),
      decimal_mode: props.mode,
    });
    emit("update:modelValue", doc);
    emit("stale", false);
    index.value = "0";
    emit("study", 0);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function edit(fn: (d: any) => void) {
  const d = clone(props.modelValue);
  fn(d.studies[Number(index.value)]);
  emit("update:modelValue", d);
}
function ensureCell(v: number, g: string) {
  edit((s) => {
    s.variables[v].cells[g] = {
      mean: null,
      sd: null,
      digits: 0,
      counts: Object.fromEntries(
        (s.variables[v].labels || []).map((k: string) => [k, null]),
      ),
      issues: [],
      evidence: [],
    };
  });
}
function addVariable() {
  edit((s) => {
    s.variables.push({
      name: "新变量 " + (s.variables.length + 1),
      kind: "mean_sd",
      unit: "",
      labels: [],
      cells: Object.fromEntries(
        s.groups.map((g: any) => [
          g.name,
          {
            mean: null,
            sd: null,
            digits: 0,
            counts: {},
            evidence: [],
            issues: [],
          },
        ]),
      ),
    });
  });
}
function labels(vi: number, value: any) {
  edit((s) => {
    const v = s.variables[vi];
    v.labels = String(value)
      .split(/[,，、]/)
      .map((x) => x.trim())
      .filter(Boolean);
    for (const c of Object.values(v.cells) as any[]) {
      c.counts = Object.fromEntries(
        v.labels.map((k: string) => [k, c.counts?.[k] ?? null]),
      );
      c.reviewed = false;
    }
  });
}
function cell(v: number, g: string, k: string, value: any) {
  edit((s) => {
    s.variables[v].cells[g][k] = value === "" ? null : Number(value);
    s.variables[v].cells[g].reviewed = false;
  });
  selected.value = { v, g };
}
function count(v: number, g: string, label: string, value: any) {
  edit((s) => {
    s.variables[v].cells[g].counts[label] = value === "" ? null : Number(value);
    s.variables[v].cells[g].reviewed = false;
  });
  selected.value = { v, g };
}
async function confirm() {
  if (!selected.value) return;
  const { v, g } = selected.value;
  try {
    const cell = await api("tool.word.prose.confirm", {
      variable: study.value.variables[v].name,
      group: g,
      cell: activeCell.value,
      fields: props.fields,
    });
    edit((s) => (s.variables[v].cells[g] = cell));
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function load(e: Event) {
  try {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    const d = JSON.parse(await f.text());
    if (!Array.isArray(d.studies)) throw Error("这不是文字匹配配置。");
    text.value = d.source_text || "";
    emit("update:modelValue", d);
    emit("stale", false);
    index.value = "0";
  } catch (e) {
    error.value = (e as Error).message;
  }
}
const activeCell = computed(
  () =>
    selected.value &&
    study.value?.variables[selected.value.v]?.cells[selected.value.g],
);
</script>
<template>
  <section class="surface scientific-section">
    <div class="section-heading">
      <div>
        <h2>文字匹配</h2>
        <p>识别一般资料后逐格核对；表格与正文分开保存，生成时合并。</p>
      </div>
      <div class="toolbar">
        <Button variant="outline" @click="file?.click()">载入文字配置</Button
        ><Button
          variant="outline"
          :disabled="!modelValue"
          @click="
            download(
              '文字匹配.json',
              JSON.stringify(modelValue, null, 2),
              'application/json',
            )
          "
          >保存文字配置</Button
        >
      </div>
    </div>
    <input
      ref="file"
      hidden
      type="file"
      accept=".json"
      @change="load"
    /><Textarea
      :model-value="text"
      aria-label="一般资料原文"
      rows="5"
      placeholder="粘贴包含组别、例数、均数或分类计数的一般资料段落"
      @update:model-value="
        (v) => {
          text = String(v);
          if (props.modelValue) {
            const d = clone(props.modelValue);
            d.source_text = text;
            emit('update:modelValue', d);
          }
          emit('stale', true);
        }
      "
    />
    <div class="toolbar">
      <label class="file-check"
        ><Checkbox v-model="autoGroups" />自动识别正文组别</label
      ><Input
        v-if="!autoGroups"
        v-model="customGroups"
        aria-label="正文自定义组别"
        placeholder="组别以顿号分隔"
      />
    </div>
    <div class="toolbar">
      <Button :disabled="busy || !text.trim()" @click="parse">{{
        busy ? "正在识别…" : "识别 / 重新识别文字"
      }}</Button
      ><SelectField
        v-if="modelValue?.studies?.length > 1"
        v-model="index"
        :options="
          modelValue.studies.map((s: any, i: number) => ({
            value: String(i),
            label: s.title || '研究 ' + (i + 1),
          }))
        "
        label="研究段落"
        @update:model-value="
          (v) => {
            emit('study', Number(v));
            selected = null;
          }
        "
      />
    </div>
    <p v-if="error" role="alert" class="field-error">{{ error }}</p>
    <template v-if="study"
      ><Button variant="outline" @click="addVariable">添加文字变量</Button>
      <div class="table-scroll">
        <table class="data-table editable-table prose-table">
          <thead>
            <tr>
              <th>变量 / 类别 / 参数</th>
              <th>类型</th>
              <th>单位</th>
              <th v-for="g in study.groups" :key="g.name">{{ g.name }}</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>例数</td>
              <td>样本量</td>
              <td>例</td>
              <td v-for="g in study.groups" :key="g.name">
                <Input
                  type="number"
                  :aria-label="g.name + ' 文字例数'"
                  :model-value="g.n ?? ''"
                  @update:model-value="
                    (v) =>
                      edit((s) => {
                        const x = s.groups.find((a: any) => a.name === g.name);
                        x.n = Number(v);
                        x.issues = [];
                      })
                  "
                />
              </td>
              <td />
            </tr>
            <template v-for="(v, vi) in study.variables" :key="vi"
              ><tr>
                <td>
                  <Input
                    :model-value="v.name"
                    aria-label="文字变量名称"
                    @update:model-value="
                      (x) => edit((s) => (s.variables[vi].name = String(x)))
                    "
                  />
                </td>
                <td>
                  <SelectField
                    :model-value="v.kind"
                    :options="[
                      { value: 'mean_sd', label: '均数±标准差' },
                      { value: 'quantile', label: '中位数(Q1,Q3)' },
                      { value: 'category', label: '分类计数' },
                      { value: 'range', label: '范围（待核对）' },
                      { value: 'unknown', label: '待核对' },
                    ]"
                    label="文字变量类型"
                    @update:model-value="
                      (x) => edit((s) => (s.variables[vi].kind = x))
                    "
                  />
                </td>
                <td>
                  <Input
                    v-if="v.kind === 'category'"
                    :model-value="v.labels.join('、')"
                    aria-label="文字类别标签"
                    @update:model-value="(x) => labels(Number(vi), x)"
                  />
                  <Input
                    :model-value="v.unit || ''"
                    aria-label="文字变量单位"
                    @update:model-value="
                      (x) => edit((s) => (s.variables[vi].unit = String(x)))
                    "
                  />
                </td>
                <td
                  v-for="g in study.groups"
                  :key="g.name"
                  :class="{ 'needs-review': v.cells[g.name]?.issues?.length }"
                  @click="selected = { v: vi, g: g.name }"
                >
                  <template v-if="v.cells[g.name]"
                    ><div v-if="v.kind === 'category'" class="cell-stack">
                      <label v-for="label in v.labels" :key="label"
                        >{{ label
                        }}<Input
                          type="number"
                          :aria-label="v.name + ' ' + g.name + ' ' + label"
                          :model-value="v.cells[g.name].counts?.[label] ?? ''"
                          @update:model-value="
                            (x) => count(Number(vi), g.name, label, x)
                          "
                      /></label>
                    </div>
                    <div v-else class="cell-stack">
                      <label
                        v-for="key in v.kind === 'mean_sd'
                          ? ['mean', 'sd', 'lower', 'upper', 'digits']
                          : v.kind === 'quantile'
                            ? ['q1', 'median', 'q3', 'lower', 'upper', 'digits']
                            : ['lower', 'upper']"
                        :key="key"
                        >{{
                          (
                            {
                              mean: "均数",
                              sd: "标准差",
                              digits: "小数位",
                              q1: "Q1",
                              median: "中位数",
                              q3: "Q3",
                              lower: "下限",
                              upper: "上限",
                            } as any
                          )[key]
                        }}<Input
                          type="number"
                          step="any"
                          :aria-label="v.name + ' ' + g.name + ' ' + key"
                          :model-value="v.cells[g.name][key] ?? ''"
                          @update:model-value="
                            (x) => cell(Number(vi), g.name, key, x)
                          "
                      /></label>
                    </div>
                    <small>{{
                      v.cells[g.name].reviewed
                        ? "已人工确认"
                        : (v.cells[g.name].issues || []).join("；")
                    }}</small></template
                  ><Button
                    v-else
                    variant="outline"
                    @click="ensureCell(Number(vi), g.name)"
                    >补全本组数值</Button
                  >
                </td>
                <td>
                  <Button
                    variant="ghost"
                    @click="edit((s) => s.variables.splice(vi, 1))"
                    >移除变量</Button
                  >
                </td>
              </tr></template
            >
          </tbody>
        </table>
      </div>
      <div v-if="study.issues?.length" class="tool-note">
        <p>{{ study.issues.join("；") }}</p>
        <Button variant="outline" @click="edit((s) => (s.issues = []))"
          >已核对研究级问题</Button
        >
      </div>
      <div v-if="activeCell" class="tool-note">
        <strong>当前格原文证据</strong>
        <p>
          {{
            activeCell.evidence?.map((e: any) => e.raw).join("；") ||
            "没有自动定位的证据，请对照完整原文核对。"
          }}
        </p>
        <p>{{ activeCell.issues?.join("；") }}</p>
        <Button variant="outline" @click="confirm"
          >确认当前格（包括表文冲突）</Button
        >
      </div>
      <div v-if="study.unparsed?.length" class="tool-note">
        <strong>未识别内容</strong>
        <pre>{{ study.unparsed }}</pre>
        <label class="file-check"
          ><Checkbox
            :model-value="!!study.unparsed_reviewed"
            @update:model-value="
              (v) => edit((s) => (s.unparsed_reviewed = !!v))
            "
          />已逐项核对未识别内容</label
        >
      </div></template
    >
    <p v-else class="tool-note">
      尚无文字匹配数据；不使用正文资料时，可以直接使用表格匹配生成。
    </p>
  </section>
</template>
