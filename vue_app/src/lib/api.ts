import { reactive } from "vue";
export interface Task {
  id: string;
  name: string;
  client: string;
  tags: string[];
  status: string;
  due_date: string | null;
  created_date: string;
  notes: string;
  directory: string;
  file_count: number;
  pending_count: number;
  next_todo?: Todo | null;
  todo_text?: string;
  file_names?: string;
}
export interface Todo {
  id: string;
  text: string;
  priority: string;
  due_date: string | null;
  completed: boolean;
  task_id: string | null;
  task_name: string;
  client: string;
  file_ids: string[];
}
export interface Material {
  id: string;
  original_name: string;
  category: string | null;
  path: string;
  size: number;
  received_at: string;
  available: boolean;
  task_id: string | null;
}
export interface Event {
  id: number;
  kind: string;
  created_at: string;
  details: Record<string, unknown>;
}
export interface Detail {
  task: Task;
  files: Material[];
  todos: Todo[];
  events: Event[];
}
export interface State {
  root: string | null;
  tasks: Task[];
  todos: Todo[];
  inbox: Material[];
  categories: string[];
  statuses: string[];
}
export const state = reactive<State>({
  root: null,
  tasks: [],
  todos: [],
  inbox: [],
  categories: ["原稿", "原始数据", "图表", "修改稿", "交付"],
  statuses: ["进行中", "待补资料", "返修中", "待交付", "已完成"],
});
export const feedback = reactive({ text: "", error: false, loading: false });
export const desktop = "__TAURI_INTERNALS__" in window;
export async function api<T = any>(
  method: string,
  params: unknown = {},
  signal?: AbortSignal,
): Promise<T> {
  let response;
  if (desktop) {
    const { invoke } = await import("@tauri-apps/api/core");
    response = await invoke<{ ok: boolean; result: T; error?: string }>(
      "python_request",
      { request: { method, params } },
    );
  } else {
    const res = await fetch("/api/bridge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method, params }),
      signal,
    });
    response = await res.json();
  }
  if (!response.ok) throw new Error(response.error || "操作失败，请重试。");
  return response.result as T;
}
export function notify(text: string, error = false) {
  feedback.text = text;
  feedback.error = error;
}
export async function refresh() {
  Object.assign(state, await api<State>("state"));
}
export async function action<T>(
  method: string,
  params: unknown = {},
  message = "已保存到本机。",
): Promise<T | undefined> {
  try {
    const result = await api<T>(method, params);
    await refresh();
    notify(message);
    return result;
  } catch (e) {
    notify(String((e as Error).message), true);
  }
}
export function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function dateText(value?: string | null) {
  return value ? value.replaceAll("-", ".") : "未设置";
}
export function bytes(n: number) {
  return n < 1024
    ? `${n} B`
    : n < 1048576
      ? `${(n / 1024).toFixed(1)} KB`
      : `${(n / 1048576).toFixed(1)} MB`;
}
export async function upload(files: File[]) {
  return Promise.all(
    files.map(async (f) => {
      const data = new Uint8Array(await f.arrayBuffer());
      if (data.length > 32 * 1024 * 1024)
        throw new Error("单个材料最多 32 MB。");
      let binary = "";
      for (let i = 0; i < data.length; i += 8192)
        binary += String.fromCharCode(...data.subarray(i, i + 8192));
      return { name: f.name, content: btoa(binary) };
    }),
  );
}
export function download(
  name: string,
  content: string,
  mime = "text/plain;charset=utf-8",
  base64 = false,
) {
  const blob = new Blob(
    [base64 ? Uint8Array.from(atob(content), (c) => c.charCodeAt(0)) : content],
    { type: mime },
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function openPath(path: string) {
  if (desktop) {
    const { openPath } = await import("@tauri-apps/plugin-opener");
    await openPath(path);
  } else {
    await navigator.clipboard.writeText(path);
    notify("路径已复制，可在文件管理器中打开。");
  }
}
