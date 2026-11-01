<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import {
  Plus,
  Search,
  Folder,
  MoreHorizontal,
  Pencil,
  Trash2,
  RotateCcw,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import PageHeading from "@/components/PageHeading.vue";
import EmptyState from "@/components/EmptyState.vue";
import DatePicker from "@/components/DatePicker.vue";
import SelectField from "@/components/SelectField.vue";
import TodoDialog from "@/components/TodoDialog.vue";
import { state, action, today, type Todo } from "@/lib/api";
const router = useRouter(),
  done = ref(false),
  query = ref(""),
  priority = ref(""),
  open = ref(false),
  editing = ref<Todo | null>(null),
  deleted = ref<Todo | null>(null);
const pending = computed(() => state.todos.filter((t) => !t.completed).length),
  completed = computed(() => state.todos.filter((t) => t.completed).length);
const rows = computed(() =>
  state.todos
    .filter(
      (t) =>
        t.completed === done.value &&
        (!priority.value || priority.value === t.priority) &&
        [t.text, t.client, t.task_name]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query.value.toLocaleLowerCase()),
    )
    .sort((a, b) => (a.due_date || "9999").localeCompare(b.due_date || "9999")),
);
async function complete(todo: Todo, value: boolean) {
  const before = todo.completed;
  todo.completed = value;
  const saved = await action(
    "todo.save",
    { id: todo.id, completed: value },
    value ? "已标记完成。" : "已恢复为未完成。",
  );
  if (saved === undefined) todo.completed = before;
}
function edit(todo: Todo | null = null) {
  editing.value = todo;
  open.value = true;
}
async function remove(todo: Todo) {
  await action(
    "todo.save",
    { id: todo.id, deleted: true },
    "已删除待办，可以撤销。",
  );
  deleted.value = todo;
}
async function undo() {
  if (deleted.value) {
    await action(
      "todo.save",
      { id: deleted.value.id, deleted: false },
      "待办已恢复。",
    );
    deleted.value = null;
  }
}
</script>
<template>
  <section>
    <PageHeading
      title="待办事项"
      subtitle="明确下一步工作，按截止日期有序推进。"
      ><Button @click="edit()"><Plus :size="16" />新增待办</Button></PageHeading
    >
    <div class="todo-toolbar">
      <div class="segmented">
        <button :class="{ selected: !done }" @click="done = false">
          未完成 <Badge variant="secondary">{{ pending }}</Badge></button
        ><button :class="{ selected: done }" @click="done = true">
          已完成 <Badge variant="secondary">{{ completed }}</Badge>
        </button>
      </div>
      <div class="filter-bar">
        <div class="search-field">
          <Search :size="16" /><Input
            v-model="query"
            aria-label="搜索待办"
            placeholder="搜索工作、客户或稿件名称…"
          />
        </div>
        <SelectField
          v-model="priority"
          :options="[
            { value: '', label: '全部优先级' },
            { value: 'high', label: '高优先级' },
            { value: 'normal', label: '普通优先级' },
            { value: 'low', label: '低优先级' },
          ]"
          label="优先级筛选"
        />
      </div>
    </div>
    <div v-if="deleted" class="undo-banner">
      <span>已删除「{{ deleted.text }}」</span
      ><Button size="sm" variant="ghost" @click="undo"
        ><RotateCcw :size="13" />撤销</Button
      >
    </div>
    <div class="table-panel">
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th class="w-12"></th>
              <th>下一步工作</th>
              <th>所属稿件 / 客户</th>
              <th>优先级</th>
              <th>截止日期</th>
              <th class="w-12"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="todo in rows" :key="todo.id">
              <td>
                <Checkbox
                  :model-value="todo.completed"
                  :aria-label="'完成 ' + todo.text"
                  @update:model-value="(v) => complete(todo, !!v)"
                />
              </td>
              <td>
                <button
                  :class="['text-left', { 'is-complete': todo.completed }]"
                  @click="edit(todo)"
                >
                  <strong>{{ todo.text }}</strong>
                </button>
              </td>
              <td>
                <button
                  v-if="todo.task_id"
                  class="task-link"
                  @click="router.push('/workspace/' + todo.task_id)"
                >
                  <Folder :size="14" />
                  <div>
                    <span>{{ todo.task_name }}</span
                    ><small>{{ todo.client }}</small>
                  </div></button
                ><span v-else class="muted">个人待办</span>
              </td>
              <td>
                <Badge
                  variant="secondary"
                  :class="{ 'tone-amber': todo.priority === 'high' }"
                  >{{
                    todo.priority === "high"
                      ? "高"
                      : todo.priority === "low"
                        ? "低"
                        : "普通"
                  }}</Badge
                >
              </td>
              <td>
                <DatePicker
                  :model-value="todo.due_date"
                  :label="'修改截止日期 ' + todo.text"
                  :class="[
                    'inline-date',
                    {
                      overdue:
                        !todo.completed &&
                        todo.due_date &&
                        todo.due_date <= today(),
                    },
                  ]"
                  @update:model-value="
                    (v) => action('todo.save', { id: todo.id, due_date: v })
                  "
                />
              </td>
              <td>
                <DropdownMenu
                  ><DropdownMenuTrigger as-child
                    ><Button
                      variant="ghost"
                      size="icon"
                      :aria-label="'待办操作 ' + todo.text"
                      ><MoreHorizontal
                        :size="17" /></Button></DropdownMenuTrigger
                  ><DropdownMenuContent align="end"
                    ><DropdownMenuItem @select="edit(todo)"
                      ><Pencil :size="14" />编辑待办</DropdownMenuItem
                    ><DropdownMenuItem @select="remove(todo)"
                      ><Trash2 :size="14" />删除待办</DropdownMenuItem
                    ></DropdownMenuContent
                  ></DropdownMenu
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState
        v-if="!rows.length"
        :title="
          query
            ? '没有找到匹配的工作'
            : done
              ? '还没有已完成的工作'
              : '今天没有待办'
        "
        :description="
          query ? '换一个关键词试试。' : '记录一项下一步工作，完成后手动勾选。'
        "
        ><Button v-if="!done && !query" variant="outline" @click="edit()"
          ><Plus :size="14" />新增待办</Button
        ></EmptyState
      >
      <div class="table-footer">
        <span>共 {{ rows.length }} 项{{ done ? "已完成工作" : "待办" }}</span
        ><span>勾选方框即可标记完成</span>
      </div>
    </div>
    <TodoDialog v-model:open="open" :todo="editing" />
  </section>
</template>
