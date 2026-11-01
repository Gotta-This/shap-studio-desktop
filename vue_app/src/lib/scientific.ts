import { reactive } from "vue";
import { api } from "./api";
export const scientificJobs = reactive<
  Record<
    string,
    {
      id: string;
      message: string;
      busy: boolean;
      error: string;
      result: any;
      cancelRequested: boolean;
    }
  >
>({});
export function jobFor(kind: string) {
  scientificJobs[kind] ||= {
    id: "",
    message: "",
    busy: false,
    error: "",
    result: null,
    cancelRequested: false,
  };
  return scientificJobs[kind];
}
export async function startJob(
  kind: "word" | "shap" | "numeric" | "category",
  params: any,
  slot: string = kind,
) {
  const job = jobFor(slot);
  if (job.busy) return;
  job.id = "";
  job.cancelRequested = false;
  job.busy = true;
  job.error = "";
  job.message = "正在准备…";
  try {
    const started = await api("tool.job.start", { kind, params });
    job.id = started.id;
    if (job.cancelRequested) await api("tool.job.cancel", { id: job.id });
    while (job.busy) {
      await new Promise((r) => setTimeout(r, 500));
      const status = await api("tool.job.status", { id: job.id });
      job.message = status.message;
      if (status.status === "done") {
        job.result = status.result;
        job.busy = false;
      } else if (status.status === "error" || status.status === "cancelled") {
        job.error = status.status === "error" ? status.message : "";
        job.busy = false;
      }
    }
  } catch (e) {
    job.error = e instanceof Error ? e.message : String(e);
    job.busy = false;
  }
}
export async function cancelJob(kind: string) {
  const job = jobFor(kind);
  if (job.busy) {
    job.cancelRequested = true;
    job.message = "正在取消，等待当前步骤结束…";
    try {
      if (job.id) await api("tool.job.cancel", { id: job.id });
    } catch (e) {
      job.error = e instanceof Error ? e.message : String(e);
    }
  }
}
export const fieldTypes = [
  { value: "unknown", label: "待选择类型" },
  { value: "mean_sd", label: "均数±标准差" },
  { value: "quantile", label: "中位数（Q1，Q3）" },
  { value: "binary", label: "二分类：确认类别" },
  { value: "gender", label: "男 / 女" },
  { value: "yesno", label: "有 / 无" },
  { value: "binary01", label: "编码 1 / 0" },
  { value: "category", label: "自定义多分类" },
  { value: "derived", label: "由其他分类派生" },
  { value: "excluded", label: "仅保留来源，不生成" },
];
export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}
export function ruleSummary(f: any) {
  if (f.kind === "mean_sd" || !f.kind)
    return `${f.mean ?? "待补"} ± ${f.sd ?? "待补"} · ${f.digits ?? 0} 位小数`;
  if (f.kind === "quantile")
    return `${f.median ?? "待补"}（${f.q1 ?? "待补"}，${f.q3 ?? "待补"}）`;
  if (f.kind === "excluded") return "保留来源，不输出病例列";
  return (f.labels || [])
    .map((x: any, i: number) => `${x} ${f.weights?.[i] ?? "待补"}%`)
    .join("；");
}
export const plotNames: Record<string, string> = {
  common: "公共样式",
  summary: "SHAP 摘要图",
  bar: "特征重要性条形图",
  force: "单样本力图",
  waterfall: "单样本瀑布图",
  dependence_protective: "保护因素依赖图",
  dependence_risk: "危险因素依赖图",
};
