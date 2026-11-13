<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Check, GripVertical, X } from "lucide-vue-next";
import { Checkbox } from "@/components/ui/checkbox";
import { api, action, type Todo } from "@/lib/api";

const todos = ref<Todo[]>([]);
let timer: ReturnType<typeof setInterval> | undefined;
const pending = computed(() => todos.value.filter((todo) => !todo.completed));
async function refresh() {
  try {
    const result = await api<{ todos: Todo[] }>("state");
    todos.value = result.todos.filter((todo) => !todo.completed);
  } catch {
    // The widget remains visible when the main app is restarting.
  }
}
async function complete(todo: Todo, value: boolean) {
  todo.completed = value;
  await action("todo.save", { id: todo.id, completed: value }, value ? "已完成。" : "已恢复。");
}
async function close() {
  if ("__TAURI_INTERNALS__" in window) {
    const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
    const current = await WebviewWindow.getByLabel("todo-widget");
    await current?.close();
  }
}
onMounted(() => { void refresh(); timer = setInterval(refresh, 15000); });
onUnmounted(() => { if (timer) clearInterval(timer); });
</script>

<template>
  <main class="todo-widget-window">
    <header class="todo-widget-header" data-tauri-drag-region>
      <div><GripVertical :size="15" /><strong>待办事项</strong><span>{{ pending.length }}</span></div>
      <button aria-label="关闭桌面待办" @click="close"><X :size="15" /></button>
    </header>
    <section class="todo-widget-list">
      <label v-for="todo in pending.slice(0, 8)" :key="todo.id" class="todo-widget-row">
        <Checkbox :model-value="todo.completed" :aria-label="'完成 ' + todo.text" @update:model-value="(value) => complete(todo, !!value)" />
        <span><strong>{{ todo.text }}</strong><small>{{ todo.task_name || "个人待办" }}{{ todo.due_date ? ` · ${todo.due_date}` : "" }}</small></span>
      </label>
      <div v-if="!pending.length" class="todo-widget-empty"><Check :size="20" />没有未完成待办</div>
    </section>
  </main>
</template>
