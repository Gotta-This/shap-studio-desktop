import { reactive } from "vue";

const storageKey = "research-studio.display-scale";
export const scaleOptions = [70, 75, 80, 85, 90, 95, 100, 110, 125];
function savedScale() {
  try {
    const value = Number(localStorage.getItem(storageKey));
    return scaleOptions.includes(value) ? value : 100;
  } catch {
    return 100;
  }
}
export const display = reactive({ scale: savedScale(), applying: false });

// The root fallback also covers browser preview and older desktop hosts.
function cssScale(scale: number) {
  document.documentElement.style.zoom = String(scale / 100);
  document.documentElement.style.setProperty("--ui-scale", String(scale / 100));
}
export async function applyScale(value: number) {
  if (!scaleOptions.includes(value) || display.applying) return;
  display.applying = true;
  try {
    if ("__TAURI_INTERNALS__" in window) {
      try {
        const { getCurrentWebview } = await import("@tauri-apps/api/webview");
        await getCurrentWebview().setZoom(value / 100);
        cssScale(100);
      } catch {
        cssScale(value);
      }
    } else cssScale(value);
    display.scale = value;
    try {
      localStorage.setItem(storageKey, String(value));
    } catch {
      /* Session-only when storage is unavailable. */
    }
  } finally {
    display.applying = false;
  }
}
export function initializeDisplay() {
  // Apply before mounting to avoid flashing the full-size interface at startup.
  cssScale(display.scale);
  return applyScale(display.scale);
}
