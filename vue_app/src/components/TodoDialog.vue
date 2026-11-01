<script setup lang="ts">
import { reactive, ref, watch } from "vue";
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
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import DatePicker from "./DatePicker.vue";
import SelectField from "./SelectField.vue";
import {
  api,
  state,
  refresh,
  notify,
  type Todo,
  type Material,
} from "@/lib/api";
const props = defineProps<{
    open: boolean;
    todo?: Todo | null;
    taskId?: string;
    files?: Material[];
  }>(),
  emit = defineEmits<{ "update:open": [boolean]; saved: [] }>();
const form = reactive({
    text: "",
    priority: "normal",
    due_date: null as string | null,
    task_id: "",
    file_ids: [] as string[],
  }),
  busy = ref(false),
  error = ref("");
watch(
  () => props.open,
  (v) => {
    if (v) {
      Object.assign(form, {
        text: props.todo?.text || "",
        priority: props.todo?.priority || "normal",
        due_date: props.todo?.due_date || null,
        task_id: props.todo?.task_id || props.taskId || "",
        file_ids: [...(props.todo?.file_ids || [])],
      });
      error.value = "";
    }
  },
);
async function save() {
  busy.value = true;
  try {
    const payload = {
      text: form.text,
      priority: form.priority,
      due_date: form.due_date,
      ...(form.task_id ? { file_ids: form.file_ids } : {}),
    };
    await api(
      "todo.save",
      props.todo
        ? { ...payload, id: props.todo.id }
        : { ...payload, task_id: form.task_id || null },
    );
    await refresh();
    notify("下一步工作已保存。");
    emit("update:open", false);
    emit("saved");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <Dialog
    :open="open"
    @update:open="
      (v) => {
        if (!busy) emit('update:open', v);
      }
    "
    ><DialogContent class="sm:max-w-lg"
      ><DialogHeader
        ><DialogTitle>{{ todo ? "编辑下一步工作" : "新增待办" }}</DialogTitle
        ><DialogDescription
          >明确要做的事，完成后再手动勾选。</DialogDescription
        ></DialogHeader
      >
      <form @submit.prevent="save" class="dialog-form">
        <div class="form-field">
          <Label for="todo-text">下一步工作 *</Label
          ><Input
            id="todo-text"
            v-model="form.text"
            required
            maxlength="300"
            placeholder="例如：核对审稿意见"
          />
        </div>
        <div v-if="!todo && !taskId" class="form-field">
          <Label>所属任务</Label
          ><SelectField
            v-model="form.task_id"
            :options="[
              { value: '', label: '个人待办，不关联稿件' },
              ...state.tasks.map((t) => ({
                value: t.id,
                label: t.client + ' / ' + t.name,
              })),
            ]"
            label="待办所属任务"
          />
        </div>
        <div class="two-columns">
          <div class="form-field">
            <Label>优先级</Label
            ><SelectField
              v-model="form.priority"
              :options="[
                { value: 'high', label: '高' },
                { value: 'normal', label: '普通' },
                { value: 'low', label: '低' },
              ]"
              label="待办优先级"
            />
          </div>
          <div class="form-field">
            <Label>截止日期</Label
            ><DatePicker v-model="form.due_date" label="待办截止日期" />
          </div>
        </div>
        <div v-if="files?.length" class="form-field">
          <Label>关联材料</Label
          ><label v-for="file in files" :key="file.id" class="file-check"
            ><Checkbox
              :model-value="form.file_ids.includes(file.id)"
              @update:model-value="
                (v) =>
                  (form.file_ids = v
                    ? [...form.file_ids, file.id]
                    : form.file_ids.filter((id) => id !== file.id))
              "
            />{{ file.original_name }}</label
          >
        </div>
        <p v-if="error" role="alert" class="field-error">{{ error }}</p>
        <DialogFooter
          ><Button
            type="button"
            variant="outline"
            :disabled="busy"
            @click="emit('update:open', false)"
            >取消</Button
          ><Button :disabled="busy" type="submit">{{
            busy ? "正在保存…" : "保存待办"
          }}</Button></DialogFooter
        >
      </form></DialogContent
    ></Dialog
  >
</template>
