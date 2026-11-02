import { upload } from "./api";

export type ImportDocument = File | { name: string; path: string };
export function documentError(files: ImportDocument[], extensions: string[]) {
  if (files.length !== 1) return "请每次拖入一个文件。";
  const extension = files[0].name.split(".").pop()?.toLowerCase();
  if (!extension || !extensions.includes(extension))
    return `请选择 ${extensions.map((x) => "." + x).join(" / ")} 文件。`;
  return "";
}
export async function documentPayload(file: ImportDocument) {
  return "path" in file
    ? { paths: [file.path] }
    : { uploads: await upload([file]) };
}
