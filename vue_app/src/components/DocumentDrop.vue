<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { Upload } from "lucide-vue-next";
import { desktop, notify } from "@/lib/api";
import { documentError, type ImportDocument } from "@/lib/documentImport";
const props = defineProps<{
  route: string;
  extensions: string[];
  label: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{ import: [file: ImportDocument] }>();
const route = useRoute(),
  dragging = ref(false);
let depth = 0,
  disposed = false,
  unlisten: (() => void) | undefined;
const active = () => route.path === props.route;
function reset() {
  depth = 0;
  dragging.value = false;
}
watch(() => route.path, reset);
watch(() => props.disabled, reset);
function receive(files: ImportDocument[]) {
  reset();
  if (!active()) return;
  if (props.disabled) {
    notify("请先完成或取消当前操作，再导入文件。", true);
    return;
  }
  const error = documentError(files, props.extensions);
  if (error) {
    notify(error, true);
    return;
  }
  emit("import", files[0]);
}
function hasFiles(e: DragEvent) {
  return Array.from(e.dataTransfer?.types || []).includes("Files");
}
function enter(e: DragEvent) {
  if (!hasFiles(e)) return;
  e.preventDefault();
  if (!desktop && active() && !props.disabled) {
    depth++;
    dragging.value = true;
  }
}
function over(e: DragEvent) {
  if (!hasFiles(e)) return;
  e.preventDefault();
  if (e.dataTransfer)
    e.dataTransfer.dropEffect = props.disabled ? "none" : "copy";
}
function leave(e: DragEvent) {
  if (!hasFiles(e)) return;
  if (--depth <= 0) reset();
}
function drop(e: DragEvent) {
  if (!hasFiles(e)) return;
  e.preventDefault();
  e.stopPropagation();
  if (!desktop) receive(Array.from(e.dataTransfer?.files || []));
  else reset();
}
onMounted(async () => {
  if (!desktop) return;
  try {
    const { getCurrentWebview } = await import("@tauri-apps/api/webview");
    const stop = await getCurrentWebview().onDragDropEvent(({ payload }) => {
      if (!active()) {
        reset();
        return;
      }
      if (payload.type === "leave") {
        reset();
        return;
      }
      if (payload.type === "drop")
        receive(
          payload.paths.map((path) => ({
            path,
            name: path.split(/[\\/]/).pop() || path,
          })),
        );
      else dragging.value = !props.disabled;
    });
    if (disposed) stop();
    else unlisten = stop;
  } catch (e) {
    notify(
      "桌面拖拽监听未能启动，可先点击导入按钮。" + (e as Error).message,
      true,
    );
  }
});
onUnmounted(() => {
  disposed = true;
  unlisten?.();
});
</script>
<template>
  <div
    class="document-drop"
    :class="{ 'document-dragging': dragging }"
    @dragenter="enter"
    @dragover="over"
    @dragleave="leave"
    @drop="drop"
  >
    <slot />
    <div v-if="dragging" class="document-drop-overlay" role="status">
      <div>
        <Upload :size="32" :stroke-width="1.7" /><strong
          >松开以导入{{ label }}</strong
        ><span
          >每次一个文件 ·
          {{ extensions.map((x) => x.toUpperCase()).join(" / ") }}</span
        >
      </div>
    </div>
  </div>
</template>
<style scoped>
.document-drop {
  min-height: 240px;
}
.document-dragging {
  outline: 2px dashed #68a282;
  outline-offset: -2px;
  border-radius: 10px;
}
.document-drop-overlay {
  position: fixed;
  inset: 90px 30px 30px 250px;
  z-index: 60;
  display: grid;
  place-items: center;
  pointer-events: none;
  border: 2px dashed #68a282;
  border-radius: 12px;
  background: #edf8f1ed;
  color: var(--foreground);
}
.document-drop-overlay > div {
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 14px;
  padding: 24px;
  text-align: center;
}
.document-drop-overlay strong {
  font-size: 20px;
}
.document-drop-overlay span {
  font-size: 13px;
  color: var(--muted-foreground);
}
@media (max-width: 1000px) {
  .document-drop-overlay {
    left: 90px;
  }
}
@media (max-width: 600px) {
  .document-drop-overlay {
    inset: 80px 16px 16px;
  }
}
</style>
