<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Grid2X2,
  Folder,
  Check,
  Inbox,
  SlidersHorizontal,
  ChartNoAxesCombined,
  FileSpreadsheet,
  Settings2,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  ArrowUpRight,
  X,
  CircleAlert,
  CircleCheck,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { state, feedback, refresh, notify, desktop } from "@/lib/api";
import { scientificJobs } from "@/lib/scientific";
const route = useRoute(),
  router = useRouter(),
  collapsed = ref(false),
  searchOpen = ref(false),
  query = ref("");
const main = [
  { path: "/", name: "工作台", icon: Grid2X2 },
  { path: "/workspace", name: "稿件工作空间", icon: Folder },
  { path: "/todos", name: "待办事项", icon: Check },
  { path: "/inbox", name: "未分类收件箱", icon: Inbox },
];
const tools = [
  { path: "/tools/category", name: "自定义类别数列", icon: SlidersHorizontal },
  {
    path: "/tools/numeric",
    name: "均数 / 标准差模拟",
    icon: ChartNoAxesCombined,
  },
  { path: "/tools/word", name: "Word 转 Excel", icon: FileSpreadsheet },
  { path: "/tools/shap", name: "模拟数据生图", icon: ChartNoAxesCombined },
];
const pending = computed(() => state.todos.filter((t) => !t.completed).length);
const activeName = computed(
  () =>
    [...main, ...tools, { path: "/settings", name: "设置与关于" }].find((n) =>
      n.path === "/" ? route.path === "/" : route.path.startsWith(n.path),
    )?.name || "工作空间",
);
const results = computed(() => {
  const q = query.value.trim().toLocaleLowerCase();
  return state.tasks
    .filter(
      (t) =>
        !q ||
        [t.name, t.client, ...t.tags, t.todo_text, t.file_names]
          .join(" ")
          .toLocaleLowerCase()
          .includes(q),
    )
    .slice(0, 10);
});
function active(path: string) {
  return path === "/" ? route.path === "/" : route.path.startsWith(path);
}
function shortcut(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    searchOpen.value = !searchOpen.value;
  }
}
let closeUnlisten: (() => void) | undefined;
let unlisten: (() => void) | undefined;
onMounted(async () => {
  if (desktop) {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    closeUnlisten = await getCurrentWindow().onCloseRequested((event) => {
      if (Object.values(scientificJobs).some((job) => job.busy)) {
        event.preventDefault();
        notify("科学计算尚未结束，请完成或取消计算后再关闭应用。");
      }
    });
    const { listen } = await import("@tauri-apps/api/event");
    unlisten = await listen("close-blocked", () =>
      notify("本机计算尚未结束，请完成后再关闭应用。"),
    );
  }
  window.addEventListener("keydown", shortcut);
  try {
    await refresh();
  } catch (e) {
    notify((e as Error).message, true);
  }
});
onUnmounted(() => {
  closeUnlisten?.();
  unlisten?.();
  window.removeEventListener("keydown", shortcut);
});
</script>
<template>
  <div class="app-shell" :class="{ 'sidebar-collapsed': collapsed }">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-icon"><Grid2X2 :size="18" /></span>
        <div><strong>科研数据工具集</strong><small>个人工作空间</small></div>
      </div>
      <button
        class="quick-search"
        aria-label="搜索任务与文件"
        @click="searchOpen = true"
      >
        <Search :size="15" /><span>搜索任务与文件</span><kbd>⌘ K</kbd>
      </button>
      <p class="nav-label">工作空间</p>
      <nav aria-label="工作空间">
        <RouterLink
          v-for="n in main"
          :key="n.path"
          :to="n.path"
          :class="['nav-item', { active: active(n.path) }]"
          :title="n.name"
          ><component :is="n.icon" :size="17" :stroke-width="1.7" /><span>{{
            n.name
          }}</span
          ><small v-if="n.path !== '/'">{{
            n.path === "/workspace"
              ? state.tasks.length
              : n.path === "/todos"
                ? pending
                : state.inbox.length
          }}</small></RouterLink
        >
      </nav>
      <p class="nav-label tools-label">科研工具</p>
      <nav aria-label="科研工具">
        <RouterLink
          v-for="n in tools"
          :key="n.path"
          :to="n.path"
          :class="['nav-item', { active: active(n.path) }]"
          :title="n.name"
          ><component :is="n.icon" :size="17" :stroke-width="1.7" /><span>{{
            n.name
          }}</span></RouterLink
        >
      </nav>
      <div class="sidebar-bottom">
        <div class="workspace-status">
          <Folder :size="16" /><span>本地工作空间</span>
        </div>
        <small class="saved-state"
          ><i />{{ state.root ? "已连接本机目录" : "尚未选择目录" }}</small
        ><RouterLink
          to="/settings"
          :class="['nav-item', { active: active('/settings') }]"
          ><Settings2 :size="17" /><span>设置</span></RouterLink
        >
        <div class="version">
          <span>V3 · 预览版</span
          ><RouterLink to="/settings"
            >检查更新 <ArrowUpRight :size="11"
          /></RouterLink>
        </div>
      </div>
    </aside>
    <div class="shell-body">
      <header class="topbar">
        <Button
          variant="ghost"
          size="icon"
          :aria-label="collapsed ? '展开侧栏' : '收起侧栏'"
          @click="collapsed = !collapsed"
          ><PanelLeftOpen v-if="collapsed" :size="17" /><PanelLeftClose
            v-else
            :size="17" /></Button
        ><span class="breadcrumb">工作空间</span
        ><span class="breadcrumb-separator">/</span><span>{{ activeName }}</span
        ><span class="offline"><i />本机 · 离线可用</span>
      </header>
      <main class="main-content">
        <RouterView v-slot="{ Component }"
          ><KeepAlive><component :is="Component" /></KeepAlive
        ></RouterView>
      </main>
    </div>
    <div
      v-if="feedback.text"
      role="status"
      :class="['toast', { 'toast-error': feedback.error }]"
    >
      <CircleAlert v-if="feedback.error" :size="18" /><CircleCheck
        v-else
        :size="18"
      /><span>{{ feedback.text }}</span
      ><Button
        size="icon"
        variant="ghost"
        aria-label="关闭提示"
        @click="feedback.text = ''"
        ><X :size="15"
      /></Button>
    </div>
    <Dialog v-model:open="searchOpen"
      ><DialogContent class="sm:max-w-xl"
        ><DialogHeader
          ><DialogTitle>搜索任务与文件</DialogTitle
          ><DialogDescription
            >搜索客户、任务、标签、文件名称或下一步工作。</DialogDescription
          ></DialogHeader
        ><Input
          v-model="query"
          autofocus
          aria-label="全局搜索"
          placeholder="搜索…"
        />
        <div class="search-results">
          <button
            v-for="task in results"
            :key="task.id"
            @click="
              router.push('/workspace/' + task.id);
              searchOpen = false;
            "
          >
            <Folder :size="18" />
            <div>
              <strong>{{ task.name }}</strong
              ><small>{{ task.client }} · {{ task.tags.join(" / ") }}</small>
            </div>
            <ArrowUpRight :size="15" />
          </button>
          <p v-if="!results.length" class="muted p-4">没有找到匹配的任务。</p>
        </div></DialogContent
      ></Dialog
    >
  </div>
</template>
