<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from "vue";
import { Camera, Circle, Copy, Download, Eraser, MousePointer2, Square, Type } from "lucide-vue-next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import PageHeading from "@/components/PageHeading.vue";
import { api, download, notify, desktop } from "@/lib/api";

type Mode = "select" | "rect" | "ellipse" | "text";
const canvas = ref<HTMLCanvasElement | null>(null);
const stage = ref<HTMLDivElement | null>(null);
const source = ref<HTMLImageElement | null>(null);
const bitmap = ref<HTMLImageElement | null>(null);
const imageData = ref("");
const mode = ref<Mode>("select");
const color = ref("#e53935");
const lineWidth = ref(4);
const fontSize = ref(26);
const text = ref("重点");
const hideApp = ref(true);
const busy = ref(false);
const error = ref("");
const drawing = ref(false);
const start = ref({ x: 0, y: 0 });
const selection = ref<{ x: number; y: number; width: number; height: number } | null>(null);
const dragSelection = ref<{ x: number; y: number; width: number; height: number } | null>(null);
let beforeDrawing: ImageData | null = null;
const undoStack = ref<ImageData[]>([]);
const redoStack = ref<ImageData[]>([]);
const scale = ref(1);

function fitCanvas() {
  if (!canvas.value || !stage.value || !bitmap.value) return;
  const maxWidth = Math.max(320, stage.value.clientWidth - 24);
  scale.value = Math.min(1, maxWidth / bitmap.value.naturalWidth);
  canvas.value.width = bitmap.value.naturalWidth;
  canvas.value.height = bitmap.value.naturalHeight;
  canvas.value.style.width = `${bitmap.value.naturalWidth * scale.value}px`;
  canvas.value.style.height = `${bitmap.value.naturalHeight * scale.value}px`;
  const ctx = canvas.value.getContext("2d");
  if (ctx) {
    ctx.drawImage(bitmap.value, 0, 0);
    selection.value = null;
    dragSelection.value = null;
    undoStack.value = [];
    redoStack.value = [];
  }
}
function point(event: PointerEvent) {
  const rect = canvas.value!.getBoundingClientRect();
  return { x: (event.clientX - rect.left) / scale.value, y: (event.clientY - rect.top) / scale.value };
}
function drawAnnotation(event: PointerEvent) {
  if (!canvas.value || !drawing.value) return;
  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;
  const p = point(event);
  if (mode.value === "select") {
    dragSelection.value = {
      x: Math.min(start.value.x, p.x), y: Math.min(start.value.y, p.y),
      width: Math.abs(p.x - start.value.x), height: Math.abs(p.y - start.value.y),
    };
  }
  if (beforeDrawing) ctx.putImageData(beforeDrawing, 0, 0);
  ctx.save();
  ctx.strokeStyle = color.value;
  ctx.fillStyle = color.value;
  ctx.lineWidth = Number(lineWidth.value);
  ctx.lineCap = "round";
  if (mode.value === "select" || mode.value === "rect") ctx.strokeRect(start.value.x, start.value.y, p.x - start.value.x, p.y - start.value.y);
  if (mode.value === "ellipse") {
    const cx = (start.value.x + p.x) / 2, cy = (start.value.y + p.y) / 2;
    ctx.beginPath();
    ctx.ellipse(cx, cy, Math.abs(p.x - start.value.x) / 2, Math.abs(p.y - start.value.y) / 2, 0, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}
function begin(event: PointerEvent) {
  if (!canvas.value) return;
  drawing.value = true;
  start.value = point(event);
  beforeDrawing = canvas.value.getContext("2d")?.getImageData(0, 0, canvas.value.width, canvas.value.height) || null;
  canvas.value.setPointerCapture(event.pointerId);
  if (mode.value === "text") {
    const ctx = canvas.value.getContext("2d");
    if (ctx) {
      if (beforeDrawing) undoStack.value.push(beforeDrawing);
      redoStack.value = [];
      ctx.font = `600 ${Number(fontSize.value)}px sans-serif`;
      ctx.fillStyle = color.value;
      ctx.fillText(text.value || "文字", start.value.x, start.value.y);
    }
    drawing.value = false;
  }
}
function end(event: PointerEvent) {
  if (!drawing.value || !canvas.value) return;
  drawAnnotation(event);
  const p = point(event);
  if (mode.value === "select") {
    selection.value = dragSelection.value;
    if (beforeDrawing) canvas.value.getContext("2d")?.putImageData(beforeDrawing, 0, 0);
  } else if (beforeDrawing) {
    undoStack.value.push(beforeDrawing);
    redoStack.value = [];
  }
  drawing.value = false;
  beforeDrawing = null;
  dragSelection.value = null;
}
function clearAnnotations() {
  fitCanvas();
}
function undo() {
  if (!canvas.value || !undoStack.value.length) return;
  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;
  redoStack.value.push(ctx.getImageData(0, 0, canvas.value.width, canvas.value.height));
  ctx.putImageData(undoStack.value.pop()!, 0, 0);
}
function redo() {
  if (!canvas.value || !redoStack.value.length) return;
  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;
  undoStack.value.push(ctx.getImageData(0, 0, canvas.value.width, canvas.value.height));
  ctx.putImageData(redoStack.value.pop()!, 0, 0);
}
function cropSelection() {
  if (!canvas.value || !selection.value || selection.value.width < 2 || selection.value.height < 2) return;
  const s = selection.value;
  const source = document.createElement("canvas");
  source.width = Math.round(s.width); source.height = Math.round(s.height);
  source.getContext("2d")?.drawImage(canvas.value, s.x, s.y, s.width, s.height, 0, 0, s.width, s.height);
  undoStack.value.push(canvas.value.getContext("2d")!.getImageData(0, 0, canvas.value.width, canvas.value.height));
  redoStack.value = [];
  canvas.value.width = source.width; canvas.value.height = source.height;
  canvas.value.getContext("2d")?.drawImage(source, 0, 0);
  selection.value = null;
  dragSelection.value = null;
  scale.value = 1;
  canvas.value.style.width = `${source.width}px`;
  canvas.value.style.height = `${source.height}px`;
}
async function capture() {
  busy.value = true;
  error.value = "";
  let hidden = false;
  try {
    if (desktop && hideApp.value) {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().hide();
      hidden = true;
      await new Promise((resolve) => setTimeout(resolve, 260));
    }
    const result = await api<{ base64: string; mime: string; width: number; height: number }>("tool.screenshot.capture");
    imageData.value = `data:${result.mime};base64,${result.base64}`;
    await nextTick();
    bitmap.value = new Image();
    bitmap.value.onload = () => {
      fitCanvas();
      void copy(true);
    };
    bitmap.value.src = imageData.value;
    if (hidden) {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().show();
      await getCurrentWindow().setFocus();
    }
    notify("截图已载入，可添加标注。");
  } catch (e) {
    error.value = (e as Error).message;
    if (hidden) {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      await getCurrentWindow().show();
    }
  } finally {
    busy.value = false;
  }
}
function pngData() { return canvas.value?.toDataURL("image/png") || imageData.value; }
async function copy(silent = false) {
  const data = pngData();
  try {
    const blob = await (await fetch(data)).blob();
    if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })]);
    else throw new Error("clipboard unavailable");
    if (!silent) notify("截图已复制到剪贴板。");
  } catch {
    if (!silent) notify("当前环境无法直接写入图片剪贴板，请使用保存文件。", true);
  }
}
function save() {
  const data = pngData();
  download("截图标注.png", data.split(",")[1], "image/png", true);
}
function shortcut(event: KeyboardEvent) {
  if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key === "4") {
    event.preventDefault();
    void capture();
  }
}
function globalShortcut() { void capture(); }
onMounted(() => {
  window.addEventListener("keydown", shortcut);
  window.addEventListener("screenshot-shortcut", globalShortcut);
});
onUnmounted(() => {
  window.removeEventListener("keydown", shortcut);
  window.removeEventListener("screenshot-shortcut", globalShortcut);
});
</script>

<template>
  <section class="scientific-page screenshot-page">
    <PageHeading title="截图与标注" subtitle="方框、圆框、文字标注，完成后可复制或保存 PNG">
      <Badge variant="secondary">快捷键（应用聚焦时）⌘ / Ctrl + Shift + 4</Badge>
    </PageHeading>
    <section class="scientific-section surface screenshot-toolbar">
      <div class="screenshot-tools">
        <Button :variant="mode === 'select' ? 'default' : 'outline'" @click="mode = 'select'"><MousePointer2 :size="15" />选择区域</Button>
        <Button :variant="mode === 'rect' ? 'default' : 'outline'" @click="mode = 'rect'"><Square :size="15" />方框</Button>
        <Button :variant="mode === 'ellipse' ? 'default' : 'outline'" @click="mode = 'ellipse'"><Circle :size="15" />圆框</Button>
        <Button :variant="mode === 'text' ? 'default' : 'outline'" @click="mode = 'text'"><Type :size="15" />文字</Button>
        <label class="screenshot-control">颜色 <input v-model="color" type="color" /></label>
        <label class="screenshot-control">线宽 <Input v-model.number="lineWidth" type="number" min="1" max="20" /></label>
        <label v-if="mode === 'text'" class="screenshot-control">字号 <Input v-model.number="fontSize" type="number" min="10" max="160" /></label>
        <label v-if="mode === 'text'" class="screenshot-control screenshot-text-input">文字 <Input v-model="text" placeholder="请输入文字" /></label>
      </div>
      <div class="screenshot-actions">
        <label class="screenshot-hide"><input v-model="hideApp" type="checkbox" />截图时隐藏当前应用窗口</label>
        <Button :disabled="busy" @click="capture"><Camera :size="15" />{{ busy ? "正在截图…" : "开始截图" }}</Button>
        <Button variant="outline" :disabled="!imageData" @click="clearAnnotations"><Eraser :size="15" />清除标注</Button>
        <Button variant="outline" :disabled="!undoStack.length" @click="undo">撤销</Button>
        <Button variant="outline" :disabled="!redoStack.length" @click="redo">重做</Button>
        <Button v-if="selection" variant="outline" @click="cropSelection">裁剪到选区</Button>
        <Button variant="outline" :disabled="!imageData" @click="copy"><Copy :size="15" />复制图片</Button>
        <Button variant="outline" :disabled="!imageData" @click="save"><Download :size="15" />保存 PNG</Button>
      </div>
      <p v-if="error" class="field-error">{{ error }}</p>
    </section>
    <section ref="stage" class="scientific-section surface screenshot-stage">
      <div v-if="!imageData" class="empty-state"><MousePointer2 :size="30" /><strong>等待截图</strong><span>点击“开始截图”或按全局快捷键 ⌘ / Ctrl + Shift + 4。</span></div>
      <div v-else class="screenshot-canvas-wrap"><img ref="source" class="screenshot-source" alt="截图底图" /><canvas ref="canvas" @pointerdown="begin" @pointermove="drawAnnotation" @pointerup="end" @pointercancel="end" /><div v-if="selection || dragSelection" class="screenshot-selection" :style="{ left: `${(selection || dragSelection)!.x * scale}px`, top: `${(selection || dragSelection)!.y * scale}px`, width: `${(selection || dragSelection)!.width * scale}px`, height: `${(selection || dragSelection)!.height * scale}px` }" /></div>
    </section>
  </section>
</template>
