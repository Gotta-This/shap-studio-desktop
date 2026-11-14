<script setup lang="ts">
import { ref } from "vue";
import { Camera, Settings2 } from "lucide-vue-next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import PageHeading from "@/components/PageHeading.vue";
import { desktop, notify } from "@/lib/api";

const busy = ref(false);
const error = ref("");
const settingsOpen = ref(false);
const settingsBusy = ref(false);
const regionHotkey = ref("");
const fullscreenHotkey = ref("");
const settingsError = ref("");
const defaultRegionHotkey = /Windows/i.test(navigator.userAgent) ? "Ctrl+Alt+Shift+A" : "Cmd+Shift+A";
const defaultFullscreenHotkey = /Windows/i.test(navigator.userAgent) ? "Ctrl+Alt+Shift+S" : "Cmd+Shift+S";

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
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const config = await invoke<{ region: string; fullscreen: string }>("quickshot_config");
    regionHotkey.value = config.region;
    fullscreenHotkey.value = config.fullscreen;
  } catch (e) {
    settingsError.value = (e as Error).message;
    notify(settingsError.value, true);
  }
}
async function saveQuickShotSettings() {
  if (!desktop || settingsBusy.value) return;
  settingsBusy.value = true;
  settingsError.value = "";
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    await invoke("set_quickshot_config", { region: regionHotkey.value.trim(), fullscreen: fullscreenHotkey.value.trim() });
    settingsOpen.value = false;
  } catch (e) {
    settingsError.value = (e as Error).message;
    notify(settingsError.value, true);
  } finally {
    settingsBusy.value = false;
  }
}
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
        <Button variant="outline" @click="settingsOpen ? (settingsOpen = false) : openQuickShotSettings()"><Settings2 :size="16" />快捷键设置</Button>
      </div>
      <p v-if="error" class="field-error">{{ error }}</p>
      <form v-if="settingsOpen" class="quickshot-settings-panel" @submit.prevent="saveQuickShotSettings">
        <label class="screenshot-shortcut-setting"><span>区域截图</span><Input v-model="regionHotkey" placeholder="Ctrl+Alt+Shift+A" /></label>
        <label class="screenshot-shortcut-setting"><span>全屏截图</span><Input v-model="fullscreenHotkey" placeholder="Ctrl+Alt+Shift+S" /></label>
        <Button type="submit" :disabled="settingsBusy">{{ settingsBusy ? "保存中…" : "保存快捷键" }}</Button>
        <p v-if="settingsError" class="field-error">{{ settingsError }}</p>
      </form>
    </section>
  </section>
</template>
