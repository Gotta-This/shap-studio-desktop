<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Plus,
  Download,
  Search,
  Folder,
  ArrowLeft,
  ArrowUpDown,
  SlidersHorizontal,
  FileText,
  MoreHorizontal,
  FolderOpen,
  Pencil,
  Link2,
  CheckCheck,
  RotateCcw,
  FileWarning,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import PageHeading from "@/components/PageHeading.vue";
import EmptyState from "@/components/EmptyState.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import SelectField from "@/components/SelectField.vue";
import DatePicker from "@/components/DatePicker.vue";
import TaskDialog from "@/components/TaskDialog.vue";
import TodoDialog from "@/components/TodoDialog.vue";
import ImportDialog from "@/components/ImportDialog.vue";
import PreviewDialog from "@/components/PreviewDialog.vue";
import {
  api,
  state,
  refresh,
  action,
  notify,
  today,
  dateText,
  bytes,
  openPath,
  upload,
  type Task,
  type Todo,
  type Material,
  type Detail,
} from "@/lib/api";
const route = useRoute(),
  router = useRouter(),
  query = ref(""),
  client = ref(""),
  status = ref(""),
  pendingOnly = ref(false),
  dueFrom = ref<string | null>(null),
  dueTo = ref<string | null>(null),
  ascending = ref(true),
  page = ref(1);
const newTask = ref(false),
  editTask = ref<Task | null>(null),
  todoOpen = ref(false),
  editTodo = ref<Todo | null>(null),
  importOpen = ref(false),
  detail = ref<Detail | null>(null),
  category = ref(""),
  fileQuery = ref(""),
  tab = ref("files"),
  preview = ref<Material | null>(null),
  loading = ref(false);
const columns = ref(["tags", "status", "due", "next", "files"]);
const id = computed(() =>
  typeof route.params.id === "string" ? route.params.id : "",
);
const pending = computed(() => state.todos.filter((t) => !t.completed));
const dueToday = computed(
  () => pending.value.filter((t) => t.due_date === today()).length,
);
const filtered = computed(() =>
  state.tasks
    .filter(
      (t) =>
        (!client.value || t.client === client.value) &&
        (!status.value || t.status === status.value) &&
        (!pendingOnly.value || t.pending_count > 0) &&
        (!dueFrom.value || (!!t.due_date && t.due_date >= dueFrom.value)) &&
        (!dueTo.value || (!!t.due_date && t.due_date <= dueTo.value)) &&
        [t.name, t.client, t.tags.join(" "), t.todo_text, t.file_names]
          .join(" ")
          .toLocaleLowerCase()
          .includes(query.value.toLocaleLowerCase()),
    )
    .sort((a, b) => {
      const left = a.due_date || "9999",
        right = b.due_date || "9999";
      return ascending.value
        ? left.localeCompare(right)
        : right.localeCompare(left);
    }),
);
const pages = computed(() =>
    Math.max(1, Math.ceil(filtered.value.length / 20)),
  ),
  visible = computed(() =>
    filtered.value.slice((page.value - 1) * 20, page.value * 20),
  );
watch(
  [query, client, status, pendingOnly, dueFrom, dueTo],
  () => (page.value = 1),
);
const files = computed(
  () =>
    detail.value?.files.filter(
      (f) =>
        (!category.value || f.category === category.value) &&
        f.original_name
          .toLocaleLowerCase()
          .includes(fileQuery.value.toLocaleLowerCase()),
    ) || [],
);
const taskTodos = computed(() => detail.value?.todos || []);
async function load() {
  if (!id.value) {
    detail.value = null;
    return;
  }
  loading.value = true;
  try {
    const target = id.value;
    const result = await api<Detail>("task.detail", { id: target });
    if (id.value === target) detail.value = result;
  } catch (e) {
    notify((e as Error).message, true);
    detail.value = null;
  } finally {
    loading.value = false;
  }
}
watch([id, () => state.tasks], load, { immediate: true });
function taskSaved(tid: string) {
  router.push("/workspace/" + tid);
  load();
}
function newTodo(todo: Todo | null = null) {
  editTodo.value = todo;
  todoOpen.value = true;
}
async function complete(todo: Todo, value: boolean) {
  const before = todo.completed;
  todo.completed = value;
  const saved = await action(
    "todo.save",
    { id: todo.id, completed: value },
    value ? "已完成这项工作。" : "已恢复为未完成。",
  );
  if (saved === undefined) todo.completed = before;
  await load();
}
async function folder() {
  try {
    await openPath(await api("task.path", { id: id.value }));
  } catch (e) {
    notify((e as Error).message, true);
  }
}
async function systemOpen(file: Material) {
  try {
    await openPath(await api("files.path", { id: file.id }));
  } catch (e) {
    notify((e as Error).message, true);
  }
}
async function recategorize(file: Material, target: string) {
  const result = await action(
    "files.archive",
    { ids: [file.id], task_id: id.value, categories: [target] },
    "文件分类与目录已同步。",
  );
  if (result) load();
}
async function relocate(file: Material) {
  const input = document.createElement("input");
  input.type = "file";
  input.onchange = async () => {
    if (!input.files?.length) return;
    try {
      await api("files.relocate", {
        id: file.id,
        uploads: await upload(Array.from(input.files)),
      });
      notify("内容校验通过，文件已重新关联。");
      await load();
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  input.click();
}
async function undo(eventId: number) {
  await action("files.undo", { id: eventId }, "归档已撤销。");
  await load();
}
</script>
<template>
  <section>
    <template v-if="!id"
      ><PageHeading
        title="稿件工作空间"
        subtitle="集中管理稿件、材料与下一步工作。"
        ><Button
          variant="outline"
          :disabled="!state.root"
          @click="importOpen = true"
          ><Download :size="16" />导入材料</Button
        ><Button
          :disabled="!state.root"
          @click="
            editTask = null;
            newTask = true;
          "
          ><Plus :size="16" />新建任务</Button
        ></PageHeading
      ><template v-if="state.root"
        ><div class="stats-grid">
          <div class="stat-card">
            <small>全部任务</small>
            <div>
              <strong>{{ state.tasks.length }}</strong
              ><span>当前工作空间</span>
            </div>
            <Folder :size="19" />
          </div>
          <div class="stat-card">
            <small>未完成待办</small>
            <div>
              <strong>{{ pending.length }}</strong
              ><span>按截止日期安排</span>
            </div>
            <CheckCheck :size="19" />
          </div>
          <div class="stat-card">
            <small>今天到期</small>
            <div>
              <strong>{{ dueToday }}</strong
              ><span>优先处理今天的工作</span>
            </div>
            <span class="stat-dot" />
          </div>
        </div>
        <div class="section-title">
          <h2>全部任务</h2>
          <Badge variant="secondary">{{ filtered.length }}</Badge>
        </div>
        <div class="filter-bar">
          <div class="search-field">
            <Search :size="16" /><Input
              v-model="query"
              aria-label="搜索稿件任务"
              placeholder="搜索客户、任务、标签、文件或下一步工作…"
            />
          </div>
          <SelectField
            v-model="client"
            :options="[
              { value: '', label: '全部客户' },
              ...Array.from(new Set(state.tasks.map((t) => t.client))),
            ]"
            label="客户筛选"
          /><SelectField
            v-model="status"
            :options="[{ value: '', label: '全部状态' }, ...state.statuses]"
            label="状态筛选"
          /><Popover
            ><PopoverTrigger as-child
              ><Button variant="outline"
                ><SlidersHorizontal :size="14" />日期与待办<Badge
                  v-if="pendingOnly || dueFrom || dueTo"
                  variant="secondary"
                  >已筛选</Badge
                ></Button
              ></PopoverTrigger
            ><PopoverContent class="w-80"
              ><div class="form-field">
                <label>截止日期范围</label
                ><DatePicker v-model="dueFrom" label="开始日期" /><DatePicker
                  v-model="dueTo"
                  label="结束日期"
                />
              </div>
              <label class="file-check mt-4"
                ><Checkbox
                  v-model="pendingOnly"
                />仅显示有未完成工作的任务</label
              ><Button
                variant="outline"
                size="sm"
                class="mt-3"
                @click="
                  dueFrom = null;
                  dueTo = null;
                  pendingOnly = false;
                "
                >重置筛选</Button
              ></PopoverContent
            ></Popover
          ><Popover
            ><PopoverTrigger as-child
              ><Button variant="outline" class="columns-button"
                >显示列</Button
              ></PopoverTrigger
            ><PopoverContent class="w-44"
              ><label
                v-for="c in [
                  { value: 'tags', name: '标签' },
                  { value: 'status', name: '状态' },
                  { value: 'due', name: '截止日期' },
                  { value: 'next', name: '下一步工作' },
                  { value: 'files', name: '文件数量' },
                ]"
                :key="c.value"
                class="file-check"
                ><Checkbox
                  :model-value="columns.includes(c.value)"
                  @update:model-value="
                    (v) =>
                      (columns = v
                        ? [...columns, c.value]
                        : columns.filter((x) => x !== c.value))
                  "
                />{{ c.name }}</label
              ></PopoverContent
            ></Popover
          >
        </div>
        <div class="table-panel">
          <div class="table-scroll">
            <table class="data-table task-table">
              <thead>
                <tr>
                  <th>任务 / 客户</th>
                  <th v-if="columns.includes('tags')">标签</th>
                  <th v-if="columns.includes('status')">状态</th>
                  <th v-if="columns.includes('due')">
                    <button class="sort-button" @click="ascending = !ascending">
                      截止日期 <ArrowUpDown :size="12" />
                    </button>
                  </th>
                  <th v-if="columns.includes('next')">下一步工作</th>
                  <th v-if="columns.includes('files')" class="text-right">
                    文件
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="task in visible"
                  :key="task.id"
                  tabindex="0"
                  @click="router.push('/workspace/' + task.id)"
                  @keydown.enter="router.push('/workspace/' + task.id)"
                >
                  <td>
                    <div class="task-name">
                      <Folder :size="18" />
                      <div>
                        <strong>{{ task.name }}</strong
                        ><small
                          >{{ task.client }} · {{ task.created_date }}</small
                        >
                      </div>
                    </div>
                  </td>
                  <td v-if="columns.includes('tags')">
                    <div class="tag-list">
                      <Badge
                        v-for="tag in task.tags"
                        :key="tag"
                        variant="secondary"
                        >{{ tag }}</Badge
                      ><span v-if="!task.tags.length" class="muted">—</span>
                    </div>
                  </td>
                  <td v-if="columns.includes('status')">
                    <StatusBadge :value="task.status" />
                  </td>
                  <td v-if="columns.includes('due')" class="nowrap">
                    {{ dateText(task.due_date) }}
                  </td>
                  <td v-if="columns.includes('next')">
                    <div class="cell-lines">
                      <span>{{
                        task.next_todo?.text ||
                        (task.pending_count ? "查看待办" : "本轮待办已完成")
                      }}</span
                      ><small
                        :class="{
                          overdue:
                            task.next_todo?.due_date &&
                            task.next_todo.due_date <= today(),
                        }"
                        >{{
                          task.next_todo
                            ? dateText(task.next_todo.due_date)
                            : "—"
                        }}</small
                      >
                    </div>
                  </td>
                  <td v-if="columns.includes('files')" class="text-right muted">
                    {{ task.file_count }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <EmptyState
            v-if="!filtered.length"
            :title="
              state.tasks.length ? '没有找到匹配的任务' : '还没有稿件任务'
            "
            :description="
              state.tasks.length
                ? '试试其他关键词或清除筛选条件。'
                : '新建第一项任务，开始整理稿件材料与下一步工作。'
            "
            ><Button
              v-if="!state.tasks.length"
              @click="
                editTask = null;
                newTask = true;
              "
              ><Plus :size="15" />新建任务</Button
            ></EmptyState
          >
          <div class="table-footer">
            <span>共 {{ filtered.length }} 项任务</span>
            <div>
              <span>每页 20 项</span
              ><Button
                size="sm"
                variant="outline"
                :disabled="page <= 1"
                @click="page--"
                >上一页</Button
              ><span>{{ page }} / {{ pages }}</span
              ><Button
                size="sm"
                variant="outline"
                :disabled="page >= pages"
                @click="page++"
                >下一页</Button
              >
            </div>
          </div>
        </div>
        <p class="local-note">
          <Folder :size="15" />任务目录与文件均保存在本机工作空间。
        </p></template
      ><EmptyState
        v-else
        title="为新稿件选择一个工作空间"
        description="指定一个本机目录，用来保存任务、材料和待办。已有历史稿件不会被扫描。"
        ><Button @click="router.push('/settings')"
          ><FolderOpen :size="16" />选择工作空间</Button
        ></EmptyState
      ></template
    ><template v-else-if="detail"
      ><PageHeading
        :title="detail.task.name"
        :subtitle="
          detail.task.client +
          ' / ' +
          detail.task.created_date +
          ' / ' +
          detail.task.name
        "
        ><Button variant="outline" @click="folder"
          ><FolderOpen :size="16" />打开文件夹</Button
        ><Button @click="importOpen = true"><Plus :size="16" />导入材料</Button
        ><template #meta
          ><div class="task-meta">
            <Button
              size="sm"
              variant="outline"
              @click="router.push('/workspace')"
              ><ArrowLeft :size="13" />全部任务</Button
            ><StatusBadge :value="detail.task.status" /><Badge
              v-for="tag in detail.task.tags"
              :key="tag"
              variant="secondary"
              >{{ tag }}</Badge
            ><span>截止日期 {{ dateText(detail.task.due_date) }}</span
            ><Button
              variant="outline"
              size="sm"
              class="ml-auto"
              @click="
                editTask = detail.task;
                newTask = true;
              "
              ><Pencil :size="13" />编辑任务</Button
            >
          </div></template
        ></PageHeading
      >
      <div class="local-tabs">
        <button :class="{ selected: tab === 'files' }" @click="tab = 'files'">
          任务文件</button
        ><button
          :class="{ selected: tab === 'events' }"
          @click="tab = 'events'"
        >
          操作记录
        </button>
      </div>
      <div v-if="tab === 'files'" class="detail-grid">
        <div class="panel">
          <div class="panel-heading">
            <h2>
              文件 <Badge variant="secondary">{{ detail.files.length }}</Badge>
            </h2>
            <div class="small-search">
              <Search :size="14" /><Input
                v-model="fileQuery"
                aria-label="搜索任务文件"
                placeholder="搜索文件"
              />
            </div>
          </div>
          <div class="category-tabs">
            <button :class="{ selected: !category }" @click="category = ''">
              全部</button
            ><button
              v-for="c in state.categories"
              :key="c"
              :class="{ selected: category === c }"
              @click="category = c"
            >
              {{ c }}
            </button>
          </div>
          <div v-for="file in files" :key="file.id" class="material-row">
            <div class="file-icon">
              <FileText v-if="file.available" :size="21" /><FileWarning
                v-else
                :size="21"
                class="text-amber-600"
              />
            </div>
            <button class="material-name" @click="preview = file">
              <strong>{{ file.original_name }}</strong
              ><small
                >{{ file.category }} · {{ bytes(file.size) }} ·
                {{ file.received_at.slice(0, 10)
                }}<span v-if="!file.available" class="overdue">
                  · 文件丢失</span
                ></small
              ></button
            ><Button
              size="sm"
              variant="outline"
              @click="file.available ? (preview = file) : relocate(file)"
              >{{ file.available ? "预览" : "重新关联" }}</Button
            ><DropdownMenu
              ><DropdownMenuTrigger as-child
                ><Button
                  variant="outline"
                  size="icon"
                  :aria-label="'操作 ' + file.original_name"
                  ><MoreHorizontal :size="18" /></Button></DropdownMenuTrigger
              ><DropdownMenuContent align="end"
                ><DropdownMenuItem @select="systemOpen(file)"
                  >使用系统程序打开</DropdownMenuItem
                ><DropdownMenuItem @select="relocate(file)"
                  >重新关联原文件</DropdownMenuItem
                ><DropdownMenuSeparator /><DropdownMenuItem
                  v-for="c in state.categories"
                  :key="c"
                  :disabled="c === file.category"
                  @select="recategorize(file, c)"
                  >归类为 {{ c }}</DropdownMenuItem
                ></DropdownMenuContent
              ></DropdownMenu
            >
          </div>
          <EmptyState
            v-if="!files.length"
            :title="fileQuery || category ? '没有匹配的文件' : '还没有文件'"
            description="原稿、数据、图表、修改稿与交付文件都可以整理在这里。"
            ><Button v-if="!detail.files.length" @click="importOpen = true"
              ><Plus :size="15" />导入材料</Button
            ></EmptyState
          >
          <div class="panel-bottom">共 {{ files.length }} 个文件</div>
        </div>
        <div class="detail-aside">
          <div class="panel">
            <div class="panel-heading">
              <h2>下一步工作</h2>
              <Button
                variant="outline"
                size="icon"
                aria-label="新增下一步工作"
                @click="newTodo()"
                ><Plus :size="17"
              /></Button>
            </div>
            <div v-for="todo in taskTodos" :key="todo.id" class="todo-card">
              <Checkbox
                :model-value="todo.completed"
                :aria-label="'完成 ' + todo.text"
                @update:model-value="(v) => complete(todo, !!v)"
              /><button
                class="todo-edit-action"
                :class="{ 'is-complete': todo.completed }"
                @click="newTodo(todo)"
              >
                <strong>{{ todo.text }}</strong
                ><small
                  >{{ todo.completed ? "已完成" : dateText(todo.due_date) }} ·
                  {{
                    todo.priority === "high"
                      ? "高"
                      : todo.priority === "low"
                        ? "低"
                        : "普通"
                  }}优先级</small
                ><small v-if="todo.file_ids.length"
                  ><Link2 :size="11" />关联
                  {{ todo.file_ids.length }} 个文件</small
                >
              </button>
            </div>
            <EmptyState
              v-if="!taskTodos.length"
              title="还没有待办"
              description="添加一项下一步工作。"
            /><RouterLink class="panel-link" to="/todos"
              >查看全部待办 →</RouterLink
            >
          </div>
          <div class="panel">
            <div class="panel-heading"><h2>最近操作</h2></div>
            <div
              v-for="event in detail.events.slice(0, 3)"
              :key="event.id"
              class="event-item"
            >
              <i />
              <div>
                <strong>{{ event.kind }}</strong
                ><small>{{
                  event.created_at.slice(0, 16).replace("T", " ")
                }}</small>
              </div>
            </div>
            <button class="panel-link" @click="tab = 'events'">
              查看操作记录 →
            </button>
          </div>
          <div v-if="detail.task.notes" class="panel p-5">
            <h2>任务备注</h2>
            <p class="muted whitespace-pre-wrap mt-3">
              {{ detail.task.notes }}
            </p>
          </div>
        </div>
      </div>
      <div v-else class="panel">
        <div class="panel-heading"><h2>操作记录</h2></div>
        <div v-for="event in detail.events" :key="event.id" class="event-item">
          <i />
          <div>
            <strong>{{ event.kind }}</strong
            ><small>{{
              event.created_at.slice(0, 19).replace("T", " ")
            }}</small>
          </div>
          <Button
            v-if="event.kind === '归档材料'"
            variant="outline"
            size="sm"
            class="ml-auto"
            @click="undo(event.id)"
            ><RotateCcw :size="13" />撤销归档</Button
          >
        </div>
        <EmptyState v-if="!detail.events.length" title="暂无操作记录" />
      </div>
      <div class="directory-banner">
        <Folder :size="19" />
        <div>
          <small>本地目录</small
          ><span>{{ state.root }} / {{ detail.task.directory }}</span>
        </div>
      </div></template
    >
    <p v-else class="muted p-10">
      {{ loading ? "正在读取稿件任务…" : "任务已不可用，请返回任务表刷新。" }}
    </p>
    <TaskDialog
      v-model:open="newTask"
      :task="editTask"
      @saved="taskSaved"
    /><TodoDialog
      v-model:open="todoOpen"
      :todo="editTodo"
      :task-id="id"
      :files="detail?.files"
      @saved="load"
    /><ImportDialog
      v-model:open="importOpen"
      :task-id="id"
      @saved="load"
    /><PreviewDialog :file="preview" @close="preview = null" />
  </section>
</template>
