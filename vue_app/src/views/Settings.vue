<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  updates,
  checkUpdate,
  downloadUpdate,
  installUpdate,
} from "@/lib/updates";
import {
  FolderOpen,
  ShieldCheck,
  RefreshCw,
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
  error = ref("");
const dataDirectory = ref("");
onMounted(async () => {
  try {
    dataDirectory.value = (await api("storage.info")).directory;
  } catch {}
});
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
              variant="outline"
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
                >默认工作空间已自动建立；也可以切换到其他目录。选择已有工作空间会读取原有索引。</small
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
          <div v-if="dataDirectory" class="connected-path">
            <HardDrive :size="20" />
            <div>
              <small>应用数据目录</small><code>{{ dataDirectory }}</code>
            </div>
            <Button
              size="icon"
              variant="outline"
              aria-label="打开应用数据目录"
              @click="openPath(dataDirectory)"
              ><ArrowUpRight :size="17"
            /></Button>
          </div>
          <p class="muted">
            待办、配置、导入记录和生成结果保存在用户目录中，替换或重新安装应用不会清除这些数据。未另选目录时，稿件使用此目录中的默认工作空间。
          </p>
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
          <Badge variant="secondary" class="ml-auto"
            >V{{ updates.current }}</Badge
          >
        </div>
        <div class="settings-content">
          <p class="muted">
            检查 GitHub 正式版，下载后校验安装包。Windows 打开安装向导；Mac
            解压后替换应用，工作空间与待办保留。
          </p>
          <div v-if="updates.release" class="update-result">
            <strong>{{
              updates.release.newer
                ? "发现新版本 V" + updates.release.version
                : "当前已是最新版本 V" + updates.current
            }}</strong>
            <span v-if="updates.release.newer && !updates.release.asset"
              >该版本暂未提供当前系统的安装包。</span
            >
          </div>
          <p v-if="updates.error" class="field-error" role="alert">
            {{ updates.error }}，请稍后重试。
          </p>
          <p v-if="updates.status === 'downloading'" role="status">
            正在下载并校验更新包，请保持应用打开…
          </p>
          <Button v-if="updates.path" @click="installUpdate">打开更新包</Button>
          <Button
            v-else-if="updates.release?.newer && updates.release.asset"
            :disabled="updates.status === 'downloading'"
            @click="downloadUpdate"
            >{{
              updates.status === "downloading" ? "正在下载…" : "下载并校验更新"
            }}</Button
          >
          <Button
            variant="outline"
            :disabled="['checking', 'downloading'].includes(updates.status)"
            @click="checkUpdate"
          >
            <RefreshCw
              :size="15"
              :class="{ 'animate-spin': updates.status === 'checking' }"
            />{{ updates.status === "checking" ? "正在检查…" : "检查更新" }}
          </Button>
          <div class="settings-note">
            <HardDrive :size="18" />
            <p>
              备份时请先关闭应用，复制完整的应用数据目录；若另选了稿件工作空间，也一并复制该目录及其中的隐藏索引。
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
