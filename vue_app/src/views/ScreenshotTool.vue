<script setup lang="ts">
import { computed, onUnmounted, ref } from "vue";
import { Camera, Settings2 } from "lucide-vue-next";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
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
const settingsSaveStatus = ref("");
const capturingShortcut = ref<"region" | "fullscreen" | null>(null);
const savedRegionHotkey = ref("");
const savedFullscreenHotkey = ref("");
const pressedShortcutKeys = new Set<string>();
const capturedShortcutKeys = new Map<string, string>();
const defaultRegionHotkey = /Windows/i.test(navigator.userAgent) ? "Ctrl+Alt+Shift+A" : "Cmd+Shift+A";
const defaultFullscreenHotkey = /Windows/i.test(navigator.userAgent) ? "Ctrl+Alt+Shift+S" : "Cmd+Shift+S";
const isMac = /Macintosh|Mac OS X/i.test(navigator.userAgent) || navigator.platform === "MacIntel";
let quickshotSuspended = false;
let capturePreparing = false;
const permissions = ref<{ screen_recording: boolean; accessibility: boolean; quickshot_running: boolean } | null>(null);
const quickshotConfigPath = ref("");
const statusRefreshing = ref(false);
const settingsDirty = computed(() => canonicalShortcut(regionHotkey.value) !== canonicalShortcut(savedRegionHotkey.value) || canonicalShortcut(fullscreenHotkey.value) !== canonicalShortcut(savedFullscreenHotkey.value));

function errorText(error: unknown) {
  if (error instanceof Error && error.message) return error.message;
  if (typeof error === "string" && error) return error;
  if (error && typeof error === "object") {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string" && message) return message;
    try { return JSON.stringify(error); } catch { return "未知错误"; }
  }
  return "未知错误";
}

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

async function beginShortcutCapture(field: "region" | "fullscreen") {
  if (capturePreparing || capturingShortcut.value === field) return;
  stopShortcutCapture(capturingShortcut.value);
  capturePreparing = true;
  settingsError.value = "正在准备快捷键录入…";
  settingsSaveStatus.value = "";
  try {
    if (!quickshotSuspended) {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("quickshot_suspend");
      quickshotSuspended = true;
    }
    capturingShortcut.value = field;
    pressedShortcutKeys.clear();
    capturedShortcutKeys.clear();
    settingsError.value = "请按住组合键，等所有按键松开后完成录入。";
    window.addEventListener("keydown", captureShortcutKeydown, true);
    window.addEventListener("keyup", captureShortcutKeyup, true);
  } catch (e) {
    settingsError.value = errorText(e);
    notify(settingsError.value, true);
  } finally {
    capturePreparing = false;
  }
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
  const aliases: Record<string, string> = { command: "cmd", meta: "cmd", super: "cmd", control: "ctrl", opt: "alt", option: "alt" };
  const order: Record<string, number> = { cmd: 0, win: 0, ctrl: 1, alt: 2, shift: 3 };
  return value.split("+").map((part) => aliases[part.trim().toLowerCase()] || part.trim().toLowerCase()).filter(Boolean).sort((a, b) => (order[a] ?? 4) - (order[b] ?? 4)).join("+");
}

async function launchQuickShot() {
  busy.value = true;
  error.value = "";
  try {
    if (!desktop) throw new Error("QuickShot 截图工具需要桌面版应用。");
    const { invoke } = await import("@tauri-apps/api/core");
    const status = await invoke<typeof permissions.value>("quickshot_permissions");
    permissions.value = status;
    if (!status?.screen_recording) throw new Error("请在系统设置 → 隐私与安全性 → 屏幕录制中允许“科研数据工具集”。");
    if (!status.accessibility) throw new Error("请在系统设置 → 隐私与安全性 → 辅助功能中允许“科研数据工具集”。");
    await invoke("quickshot_capture");
  } catch (e) {
    error.value = errorText(e);
    notify(error.value, true);
  } finally {
    busy.value = false;
  }
}
async function openPermissionSettings(kind: "accessibility" | "screen") {
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("quickshot_open_permissions", { kind });
  } catch (e) {
    notify(errorText(e), true);
  }
}
async function refreshQuickShotStatus() {
  if (statusRefreshing.value) return;
  if (settingsBusy.value) {
    notify("快捷键正在保存，请等待保存完成。", true);
    return;
  }
  if (settingsOpen.value && settingsDirty.value) {
    await saveQuickShotSettings();
    if (settingsOpen.value && settingsDirty.value) return;
  }
  statusRefreshing.value = true;
  settingsSaveStatus.value = "正在读取 QuickShot 当前配置…";
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const status = await invoke<{ region: string; fullscreen: string; screen_recording: boolean; accessibility: boolean; quickshot_running: boolean; config_path?: string }>("quickshot_refresh");
    regionHotkey.value = status.region;
    fullscreenHotkey.value = status.fullscreen;
    savedRegionHotkey.value = status.region;
    savedFullscreenHotkey.value = status.fullscreen;
    quickshotConfigPath.value = status.config_path || "";
    permissions.value = status;
    settingsSaveStatus.value = `已读取当前配置，QuickShot ${status.quickshot_running ? "正在运行" : "未运行"}。`;
    notify("已刷新 QuickShot 当前状态。");
  } catch (e) {
    settingsSaveStatus.value = "读取状态失败，请查看错误信息。";
    notify(errorText(e), true);
  } finally {
    statusRefreshing.value = false;
  }
}

async function openQuickShotSettings() {
  if (!desktop) return;
  settingsOpen.value = true;
  settingsError.value = "";
  settingsSaveStatus.value = "";
  regionHotkey.value = defaultRegionHotkey;
  fullscreenHotkey.value = defaultFullscreenHotkey;
  savedRegionHotkey.value = defaultRegionHotkey;
  savedFullscreenHotkey.value = defaultFullscreenHotkey;
  capturingShortcut.value = null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const config = await invoke<{ region: string; fullscreen: string; hide_current_window?: boolean; config_path?: string }>("quickshot_config");
    permissions.value = await invoke<typeof permissions.value>("quickshot_permissions");
    regionHotkey.value = config.region;
    fullscreenHotkey.value = config.fullscreen;
    savedRegionHotkey.value = config.region;
    savedFullscreenHotkey.value = config.fullscreen;
    quickshotConfigPath.value = config.config_path || "";
    hideCurrentWindow.value = config.hide_current_window !== false;
  } catch (e) {
    settingsError.value = errorText(e);
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
    settingsError.value = errorText(e);
    notify(settingsError.value, true);
  } finally {
    quickshotSuspended = false;
  }
}
async function saveQuickShotSettings() {
  if (!desktop || settingsBusy.value) return;
  settingsBusy.value = true;
  settingsError.value = "";
  settingsSaveStatus.value = "正在写入 QuickShot 配置…";
  notify("正在保存快捷键…");
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const region = regionHotkey.value.trim();
    const fullscreen = fullscreenHotkey.value.trim();
    const warnings: string[] = [];
    const reservedSearch = /Windows/i.test(navigator.userAgent) ? "ctrl+k" : "cmd+k";
    if ([canonicalShortcut(region), canonicalShortcut(fullscreen)].includes(reservedSearch)) {
      warnings.push("该快捷键已被应用搜索占用，已保存但可能无法触发。");
    }
    const saved = await invoke<{ warning?: string | null }>("set_quickshot_config", { region, fullscreen, hideCurrentWindow: hideCurrentWindow.value });
    if (saved.warning) warnings.push(saved.warning);
    const actual = await invoke<{ region: string; fullscreen: string; hide_current_window?: boolean; config_path?: string }>("quickshot_config");
    if (canonicalShortcut(actual.region) !== canonicalShortcut(region) || canonicalShortcut(actual.fullscreen) !== canonicalShortcut(fullscreen)) {
      throw new Error(`QuickShot 配置保存后回读不一致，当前仍为：区域截图 ${actual.region}，全屏截图 ${actual.fullscreen}`);
    }
    regionHotkey.value = actual.region;
    fullscreenHotkey.value = actual.fullscreen;
    savedRegionHotkey.value = actual.region;
    savedFullscreenHotkey.value = actual.fullscreen;
    quickshotConfigPath.value = actual.config_path || quickshotConfigPath.value;
    hideCurrentWindow.value = actual.hide_current_window !== false;
    capturingShortcut.value = null;
    quickshotSuspended = false;
    settingsSaveStatus.value = "快捷键已保存，QuickShot 正在运行，应用级快捷键已重新注册。";
    if (warnings.length) notify(warnings.join(" "), true);
  } catch (e) {
    settingsError.value = errorText(e);
    settingsSaveStatus.value = "保存失败，请查看下方错误信息。";
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
      <div v-if="error" class="field-error quickshot-launch-error"><span>{{ error }}</span><Button v-if="isMac && permissions && !permissions.screen_recording" type="button" variant="outline" size="sm" @click="openPermissionSettings('screen')">打开屏幕录制设置</Button><Button v-if="isMac && permissions && !permissions.accessibility" type="button" variant="outline" size="sm" @click="openPermissionSettings('accessibility')">打开辅助功能设置</Button></div>
      <form v-if="settingsOpen" class="quickshot-settings-panel" @submit.prevent="saveQuickShotSettings">
        <div v-if="isMac && permissions" class="quickshot-permission-status" :class="{ ready: permissions.screen_recording && permissions.accessibility && permissions.quickshot_running }">
          <span>屏幕录制：{{ permissions.screen_recording ? "已允许" : "未允许" }}</span><span>辅助功能：{{ permissions.accessibility ? "已允许" : "未允许" }}</span><span>QuickShot：{{ permissions.quickshot_running ? "运行中" : "未运行" }}</span><Button v-if="!permissions.screen_recording" type="button" variant="outline" size="sm" @click="openPermissionSettings('screen')">打开屏幕录制设置</Button><Button v-if="!permissions.accessibility" type="button" variant="outline" size="sm" @click="openPermissionSettings('accessibility')">打开辅助功能设置</Button>
        </div>
        <Button type="button" variant="outline" size="sm" :disabled="statusRefreshing || settingsBusy" @click="refreshQuickShotStatus">{{ statusRefreshing ? "刷新中…" : "刷新状态" }}</Button>
        <strong class="quickshot-current-shortcuts">当前生效配置：区域截图 {{ regionHotkey }} · 全屏截图 {{ fullscreenHotkey }}</strong>
        <label class="screenshot-shortcut-setting"><span>区域截图</span><button type="button" class="shortcut-capture-field" :class="{ active: capturingShortcut === 'region' }" @click="beginShortcutCapture('region')" @focus="beginShortcutCapture('region')">{{ capturingShortcut === "region" ? "请按住并松开快捷键…" : regionHotkey || "未设置" }}</button></label>
        <label class="screenshot-shortcut-setting"><span>全屏截图</span><button type="button" class="shortcut-capture-field" :class="{ active: capturingShortcut === 'fullscreen' }" @click="beginShortcutCapture('fullscreen')" @focus="beginShortcutCapture('fullscreen')">{{ capturingShortcut === "fullscreen" ? "请按住并松开快捷键…" : fullscreenHotkey || "未设置" }}</button></label>
        <label class="screenshot-hide-window-setting"><input v-model="hideCurrentWindow" type="checkbox" />隐藏当前应用窗口（默认开启）</label>
        <button type="button" :class="buttonVariants()" :disabled="settingsBusy" @mousedown.stop="saveQuickShotSettings" @click.stop="saveQuickShotSettings">{{ settingsBusy ? "保存中…" : "保存快捷键" }}</button>
        <p v-if="settingsSaveStatus" class="quickshot-save-status">{{ settingsSaveStatus }}</p>
        <p v-if="settingsError" class="field-error">{{ settingsError }}</p>
      </form>
    </section>
  </section>
</template>
