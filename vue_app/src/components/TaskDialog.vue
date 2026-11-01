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
import { Textarea } from "@/components/ui/textarea";
import SelectField from "./SelectField.vue";
import DatePicker from "./DatePicker.vue";
import { api, state, refresh, notify, type Task } from "@/lib/api";
const props = defineProps<{ open: boolean; task?: Task | null }>(),
  emit = defineEmits<{ "update:open": [boolean]; saved: [id: string] }>();
const form = reactive({
    name: "",
    client: "",
    tags: "",
    status: "进行中",
    deadline: null as string | null,
    notes: "",
    first_todo: "整理稿件材料",
    todo_deadline: null as string | null,
    priority: "normal",
  }),
  busy = ref(false),
  error = ref("");
watch(
  () => props.open,
  (v) => {
    if (v) {
      const t = props.task;
      Object.assign(form, {
        name: t?.name || "",
        client: t?.client || "",
        tags: t?.tags.join("，") || "",
        status: t?.status || "进行中",
        deadline: t?.due_date || null,
        notes: t?.notes || "",
        first_todo: "整理稿件材料",
        todo_deadline: null,
        priority: "normal",
      });
      error.value = "";
    }
  },
);
async function save() {
  busy.value = true;
  error.value = "";
  try {
    const payload = {
      name: form.name,
      client: form.client,
      tags: form.tags,
      status: form.status,
      deadline: form.deadline,
      notes: form.notes,
    };
    const id = props.task
      ? (await api("task.update", { id: props.task.id, ...payload }),
        props.task.id)
      : await api<string>("task.create", {
          ...payload,
          first_todo: form.first_todo,
          todo_deadline: form.todo_deadline,
          priority: form.priority,
        });
    await refresh();
    notify(
      props.task ? "任务信息和目录已同步。" : "任务目录与第一项待办已创建。",
    );
    emit("update:open", false);
    emit("saved", id);
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
    ><DialogContent class="sm:max-w-[600px] max-h-[90vh] overflow-y-auto"
      ><DialogHeader
        ><DialogTitle>{{ task ? "编辑任务信息" : "新建稿件任务" }}</DialogTitle
        ><DialogDescription>{{
          task
            ? "修改客户或任务名称会同步重命名实际目录，创建日期保持不变。"
            : "建立本地任务目录，材料与下一步工作从这里开始。"
        }}</DialogDescription></DialogHeader
      >
      <form @submit.prevent="save" class="dialog-form">
        <div class="form-field">
          <Label for="task-client">客户 / 甲方</Label
          ><Input
            id="task-client"
            v-model="form.client"
            placeholder="例如：张老师；留空归入未分类"
          />
        </div>
        <div class="form-field">
          <Label for="task-name">任务名称 <span>*</span></Label
          ><Input
            id="task-name"
            v-model="form.name"
            required
            maxlength="100"
            placeholder="例如：冠心病降脂论文 · 第二轮返修"
          />
        </div>
        <div class="form-field">
          <Label for="task-tags">标签</Label
          ><Input
            id="task-tags"
            v-model="form.tags"
            placeholder="用逗号分隔，例如：预测模型，返修"
          />
        </div>
        <div class="two-columns">
          <div class="form-field">
            <Label>任务状态</Label
            ><SelectField
              v-model="form.status"
              :options="state.statuses"
              label="任务状态"
            />
          </div>
          <div class="form-field">
            <Label>截止日期</Label
            ><DatePicker v-model="form.deadline" label="任务截止日期" />
          </div>
        </div>
        <div v-if="!task" class="form-field">
          <Label for="first-todo">第一项待办 <span>*</span></Label
          ><Input
            id="first-todo"
            v-model="form.first_todo"
            required
            placeholder="例如：核对审稿意见"
          /><small
            >完成状态由你手动确认，导入新材料不会撤回已完成的工作。</small
          >
        </div>
        <div v-if="!task" class="two-columns">
          <div class="form-field">
            <Label>第一项待办截止日期</Label
            ><DatePicker
              v-model="form.todo_deadline"
              label="第一项待办截止日期"
            /><small>留空时沿用任务截止日期</small>
          </div>
          <div class="form-field">
            <Label>第一项待办优先级</Label
            ><SelectField
              v-model="form.priority"
              :options="[
                { value: 'high', label: '高' },
                { value: 'normal', label: '普通' },
                { value: 'low', label: '低' },
              ]"
              label="第一项待办优先级"
            />
          </div>
        </div>
        <div class="form-field">
          <Label for="task-notes">备注</Label
          ><Textarea
            id="task-notes"
            v-model="form.notes"
            placeholder="记录交付要求或需要注意的事项…"
            rows="3"
          />
        </div>
        <div class="directory-hint">
          <small>目录结构</small
          ><code
            >{{ form.client || "未分类" }} /
            {{ task?.created_date || "YYYYMMDD" }} /
            {{ form.name || "任务名称" }}</code
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
          ><Button type="submit" :disabled="busy">{{
            busy ? "正在保存…" : task ? "保存修改" : "创建任务"
          }}</Button></DialogFooter
        >
      </form></DialogContent
    ></Dialog
  >
</template>
