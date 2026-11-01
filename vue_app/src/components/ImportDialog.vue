<script setup lang="ts">
import { reactive, ref, watch, computed } from "vue";
import { Upload, File, X, FolderOpen } from "lucide-vue-next";
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
import SelectField from "./SelectField.vue";
import DatePicker from "./DatePicker.vue";
import {
  api,
  state,
  refresh,
  notify,
  upload,
  desktop,
  bytes,
  type Material,
} from "@/lib/api";
const props = defineProps<{
    open: boolean;
    taskId?: string;
    archive?: Material[];
  }>(),
  emit = defineEmits<{ "update:open": [boolean]; saved: [] }>();
const rows = ref<
    {
      name: string;
      size?: number;
      category: string;
      file?: File;
      path?: string;
      id?: string;
    }[]
  >([]),
  busy = ref(false),
  error = ref(""),
  input = ref<HTMLInputElement>();
const form = reactive({
  task_id: "",
  todo_text: "",
  deadline: null as string | null,
});
watch(
  () => props.open,
  (v) => {
    if (v) {
      rows.value = (props.archive || []).map((f) => ({
        name: f.original_name,
        size: f.size,
        category: f.category || "原稿",
        id: f.id,
      }));
      Object.assign(form, {
        task_id: props.taskId || "",
        todo_text: "",
        deadline: null,
      });
      error.value = "";
    }
  },
);
function add(files: FileList | null) {
  if (files)
    rows.value.push(
      ...Array.from(files).map((file) => ({
        name: file.name,
        size: file.size,
        category: "原稿",
        file,
      })),
    );
}
async function pick() {
  if (!desktop) {
    input.value?.click();
    return;
  }
  const { open } = await import("@tauri-apps/plugin-dialog");
  const paths = await open({ multiple: true, title: "选择稿件材料" });
  if (paths)
    rows.value.push(
      ...(Array.isArray(paths) ? paths : [paths]).map((path) => ({
        name: path.split(/[\\/]/).pop() || path,
        category: "原稿",
        path,
      })),
    );
}
const valid = computed(
  () => rows.value.length > 0 && (!props.archive || form.task_id),
);
async function save() {
  busy.value = true;
  error.value = "";
  try {
    if (props.archive)
      await api("files.archive", {
        ids: rows.value.map((r) => r.id),
        task_id: form.task_id,
        categories: rows.value.map((r) => r.category),
        todo_text: form.todo_text,
        deadline: form.deadline,
      });
    else {
      const result = await api<{ received: number; duplicates: string[] }>(
        "files.import",
        {
          task_id: form.task_id || null,
          paths: rows.value.filter((r) => r.path).map((r) => r.path),
          uploads: await upload(
            rows.value.flatMap((r) => (r.file ? [r.file] : [])),
          ),
          categories: form.task_id
            ? rows.value.map((r) => r.category)
            : undefined,
          todo_text: form.task_id ? form.todo_text : "",
          deadline: form.deadline,
        },
      );
      notify(
        `已接收 ${result.received} 个新文件${result.duplicates.length ? "，复用 " + result.duplicates.length + " 个重复材料" : ""}。`,
      );
    }
    await refresh();
    if (props.archive) notify("材料已归档，可在操作记录中撤销符合条件的归档。");
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
    ><DialogContent class="sm:max-w-[660px] max-h-[90vh] overflow-y-auto"
      ><DialogHeader
        ><DialogTitle>{{ archive ? "归档材料" : "导入材料" }}</DialogTitle
        ><DialogDescription>{{
          archive
            ? "选择归属任务和分类，将材料移动到任务目录。"
            : "外部原件保持不变，工作空间接收副本并自动检查重复内容。"
        }}</DialogDescription></DialogHeader
      >
      <form @submit.prevent="save" class="dialog-form">
        <div class="form-field">
          <Label>归属任务</Label
          ><SelectField
            v-model="form.task_id"
            :options="[
              ...(!archive
                ? [{ value: '', label: '未分类收件箱，稍后归档' }]
                : []),
              ...state.tasks.map((t) => ({
                value: t.id,
                label: t.client + ' / ' + t.name,
              })),
            ]"
            label="材料归属任务"
          />
        </div>
        <input
          ref="input"
          type="file"
          multiple
          class="hidden"
          aria-label="选择导入材料"
          @change="(e) => add((e.target as HTMLInputElement).files)"
        />
        <div
          v-if="!archive"
          class="upload-zone"
          @dragover.prevent
          @drop.prevent="(e) => add(e.dataTransfer?.files || null)"
        >
          <Upload :size="25" /><strong>拖入材料，或选择本机文件</strong
          ><span>Word、PDF、数据文件与图表</span
          ><Button type="button" variant="outline" @click="pick"
            ><FolderOpen :size="15" />选择材料</Button
          >
        </div>
        <div v-if="rows.length" class="import-files">
          <div v-for="(row, index) in rows" :key="index" class="import-file">
            <File :size="18" />
            <div>
              <strong>{{ row.name }}</strong
              ><small v-if="row.size != null">{{ bytes(row.size) }}</small>
            </div>
            <SelectField
              v-if="form.task_id"
              v-model="row.category"
              :options="state.categories"
              :label="'文件分类 ' + row.name"
            /><Button
              v-if="!archive"
              variant="ghost"
              size="icon"
              type="button"
              :aria-label="'移除 ' + row.name"
              @click="rows.splice(index, 1)"
              ><X :size="15"
            /></Button>
          </div>
        </div>
        <div v-if="form.task_id" class="two-columns">
          <div class="form-field">
            <Label for="import-next">新增下一步工作（可选）</Label
            ><Input
              id="import-next"
              v-model="form.todo_text"
              placeholder="例如：核对新收到的图表"
            />
          </div>
          <div class="form-field">
            <Label>待办截止日期</Label><DatePicker v-model="form.deadline" />
          </div>
        </div>
        <p v-if="error" role="alert" class="field-error">{{ error }}</p>
        <DialogFooter
          ><Button
            variant="outline"
            type="button"
            :disabled="busy"
            @click="emit('update:open', false)"
            >取消</Button
          ><Button type="submit" :disabled="busy || !valid"
            >{{ busy ? "正在整理材料…" : archive ? "确认归档" : "确认导入"
            }}<span v-if="rows.length">
              · {{ rows.length }} 个文件</span
            ></Button
          ></DialogFooter
        >
      </form></DialogContent
    ></Dialog
  >
</template>
