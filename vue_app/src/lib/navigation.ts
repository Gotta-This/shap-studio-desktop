import {
  LayoutDashboard,
  FolderKanban,
  ListTodo,
  Inbox,
  ListOrdered,
  Sigma,
  FileSpreadsheet,
  ChartScatter,
  BrainCircuit,
  MonitorCog,
  Table2,
  Scale,
} from "lucide-vue-next";

export const mainNavigation = [
  { path: "/", name: "工作台", icon: LayoutDashboard },
  { path: "/workspace", name: "稿件工作空间", icon: FolderKanban },
  { path: "/todos", name: "待办事项", icon: ListTodo },
  { path: "/inbox", name: "未分类收件箱", icon: Inbox },
];

export const scientificTools = [
  {
    path: "/tools/category",
    name: "自定义类别数列",
    desc: "按类别与数量生成随机数列",
    icon: ListOrdered,
  },
  {
    path: "/tools/numeric",
    name: "均数 / 标准差模拟",
    desc: "从汇总统计生成模拟数值",
    icon: Sigma,
  },
  {
    path: "/tools/word",
    name: "Word 转 Excel",
    desc: "导入表格，核对指标与分组",
    icon: FileSpreadsheet,
  },
  {
    path: "/tools/shap",
    name: "模拟数据生图",
    desc: "数据、模型与 SHAP 图表",
    icon: ChartScatter,
  },
  {
    path: "/tools/prediction",
    name: "预测模型分析",
    desc: "导入病例，训练二分类模型并生成论文图表",
    icon: BrainCircuit,
  },
  {
    path: "/tools/crosstabs",
    name: "列联表统计分析",
    desc: "按 SPSS CROSSTABS 标准分析分类频数",
    icon: Table2,
  },
  {
    path: "/tools/means-ttest",
    name: "平均值对比（t 检验）",
    desc: "根据两组均值、标准差和例数比较平均值",
    icon: Scale,
  },
  {
    path: "/tools/desktop-layout",
    name: "桌面布局备份",
    desc: "备份 Windows 图标排列，保留历史并一键恢复",
    icon: MonitorCog,
  },
];
