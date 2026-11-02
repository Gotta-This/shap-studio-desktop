<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2 } from "lucide-vue-next";
import { clone } from "@/lib/scientific";
const props = defineProps<{
    modelValue: any[];
    columns: { key: string; label: string; text?: boolean }[];
    title?: string;
  }>(),
  emit = defineEmits<{ "update:modelValue": [any[]] }>();
function change(i: number, key: string, value: any, text?: boolean) {
  const rows = clone(props.modelValue);
  rows[i][key] = text ? String(value) : value === "" ? null : Number(value);
  emit("update:modelValue", rows);
}
function add() {
  emit("update:modelValue", [
    ...props.modelValue,
    Object.fromEntries(
      props.columns.map((c) => [c.key, c.text ? "新类别" : 0]),
    ),
  ]);
}
</script>
<template>
  <div class="rows-editor">
    <h3 v-if="title">{{ title }}</h3>
    <div class="table-scroll">
      <table class="data-table editable-table">
        <thead>
          <tr>
            <th v-for="c in columns" :key="c.key">{{ c.label }}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in modelValue" :key="i">
            <td v-for="c in columns" :key="c.key">
              <Input
                :model-value="row[c.key] ?? ''"
                :aria-label="(title || '列表') + ' ' + c.label + ' ' + (i + 1)"
                :type="c.text ? 'text' : 'number'"
                step="any"
                @update:model-value="(v) => change(i, c.key, v, c.text)"
              />
            </td>
            <td>
              <Button
                variant="outline"
                size="icon"
                :aria-label="'删除第 ' + (i + 1) + ' 行'"
                @click="
                  emit(
                    'update:modelValue',
                    modelValue.filter((_, index) => index !== i),
                  )
                "
                ><Trash2 :size="13"
              /></Button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <Button variant="outline" size="sm" @click="add"
      ><Plus :size="13" />添加一行</Button
    >
  </div>
</template>
