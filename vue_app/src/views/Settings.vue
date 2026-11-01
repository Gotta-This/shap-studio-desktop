<script setup lang="ts">
import { ref } from "vue";
import {
  FolderOpen,
  ShieldCheck,
  RefreshCw,
  ExternalLink,
  HardDrive,
  Check,
  ArrowUpRight,
} from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import PageHeading from "@/components/PageHeading.vue";
import { state, api, refresh, notify, desktop, openPath } from "@/lib/api";
const path = ref(""),
  busy = ref(false),
  error = ref(""),
  updateState = ref<"idle" | "checking" | "ready" | "error">("idle"),
  latest = ref<any>(null);
async function browse() {
  if (!desktop) {
    document.getElementById("workspace-path")?.focus();
    return;
  }
  const { open } = await import("@tauri-apps/plugin-dialog");
  const folder = await open({ directory: true, title: "选择稿件工作空间" });
  if (typeof folder === "string") path.value = folder;
}
async function connect() {
  busy.value = true;
  error.value = "";
  try {
    await api("workspace.enable", { root: path.value });
    await refresh();
    notify("本地工作空间已连接，不会扫描已有历史材料。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function checkUpdate() {
  updateState.value = "checking";
  try {
    const r = await fetch(
      "https://api.github.com/repos/Gotta-This/shap-studio-desktop/releases/latest",
      { headers: { Accept: "application/vnd.github+json" } },
    );
    if (!r.ok) throw Error("更新服务暂时不可用");
    latest.value = await r.json();
    updateState.value = "ready";
  } catch {
    updateState.value = "error";
  }
}
</script>
<template>
  <section class="settings-page">
    <PageHeading title="设置与关于" subtitle="本地存储、工作空间与版本信息。" />
    <div class="settings-grid">
      <div class="panel">
        <div class="settings-heading">
          <div class="setting-icon"><FolderOpen :size="21" /></div>
          <div>
            <h2>本地工作空间</h2>
            <p>一个目录，保存任务、材料与关联待办。</p>
          </div>
          <Badge v-if="state.root" variant="secondary" class="ml-auto"
            ><Check :size="12" />已连接</Badge
          >
        </div>
        <div class="settings-content">
          <div v-if="state.root" class="connected-path">
            <HardDrive :size="20" />
            <div>
              <small>当前目录</small><code>{{ state.root }}</code>
            </div>
            <Button
              size="icon"
              variant="ghost"
              aria-label="打开当前工作空间"
              @click="openPath(state.root)"
              ><ArrowUpRight :size="17"
            /></Button>
          </div>
          <form class="dialog-form" @submit.prevent="connect">
            <div class="form-field">
              <Label for="workspace-path">{{
                state.root ? "切换工作空间" : "选择存放新稿件的文件夹"
              }}</Label>
              <div class="path-input">
                <Input
                  id="workspace-path"
                  v-model="path"
                  required
                  placeholder="输入本机文件夹的完整路径"
                /><Button variant="outline" type="button" @click="browse"
                  ><FolderOpen :size="15" />选择文件夹</Button
                >
              </div>
              <small
                >新目录会建立任务索引；选择已有工作空间会读取原有索引。</small
              >
            </div>
            <p v-if="error" role="alert" class="field-error">{{ error }}</p>
            <Button
              :disabled="busy || !path"
              class="self-start"
              type="submit"
              >{{
                busy
                  ? "正在连接…"
                  : state.root
                    ? "切换到此目录"
                    : "启用工作空间"
              }}</Button
            >
          </form>
          <div class="settings-note">
            <ShieldCheck :size="19" />
            <p>
              只管理启用后明确创建的任务与接收的材料，不自动扫描历史文稿。切换目录会保留原目录及其所有文件。
            </p>
          </div>
        </div>
      </div>
      <div class="panel">
        <div class="settings-heading">
          <div class="setting-icon"><RefreshCw :size="20" /></div>
          <div>
            <h2>版本与更新</h2>
            <p>科研数据工具集 · V3</p>
          </div>
          <Badge variant="secondary" class="ml-auto">开发预览</Badge>
        </div>
        <div class="settings-content">
          <p class="muted">
            当前为独立开发分支的 Vue V3 预览版。正式版更新单独展示，避免将 Qt
            安装包当作 Vue 更新安装。
          </p>
          <div v-if="updateState === 'ready'" class="update-result">
            <strong>当前正式版 {{ latest?.tag_name }}</strong
            ><span>{{ latest?.name }}</span
            ><a :href="latest?.html_url" target="_blank" rel="noreferrer"
              >查看正式版下载 <ExternalLink :size="13"
            /></a>
          </div>
          <p v-if="updateState === 'error'" class="field-error" role="alert">
            检查失败，请确认网络后重试。
          </p>
          <Button
            variant="outline"
            :disabled="updateState === 'checking'"
            @click="checkUpdate"
            ><RefreshCw
              :size="15"
              :class="{ 'animate-spin': updateState === 'checking' }"
            />{{
              updateState === "checking" ? "正在检查…" : "检查正式版更新"
            }}</Button
          >
          <div class="settings-note">
            <HardDrive :size="18" />
            <p>
              备份前关闭应用，并完整复制工作空间文件夹，包含隐藏索引。当前按单人本地使用设计。
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
