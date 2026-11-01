<script setup lang="ts">
import { ref, watch } from "vue";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ExternalLink, FileWarning } from "lucide-vue-next";
import { api, openPath, notify, type Material } from "@/lib/api";
const props = defineProps<{ file: Material | null }>(),
  emit = defineEmits<{ close: [] }>();
const content = ref<any>(null),
  error = ref(""),
  loading = ref(false);
watch(
  () => props.file,
  async (file) => {
    content.value = null;
    error.value = "";
    if (!file) return;
    loading.value = true;
    try {
      content.value = await api("files.preview", { id: file.id });
    } catch (e) {
      error.value = (e as Error).message;
    } finally {
      loading.value = false;
    }
  },
);
async function open() {
  try {
    await openPath(await api("files.path", { id: props.file?.id }));
  } catch (e) {
    notify((e as Error).message, true);
  }
}
</script>
<template>
  <Dialog
    :open="!!file"
    @update:open="
      (v) => {
        if (!v) emit('close');
      }
    "
    ><DialogContent class="sm:max-w-[900px] max-h-[90vh] overflow-y-auto"
      ><DialogHeader
        ><DialogTitle>{{ file?.original_name || "材料预览" }}</DialogTitle
        ><DialogDescription
          >只读预览 · 原始文件保持不变</DialogDescription
        ></DialogHeader
      >
      <p v-if="loading" class="muted p-8">正在读取材料…</p>
      <div v-else-if="error" class="empty-state">
        <FileWarning :size="30" />
        <p role="alert">{{ error }}</p>
      </div>
      <pre v-else-if="content?.kind === 'text'" class="document-preview">{{
        content.text
      }}</pre>
      <img
        v-else-if="content?.kind === 'image'"
        :src="content.url"
        :alt="content.name"
        class="image-preview"
      /><iframe
        v-else-if="content?.kind === 'pdf'"
        :src="content.url"
        title="PDF 材料预览"
        class="pdf-preview"
      /><Button variant="outline" class="ml-auto" @click="open"
        ><ExternalLink :size="15" />使用系统程序打开</Button
      ></DialogContent
    ></Dialog
  >
</template>
