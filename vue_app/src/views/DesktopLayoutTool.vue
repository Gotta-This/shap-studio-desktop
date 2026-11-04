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
  Download,
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
import { api, notify, openPath, download } from "@/lib/api";
interface AssistantBackup {
  status: string;
  message: string;
  file_count?: number;
  bytes?: number;
}
interface Backup {
  assistant?: AssistantBackup;
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
  assistant?: {
    checked: boolean;
    running: boolean;
    installed: boolean;
    data_found: boolean;
    message: string;
  };
  settings?: {
    feature_enabled?: boolean;
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
  needs_move_count?: number;
  display_changed: boolean;
  fingerprint: string;
}
interface AssistantPlan {
  file_count: number;
  bytes: number;
  fingerprint: string;
  current_exists: boolean;
  message: string;
}
const rollbackDirectory = ref("");
const restoreSummary = ref("");
const restoreFailed = ref(false);
async function exportDiagnostics() {
  busy.value = true;
  try {
    const value = await api<{ name: string; content: string }>(
      "desktop.layout.diagnostics",
    );
    await download(value.name, value.content, "application/json");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
const data = ref<LayoutInfo | null>(null),
  loading = ref(false),
  busy = ref(false),
  error = ref("");
const label = ref(""),
  permanent = ref(false);
const featureEnabled = ref(true);
const autoEnabled = ref(true),
  intervalMinutes = ref(10),
  keepRecent = ref(144),
  settingsConfirm = ref(false);
const pending = ref<{
  kind: "restore" | "assistant_restore" | "delete" | "unprotect";
  backup: Backup;
  plan?: Plan;
  assistantPlan?: AssistantPlan;
} | null>(null);
async function load(syncSettings = true) {
  loading.value = true;
  try {
    data.value = await api("desktop.layout.info");
    error.value = "";
    if (syncSettings && data.value?.settings) {
      featureEnabled.value = data.value.settings.feature_enabled !== false;
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
      feature_enabled: featureEnabled.value,
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
    const result = await api<Backup>("desktop.layout.backup", {
      label: label.value,
      protected: permanent.value,
    });
    label.value = "";
    permanent.value = false;
    await load();
    if (result.assistant?.status === "failed")
      error.value = result.assistant.message;
    notify(
      result.assistant?.status === "saved"
        ? "Windows 布局及 360 数据副本已保存。"
        : "Windows 桌面排列已备份。",
    );
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
  restoreSummary.value = "";
  rollbackDirectory.value = "";
  try {
    const plan = await api<Plan>("desktop.layout.preview", { id: backup.id });
    pending.value = { kind: "restore", backup, plan };
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function prepareAssistant(backup: Backup) {
  busy.value = true;
  error.value = "";
  restoreSummary.value = "";
  rollbackDirectory.value = "";
  try {
    const plan = await api<AssistantPlan>("desktop.layout.assistant_preview", {
      id: backup.id,
    });
    pending.value = { kind: "assistant_restore", backup, assistantPlan: plan };
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
    if (action.kind === "assistant_restore") {
      const result = await api<{ message: string; rollback_directory: string }>(
        "desktop.layout.assistant_restore",
        {
          id: action.backup.id,
          fingerprint: action.assistantPlan?.fingerprint,
        },
      );
      restoreFailed.value = false;
      restoreSummary.value = result.message;
      rollbackDirectory.value = result.rollback_directory;
      notify("360 配置文件已恢复，请启动 360 检查布局。");
    } else if (action.kind === "restore") {
      const result = await api<
        Plan & {
          unmatched_positions: number;
          diagnostic_id?: string;
          diagnostic_saved?: boolean;
        }
      >("desktop.layout.restore", {
        id: action.backup.id,
        fingerprint: action.plan?.fingerprint,
      });
      const restored = result.restored_count ?? action.plan!.restored_count;
      const missing = result.missing_count ?? action.plan!.missing_count;
      restoreFailed.value = !!result.unmatched_positions;
      restoreSummary.value = result.unmatched_positions
        ? `Windows 有 ${result.unmatched_positions} 个图标未按预期落位。恢复前排列已自动备份，请导出诊断日志。`
        : result.needs_move_count === 0
          ? "所选备份与当前排列一致，没有需要移动的图标。请确认选择的是打乱排列之前的备份。"
          : `已恢复 ${restored} / ${restored + missing} 个备份图标；${missing} 个未匹配并跳过；${result.new_count ?? action.plan!.new_count} 个新增图标已放入空网格。`;
      if (result.diagnostic_id)
        restoreSummary.value += ` 诊断编号：${result.diagnostic_id.slice(0, 12)}。`;
      if (result.diagnostic_saved === false)
        restoreSummary.value += " 诊断日志未能写入，请检查数据目录写入权限。";
      notify(restoreSummary.value, restoreFailed.value);
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
    <p
      v-if="restoreSummary"
      class="layout-restore-summary"
      :class="restoreFailed ? 'field-error' : 'muted'"
      role="status"
    >
      {{ restoreSummary }}
    </p>
    <p v-if="rollbackDirectory" class="muted">
      恢复前的 360 配置已完整保留，不参与普通备份份数清理。
      <Button variant="outline" size="sm" @click="openPath(rollbackDirectory)"
        >打开恢复前的 360 配置目录</Button
      >
    </p>
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
      <div class="layout-diagnostics muted">
        <span
          >恢复异常时，可导出诊断日志；日志不包含桌面文件名、完整路径或文件内容。</span
        >
        <Button
          variant="outline"
          size="sm"
          :disabled="busy"
          @click="exportDiagnostics"
          ><Download :size="14" />导出诊断日志</Button
        >
      </div>
      <div class="panel layout-save-panel">
        <h2>工具与自动备份设置</h2>
        <p v-if="data.settings?.feature_enabled === false" class="muted">
          工具已关闭：停止手动备份、自动备份及恢复，历史记录继续保留。
        </p>
        <p class="muted">
          软件打开期间按频率自动保存；关闭后停止，下次打开会检查是否到期。
        </p>
        <form class="layout-save-form" @submit.prevent="saveSettings()">
          <label class="layout-permanent"
            ><Checkbox
              v-model="featureEnabled"
              aria-label="启用桌面布局工具"
            />启用桌面布局工具</label
          >
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
          默认每 10 分钟备份一次、保留 144 份，连续运行约覆盖 24
          小时；按份数清理，不按时间删除。
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
      <div class="panel">
        <h2>360 桌面助手兼容备份</h2>
        <p role="status">
          {{
            !data.assistant?.checked
              ? "运行状态检测失败，请刷新重试"
              : data.assistant.running
                ? "360 正在运行：备份 Windows 原生布局，并同步保存 360 数据目录副本。"
                : data.assistant.installed
                  ? "检测到安装记录或残留数据，360 当前未运行：仅备份 Windows 原生布局。"
                  : "未检测到 360 桌面助手：仅备份 Windows 原生布局。"
          }}
        </p>
        <p class="muted">
          360 副本按原文件压缩保存于备份目录的 360-data
          文件夹，相同内容共用副本。运行中复制尚未经 360
          恢复验证，恢复时须先退出 360，通过校验和确认后才会替换配置。
        </p>
        <p class="muted">
          Windows 原生备份记录当时系统接口可读取的排列，无法还原未曾备份的“启动
          360 前布局”。360 运行期间暂停两种恢复。退出 360
          后点击“刷新备份”，再选择对应恢复按钮。
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
          <Button
            type="submit"
            :disabled="
              busy || loading || data.settings?.feature_enabled === false
            "
            ><MonitorCog :size="16" />{{
              busy ? "正在处理…" : "备份当前排列"
            }}</Button
          >
        </form>
        <p class="muted layout-retention">
          普通备份保留最近
          {{ data.keep_recent }}
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
                <th>360 同步副本</th>
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
                  <span
                    :class="
                      backup.assistant?.status === 'failed'
                        ? 'field-error'
                        : 'muted'
                    "
                    >{{
                      backup.assistant?.status === "saved"
                        ? `已保存 · ${backup.assistant.file_count} 个文件`
                        : backup.assistant?.status === "failed"
                          ? "同步失败"
                          : backup.assistant?.status === "not_running"
                            ? "360 未运行"
                            : "历史备份无副本"
                    }}</span
                  >
                  <small class="muted layout-safety-label">{{
                    backup.assistant?.message
                  }}</small>
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
                      :disabled="
                        busy ||
                        data.settings?.feature_enabled === false ||
                        data.assistant?.running
                      "
                      :aria-label="'恢复备份 ' + backup.label"
                      @click="prepare(backup)"
                      ><ArchiveRestore :size="14" />恢复 Windows</Button
                    >
                    <Button
                      v-if="backup.assistant?.status === 'saved'"
                      variant="outline"
                      size="sm"
                      :disabled="
                        busy ||
                        data.settings?.feature_enabled === false ||
                        data.assistant?.running
                      "
                      :aria-label="'恢复360备份 ' + backup.label"
                      @click="prepareAssistant(backup)"
                      ><ArchiveRestore :size="14" />恢复 360</Button
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
            pending?.kind === "assistant_restore"
              ? "恢复 360 桌面助手配置"
              : pending?.kind === "restore"
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
          <p v-if="pending.plan.needs_move_count === 0" class="field-error">
            这份备份与当前排列一致，没有需要移动的图标。请确认没有选到刚生成的“恢复前自动备份”。
          </p>
          <p v-if="pending.plan.display_changed" class="muted">
            当前显示设置与备份不同，将按保存的坐标恢复。
          </p>
          <p class="muted">确认后会先自动备份当前排列，再执行恢复。</p>
        </div>
        <div
          v-else-if="
            pending?.kind === 'assistant_restore' && pending.assistantPlan
          "
          class="layout-confirm"
        >
          <p>
            将恢复 {{ pending.assistantPlan.file_count }} 个 360 数据文件（{{
              (pending.assistantPlan.bytes / 1024 / 1024).toFixed(2)
            }}
            MB）。
          </p>
          <p>{{ pending.assistantPlan.message }}</p>
          <p class="field-error">
            将整体替换 360 数据目录，包括副本中的设置和历史数据。360
            必须保持退出；运行中复制的副本仍需启动后人工确认兼容性。
          </p>
          <p v-if="pending.assistantPlan.current_exists" class="muted">
            当前配置会先整体移至同级回退目录，写入失败会尝试自动回退。
          </p>
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
              : pending?.kind === "assistant_restore"
                ? "确认恢复360配置"
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
.layout-diagnostics {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 12px;
}
</style>
