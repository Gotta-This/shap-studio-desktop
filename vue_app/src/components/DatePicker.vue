<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  CalendarDate,
  parseDate,
  today as calendarToday,
  getLocalTimeZone,
} from "@internationalized/date";
import { CalendarDays, X } from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Input } from "@/components/ui/input";
const props = defineProps<{ modelValue?: string | null; label?: string }>();
const emit = defineEmits<{ "update:modelValue": [value: string | null] }>();
const open = ref(false),
  draft = ref(""),
  error = ref("");
const selected = computed(() => {
  try {
    return props.modelValue ? parseDate(props.modelValue) : undefined;
  } catch {
    return undefined;
  }
});
watch(open, (v) => {
  if (v) {
    draft.value = props.modelValue || "";
    error.value = "";
  }
});
function commit(value: string | null) {
  emit("update:modelValue", value);
  open.value = false;
}
function enter() {
  try {
    if (!draft.value.trim()) return commit(null);
    const parsed = parseDate(draft.value.trim());
    if (parsed.toString() !== draft.value.trim()) throw Error();
    commit(parsed.toString());
  } catch {
    error.value = "请输入有效日期，例如 2028-02-29。";
  }
}
function choose(value: unknown) {
  if (value instanceof CalendarDate) commit(value.toString());
  else if (value) commit(String(value));
}
</script>
<template>
  <Popover v-model:open="open"
    ><PopoverTrigger as-child
      ><Button
        type="button"
        variant="outline"
        :aria-label="label || '选择日期'"
        class="date-trigger justify-start font-normal"
        :class="{ 'text-muted-foreground': !modelValue }"
        ><CalendarDays :size="15" /><span>{{
          modelValue || "选择日期"
        }}</span></Button
      ></PopoverTrigger
    ><PopoverContent align="start" class="w-auto p-3" :side-offset="6"
      ><form @submit.prevent="enter">
        <Input
          v-model="draft"
          aria-label="输入日期"
          placeholder="YYYY-MM-DD"
          @input="error = ''"
        />
        <p v-if="error" class="field-error">{{ error }}</p>
      </form>
      <Calendar
        :model-value="selected"
        :default-placeholder="selected"
        locale="zh-CN"
        layout="month-and-year"
        :week-starts-on="1"
        initial-focus
        @update:model-value="choose"
      />
      <div class="calendar-footer">
        <Button
          size="sm"
          variant="outline"
          @click="commit(calendarToday(getLocalTimeZone()).toString())"
          >今天</Button
        ><Button
          size="sm"
          variant="outline"
          @click="
            commit(
              calendarToday(getLocalTimeZone()).add({ days: 1 }).toString(),
            )
          "
          >明天</Button
        ><Button
          size="sm"
          variant="outline"
          class="ml-auto"
          @click="commit(null)"
          ><X :size="13" />清除</Button
        >
      </div></PopoverContent
    ></Popover
  >
</template>
