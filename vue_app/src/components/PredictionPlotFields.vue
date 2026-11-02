<script setup lang="ts">
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import NumberField from "./NumberField.vue";
import SelectField from "./SelectField.vue";
import type { PlotField } from "@/lib/predictionPlotFields";
defineProps<{
  value: Record<string, any>;
  fields: PlotField[];
  prefix?: string;
}>();
function numbers(value: string | number) {
  return String(value)
    .split(/[,，\s]+/)
    .filter(Boolean)
    .map(Number);
}
</script>
<template>
  <div class="plot-fields">
    <div
      v-for="f in fields"
      :key="f.key"
      :class="['plot-field', { 'plot-field-wide': f.kind === 'textarea' }]"
    >
      <NumberField
        v-if="f.kind === 'number'"
        v-model="value[f.key]"
        :label="f.label"
        :aria-label="(prefix || '') + f.label"
        :min="f.min"
        :max="f.max"
        :integer="f.integer"
      />
      <label v-else-if="f.kind === 'boolean'" class="plot-check"
        ><Checkbox
          v-model="value[f.key]"
          :aria-label="(prefix || '') + f.label"
        />{{ f.label }}</label
      >
      <template v-else
        ><label>{{ f.label }}</label>
        <SelectField
          v-if="f.kind === 'select'"
          v-model="value[f.key]"
          :options="f.options || []"
          :label="(prefix || '') + f.label"
        />
        <div v-else-if="f.kind === 'color'" class="plot-color">
          <input
            type="color"
            v-model="value[f.key]"
            :aria-label="(prefix || '') + f.label + '选色'"
          /><Input
            v-model="value[f.key]"
            :aria-label="(prefix || '') + f.label"
          />
        </div>
        <textarea
          v-else-if="f.kind === 'textarea'"
          v-model="value[f.key]"
          :aria-label="(prefix || '') + f.label"
          rows="2"
        />
        <Input
          v-else-if="f.kind === 'list'"
          :model-value="(value[f.key] || []).join(', ')"
          :aria-label="(prefix || '') + f.label"
          @update:model-value="value[f.key] = numbers($event)"
        />
        <Input
          v-else
          v-model="value[f.key]"
          :aria-label="(prefix || '') + f.label"
        />
      </template>
    </div>
  </div>
</template>
<style scoped>
.plot-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.plot-field {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12px;
}
.plot-field-wide {
  grid-column: 1/-1;
}
.plot-field > label {
  font-weight: 500;
}
.plot-check {
  display: flex;
  gap: 8px;
  align-items: center;
  min-height: 64px;
}
.plot-color {
  display: flex;
  gap: 8px;
  align-items: center;
}
.plot-color input[type="color"] {
  width: 36px;
  height: 34px;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 6px;
  flex: none;
}
.plot-field textarea {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 8px;
  background: var(--background);
  resize: vertical;
}
.plot-field :deep(.form-field) {
  gap: 7px;
}
.plot-field :deep(label) {
  font-size: 12px;
}
.plot-field :deep(input) {
  font-size: 12px;
}
@media (max-width: 900px) {
  .plot-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 560px) {
  .plot-fields {
    grid-template-columns: 1fr;
  }
}
</style>
