<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import {
  ArchiveRestore,
  MonitorCog,
  MonitorX,
  RefreshCw,
  ShieldCheck,
  Trash2,
  LockKeyhole,
} from "lucide-vue-next";
import PageHeading from "@/components/PageHeading.vue";
import EmptyState from "@/components/EmptyState.vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  desktopSchedule,
  refreshDesktopSchedule,
} from "@/lib/desktopLayoutSchedule";
import { api, notify, openPath } from "@/lib/api";
interface Backup {
  id: string;
  label: string;
  created_at: string;
  protected: boolean;
  reason: string;
  icon_count: number;
  display: { width: number; height: number; dpi: number };
}
interface LayoutInfo {
  supported: boolean;
  message: string;
  backups: Backup[];
  directory: string;
  keep_recent: number;
  settings?: {
    enabled: boolean;
    interval_minutes: number;
    keep_recent: number;
    last_automatic_at: string | null;
    next_due_at: number | null;
    last_error: string;
  };
  unreadable?: number;
}
interface Plan {
  restored_count: number;
  new_count: number;
  missing_count: number;
  display_changed: boolean;
  fingerprint: string;
}
const data = ref<LayoutInfo | null>(null),
  loading = ref(false),
  busy = ref(false),
  error = ref("");
const label = ref(""),
  permanent = ref(false);
const autoEnabled = ref(true),
  intervalMinutes = ref(10),
  keepRecent = ref(144),
  settingsConfirm = ref(false);
const pending = ref<{
  kind: "restore" | "delete" | "unprotect";
  backup: Backup;
  plan?: Plan;
} | null>(null);
async function load(syncSettings = true) {
  loading.value = true;
  try {
    data.value = await api("desktop.layout.info");
    error.value = "";
    if (syncSettings && data.value?.settings) {
      autoEnabled.value = data.value.settings.enabled;
      intervalMinutes.value = data.value.settings.interval_minutes;
      keepRecent.value = data.value.settings.keep_recent;
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}
function refreshHistory() {
  void load(false);
}
onMounted(() => {
  void load();
  window.addEventListener("desktop-layout-updated", refreshHistory);
});
onUnmounted(() =>
  window.removeEventListener("desktop-layout-updated", refreshHistory),
);
async function saveSettings(confirmed = false) {
  if (
    !confirmed &&
    (data.value?.backups.filter((b) => !b.protected).length || 0) >
      keepRecent.value
  ) {
    settingsConfirm.value = true;
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    const result = await api("desktop.layout.settings", {
      enabled: autoEnabled.value,
      interval_minutes: intervalMinutes.value,
      keep_recent: keepRecent.value,
    });
    settingsConfirm.value = false;
    await load();
    refreshDesktopSchedule();
    notify(
      result.removed
        ? `设置已保存，已清理 ${result.removed} 份普通旧备份。`
        : "自动备份设置已保存。",
    );
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function date(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
async function save() {
  busy.value = true;
  error.value = "";
  try {
    await api("desktop.layout.backup", {
      label: label.value,
      protected: permanent.value,
    });
    label.value = "";
    permanent.value = false;
    await load();
    notify("当前桌面排列已备份。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function protect(backup: Backup) {
  if (backup.protected) {
    pending.value = { kind: "unprotect", backup };
    return;
  }
  busy.value = true;
  error.value = "";
  try {
    await api("desktop.layout.protect", { id: backup.id, protected: true });
    await load();
    notify("此备份已设为永久保留。");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function prepare(backup: Backup) {
  busy.value = true;
  error.value = "";
  try {
    const plan = await api<Plan>("desktop.layout.preview", { id: backup.id });
    pending.value = { kind: "restore", backup, plan };
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function confirm() {
  if (!pending.value) return;
  const action = pending.value;
  busy.value = true;
  error.value = "";
  try {
    if (action.kind === "restore") {
      const result = await api<{ unmatched_positions: number }>(
        "desktop.layout.restore",
        { id: action.backup.id, fingerprint: action.plan?.fingerprint },
      );
      notify(
        result.unmatched_positions
          ? `Windows 有 ${result.unmatched_positions} 个图标未按预期落位，恢复前的排列已自动备份。`
          : "桌面排列已恢复，新增图标已安置到空位置。",
        !!result.unmatched_positions,
      );
    } else if (action.kind === "delete") {
      await api("desktop.layout.delete", { id: action.backup.id });
      notify("备份已删除。");
    } else {
      await api("desktop.layout.protect", {
        id: action.backup.id,
        protected: false,
      });
      notify("已取消永久保留。");
    }
    pending.value = null;
    await load();
  } catch (e) {
    error.value = (e as Error).message;
    pending.value = null;
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <section class="layout-backup-page">
    <PageHeading
      title="桌面布局备份"
      subtitle="保存 Windows 桌面图标位置，排列错乱后恢复。"
    >
      <Badge variant="secondary"><MonitorCog :size="14" />Windows 专用</Badge>
    </PageHeading>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    <div v-if="loading && !data" class="panel">
      <EmptyState title="正在检测系统…" />
    </div>
    <div v-else-if="data && !data.supported" class="panel">
      <EmptyState
        title="非windows电脑无法使用"
        description="桌面布局备份与恢复功能仅支持 Windows，需在 Windows 电脑上操作。"
      >
        <template #icon><MonitorX :size="28" /></template>
      </EmptyState>
    </div>
    <template v-else-if="data?.supported">
      <div class="panel layout-save-panel">
        <h2>自动备份设置</h2>
        <p class="muted">
          软件打开期间按频率自动保存；关闭后停止，下次打开会检查是否到期。
        </p>
        <form class="layout-save-form" @submit.prevent="saveSettings()">
          <label class="layout-permanent"
            ><Checkbox
              v-model="autoEnabled"
              aria-label="启用自动备份"
            />启用自动备份</label
          >
          <label class="layout-setting-field" for="desktop-layout-interval"
            >备份频率（分钟）<Input
              id="desktop-layout-interval"
              v-model.number="intervalMinutes"
              type="number"
              min="1"
              max="1440"
              required
          /></label>
          <label class="layout-setting-field" for="desktop-layout-retention"
            >普通备份保留份数<Input
              id="desktop-layout-retention"
              v-model.number="keepRecent"
              type="number"
              min="1"
              max="500"
              required
          /></label>
          <Button type="submit" variant="outline" :disabled="busy || loading"
            >保存备份设置</Button
          >
        </form>
        <p class="muted layout-retention">
          永久保留的备份不占普通份数。自动备份、手动备份和恢复前备份共用普通份数限制。
        </p>
        <p class="muted layout-retention">
          默认每 10 分钟备份一次、保留 144 份，连续运行约覆盖 24 小时；按份数清理，不按时间删除。
        </p>
        <p
          v-if="data.settings?.last_automatic_at"
          class="muted layout-retention"
        >
          上次自动备份：{{ date(data.settings.last_automatic_at) }}
        </p>
        <p
          v-if="desktopSchedule.error || data.settings?.last_error"
          class="field-error"
        >
          自动备份暂未成功：{{
            desktopSchedule.error || data.settings?.last_error
          }}，软件运行时会重试。
        </p>
      </div>
      <div class="panel layout-save-panel">
        <div>
          <h2>备份当前排列</h2>
          <p class="muted">先把图标摆好，再保存一份随时可恢复的布局。</p>
        </div>
        <form class="layout-save-form" @submit.prevent="save">
          <Input
            v-model="label"
            maxlength="80"
            aria-label="备份名称"
            placeholder="备份名称（可选，例如：常用工作桌面）"
          />
          <label class="layout-permanent"
            ><Checkbox
              v-model="permanent"
              aria-label="永久保留此备份"
            />永久保留此备份</label
          >
          <Button type="submit" :disabled="busy || loading"
            ><MonitorCog :size="16" />{{
              busy ? "正在处理…" : "备份当前排列"
            }}</Button
          >
        </form>
        <p class="muted layout-retention">
          普通备份保留最近
          {{
            data.keep_recent
          }}
          份；永久备份不参与自动清理。每次恢复前会自动备份当前排列。
        </p>
      </div>
      <div class="section-title">
        <h2>历史备份</h2>
        <Badge variant="secondary">{{ data.backups.length }}</Badge>
        <Button
          class="ml-auto"
          variant="outline"
          size="sm"
          :disabled="busy || loading"
          @click="load()"
          ><RefreshCw :size="14" />刷新备份</Button
        >
      </div>
      <p v-if="data.unreadable" class="muted">
        有 {{ data.unreadable }} 份备份文件无法读取，已保留原文件。
      </p>
      <div class="table-panel">
        <div v-if="data.backups.length" class="table-scroll">
          <table class="data-table layout-history">
            <thead>
              <tr>
                <th>备份名称</th>
                <th>保存时间</th>
                <th>图标 / 显示设置</th>
                <th>保留方式</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="backup in data.backups" :key="backup.id">
                <td>
                  <strong>{{ backup.label }}</strong
                  ><small
                    v-if="
                      backup.reason === 'before_restore' ||
                      backup.reason === 'automatic'
                    "
                    class="muted layout-safety-label"
                    >{{
                      backup.reason === "automatic"
                        ? "按频率自动保存"
                        : "恢复前自动保存"
                    }}</small
                  >
                </td>
                <td>{{ date(backup.created_at) }}</td>
                <td>
                  {{ backup.icon_count }} 个图标<small
                    class="muted layout-safety-label"
                    >{{ backup.display.width }} × {{ backup.display.height }} ·
                    {{ backup.display.dpi }} DPI</small
                  >
                </td>
                <td>
                  <Badge v-if="backup.protected" variant="secondary"
                    ><ShieldCheck :size="13" />永久保留</Badge
                  ><span v-else class="muted">普通历史</span>
                </td>
                <td>
                  <div class="layout-row-actions">
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="busy"
                      :aria-label="'恢复备份 ' + backup.label"
                      @click="prepare(backup)"
                      ><ArchiveRestore :size="14" />恢复</Button
                    >
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="busy"
                      :aria-label="
                        (backup.protected ? '取消永久保留 ' : '永久保留 ') +
                        backup.label
                      "
                      @click="protect(backup)"
                      ><LockKeyhole :size="14" />{{
                        backup.protected ? "取消永久保留" : "永久保留"
                      }}</Button
                    >
                    <Button
                      variant="outline"
                      size="sm"
                      :disabled="busy || backup.protected"
                      :aria-label="'删除备份 ' + backup.label"
                      :title="
                        backup.protected
                          ? '先取消永久保留后才可删除'
                          : '删除此备份'
                      "
                      @click="pending = { kind: 'delete', backup }"
                      ><Trash2 :size="14" />删除</Button
                    >
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState
          v-else
          title="还没有桌面布局备份"
          description="保存当前排列后，即可在这里管理和恢复历史备份。"
          ><template #icon><ArchiveRestore :size="26" /></template
        ></EmptyState>
      </div>
      <div class="layout-location muted">
        备份保存在应用数据目录，更新软件会保留。<Button
          variant="outline"
          size="sm"
          @click="openPath(data.directory)"
          >打开备份目录</Button
        >
      </div>
    </template>
    <Button v-else variant="outline" @click="load()">重新检测</Button>
    <Dialog
      :open="settingsConfirm"
      @update:open="
        (v) => {
          if (!busy) settingsConfirm = v;
        }
      "
      ><DialogContent
        ><DialogHeader
          ><DialogTitle>清理多余的普通备份？</DialogTitle
          ><DialogDescription
            >普通备份将仅保留最近
            {{ keepRecent }} 份，永久备份会全部保留。</DialogDescription
          ></DialogHeader
        ><DialogFooter
          ><Button
            variant="outline"
            :disabled="busy"
            @click="settingsConfirm = false"
            >取消</Button
          ><Button :disabled="busy" @click="saveSettings(true)"
            >确认保存并清理</Button
          ></DialogFooter
        ></DialogContent
      ></Dialog
    >
    <Dialog
      :open="!!pending"
      @update:open="
        (v) => {
          if (!v && !busy) pending = null;
        }
      "
    >
      <DialogContent
        ><DialogHeader>
          <DialogTitle>{{
            pending?.kind === "restore"
              ? "恢复桌面排列"
              : pending?.kind === "delete"
                ? "删除此备份？"
                : "取消永久保留？"
          }}</DialogTitle>
          <DialogDescription>{{ pending?.backup.label }}</DialogDescription>
        </DialogHeader>
        <div
          v-if="pending?.kind === 'restore' && pending.plan"
          class="layout-confirm"
        >
          <p>
            恢复 {{ pending.plan.restored_count }} 个已有图标；{{
              pending.plan.new_count
            }}
            个新增图标将放入空网格。
          </p>
          <p v-if="pending.plan.missing_count" class="muted">
            {{ pending.plan.missing_count }} 个图标已不在当前桌面，会跳过。
          </p>
          <p v-if="pending.plan.display_changed" class="muted">
            当前显示设置与备份不同，将按保存的坐标恢复。
          </p>
          <p class="muted">确认后会先自动备份当前排列，再执行恢复。</p>
        </div>
        <p v-else-if="pending?.kind === 'delete'" class="muted">
          删除后，该备份将从历史记录中移除。
        </p>
        <p v-else class="muted">
          取消后将参与普通历史备份清理；保留最近
          {{ data?.keep_recent }} 份普通备份。
        </p>
        <DialogFooter
          ><Button variant="outline" :disabled="busy" @click="pending = null"
            >取消</Button
          ><Button :disabled="busy" @click="confirm">{{
            busy
              ? "正在处理…"
              : pending?.kind === "restore"
                ? "确认恢复排列"
                : pending?.kind === "delete"
                  ? "确认删除备份"
                  : "确认取消永久保留"
          }}</Button></DialogFooter
        >
      </DialogContent>
    </Dialog>
  </section>
</template>
<style scoped>
.layout-save-panel {
  padding: 20px;
  margin-bottom: 24px;
}
.layout-save-panel h2 {
  margin-bottom: 6px;
}
.layout-save-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-top: 18px;
}
.layout-save-form > input {
  flex: 1;
  min-width: 190px;
}
.layout-permanent {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.layout-retention {
  margin-top: 12px;
  font-size: 12px;
}
.layout-history {
  min-width: 820px;
}
.layout-safety-label {
  display: block;
  margin-top: 4px;
  font-size: 11px;
}
.layout-row-actions {
  display: flex;
  gap: 6px;
}
.layout-location {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 16px;
  font-size: 12px;
}
.layout-setting-field {
  display: grid;
  gap: 6px;
  width: 170px;
  font-size: 12px;
}
.layout-confirm {
  display: grid;
  gap: 10px;
}
</style>
