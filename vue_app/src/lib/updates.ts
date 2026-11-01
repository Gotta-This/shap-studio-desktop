import { reactive } from "vue";
import { api, notify, openPath } from "./api";
import { scientificJobs } from "./scientific";
export const updates = reactive({
  current: "3.0.0",
  status: "idle",
  release: null as any,
  path: "",
  error: "",
});
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
  try {
    const result = await api("updates.download");
    updates.path = result.path;
    updates.status = "downloaded";
    notify("更新包已下载并通过校验，可在任务结束后打开安装。");
  } catch (e) {
    updates.error = (e as Error).message;
    updates.status = "error";
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
