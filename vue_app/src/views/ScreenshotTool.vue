<script setup lang="ts">
import { onUnmounted, ref } from "vue";
import { Camera, Settings2 } from "lucide-vue-next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import PageHeading from "@/components/PageHeading.vue";
import { desktop, notify } from "@/lib/api";

const busy = ref(false);
const error = ref("");
const settingsOpen = ref(false);
const settingsBusy = ref(false);
const regionHotkey = ref("");
const fullscreenHotkey = ref("");
const hideCurrentWindow = ref(true);
const settingsError = ref("");
const capturingShortcut = ref<"region" | "fullscreen" | null>(null);
const savedRegionHotkey = ref("");
const savedFullscreenHotkey = ref("");
const pressedShortcutKeys = new Set<string>();
const capturedShortcutKeys = new Map<string, string>();
const defaultRegionHotkey = /Windows/i.test(navigator.userAgent) ? "Ctrl+Alt+Shift+A" : "Cmd+Shift+A";
const defaultFullscreenHotkey = /Windows/i.test(navigator.userAgent) ? "Ctrl+Alt+Shift+S" : "Cmd+Shift+S";
let quickshotSuspended = false;

function shortcutKey(event: KeyboardEvent) {
  const code = event.code;
  if (/^Key[A-Z]$/.test(code)) return code.slice(3);
  if (/^Digit[0-9]$/.test(code)) return code.slice(5);
  if (/^F([1-9]|1[0-9]|2[0-4])$/.test(code)) return code;
  const keys: Record<string, string> = {
    " ": "SPACE",
    Enter: "ENTER",
    Tab: "TAB",
    Backspace: "BACKSPACE",
    Escape: "ESCAPE",
  };
  return keys[event.key] || "";
}

function shortcutModifier(event: KeyboardEvent) {
  if (event.key === "Control" || event.code.startsWith("Control")) return "Ctrl";
  if (event.key === "Alt" || event.code.startsWith("Alt")) return "Alt";
  if (event.key === "Shift" || event.code.startsWith("Shift")) return "Shift";
  if (event.key === "Meta" || event.code.startsWith("Meta")) return /Windows/i.test(navigator.userAgent) ? "Win" : "Cmd";
  return "";
}

function beginShortcutCapture(field: "region" | "fullscreen") {
  stopShortcutCapture(capturingShortcut.value);
  capturingShortcut.value = field;
  pressedShortcutKeys.clear();
  capturedShortcutKeys.clear();
  settingsError.value = "请按住组合键，等所有按键松开后完成录入。";
  window.addEventListener("keydown", captureShortcutKeydown, true);
  window.addEventListener("keyup", captureShortcutKeyup, true);
}

function stopShortcutCapture(field: "region" | "fullscreen" | null) {
  if (capturingShortcut.value === field) {
    capturingShortcut.value = null;
    pressedShortcutKeys.clear();
    capturedShortcutKeys.clear();
    window.removeEventListener("keydown", captureShortcutKeydown, true);
    window.removeEventListener("keyup", captureShortcutKeyup, true);
  }
}

function commitCapturedShortcut(field: "region" | "fullscreen") {
  const capturedTokens = new Set(capturedShortcutKeys.values());
  const modifiers = ["Cmd", "Win", "Ctrl", "Alt", "Shift"].filter((key) => capturedTokens.has(key));
  const mainKey = [...capturedTokens].find((key) => !modifiers.includes(key));
  const value = [...modifiers, ...(mainKey ? [mainKey] : [])].join("+");
  if (!value) {
    settingsError.value = "请至少按下一个快捷键。";
  } else {
    if (field === "region") regionHotkey.value = value;
    else fullscreenHotkey.value = value;
    settingsError.value = mainKey ? "" : "还需要一个字母、数字或功能键才能保存。";
  }
  pressedShortcutKeys.clear();
  capturedShortcutKeys.clear();
  capturingShortcut.value = null;
  window.removeEventListener("keydown", captureShortcutKeydown, true);
  window.removeEventListener("keyup", captureShortcutKeyup, true);
}

function captureShortcutKeydown(event: KeyboardEvent) {
  const field = capturingShortcut.value;
  if (!field) return;
  event.preventDefault();
  event.stopPropagation();
  if (event.key === "Escape" && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    stopShortcutCapture(field);
    settingsError.value = "";
    return;
  }
  const token = shortcutModifier(event) || shortcutKey(event);
  if (!token) return;
  const physicalKey = event.code || event.key;
  pressedShortcutKeys.add(physicalKey);
  capturedShortcutKeys.set(physicalKey, token);
}

function captureShortcutKeyup(event: KeyboardEvent) {
  const field = capturingShortcut.value;
  if (!field) return;
  event.preventDefault();
  event.stopPropagation();
  pressedShortcutKeys.delete(event.code || event.key);
  if (pressedShortcutKeys.size === 0 && capturedShortcutKeys.size > 0) commitCapturedShortcut(field);
}

function canonicalShortcut(value: string) {
  const order: Record<string, number> = { cmd: 0, win: 0, meta: 0, super: 0, ctrl: 1, control: 1, alt: 2, opt: 2, option: 2, shift: 3 };
  return value.split("+").map((part) => part.trim().toLowerCase()).filter(Boolean).sort((a, b) => (order[a] ?? 4) - (order[b] ?? 4)).join("+");
}

async function launchQuickShot() {
  busy.value = true;
  error.value = "";
  try {
    if (!desktop) throw new Error("QuickShot 截图工具需要桌面版应用。");
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("quickshot_capture");
  } catch (e) {
    error.value = (e as Error).message;
    notify(error.value, true);
  } finally {
    busy.value = false;
  }
}

async function openQuickShotSettings() {
  if (!desktop) return;
  settingsOpen.value = true;
  settingsError.value = "";
  regionHotkey.value = defaultRegionHotkey;
  fullscreenHotkey.value = defaultFullscreenHotkey;
  savedRegionHotkey.value = defaultRegionHotkey;
  savedFullscreenHotkey.value = defaultFullscreenHotkey;
  capturingShortcut.value = null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("quickshot_suspend");
    quickshotSuspended = true;
    const config = await invoke<{ region: string; fullscreen: string; hide_current_window?: boolean }>("quickshot_config");
    regionHotkey.value = config.region;
    fullscreenHotkey.value = config.fullscreen;
    savedRegionHotkey.value = config.region;
    savedFullscreenHotkey.value = config.fullscreen;
    hideCurrentWindow.value = config.hide_current_window !== false;
  } catch (e) {
    settingsError.value = (e as Error).message;
    notify(settingsError.value, true);
  }
}
async function closeQuickShotSettings() {
  settingsOpen.value = false;
  stopShortcutCapture(capturingShortcut.value);
  if (!quickshotSuspended) return;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("quickshot_resume");
  } catch (e) {
    settingsError.value = (e as Error).message;
    notify(settingsError.value, true);
  } finally {
    quickshotSuspended = false;
  }
}
async function saveQuickShotSettings() {
  if (!desktop || settingsBusy.value) return;
  settingsBusy.value = true;
  settingsError.value = "";
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const region = regionHotkey.value.trim();
    const fullscreen = fullscreenHotkey.value.trim();
    const warnings: string[] = [];
    const reservedSearch = /Windows/i.test(navigator.userAgent) ? "ctrl+k" : "cmd+k";
    if ([canonicalShortcut(region), canonicalShortcut(fullscreen)].includes(reservedSearch)) {
      warnings.push("该快捷键已被应用搜索占用，已保存但可能无法触发。");
    }
    const saved = await invoke<{ warning?: string | null }>("set_quickshot_config", { region, fullscreen, hide_current_window: hideCurrentWindow.value });
    if (saved.warning) warnings.push(saved.warning);
    savedRegionHotkey.value = region;
    savedFullscreenHotkey.value = fullscreen;
    capturingShortcut.value = null;
    quickshotSuspended = false;
    settingsOpen.value = false;
    if (warnings.length) notify(warnings.join(" "), true);
  } catch (e) {
    settingsError.value = (e as Error).message;
    notify(settingsError.value, true);
  } finally {
    settingsBusy.value = false;
  }
}
onUnmounted(() => {
  if (quickshotSuspended) {
    void closeQuickShotSettings();
  }
});
</script>

<template>
  <section class="scientific-page screenshot-page">
    <PageHeading title="截图与标注" subtitle="区域截图与快捷键设置。">
      <Badge variant="secondary">macOS / Windows</Badge>
    </PageHeading>
    <section class="scientific-section surface quickshot-launch-card">
      <div class="quickshot-launch-icon"><Camera :size="24" /></div>
      <div class="quickshot-launch-copy">
        <h2>截图</h2>
        <p class="muted">拖动选择区域后，在工具栏中完成标注并复制到剪贴板。</p>
      </div>
      <div class="quickshot-launch-actions">
        <Button :disabled="busy" @click="launchQuickShot"><Camera :size="16" />{{ busy ? "正在启动…" : "开始截图" }}</Button>
        <Button variant="outline" @click="settingsOpen ? closeQuickShotSettings() : openQuickShotSettings()"><Settings2 :size="16" />快捷键设置</Button>
      </div>
      <p v-if="error" class="field-error">{{ error }}</p>
      <form v-if="settingsOpen" class="quickshot-settings-panel" @submit.prevent="saveQuickShotSettings">
        <label class="screenshot-shortcut-setting"><span>区域截图</span><button type="button" class="shortcut-capture-field" :class="{ active: capturingShortcut === 'region' }" @click="beginShortcutCapture('region')" @focus="beginShortcutCapture('region')" @blur="stopShortcutCapture('region')">{{ capturingShortcut === "region" ? "请按住并松开快捷键…" : regionHotkey || "未设置" }}</button></label>
        <label class="screenshot-shortcut-setting"><span>全屏截图</span><button type="button" class="shortcut-capture-field" :class="{ active: capturingShortcut === 'fullscreen' }" @click="beginShortcutCapture('fullscreen')" @focus="beginShortcutCapture('fullscreen')" @blur="stopShortcutCapture('fullscreen')">{{ capturingShortcut === "fullscreen" ? "请按住并松开快捷键…" : fullscreenHotkey || "未设置" }}</button></label>
        <label class="screenshot-hide-window-setting"><input v-model="hideCurrentWindow" type="checkbox" />隐藏当前应用窗口（默认开启）</label>
        <Button type="submit" :disabled="settingsBusy">{{ settingsBusy ? "保存中…" : "保存快捷键" }}</Button>
        <p v-if="settingsError" class="field-error">{{ settingsError }}</p>
      </form>
    </section>
  </section>
</template>
