<script setup lang="ts">
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
defineProps<{
  label: string;
  disabled?: boolean;
  modelValue?: number | null;
  integer?: boolean;
  min?: number;
  max?: number;
  placeholder?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [number | null] }>();
</script>
<template>
  <div class="form-field">
    <Label>{{ label }}</Label
    ><Input
      :model-value="modelValue ?? ''"
      :aria-label="label"
      type="number"
      :disabled="disabled"
      :step="integer ? 1 : 'any'"
      :min="min"
      :max="max"
      :placeholder="placeholder"
      @update:model-value="
        (v) => emit('update:modelValue', v === '' ? null : Number(v))
      "
    />
  </div>
</template>
