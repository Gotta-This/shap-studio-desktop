import { reactive } from "vue";
import { api } from "./api";
export const desktopSchedule = reactive({ error: "" });
let timer: ReturnType<typeof setTimeout> | undefined;
let stopped = true,
  running = false;
async function pulse() {
  if (stopped || running) return;
  clearTimeout(timer);
  running = true;
  let delay = 30000;
  try {
    const value = await api("desktop.layout.tick");
    if (!value.supported) {
      stopped = true;
      return;
    }
    if (value.created || desktopSchedule.error !== (value.last_error || ""))
      window.dispatchEvent(new Event("desktop-layout-updated"));
    desktopSchedule.error = value.last_error || "";
    if (value.enabled && value.next_due_at)
      delay = Math.max(
        5000,
        Math.min(30000, value.next_due_at * 1000 - Date.now()),
      );
  } catch (e) {
    desktopSchedule.error = (e as Error).message;
  } finally {
    running = false;
    if (!stopped) timer = setTimeout(pulse, delay);
  }
}
function wake() {
  if (document.visibilityState === "visible") void pulse();
}
export function refreshDesktopSchedule() {
  void pulse();
}
export function startDesktopSchedule() {
  stopDesktopSchedule();
  stopped = false;
  window.addEventListener("focus", wake);
  document.addEventListener("visibilitychange", wake);
  // tick performs the platform and due-time checks. Transient startup failures
  // are retried by pulse, so an unavailable bridge cannot disable the schedule.
  void pulse();
}
export function stopDesktopSchedule() {
  stopped = true;
  clearTimeout(timer);
  window.removeEventListener("focus", wake);
  document.removeEventListener("visibilitychange", wake);
}
