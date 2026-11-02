<script setup lang="ts">
import { computed, ref } from "vue";
import { Download, FolderInput, FileText, Search } from "lucide-vue-next";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import PageHeading from "@/components/PageHeading.vue";
import EmptyState from "@/components/EmptyState.vue";
import ImportDialog from "@/components/ImportDialog.vue";
import PreviewDialog from "@/components/PreviewDialog.vue";
import { state, bytes, type Material } from "@/lib/api";
const query = ref(""),
  selected = ref<string[]>([]),
  importOpen = ref(false),
  archiveOpen = ref(false),
  preview = ref<Material | null>(null);
const rows = computed(() =>
    state.inbox.filter((f) =>
      f.original_name
        .toLocaleLowerCase()
        .includes(query.value.toLocaleLowerCase()),
    ),
  ),
  selectedFiles = computed(() =>
    state.inbox.filter((f) => selected.value.includes(f.id)),
  );
</script>
<template>
  <section>
    <PageHeading
      title="未分类收件箱"
      subtitle="先接收新材料，再归档到对应稿件。"
      ><Button
        variant="outline"
        :disabled="!state.root"
        @click="importOpen = true"
        ><Download :size="16" />接收材料</Button
      ><Button :disabled="!selectedFiles.length" @click="archiveOpen = true"
        ><FolderInput :size="16" />归档到任务
        <span v-if="selectedFiles.length">{{
          selectedFiles.length
        }}</span></Button
      ></PageHeading
    >
    <div class="inbox-note">
      <FolderInput :size="20" />
      <div>
        <strong>只整理新接收的材料</strong>
        <p>
          已有历史稿件不会自动扫描；归档会移动工作空间内的副本，外部原件保持不变。
        </p>
      </div>
    </div>
    <div class="section-title">
      <h2>待归档材料</h2>
      <Badge variant="secondary">{{ state.inbox.length }}</Badge>
      <div class="search-field ml-auto max-w-xs">
        <Search :size="15" /><Input
          v-model="query"
          aria-label="搜索收件箱"
          placeholder="搜索材料名称…"
        />
      </div>
    </div>
    <div class="table-panel">
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th class="w-12">
                <Checkbox
                  :model-value="
                    !!rows.length && rows.every((f) => selected.includes(f.id))
                  "
                  aria-label="全选待归档材料"
                  @update:model-value="
                    (v) => (selected = v ? rows.map((f) => f.id) : [])
                  "
                />
              </th>
              <th>文件名称</th>
              <th>接收时间</th>
              <th>大小</th>
              <th>状态</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="file in rows" :key="file.id">
              <td>
                <Checkbox
                  :model-value="selected.includes(file.id)"
                  :aria-label="'选择 ' + file.original_name"
                  @update:model-value="
                    (v) =>
                      (selected = v
                        ? [...selected, file.id]
                        : selected.filter((id) => id !== file.id))
                  "
                />
              </td>
              <td>
                <button class="task-name" @click="preview = file">
                  <FileText :size="19" /><strong>{{
                    file.original_name
                  }}</strong>
                </button>
              </td>
              <td class="muted">
                {{ file.received_at.slice(0, 16).replace("T", " ") }}
              </td>
              <td class="muted">{{ bytes(file.size) }}</td>
              <td>
                <Badge
                  variant="secondary"
                  :class="{ 'tone-amber': !file.available }"
                  >{{ file.available ? "待归档" : "文件丢失" }}</Badge
                >
              </td>
              <td>
                <Button
                  variant="outline"
                  size="sm"
                  @click="
                    selected = [file.id];
                    archiveOpen = true;
                  "
                  >归档 →</Button
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <EmptyState
        v-if="!rows.length"
        title="收件箱很整洁"
        description="收到尚未确定归属的新材料时，可以先存放在这里。"
        ><Button v-if="state.root" variant="outline" @click="importOpen = true"
          ><Download :size="15" />接收材料</Button
        ><RouterLink v-else to="/settings"
          >先选择工作空间 →</RouterLink
        ></EmptyState
      >
      <div class="table-footer">
        <span>共 {{ rows.length }} 个材料</span
        ><span v-if="selectedFiles.length"
          >已选择 {{ selectedFiles.length }} 个</span
        >
      </div>
    </div>
    <ImportDialog v-model:open="importOpen" /><ImportDialog
      v-model:open="archiveOpen"
      :archive="selectedFiles"
      @saved="selected = []"
    /><PreviewDialog :file="preview" @close="preview = null" />
  </section>
</template>
