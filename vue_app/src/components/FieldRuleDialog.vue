<script setup lang="ts">
import { ref, watch } from "vue";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import SelectField from "./SelectField.vue";
import NumberField from "./NumberField.vue";
import RowsEditor from "./RowsEditor.vue";
import { api } from "@/lib/api";
import { clone, fieldTypes } from "@/lib/scientific";
const props = defineProps<{ field: any; peers?: any[] }>(),
  emit = defineEmits<{
    close: [];
    save: [field: any, sync: boolean, peers: any[]];
  }>();
const form = ref<any>({}),
  sync = ref(true),
  error = ref(""),
  saving = ref(false);
watch(
  () => props.field,
  (value) => {
    if (value) {
      form.value = clone({ ...value, kind: value.kind || "mean_sd" });
      sync.value = value.source_kind !== "ungrouped_table";
      error.value = "";
    }
  },
  { immediate: true },
);
async function kind(value: string) {
  try {
    form.value = await api("tool.word.convert", {
      field: form.value,
      kind: value,
    });
    error.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  }
}
function categories() {
  return (form.value.labels || []).map((label: any, i: number) => ({
    label,
    weight: form.value.weights?.[i] ?? null,
  }));
}
function setCategories(rows: any[]) {
  form.value.labels = rows.map((r) =>
    form.value.kind === "binary01" ? Number(r.label) : r.label,
  );
  form.value.weights = rows.map((r) => r.weight);
}
async function save() {
  if (saving.value) return;
  error.value = "";
  saving.value = true;
  try {
    const saved = await api("tool.word.field.save", {
      field: form.value,
      peers: sync.value ? props.peers || [] : [],
    });
    emit("save", saved.field, sync.value, saved.peers);
    emit("close");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    saving.value = false;
  }
}
</script>
<template>
  <Dialog
    :open="!!field"
    @update:open="
      (v) => {
        if (!v && !saving) emit('close');
      }
    "
    ><DialogContent class="sm:max-w-2xl max-h-[90vh] overflow-y-auto"
      ><DialogHeader
        ><DialogTitle>编辑字段 · {{ field?.name }}</DialogTitle
        ><DialogDescription
          >{{ field?.group }} ·
          各行数值、比例与确认状态独立保存</DialogDescription
        ></DialogHeader
      >
      <div class="tool-note">
        Word 原文：{{ field?.raw || "手工配置" }}<br />原表头：{{
          field?.header_path?.join(" → ") || field?.name
        }}
      </div>
      <div class="form-field">
        <Label>分类 / 上级表头</Label
        ><Input v-model="form.classification" aria-label="分类 / 上级表头" />
      </div>
      <SelectField
        :model-value="form.kind"
        :options="fieldTypes"
        label="字段数据类型"
        @update:model-value="kind"
      />
      <div
        v-if="['mean_sd', 'quantile'].includes(form.kind)"
        class="two-columns"
      >
        <template v-if="form.kind === 'mean_sd'"
          ><NumberField v-model="form.mean" label="字段均数" /><NumberField
            v-model="form.sd"
            label="字段标准差" /></template
        ><template v-else
          ><NumberField
            v-model="form.q1"
            label="第 1 四分位数 Q1" /><NumberField
            v-model="form.median"
            label="中位数" /><NumberField
            v-model="form.q3"
            label="第 3 四分位数 Q3" /></template
        ><NumberField
          v-model="form.lower"
          label="模拟下限（均数型可留空）"
        /><NumberField
          v-model="form.upper"
          label="模拟上限（均数型可留空）"
        /><NumberField
          v-model="form.digits"
          label="小数位（0～4）"
          integer
          :min="0"
          :max="4"
        /><SelectField
          v-if="form.kind === 'mean_sd'"
          v-model="form.parity"
          :options="[
            { value: 'any', label: '任意数值' },
            { value: 'odd', label: '奇数' },
            { value: 'even', label: '偶数' },
          ]"
          label="字段数值类型"
        />
      </div>
      <RowsEditor
        v-else-if="
          ['binary', 'gender', 'yesno', 'binary01', 'category'].includes(
            form.kind,
          )
        "
        :model-value="categories()"
        :columns="[
          { key: 'label', label: '输出类别', text: true },
          { key: 'weight', label: '占比 %' },
        ]"
        title="类别与比例"
        @update:model-value="setCategories"
      />
      <div v-else-if="form.kind === 'derived'" class="form-field">
        <Label>来源字段</Label><Input v-model="form.from_field" /><Label
          >计为有效的类别（逗号分隔）</Label
        ><Input
          :model-value="form.positive_labels?.join('，') || ''"
          @update:model-value="
            (v) =>
              (form.positive_labels = String(v)
                .split(/[,，、]/)
                .filter(Boolean))
          "
        />
      </div>
      <p v-if="form.kind === 'quantile'" class="tool-note">
        请确认括号内为 Q1、Q3。尾部上下限是模拟假设，可修改后确认。
      </p>
      <p v-if="form.review_note" class="field-error">{{ form.review_note }}</p>
      <label v-if="field?.source_kind !== 'ungrouped_table'" class="file-check"
        ><Checkbox
          v-model="sync"
        />同步本表同名字段的类型与类别；其他组数值和确认状态不变</label
      >
      <p v-if="error" role="alert" class="field-error">{{ error }}</p>
      <DialogFooter
        ><Button variant="outline" :disabled="saving" @click="emit('close')"
          >取消</Button
        ><Button :disabled="saving" @click="save">{{
          saving ? "正在保存…" : "确认并应用"
        }}</Button></DialogFooter
      ></DialogContent
    ></Dialog
  >
</template>
