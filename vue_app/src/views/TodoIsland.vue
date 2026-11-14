<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { Camera, Check, Copy, ListTodo, LoaderCircle, Play, Plus, SlidersHorizontal, Trash2, X } from "lucide-vue-next";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { api, notify, type Todo } from "@/lib/api";
import { clone, jobFor, startJob } from "@/lib/scientific";

const todos = ref<Todo[]>([]);
const expanded = ref(false);
const ready = ref(false);
const showSettings = ref(false);
const opacity = ref(Number(localStorage.getItem("todo-island-opacity") || "0.94"));
const compactWidth = ref(240);
const expandedWidth = ref(380);
const animationMs = ref(360);
const showScreenshot = ref(true);
const shortcutTool = ref(localStorage.getItem("todo-island-tool") || "none");
const categoryRows = ref<{ value: number; count: number }[]>(loadStored("todo-island-category-rows", [{ value: 1, count: 28 }, { value: 0, count: 93 }]));
const categorySeed = ref(Number(localStorage.getItem("todo-island-category-seed") || "12"));
const numeric = reactive(loadStored("todo-island-numeric", { n: 70, mean: 27.92, sd: 14.87, digits: 0, lower: null as number | null, upper: null as number | null, mode: "target", seed: 12 }));
const shortcutResult = ref<any>(null);
const shortcutBusy = ref(false);
const shortcutError = ref("");
const shortcutCopied = ref(false);
const pending = computed(() => todos.value.filter((todo) => !todo.completed));
let timer: ReturnType<typeof setInterval> | undefined;
let collapseTimer: ReturnType<typeof setTimeout> | undefined;
let collapseResizeTimer: ReturnType<typeof setTimeout> | undefined;
let resizeSequence = 0;
let unlistenTodoUpdated: (() => void) | undefined;
let unlistenConfigUpdated: (() => void) | undefined;
let unlistenHover: (() => void) | undefined;
let shortcutCopiedTimer: ReturnType<typeof setTimeout> | undefined;
let lightweightTodosUnavailable = false;

function loadStored<T>(key: string, fallback: T): T {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) as T : fallback; } catch { return fallback; }
}
function saveShortcutState() {
  localStorage.setItem("todo-island-tool", shortcutTool.value);
  localStorage.setItem("todo-island-category-rows", JSON.stringify(categoryRows.value));
  localStorage.setItem("todo-island-category-seed", String(categorySeed.value));
  localStorage.setItem("todo-island-numeric", JSON.stringify(numeric));
}
watch([shortcutTool, categoryRows, categorySeed, numeric], saveShortcutState, { deep: true });
watch([shortcutTool, showSettings, pending, () => categoryRows.value.length], () => { if (expanded.value) void resizeIsland(true); });
const categoryTotal = computed(() => categoryRows.value.reduce((sum, row) => sum + Number(row.count || 0), 0));
const shortcutJob = computed(() => jobFor("todo-island"));

async function refresh() {
  try {
    const result = lightweightTodosUnavailable
      ? await api<{ todos: Todo[] }>("state")
      : await api<{ todos: Todo[] }>("todos.state");
    todos.value = result.todos;
    try { localStorage.setItem("todo-island-todos", JSON.stringify(result.todos)); } catch { /* cache is optional */ }
    return true;
  } catch {
    if (!lightweightTodosUnavailable) {
      lightweightTodosUnavailable = true;
      try {
        const result = await api<{ todos: Todo[] }>("state");
        todos.value = result.todos;
        try { localStorage.setItem("todo-island-todos", JSON.stringify(result.todos)); } catch { /* cache is optional */ }
        return true;
      } catch { /* keep the cached list */ }
    }
    // Keep the last known list visible if the engine is temporarily unavailable.
    return false;
  }
}
async function loadConfig() {
  if (!("__TAURI_INTERNALS__" in window)) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const config = await invoke<{ compact_width: number; expanded_width: number; animation_ms?: number; show_screenshot?: boolean }>("todo_island_config_command");
    compactWidth.value = config.compact_width;
    expandedWidth.value = config.expanded_width;
    animationMs.value = config.animation_ms ?? 360;
    showScreenshot.value = config.show_screenshot !== false;
  } catch {
    // Keep the defaults if the native settings command is unavailable.
  }
}
async function saveToolVisibility(value: boolean) {
  showScreenshot.value = value;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("set_todo_island_config", { config: { compact_width: compactWidth.value, expanded_width: expandedWidth.value, show_screenshot: value } });
  } catch (error) {
    showScreenshot.value = !value;
    notify(`灵动岛工具设置失败：${String((error as Error).message || error)}`, true);
  }
}
async function capture() {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("quickshot_capture");
  } catch (error) {
    notify(`截图工具启动失败：${String((error as Error).message || error)}`, true);
  }
}
async function generateShortcut() {
  shortcutBusy.value = true;
  shortcutError.value = "";
  shortcutResult.value = null;
  try {
    const kind = shortcutTool.value === "category" ? "category" : "numeric";
    const params = kind === "category" ? { rows: categoryRows.value, seed: categorySeed.value } : clone(numeric);
    await startJob(kind, params, "todo-island");
    if (shortcutJob.value.error) throw new Error(shortcutJob.value.error);
    shortcutResult.value = shortcutJob.value.result;
    await autoCopyShortcutResult(shortcutResult.value, kind);
  } catch (error) {
    shortcutError.value = String((error as Error).message || error);
  } finally {
    shortcutBusy.value = false;
  }
}
async function autoCopyShortcutResult(result: any, kind: string) {
  const text = result.values.map((value: number) => kind === "numeric" ? value.toFixed(result.params?.digits ?? 0) : String(value)).join("\n");
  try {
    await navigator.clipboard.writeText(text);
    shortcutCopied.value = true;
    if (shortcutCopiedTimer) clearTimeout(shortcutCopiedTimer);
    shortcutCopiedTimer = setTimeout(() => { shortcutCopied.value = false; }, 1600);
  } catch {
    shortcutError.value = "数据已生成，但自动复制到剪贴板失败。";
  }
}
async function copyShortcutResult() {
  if (!shortcutResult.value) return;
  try {
    await navigator.clipboard.writeText(shortcutResult.value.values.join("\n"));
    notify("结果已复制。");
  } catch { notify("复制失败。", true); }
}
async function complete(todo: Todo, value: boolean) {
  const previous = todo.completed;
  todo.completed = value;
  try {
    await api("todo.save", { id: todo.id, completed: value });
    const { emit } = await import("@tauri-apps/api/event");
    await emit("todo-updated");
    await refresh();
  } catch {
    todo.completed = previous;
  }
}
async function resizeIsland(open: boolean) {
  if (!("__TAURI_INTERNALS__" in window)) return;
  const sequence = ++resizeSequence;
  try {
    const [{ getCurrentWindow, currentMonitor }, { LogicalPosition, LogicalSize }] = await Promise.all([
      import("@tauri-apps/api/window"),
      import("@tauri-apps/api/dpi"),
    ]);
    const current = getCurrentWindow();
    const monitor = await currentMonitor();
    if (sequence !== resizeSequence) return;
    const width = open ? expandedWidth.value : compactWidth.value;
    const todoRows = Math.min(pending.value.length, 8);
    const settingsExtra = showSettings.value ? 82 : 0;
    const height = !open ? 44 : Math.min(760, Math.max(190, shortcutTool.value === "category" ? 285 + categoryRows.value.length * 36 + todoRows * 46 + settingsExtra : shortcutTool.value === "numeric" ? 285 + todoRows * 46 + settingsExtra : 82 + todoRows * 46 + settingsExtra));
    await current.setSize(new LogicalSize(width, height));
    if (monitor) {
      const scale = monitor.scaleFactor;
      const x = monitor.position.x / scale + (monitor.size.width / scale - width) / 2;
      const y = monitor.position.y / scale + 8;
      await current.setPosition(new LogicalPosition(x, y));
    }
  } catch {
    // Keep the current window usable if the display changes during a resize.
  }
}
function expand() {
  if (collapseTimer) clearTimeout(collapseTimer);
  if (collapseResizeTimer) clearTimeout(collapseResizeTimer);
  if (shortcutCopiedTimer) clearTimeout(shortcutCopiedTimer);
  if (expanded.value) return;
  expanded.value = true;
  void resizeIsland(true);
}
function scheduleCollapse() {
  if (collapseTimer) clearTimeout(collapseTimer);
  collapseTimer = setTimeout(() => {
    expanded.value = false;
    showSettings.value = false;
    collapseResizeTimer = setTimeout(() => { void resizeIsland(false); }, Math.round(animationMs.value * 0.75));
  }, Math.round(animationMs.value * 0.3));
}
function saveOpacity(value: string | number) {
  const next = Math.min(1, Math.max(0.55, Number(value)));
  opacity.value = next;
  localStorage.setItem("todo-island-opacity", String(next));
}
async function close() {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("set_todo_island_enabled", { enabled: false });
}
async function showWhenReady() {
  ready.value = true;
}
onMounted(async () => {
  try {
    const cached = localStorage.getItem("todo-island-todos");
    if (cached) todos.value = JSON.parse(cached) as Todo[];
  } catch {
    // Start empty when cached data is unavailable.
  }
  void loadConfig();
  timer = setInterval(refresh, 1500);
  await showWhenReady();
  if ("__TAURI_INTERNALS__" in window) {
    const { listen } = await import("@tauri-apps/api/event");
    unlistenTodoUpdated = await listen("todo-updated", () => { void refresh(); });
    unlistenConfigUpdated = await listen<{ compact_width: number; expanded_width: number; animation_ms?: number; show_screenshot?: boolean }>("todo-island-config-updated", (event) => {
      compactWidth.value = event.payload.compact_width;
      expandedWidth.value = event.payload.expanded_width;
      animationMs.value = event.payload.animation_ms ?? 360;
      showScreenshot.value = event.payload.show_screenshot !== false;
      void resizeIsland(expanded.value);
    });
    unlistenHover = await listen<boolean>("todo-island-hover", (event) => {
      if (event.payload) expand();
      else scheduleCollapse();
    });
  }
  void refresh();
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
  if (collapseTimer) clearTimeout(collapseTimer);
  if (collapseResizeTimer) clearTimeout(collapseResizeTimer);
  unlistenTodoUpdated?.();
  unlistenConfigUpdated?.();
  unlistenHover?.();
});
</script>

<template>
  <main class="todo-island" :class="{ 'todo-island-expanded': expanded, 'todo-island-ready': ready, 'todo-island-with-tool': shortcutTool !== 'none', 'todo-island-tool-category': shortcutTool === 'category', 'todo-island-tool-numeric': shortcutTool === 'numeric' }" :style="{ '--todo-opacity': opacity, '--todo-animation-ms': `${animationMs}ms` }" @pointerenter="expand" @pointermove="expand" @pointerleave="scheduleCollapse">
    <header class="todo-island-header">
      <div class="todo-island-title"><ListTodo :size="16" /><strong>待办事项</strong><span>{{ pending.length }}</span></div>
      <Transition name="todo-island-header-content" mode="out-in">
      <span v-if="!expanded" key="preview" class="todo-island-preview">{{ pending[0]?.text || "今天没有待办" }}</span>
      <div v-else key="actions" class="todo-island-actions">
        <button v-if="showScreenshot" aria-label="开始截图" @click="capture"><Camera :size="15" /></button>
        <button aria-label="调整灵动岛工具" @click="showSettings = !showSettings"><SlidersHorizontal :size="15" /></button>
        <button aria-label="关闭待办灵动岛" @click="close"><X :size="15" /></button>
      </div>
      </Transition>
    </header>
    <Transition name="todo-island-panel">
      <div v-if="expanded" class="todo-island-panel">
        <div v-if="showSettings" class="todo-island-settings">
          <div class="todo-island-setting-row"><span>透明度</span><input :value="opacity" type="range" min="0.55" max="1" step="0.05" @input="saveOpacity(($event.target as HTMLInputElement).value)" /><strong>{{ Math.round(opacity * 100) }}%</strong></div>
          <label class="todo-island-tool-toggle"><Checkbox :model-value="showScreenshot" @update:model-value="(value) => saveToolVisibility(!!value)" /><span>显示截图按钮</span></label>
          <label class="todo-island-tool-picker"><span>快捷工具</span><select v-model="shortcutTool"><option value="none">不显示</option><option value="category">自定义类别数列</option><option value="numeric">均数 / 标准差模拟</option></select></label>
        </div>
        <section v-if="shortcutTool !== 'none'" class="todo-island-tool-form">
          <div class="todo-island-tool-heading"><strong>{{ shortcutTool === 'category' ? '自定义类别数列' : '均数 / 标准差模拟' }}</strong><span>参数会自动保留</span></div>
          <template v-if="shortcutTool === 'category'">
            <div v-for="(row, index) in categoryRows" :key="index" class="todo-island-category-row"><Input v-model.number="row.value" type="number" aria-label="类别值" /><Input v-model.number="row.count" type="number" min="0" aria-label="类别数量" /><button type="button" aria-label="删除类别" :disabled="categoryRows.length < 2" @click="categoryRows.splice(index, 1)"><Trash2 :size="12" /></button></div>
            <div class="todo-island-tool-actions"><button type="button" @click="categoryRows.push({ value: categoryRows.length, count: 10 })"><Plus :size="12" />添加类别</button><span>合计 {{ categoryTotal }}</span></div>
            <label class="todo-island-mini-field"><span>随机种子</span><Input v-model.number="categorySeed" type="number" /></label>
          </template>
          <template v-else>
            <div class="todo-island-numeric-grid"><label><span>例数</span><Input v-model.number="numeric.n" type="number" min="2" max="5000" /></label><label><span>均数</span><Input v-model.number="numeric.mean" type="number" step="any" /></label><label><span>标准差</span><Input v-model.number="numeric.sd" type="number" min="0" step="any" /></label><label><span>随机种子</span><Input v-model.number="numeric.seed" type="number" /></label></div>
          </template>
          <button type="button" class="todo-island-generate" :disabled="shortcutBusy" @click="generateShortcut"><LoaderCircle v-if="shortcutBusy" class="spin" :size="13" /><Copy v-else-if="shortcutCopied" :size="13" /><Play v-else :size="13" />{{ shortcutBusy ? '生成中…' : shortcutCopied ? '已自动复制' : '生成' }}</button>
          <div v-if="shortcutError" class="todo-island-tool-error">{{ shortcutError }}</div>
          <div v-if="shortcutResult" class="todo-island-tool-result"><span>已生成 {{ shortcutResult.values.length }} 个数值</span><button type="button" aria-label="复制结果" @click="copyShortcutResult"><Copy :size="13" /></button></div>
        </section>
        <section class="todo-island-list" :class="{ 'todo-island-list-scroll': pending.length > 8 }">
          <div v-for="todo in pending" :key="todo.id" class="todo-island-row">
            <Checkbox :model-value="todo.completed" :aria-label="'完成 ' + todo.text" @update:model-value="(value) => complete(todo, !!value)" />
            <span><strong>{{ todo.text }}</strong><small>{{ todo.task_name || "个人待办" }}{{ todo.due_date ? ` · ${todo.due_date}` : "" }}</small></span>
          </div>
          <div v-if="!pending.length" class="todo-island-empty"><Check :size="18" />没有未完成待办</div>
        </section>
      </div>
    </Transition>
  </main>
</template>
