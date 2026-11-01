import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";
import { spawn } from "node:child_process";
export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  plugins: [
    vue(),
    tailwindcss(),
    {
      name: "local-python-bridge",
      configureServer(server) {
        server.middlewares.use("/api/bridge", (req, res) => {
          const origin = req.headers.origin;
          const host = req.headers.host;
          const localHosts = [
            `127.0.0.1:${server.config.server.port}`,
            `localhost:${server.config.server.port}`,
          ];
          let sameOrigin = !origin;
          try {
            if (origin) sameOrigin = new URL(origin).host === host;
          } catch {
            sameOrigin = false;
          }
          if (
            req.method !== "POST" ||
            !req.headers["content-type"]?.startsWith("application/json") ||
            !sameOrigin ||
            !localHosts.includes(host || "")
          ) {
            res.statusCode = 403;
            res.end("Local application requests only");
            return;
          }
          let body = "";
          let size = 0;
          req.on("data", (chunk) => {
            size += chunk.length;
            if (size > 48 * 1024 * 1024) req.destroy();
            else body += chunk;
          });
          req.on("end", () => {
            const python = process.env.RESEARCH_V3_PYTHON || "python3";
            const child = spawn(
              python,
              [fileURLToPath(new URL("./python/bridge.py", import.meta.url))],
              { env: { ...process.env, MPLBACKEND: "Agg" } },
            );
            let output = "";
            let errors = "";
            let done = false;
            const timeout = setTimeout(
              () => {
                child.kill();
              },
              10 * 60 * 1000,
            );
            res.on("close", () => {
              if (!done) child.kill();
            });
            child.stdout.on("data", (data) => {
              output += data;
            });
            child.stderr.on("data", (data) => {
              errors = (errors + data).slice(-4000);
            });
            child.on("error", (error) => {
              done = true;
              clearTimeout(timeout);
              res.setHeader("Content-Type", "application/json");
              res.end(
                JSON.stringify({
                  ok: false,
                  error: `Python 无法启动：${error.message}`,
                }),
              );
            });
            child.on("close", () => {
              done = true;
              clearTimeout(timeout);
              if (res.writableEnded) return;
              res.setHeader("Content-Type", "application/json; charset=utf-8");
              res.end(
                output ||
                  JSON.stringify({
                    ok: false,
                    error: errors || "操作已取消或 Python 进程提前结束。",
                  }),
              );
            });
            child.stdin.end(body);
          });
        });
      },
    },
  ],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: { port: 1420, strictPort: true, host: "127.0.0.1" },
  clearScreen: false,
});
