<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { Camera, Check, Copy, Delete, ListTodo, LoaderCircle, Pin, PinOff, Play, Plus, SlidersHorizontal, Trash2, X } from "lucide-vue-next";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, notify, type Todo } from "@/lib/api";
import { clone, jobFor, startJob } from "@/lib/scientific";

const todos = ref<Todo[]>([]);
const expanded = ref(false);
const ready = ref(false);
const showSettings = ref(false);
const toolSelectOpen = ref(false);
const islandHovered = ref(false);
const dragging = ref(false);
const longPressing = ref(false);
const opacity = ref(Number(localStorage.getItem("todo-island-opacity") || "0.94"));
const compactWidth = ref(240);
const expandedWidth = ref(380);
const animationMs = ref(360);
const showScreenshot = ref(true);
const shortcutTool = ref(localStorage.getItem("todo-island-tool") || "none");
const featuredTodoId = ref(localStorage.getItem("todo-island-featured-todo") || "");
const storedIslandX = Number(localStorage.getItem("todo-island-position-x"));
const islandPositionX = ref(Number.isFinite(storedIslandX) ? storedIslandX : null);
const categoryRows = ref<{ value: number; count: number }[]>(loadStored("todo-island-category-rows", [{ value: 1, count: 28 }, { value: 0, count: 93 }]));
const categorySeed = ref(Number(localStorage.getItem("todo-island-category-seed") || "12"));
const numeric = reactive(loadStored("todo-island-numeric", { n: 70, mean: 27.92, sd: 14.87, digits: 0, lower: null as number | null, upper: null as number | null, mode: "target", seed: 12 }));
type CalculatorOperator = "+" | "−" | "×" | "÷";
type CalculatorState = {
  display: string;
  storedValue: number | null;
  operator: CalculatorOperator | null;
  waitingForOperand: boolean;
  justEvaluated: boolean;
  expression: string;
};
const calculator = reactive<CalculatorState>(loadStored("todo-island-calculator", {
  display: "0",
  storedValue: null,
  operator: null,
  waitingForOperand: false,
  justEvaluated: false,
  expression: "",
}));
const shortcutResult = ref<any>(null);
const shortcutBusy = ref(false);
const shortcutError = ref("");
const shortcutCopied = ref(false);
const quickTodoText = ref("");
const quickTodoBusy = ref(false);
const priorityRank: Record<string, number> = { high: 0, normal: 1, low: 2 };
const pending = computed(() => todos.value.filter((todo) => !todo.completed).sort(compareTodos));
let timer: ReturnType<typeof setInterval> | undefined;
let collapseTimer: ReturnType<typeof setTimeout> | undefined;
let collapseResizeTimer: ReturnType<typeof setTimeout> | undefined;
let resizeSequence = 0;
let unlistenTodoUpdated: (() => void) | undefined;
let unlistenConfigUpdated: (() => void) | undefined;
let unlistenHover: (() => void) | undefined;
let shortcutCopiedTimer: ReturnType<typeof setTimeout> | undefined;
let longPressTimer: ReturnType<typeof setTimeout> | undefined;
let panelResizeObserver: ResizeObserver | undefined;
let observedPanel: HTMLElement | undefined;
let panelResizeTimer: ReturnType<typeof setTimeout> | undefined;
let pressState: { pointerId: number; startX: number; target: HTMLElement } | undefined;
let dragState: {
  pointerId: number;
  startX: number;
  originX: number;
  minX: number;
  maxX: number;
  topY: number;
  moveWindow: (x: number, y: number) => Promise<void>;
} | undefined;
let lightweightTodosUnavailable = false;

function loadStored<T>(key: string, fallback: T): T {
  try { const value = localStorage.getItem(key); return value ? JSON.parse(value) as T : fallback; } catch { return fallback; }
}
function saveShortcutState() {
  localStorage.setItem("todo-island-tool", shortcutTool.value);
  localStorage.setItem("todo-island-category-rows", JSON.stringify(categoryRows.value));
  localStorage.setItem("todo-island-category-seed", String(categorySeed.value));
  localStorage.setItem("todo-island-numeric", JSON.stringify(numeric));
  localStorage.setItem("todo-island-calculator", JSON.stringify(calculator));
}
watch([shortcutTool, categoryRows, categorySeed, numeric, calculator], saveShortcutState, { deep: true });
watch([shortcutTool, showSettings, pending, () => categoryRows.value.length], () => { if (expanded.value) void resizeIsland(true); });
watch(showSettings, (open) => {
  if (!open) return;
  if (collapseTimer) clearTimeout(collapseTimer);
  if (collapseResizeTimer) clearTimeout(collapseResizeTimer);
});
const categoryTotal = computed(() => categoryRows.value.reduce((sum, row) => sum + Number(row.count || 0), 0));
const shortcutJob = computed(() => jobFor("todo-island"));

function compareTodos(left: Todo, right: Todo) {
  const leftFeatured = left.id === featuredTodoId.value ? 0 : 1;
  const rightFeatured = right.id === featuredTodoId.value ? 0 : 1;
  if (leftFeatured !== rightFeatured) return leftFeatured - rightFeatured;
  const priorityDifference = (priorityRank[left.priority] ?? 1) - (priorityRank[right.priority] ?? 1);
  if (priorityDifference) return priorityDifference;
  const leftDue = left.due_date || "9999-12-31";
  const rightDue = right.due_date || "9999-12-31";
  const dueDifference = leftDue.localeCompare(rightDue);
  if (dueDifference) return dueDifference;
  const createdDifference = (right.created_at || "").localeCompare(left.created_at || "");
  if (createdDifference) return createdDifference;
  return (right.created_order || 0) - (left.created_order || 0) || right.id.localeCompare(left.id);
}
function toggleFeaturedTodo(id: string) {
  featuredTodoId.value = featuredTodoId.value === id ? "" : id;
  if (featuredTodoId.value) localStorage.setItem("todo-island-featured-todo", featuredTodoId.value);
  else localStorage.removeItem("todo-island-featured-todo");
}
async function addQuickTodo() {
  const text = quickTodoText.value.trim();
  if (!text || quickTodoBusy.value) return;
  quickTodoBusy.value = true;
  try {
    await api("todo.save", { text, priority: "normal", due_date: null, task_id: null });
    quickTodoText.value = "";
    await refresh();
    notify("待办已添加。");
  } catch (error) {
    notify(String((error as Error).message || error), true);
  } finally {
    quickTodoBusy.value = false;
  }
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}
function cancelLongPress() {
  if (longPressTimer) clearTimeout(longPressTimer);
  longPressTimer = undefined;
  pressState = undefined;
  longPressing.value = false;
}
function saveIslandPosition(x: number) {
  islandPositionX.value = x;
  localStorage.setItem("todo-island-position-x", String(x));
}
function schedulePanelResize() {
  if (!expanded.value) return;
  if (panelResizeTimer) clearTimeout(panelResizeTimer);
  panelResizeTimer = setTimeout(() => { void resizeIsland(true); }, 40);
}
function formatCalculatorValue(value: number) {
  if (!Number.isFinite(value)) return "错误";
  const compact = Number(value.toPrecision(12)).toString();
  return compact.length <= 14 ? compact : value.toExponential(8);
}
function resetCalculator() {
  calculator.display = "0";
  calculator.storedValue = null;
  calculator.operator = null;
  calculator.waitingForOperand = false;
  calculator.justEvaluated = false;
  calculator.expression = "";
}
function calculatorDigit(digit: string) {
  if (calculator.display === "错误" || calculator.waitingForOperand || calculator.justEvaluated) {
    calculator.display = digit;
    calculator.waitingForOperand = false;
    calculator.justEvaluated = false;
    if (calculator.operator === null) calculator.expression = digit;
    return;
  }
  if (calculator.display === "0") calculator.display = digit;
  else if (calculator.display.length < 14) calculator.display += digit;
}
function calculatorDecimal() {
  if (calculator.display === "错误" || calculator.waitingForOperand || calculator.justEvaluated) {
    calculator.display = "0.";
    calculator.waitingForOperand = false;
    calculator.justEvaluated = false;
    if (calculator.operator === null) calculator.expression = "0.";
    return;
  }
  if (!calculator.display.includes(".")) calculator.display += ".";
}
function calculatorBackspace() {
  if (calculator.display === "错误" || calculator.waitingForOperand || calculator.justEvaluated) return;
  calculator.display = calculator.display.length > 1 ? calculator.display.slice(0, -1) : "0";
  if (calculator.display === "-") calculator.display = "0";
}
function calculatorToggleSign() {
  if (calculator.display === "错误" || Number(calculator.display) === 0) return;
  calculator.display = calculator.display.startsWith("-") ? calculator.display.slice(1) : `-${calculator.display}`;
}
function calculatorPercent() {
  if (calculator.display === "错误") return;
  calculator.display = formatCalculatorValue(Number(calculator.display) / 100);
}
function applyCalculatorOperation(left: number, operator: CalculatorOperator, right: number) {
  if (operator === "+") return left + right;
  if (operator === "−") return left - right;
  if (operator === "×") return left * right;
  return right === 0 ? Number.NaN : left / right;
}
function calculatorOperator(operator: CalculatorOperator) {
  if (calculator.display === "错误") return;
  const input = Number(calculator.display);
  if (calculator.operator && calculator.waitingForOperand) {
    calculator.operator = operator;
    calculator.expression = `${formatCalculatorValue(calculator.storedValue ?? input)} ${operator}`;
    return;
  }
  if (calculator.storedValue === null) calculator.storedValue = input;
  else if (calculator.operator) {
    const result = applyCalculatorOperation(calculator.storedValue, calculator.operator, input);
    if (!Number.isFinite(result)) {
      calculator.display = "错误";
      calculator.storedValue = null;
      calculator.operator = null;
      calculator.waitingForOperand = true;
      calculator.justEvaluated = true;
      calculator.expression = "不能除以 0";
      return;
    }
    calculator.display = formatCalculatorValue(result);
    calculator.storedValue = result;
  }
  calculator.operator = operator;
  calculator.waitingForOperand = true;
  calculator.justEvaluated = false;
  calculator.expression = `${formatCalculatorValue(calculator.storedValue)} ${operator}`;
}
function calculatorEquals() {
  if (calculator.display === "错误" || calculator.storedValue === null || calculator.operator === null) return;
  const right = Number(calculator.display);
  const left = calculator.storedValue;
  const operator = calculator.operator;
  const result = applyCalculatorOperation(left, operator, right);
  if (!Number.isFinite(result)) {
    calculator.display = "错误";
    calculator.expression = "不能除以 0";
  } else {
    calculator.display = formatCalculatorValue(result);
    calculator.expression = `${formatCalculatorValue(left)} ${operator} ${formatCalculatorValue(right)} =`;
  }
  calculator.storedValue = null;
  calculator.operator = null;
  calculator.waitingForOperand = true;
  calculator.justEvaluated = true;
}
function handleCalculatorKeydown(event: KeyboardEvent) {
  if (shortcutTool.value !== "calculator") return;
  if (event.target instanceof HTMLElement && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) return;
  const key = event.key;
  const code = event.code;
  if (/^[0-9]$/.test(key)) calculatorDigit(key);
  else if (key === "." || key === ",") calculatorDecimal();
  else if (key === "+" || key === "Add" || code === "NumpadAdd") calculatorOperator("+");
  else if (key === "-" || key === "Subtract" || code === "NumpadSubtract") calculatorOperator("−");
  else if (key === "*" || key === "Multiply" || code === "NumpadMultiply" || key.toLowerCase() === "x") calculatorOperator("×");
  else if (key === "/" || key === "Divide" || code === "NumpadDivide") calculatorOperator("÷");
  else if (key === "%") calculatorPercent();
  else if (key === "Enter" || key === "=") calculatorEquals();
  else if (key === "Backspace") calculatorBackspace();
  else if (key === "NumLock" || code === "NumLock") resetCalculator();
  else if (key === "Escape" || key.toLowerCase() === "c") resetCalculator();
  else return;
  event.preventDefault();
}

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
  let islandWindow: Awaited<ReturnType<typeof import("@tauri-apps/api/window").getCurrentWindow>> | undefined;
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    islandWindow = getCurrentWindow();
    await islandWindow.hide();
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("quickshot_capture");
    setTimeout(() => { void islandWindow?.show(); }, 2200);
  } catch (error) {
    if (islandWindow) await islandWindow.show().catch(() => undefined);
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
    // Wait until the todo list and its transitions have committed before
    // resizing the transparent native window. Resizing on the old DOM can
    // clip the rounded bottom edge while a todo is being completed. The
    // measured panel height also keeps platform display scaling consistent.
    await nextTick();
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    const [{ getCurrentWindow, currentMonitor }, { LogicalPosition, LogicalSize }] = await Promise.all([
      import("@tauri-apps/api/window"),
      import("@tauri-apps/api/dpi"),
    ]);
    const current = getCurrentWindow();
    const monitor = await currentMonitor();
    if (sequence !== resizeSequence) return;
    const width = open ? expandedWidth.value : compactWidth.value;
    const island = document.querySelector<HTMLElement>(".todo-island");
    const header = island?.querySelector<HTMLElement>(".todo-island-header");
    const panel = island?.querySelector<HTMLElement>(".todo-island-panel");
    if (panel && panel !== observedPanel) {
      panelResizeObserver?.disconnect();
      panelResizeObserver = new ResizeObserver(schedulePanelResize);
      panelResizeObserver.observe(panel);
      observedPanel = panel;
    }
    const list = panel?.querySelector<HTMLElement>(".todo-island-list");
    const measuredListHeight = list?.scrollHeight ?? 0;
    const expectedListHeight = pending.value.length
      ? Math.min(300, pending.value.length * 46 + 10)
      : 100;
    const panelChildrenHeight = panel
      ? Array.from(panel.children).reduce((height, child) => {
        const element = child as HTMLElement;
        return Math.max(height, element.offsetTop + element.scrollHeight);
      }, 0)
      : 0;
    const contentHeight = header && panel
      ? Math.ceil(header.getBoundingClientRect().height + Math.max(panel.scrollHeight, panelChildrenHeight) + Math.max(0, expectedListHeight - measuredListHeight))
      : 190;
    const calculatorMinimum = shortcutTool.value === "calculator"
      ? 470 + Math.min(pending.value.length, 8) * 46
      : 0;
    const height = !open ? 44 : Math.min(760, Math.max(190, contentHeight + 2, calculatorMinimum));
    await current.setSize(new LogicalSize(width, height));
    if (monitor) {
      const scale = monitor.scaleFactor;
      const monitorX = monitor.position.x / scale;
      const monitorWidth = monitor.size.width / scale;
      const margin = 8;
      const minX = monitorX + margin;
      const maxX = Math.max(minX, monitorX + monitorWidth - expandedWidth.value - margin);
      const centeredX = monitorX + (monitorWidth - width) / 2;
      const x = clamp(islandPositionX.value ?? centeredX, minX, maxX);
      const y = monitor.position.y / scale + 8;
      if (islandPositionX.value !== null) islandPositionX.value = x;
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
  if (toolSelectOpen.value || dragging.value) {
    if (collapseTimer) clearTimeout(collapseTimer);
    if (collapseResizeTimer) clearTimeout(collapseResizeTimer);
    return;
  }
  if (collapseTimer) clearTimeout(collapseTimer);
  collapseTimer = setTimeout(() => {
    expanded.value = false;
    showSettings.value = false;
    collapseResizeTimer = setTimeout(() => { void resizeIsland(false); }, Math.round(animationMs.value * 0.75));
  }, Math.round(animationMs.value * 0.3));
}
function startLongPress(event: PointerEvent) {
  if (event.button !== 0 || dragging.value || toolSelectOpen.value || pressState) return;
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest("button, input, textarea, select, label, [data-slot='checkbox'], [data-slot='select-trigger']")) return;
  const root = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  if (!root) return;
  pressState = { pointerId: event.pointerId, startX: event.screenX, target: root };
  longPressing.value = true;
  longPressTimer = setTimeout(() => {
    longPressTimer = undefined;
    void beginIslandDrag();
  }, 5000);
}
async function beginIslandDrag() {
  const press = pressState;
  if (!press || dragState || !("__TAURI_INTERNALS__" in window)) return;
  try {
    const [{ getCurrentWindow, currentMonitor }, { LogicalPosition }] = await Promise.all([
      import("@tauri-apps/api/window"),
      import("@tauri-apps/api/dpi"),
    ]);
    const current = getCurrentWindow();
    const monitor = await currentMonitor();
    const outer = await current.outerPosition();
    if (!monitor || pressState !== press) return;
    const scale = monitor.scaleFactor;
    const monitorX = monitor.position.x / scale;
    const monitorWidth = monitor.size.width / scale;
    const margin = 8;
    const minX = monitorX + margin;
    const maxX = Math.max(minX, monitorX + monitorWidth - expandedWidth.value - margin);
    const originX = clamp(outer.x / scale, minX, maxX);
    const topY = monitor.position.y / scale + 8;
    const moveWindow = (x: number, y: number) => current.setPosition(new LogicalPosition(x, y));
    dragState = { pointerId: press.pointerId, startX: press.startX, originX, minX, maxX, topY, moveWindow };
    dragging.value = true;
    longPressing.value = false;
    press.target.setPointerCapture?.(press.pointerId);
    cancelLongPress();
    islandPositionX.value = originX;
    await moveWindow(originX, topY);
  } catch (error) {
    cancelLongPress();
    dragState = undefined;
    dragging.value = false;
    longPressing.value = false;
    notify(`灵动岛移动启动失败：${String((error as Error).message || error)}`, true);
  }
}
function finishIslandDrag(event: PointerEvent) {
  if (!dragState || event.pointerId !== dragState.pointerId) {
    cancelLongPress();
    return;
  }
  const root = event.currentTarget instanceof HTMLElement ? event.currentTarget : null;
  try { root?.releasePointerCapture?.(event.pointerId); } catch { /* pointer capture may already be released */ }
  saveIslandPosition(islandPositionX.value ?? dragState.originX);
  dragState = undefined;
  dragging.value = false;
  cancelLongPress();
}
function handleIslandPointerDown(event: PointerEvent) {
  startLongPress(event);
}
function handleIslandPointerEnter() {
  islandHovered.value = true;
  expand();
}
function handleIslandPointerMove(event: PointerEvent) {
  islandHovered.value = true;
  if (dragState && event.pointerId === dragState.pointerId) {
    const nextX = clamp(dragState.originX + event.screenX - dragState.startX, dragState.minX, dragState.maxX);
    islandPositionX.value = nextX;
    void dragState.moveWindow(nextX, dragState.topY);
    return;
  }
  expand();
}
function handleIslandPointerLeave() {
  islandHovered.value = false;
  if (!dragging.value) cancelLongPress();
  scheduleCollapse();
}
function handleIslandPointerUp(event: PointerEvent) {
  finishIslandDrag(event);
}
function handleIslandPointerCancel(event: PointerEvent) {
  finishIslandDrag(event);
}
function handleToolSelectOpen(open: boolean) {
  toolSelectOpen.value = open;
  if (open) {
    if (collapseTimer) clearTimeout(collapseTimer);
    if (collapseResizeTimer) clearTimeout(collapseResizeTimer);
    return;
  }
  if (!islandHovered.value) scheduleCollapse();
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
  void resizeIsland(false);
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
  if (panelResizeTimer) clearTimeout(panelResizeTimer);
  panelResizeObserver?.disconnect();
  panelResizeObserver = undefined;
  observedPanel = undefined;
  cancelLongPress();
  dragState = undefined;
  dragging.value = false;
  unlistenTodoUpdated?.();
  unlistenConfigUpdated?.();
  unlistenHover?.();
});
</script>

<template>
  <main class="todo-island" :class="{ 'todo-island-expanded': expanded, 'todo-island-ready': ready, 'todo-island-with-tool': shortcutTool !== 'none', 'todo-island-tool-category': shortcutTool === 'category', 'todo-island-tool-numeric': shortcutTool === 'numeric', 'todo-island-tool-calculator': shortcutTool === 'calculator', 'todo-island-dragging': dragging, 'todo-island-long-pressing': longPressing }" :style="{ '--todo-opacity': opacity, '--todo-animation-ms': `${animationMs}ms` }" tabindex="-1" @keydown="handleCalculatorKeydown" @pointerdown="handleIslandPointerDown" @pointerup="handleIslandPointerUp" @pointercancel="handleIslandPointerCancel" @pointerenter="handleIslandPointerEnter" @pointermove="handleIslandPointerMove" @pointerleave="handleIslandPointerLeave">
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
          <div class="todo-island-tool-picker">
            <span>快捷工具</span>
            <Select v-model="shortcutTool" :open="toolSelectOpen" @update:open="handleToolSelectOpen">
              <SelectTrigger class="todo-island-tool-select" aria-label="快捷工具">
                <SelectValue />
              </SelectTrigger>
              <SelectContent class="todo-island-tool-select-content" @pointerenter="expand" @pointermove="expand" @pointerleave="scheduleCollapse">
                <SelectItem value="none">不显示</SelectItem>
                <SelectItem value="category">自定义类别数列</SelectItem>
                <SelectItem value="numeric">均数 / 标准差模拟</SelectItem>
                <SelectItem value="calculator">计算器</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <small class="todo-island-drag-hint">{{ dragging ? '左右拖动中' : longPressing ? '继续按住，准备移动…' : '点击图钉优先显示，长按灵动岛 5 秒可移动位置' }}</small>
        </div>
        <form class="todo-island-quick-add" autocomplete="off" @submit.prevent="addQuickTodo">
          <input v-model="quickTodoText" name="todo-quick-add" autocomplete="new-password" maxlength="300" placeholder="新增待办…" aria-label="新增待办" />
          <button type="submit" :disabled="quickTodoBusy || !quickTodoText.trim()" aria-label="添加待办"><Plus :size="14" /></button>
        </form>
        <section v-if="shortcutTool !== 'none'" class="todo-island-tool-form">
          <div class="todo-island-tool-heading"><strong>{{ shortcutTool === 'category' ? '自定义类别数列' : shortcutTool === 'numeric' ? '均数 / 标准差模拟' : '计算器' }}</strong><span>{{ shortcutTool === 'calculator' ? '支持键盘输入' : '参数会自动保留' }}</span></div>
          <template v-if="shortcutTool === 'category'">
            <div v-for="(row, index) in categoryRows" :key="index" class="todo-island-category-row"><Input v-model.number="row.value" type="number" aria-label="类别值" /><Input v-model.number="row.count" type="number" min="0" aria-label="类别数量" /><button type="button" aria-label="删除类别" :disabled="categoryRows.length < 2" @click="categoryRows.splice(index, 1)"><Trash2 :size="12" /></button></div>
            <div class="todo-island-tool-actions"><button type="button" @click="categoryRows.push({ value: categoryRows.length, count: 10 })"><Plus :size="12" />添加类别</button><span>合计 {{ categoryTotal }}</span></div>
            <label class="todo-island-mini-field"><span>随机种子</span><Input v-model.number="categorySeed" type="number" /></label>
          </template>
          <template v-else-if="shortcutTool === 'numeric'">
            <div class="todo-island-numeric-grid"><label><span>例数</span><Input v-model.number="numeric.n" type="number" min="2" max="5000" /></label><label><span>均数</span><Input v-model.number="numeric.mean" type="number" step="any" /></label><label><span>标准差</span><Input v-model.number="numeric.sd" type="number" min="0" step="any" /></label><label><span>随机种子</span><Input v-model.number="numeric.seed" type="number" /></label></div>
          </template>
          <template v-else>
            <div class="todo-island-calculator-display" aria-live="polite"><span>{{ calculator.expression || '输入数字开始' }}</span><strong>{{ calculator.display }}</strong></div>
            <div class="todo-island-calculator-grid" role="group" aria-label="计算器按键">
              <button type="button" class="calculator-utility" aria-label="清除" @click="resetCalculator">C</button>
              <button type="button" class="calculator-utility" aria-label="正负号" @click="calculatorToggleSign">±</button>
              <button type="button" class="calculator-utility" aria-label="百分比" @click="calculatorPercent">%</button>
              <button type="button" class="calculator-operator" aria-label="除法" @click="calculatorOperator('÷')">÷</button>
              <button v-for="digit in ['7', '8', '9']" :key="digit" type="button" @click="calculatorDigit(digit)">{{ digit }}</button>
              <button type="button" class="calculator-operator" aria-label="乘法" @click="calculatorOperator('×')">×</button>
              <button v-for="digit in ['4', '5', '6']" :key="digit" type="button" @click="calculatorDigit(digit)">{{ digit }}</button>
              <button type="button" class="calculator-operator" aria-label="减法" @click="calculatorOperator('−')">−</button>
              <button v-for="digit in ['1', '2', '3']" :key="digit" type="button" @click="calculatorDigit(digit)">{{ digit }}</button>
              <button type="button" class="calculator-operator" aria-label="加法" @click="calculatorOperator('+')">+</button>
              <button type="button" class="calculator-backspace" aria-label="退格" @click="calculatorBackspace"><Delete :size="13" /></button>
              <button type="button" class="calculator-zero" @click="calculatorDigit('0')">0</button>
              <button type="button" @click="calculatorDecimal">.</button>
              <button type="button" class="calculator-equals" aria-label="等于" @click="calculatorEquals">=</button>
            </div>
          </template>
          <template v-if="shortcutTool !== 'calculator'">
            <button type="button" class="todo-island-generate" :disabled="shortcutBusy" @click="generateShortcut"><LoaderCircle v-if="shortcutBusy" class="spin" :size="13" /><Copy v-else-if="shortcutCopied" :size="13" /><Play v-else :size="13" />{{ shortcutBusy ? '生成中…' : shortcutCopied ? '已自动复制' : '生成' }}</button>
            <div v-if="shortcutError" class="todo-island-tool-error">{{ shortcutError }}</div>
            <div v-if="shortcutResult" class="todo-island-tool-result"><span>已生成 {{ shortcutResult.values.length }} 个数值</span><button type="button" aria-label="复制结果" @click="copyShortcutResult"><Copy :size="13" /></button></div>
          </template>
        </section>
        <section class="todo-island-list" :class="{ 'todo-island-list-scroll': pending.length > 8 }">
          <div v-for="todo in pending" :key="todo.id" class="todo-island-row">
            <Checkbox :model-value="todo.completed" :aria-label="'完成 ' + todo.text" @update:model-value="(value) => complete(todo, !!value)" />
            <span><strong>{{ todo.text }}</strong><small>{{ todo.task_name || "个人待办" }}{{ todo.due_date ? ` · ${todo.due_date}` : "" }}</small></span>
            <button type="button" class="todo-island-pin" :aria-label="featuredTodoId === todo.id ? '取消优先显示 ' + todo.text : '优先显示 ' + todo.text" @click.stop="toggleFeaturedTodo(todo.id)"><PinOff v-if="featuredTodoId === todo.id" :size="14" /><Pin v-else :size="14" /></button>
          </div>
          <div v-if="!pending.length" class="todo-island-empty"><Check :size="18" />没有未完成待办</div>
        </section>
      </div>
    </Transition>
  </main>
</template>
