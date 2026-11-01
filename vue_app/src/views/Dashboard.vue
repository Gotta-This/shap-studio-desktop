<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowRight,
  Folder,
  Check,
  Inbox,
  Plus,
  SlidersHorizontal,
  ChartNoAxesCombined,
  FileSpreadsheet,
  ArrowUpRight,
  Sun,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import PageHeading from "@/components/PageHeading.vue";
import EmptyState from "@/components/EmptyState.vue";
import { state, today, dateText } from "@/lib/api";
const router = useRouter(),
  pending = computed(() => state.todos.filter((t) => !t.completed)),
  urgent = computed(() =>
    [...pending.value]
      .sort((a, b) =>
        (a.due_date || "9999").localeCompare(b.due_date || "9999"),
      )
      .slice(0, 5),
  );
const tools = [
  {
    path: "category",
    name: "自定义类别数列",
    desc: "按类别与数量生成随机数列",
    icon: SlidersHorizontal,
  },
  {
    path: "numeric",
    name: "均数 / 标准差模拟",
    desc: "从汇总统计生成模拟数值",
    icon: ChartNoAxesCombined,
  },
  {
    path: "word",
    name: "Word 转 Excel",
    desc: "导入表格，核对指标与分组",
    icon: FileSpreadsheet,
  },
  {
    path: "shap",
    name: "模拟数据生图",
    desc: "数据、模型与 SHAP 图表",
    icon: ChartNoAxesCombined,
  },
];
const dayLabel = computed(() =>
  new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date()),
);
</script>
<template>
  <section>
    <PageHeading
      title="工作台"
      subtitle="把稿件、材料与科研工作安排得井井有条。"
      ><span class="today-label"
        ><Sun :size="16" />{{ dayLabel }}</span
      ></PageHeading
    >
    <div class="welcome-panel">
      <div>
        <Badge variant="secondary">个人工作空间</Badge>
        <h2>从一项清晰的工作开始。</h2>
        <p>
          {{
            pending.length
              ? "还有 " + pending.length + " 项工作待处理，让每一步都有着落。"
              : "今天的工作由你安排，材料与进度都保存在本机。"
          }}
        </p>
        <Button @click="router.push(state.root ? '/workspace' : '/settings')"
          >{{ state.root ? "打开稿件工作空间" : "选择本地工作空间"
          }}<ArrowRight :size="15"
        /></Button>
      </div>
      <div class="welcome-art" aria-hidden="true">
        <div><Folder :size="31" /><span>稿件与材料</span><i /></div>
        <div>
          <Check :size="25" /><span>下一步工作</span><small>有序推进</small>
        </div>
      </div>
    </div>
    <div class="dashboard-grid">
      <div class="panel">
        <div class="panel-heading">
          <h2>
            接下来要做的事
            <Badge variant="secondary">{{ pending.length }}</Badge>
          </h2>
          <RouterLink to="/todos" class="subtle-link"
            >全部待办 <ArrowUpRight :size="13"
          /></RouterLink>
        </div>
        <button
          v-for="todo in urgent"
          :key="todo.id"
          class="dashboard-todo"
          @click="
            router.push(todo.task_id ? '/workspace/' + todo.task_id : '/todos')
          "
        >
          <span class="round-check" />
          <div>
            <strong>{{ todo.text }}</strong
            ><small
              >{{ todo.client ? todo.client + " · " : ""
              }}{{ todo.task_name }}</small
            >
          </div>
          <span
            :class="[
              'due-label',
              { overdue: todo.due_date && todo.due_date <= today() },
            ]"
            >{{ dateText(todo.due_date) }}</span
          ></button
        ><EmptyState
          v-if="!urgent.length"
          title="今天没有待办"
          description="给自己留一点从容，也可以添加新的工作。"
          ><Button variant="outline" @click="router.push('/todos')"
            ><Plus :size="14" />添加待办</Button
          ></EmptyState
        >
      </div>
      <div class="panel overview-panel">
        <div class="panel-heading"><h2>工作空间概览</h2></div>
        <RouterLink to="/workspace"
          ><Folder :size="17" /><span>稿件任务</span
          ><strong>{{ state.tasks.length }}</strong></RouterLink
        ><RouterLink to="/todos"
          ><Check :size="17" /><span>未完成待办</span
          ><strong>{{ pending.length }}</strong></RouterLink
        ><RouterLink to="/inbox"
          ><Inbox :size="17" /><span>待归档材料</span
          ><strong>{{ state.inbox.length }}</strong></RouterLink
        >
        <div class="overview-note">
          <i />{{
            state.root ? "任务与文件保存在本机目录" : "选择目录后开始整理新稿件"
          }}
        </div>
      </div>
    </div>
    <div class="section-title">
      <h2>科研工具</h2>
      <span>独立参数，随时切换</span>
    </div>
    <div class="tool-cards">
      <RouterLink
        v-for="tool in tools"
        :key="tool.path"
        :to="'/tools/' + tool.path"
        ><div class="tool-icon"><component :is="tool.icon" :size="21" /></div>
        <ArrowUpRight class="tool-arrow" :size="16" />
        <h3>{{ tool.name }}</h3>
        <p>{{ tool.desc }}</p></RouterLink
      >
    </div>
  </section>
</template>
