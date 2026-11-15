import { reactive } from "vue";
import { version } from "../../package.json";
import { api, bytes, notify, openPath } from "./api";
import { scientificJobs } from "./scientific";
type UpdateProgress = {
  status: "idle" | "starting" | "downloading" | "verifying" | "complete" | "error";
  downloaded: number;
  total: number;
  percent: number;
  speed: number;
  error: string;
};
export const updates = reactive({
  current: version,
  status: "idle",
  release: null as any,
  path: "",
  error: "",
  progress: {
    status: "idle",
    downloaded: 0,
    total: 0,
    percent: 0,
    speed: 0,
    error: "",
  } as UpdateProgress,
});
let progressTimer: ReturnType<typeof setInterval> | undefined;

async function refreshProgress() {
  try {
    updates.progress = await api<UpdateProgress>("updates.progress");
  } catch {
    // The download result remains authoritative when progress polling is unavailable.
  }
}

export function formatUpdateBytes(value: number) {
  return bytes(Math.max(0, Number(value) || 0));
}

export function formatUpdateSpeed(value: number) {
  return `${formatUpdateBytes(value)}/s`;
}
export async function checkUpdate() {
  if (updates.status === "checking" || updates.status === "downloading") return;
  updates.status = "checking";
  updates.error = "";
  try {
    updates.release = await api("updates.check");
    updates.status = "ready";
  } catch (e) {
    updates.error = (e as Error).message;
    updates.status = "error";
  }
}
export async function downloadUpdate() {
  if (updates.status === "downloading") return;
  updates.status = "downloading";
  updates.error = "";
  updates.progress = { status: "starting", downloaded: 0, total: 0, percent: 0, speed: 0, error: "" };
  await refreshProgress();
  progressTimer = setInterval(() => { void refreshProgress(); }, 250);
  try {
    const result = await api("updates.download");
    updates.path = result.path;
    await refreshProgress();
    updates.status = "downloaded";
    notify("更新包已下载并通过校验，可在任务结束后打开安装。");
  } catch (e) {
    updates.error = (e as Error).message;
    await refreshProgress();
    updates.status = "error";
  } finally {
    if (progressTimer) clearInterval(progressTimer);
    progressTimer = undefined;
  }
}
export async function installUpdate() {
  if (Object.values(scientificJobs).some((job) => job.busy)) {
    notify("请先完成或取消当前计算，再安装更新。");
    return;
  }
  try {
    await openPath(updates.path);
    notify("已打开更新包，请退出当前应用后按提示安装或替换应用。");
  } catch (e) {
    notify((e as Error).message, true);
  }
}
