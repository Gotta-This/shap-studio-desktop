<script setup lang="ts">
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
const props = defineProps<{
  modelValue?: string | null;
  options: (string | { value: string; label: string })[];
  placeholder?: string;
  label?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>
<template>
  <Select
    :model-value="modelValue || '__all'"
    @update:model-value="
      (v) => emit('update:modelValue', String(v) === '__all' ? '' : String(v))
    "
    ><SelectTrigger :aria-label="label || placeholder" class="w-full"
      ><SelectValue :placeholder="placeholder" /></SelectTrigger
    ><SelectContent
      ><SelectItem
        v-for="(o, i) in props.options"
        :key="i"
        :value="(typeof o === 'string' ? o : o.value) || '__all'"
        >{{ typeof o === "string" ? o : o.label }}</SelectItem
      ></SelectContent
    ></Select
  >
</template>
