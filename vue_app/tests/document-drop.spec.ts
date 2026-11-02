import { test, expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
function fixtures() {
  return JSON.parse(
    execFileSync(
      process.env.RESEARCH_V3_PYTHON || resolve(".venv/bin/python"),
      [
        "-c",
        `import tempfile,json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
p=Path(tempfile.mkdtemp());w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
root=E.Element(w+'document');body=E.SubElement(root,w+'body');t=E.SubElement(body,w+'tbl')
for row in [['项目','对照组(n=10)','试验组(n=12)'],['评分','50±5','60±5']]:
 r=E.SubElement(t,w+'tr')
 for text in row:E.SubElement(E.SubElement(E.SubElement(E.SubElement(r,w+'tc'),w+'p'),w+'r'),w+'t').text=text
word=p/'拖拽中文测试.DOCX'
with ZipFile(word,'w') as z:z.writestr('word/document.xml',E.tostring(root))
csv=p/'预测数据.CSV';csv.write_text('编号,分组,年龄\\n'+'\\n'.join(f'P{i},{i%2},{30+i}' for i in range(40)),encoding='utf-8-sig')
print(json.dumps(dict(word=str(word),csv=str(csv))))`,
      ],
      { encoding: "utf8" },
    ),
  );
}
async function drop(
  page: Page,
  selector: string,
  files: { name: string; content: string }[],
  type = "drop",
) {
  await page.locator(selector).evaluate(
    (node, { files, type }) => {
      const dt = new DataTransfer();
      for (const f of files)
        dt.items.add(
          new File(
            [Uint8Array.from(atob(f.content), (c) => c.charCodeAt(0))],
            f.name,
          ),
        );
      node.dispatchEvent(
        new DragEvent(type, {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
        }),
      );
    },
    { files, type },
  );
}
function file(path: string) {
  return {
    name: path.split("/").pop()!,
    content: readFileSync(path).toString("base64"),
  };
}
async function native(page: Page) {
  await page.addInitScript(() => {
    const h = window as any,
      callbacks = new Map<number, any>(),
      listeners = new Map<number, any>();
    let seq = 0;
    h.__nativeCalls = [];
    h.__TAURI_EVENT_PLUGIN_INTERNALS__ = {
      unregisterListener: (_: any, id: number) => listeners.delete(id),
    };
    h.__TAURI_INTERNALS__ = {
      metadata: {
        currentWindow: { label: "main" },
        currentWebview: { label: "main", windowLabel: "main" },
      },
      transformCallback: (cb: any) => {
        callbacks.set(++seq, cb);
        return seq;
      },
      unregisterCallback: (id: number) => callbacks.delete(id),
      invoke: async (command: string, args: any) => {
        h.__nativeCalls.push({ command, args });
        if (command === "python_request") {
          const r = await fetch("/api/bridge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(args.request),
          });
          return r.json();
        }
        if (command === "plugin:event|listen") {
          const id = ++seq;
          listeners.set(id, args);
          return id;
        }
        if (command === "plugin:event|unlisten") return;
        return 1;
      },
    };
    h.__emitDrop = (event: string, paths: string[]) => {
      for (const [id, l] of listeners)
        if (l.event === event)
          callbacks.get(l.handler)?.({
            event,
            id,
            payload: { paths, position: { x: 400, y: 250 } },
          });
    };
  });
}
test("browser Word drop highlights, imports and keeps replacement confirmation", async ({
  page,
}) => {
  const f = fixtures();
  await page.goto("/#/tools/word");
  await expect(
    page.getByRole("button", { name: "导入 Word", exact: true }),
  ).toBeEnabled();
  await drop(page, ".word-page", [file(f.word)], "dragenter");
  await expect(page.getByText("松开以导入Word 文档")).toBeVisible();
  await drop(page, ".word-page", [file(f.word)]);
  await expect(page.getByText("松开以导入Word 文档")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "查看原表与识别草稿" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "导入 Word", exact: true }),
  ).toBeEnabled();
  await drop(page, ".word-page", [file(f.word)]);
  await expect(page.getByRole("dialog")).toContainText("替换当前 Word 导入？");
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "查看原表与识别草稿" }),
  ).toBeVisible();
});
test("browser prediction accepts dragged CSV and rejects invalid or multiple files", async ({
  page,
}) => {
  const f = fixtures();
  await page.goto("/#/tools/prediction");
  await drop(page, ".prediction-tool", [
    { name: "错误.pdf", content: btoa("fake") },
  ]);
  await expect(page.getByRole("status")).toContainText(".xlsx / .csv");
  await drop(page, ".prediction-tool", [file(f.csv), file(f.csv)]);
  await expect(page.getByRole("status")).toContainText("每次拖入一个文件");
  await drop(page, ".prediction-tool", [file(f.csv)]);
  await expect(page.getByText("40 例 · 3 列 · 已选 1 项指标")).toBeVisible();
});
test("desktop native paths import into the active tool exactly once across cached pages", async ({
  page,
}) => {
  const f = fixtures();
  await native(page);
  await page.goto("/#/tools/word");
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as any).__nativeCalls.filter(
            (c: any) =>
              c.command === "plugin:event|listen" &&
              c.args.event === "tauri://drag-drop",
          ).length,
      ),
    )
    .toBe(1);
  await page.evaluate(
    (paths) => (window as any).__emitDrop("tauri://drag-enter", paths),
    [f.word],
  );
  await expect(page.getByText("松开以导入Word 文档")).toBeVisible();
  await page.evaluate(
    (paths) => (window as any).__emitDrop("tauri://drag-drop", paths),
    [f.word],
  );
  await expect(
    page.getByRole("button", { name: "查看原表与识别草稿" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "科研工具" })
    .getByRole("link", { name: "预测模型分析" })
    .click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as any).__nativeCalls.filter(
            (c: any) =>
              c.command === "plugin:event|listen" &&
              c.args.event === "tauri://drag-drop",
          ).length,
      ),
    )
    .toBe(2);
  await page.evaluate(
    (paths) => (window as any).__emitDrop("tauri://drag-drop", paths),
    [f.csv],
  );
  await expect(page.getByText("40 例 · 3 列 · 已选 1 项指标")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .getByRole("navigation", { name: "工作空间" })
    .getByRole("link", { name: /工作台/ })
    .click();
  await page.evaluate(
    (paths) => (window as any).__emitDrop("tauri://drag-drop", paths),
    [f.csv],
  );
  const calls = await page.evaluate(() =>
    (window as any).__nativeCalls.filter(
      (c: any) =>
        c.command === "python_request" &&
        ["tool.word.scan", "tool.prediction.inspect"].includes(
          c.args.request.method,
        ),
    ),
  );
  expect(calls).toHaveLength(2);
  expect(calls[0].args.request.params.paths).toEqual([f.word]);
  expect(calls[1].args.request.params.paths).toEqual([f.csv]);
  expect(calls.every((c: any) => !c.args.request.params.uploads)).toBeTruthy();
});
