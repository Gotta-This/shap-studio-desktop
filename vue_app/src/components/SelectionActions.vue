<script setup lang="ts">
import { computed } from "vue";
import { Button } from "@/components/ui/button";
import { changeSelection, type SelectionMode } from "@/lib/selection";
const props = withDefaults(
  defineProps<{
    modelValue?: readonly string[];
    items: readonly string[];
    label: string;
    scope?: string;
    disabled?: boolean;
  }>(),
  { scope: "全部项目", disabled: false, modelValue: () => [] },
);
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>();
const ids = computed(() => [...new Set(props.items)]);
const count = computed(
  () => ids.value.filter((id) => props.modelValue.includes(id)).length,
);
const outside = computed(
  () => new Set(props.modelValue.filter((id) => !ids.value.includes(id))).size,
);
function apply(mode: SelectionMode) {
  if (!props.disabled)
    emit(
      "update:modelValue",
      changeSelection(props.modelValue, ids.value, mode),
    );
}
</script>
<template>
  <div class="selection-actions" role="group" :aria-label="label + '批量选择'">
    <span class="selection-count"
      >{{ label }} · {{ scope }} · 已选 {{ count }}/{{ ids.length
      }}<span v-if="outside">（范围外另选 {{ outside }} 项）</span></span
    >
    <div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        :aria-label="label + '全选'"
        :disabled="disabled || !ids.length || count === ids.length"
        @click="apply('all')"
        >全选</Button
      >
      <Button
        type="button"
        variant="outline"
        size="sm"
        :aria-label="label + '全不选'"
        :disabled="disabled || !count"
        @click="apply('none')"
        >全不选</Button
      >
      <Button
        type="button"
        variant="outline"
        size="sm"
        :aria-label="label + '反选'"
        :disabled="disabled || !ids.length"
        @click="apply('invert')"
        >反选</Button
      >
    </div>
  </div>
</template>
<style scoped>
.selection-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}
.selection-count {
  font-size: 12px;
  color: var(--muted-foreground);
}
.selection-actions > div {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
