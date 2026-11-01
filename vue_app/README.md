# 科研数据工具集 · Vue V3

独立开发分支 `codex/vue3-v3-ui`，从 Qt v1.1.2 分出。界面依据 `design/shadcn-v3` 已确认的浅绿色 Penpot 稿实现，使用 Vue 3、TypeScript、真正的 shadcn-vue / Reka UI 组件、Tailwind CSS 4 和 Tauri 2。Qt 引擎继续复用，V3 安装包使用独立发布流程。

## 运行

需要 Node.js 22.12+，以及 Python 3.12。Tauri 开发还需要 Rust 与对应系统的原生构建工具。

```sh
cd vue_app
npm ci
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export RESEARCH_V3_PYTHON="$PWD/.venv/bin/python"
npm run dev
```

访问 `http://127.0.0.1:1420`。Windows 的 Python 路径为 `.venv/Scripts/python.exe`。浏览器通过本机 Vite 桥接调用 Python；开发服务仅监听 127.0.0.1，检查 Host / Origin，并拒绝跨站写入。`npm run preview` 仅展示静态构建，不带 Python 桥接，功能验收应使用 `dev` 或 Tauri。

开发服务默认使用 `vue_app/.v3-data`。正式应用的数据保存在用户隐藏目录，旧 V3 应用目录会自动保留到新位置。可以用 `RESEARCH_V3_PROFILE` 指向独立测试配置。前端不再提供 Qt 数据迁移入口。用户在设置中明确选择已有稿件工作空间后，读写与 Qt 相同的 `.manuscripts.sqlite3` 和实际目录；请关闭另一版本后再使用同一空间。

## 桌面运行与打包

```sh
# 开发：前端与 Python 源码均在本机；不会要求预先准备随包二进制
npm run desktop:dev

# 分发：先把 Python 与科学依赖打成当前系统的 sidecar
.venv/bin/python scripts/build-sidecar.py
python scripts/test-packaged-engine.py src-tauri/binaries/research-python-aarch64-apple-darwin
npm run desktop:build
```

打包时 Vue 编译为静态文件。安装后的 Tauri 应用通过 Rust 调用随包的 `research-python`，不启动 Node 服务，不要求用户另装 Node 或 Python。不同系统与 CPU 架构必须分别构建；Windows 随包文件带 `.exe`。`src-tauri/binaries` 的二进制不提交到 Git。当前 Mac 构建用于本地预览，没有开发者证书签名或 Apple 公证。

## 已接通的页面与操作

- 工作台：真实任务、待办与收件箱概览，科研工具快捷入口。
- 稿件总览：客户 / 状态 / 日期 / 未完成筛选，全文搜索、显示列、排序和分页。
- 任务详情：真实目录与改名，五类材料、文件搜索、预览、系统打开、分类、丢失后校验恢复，关联待办和操作记录。
- 新建 / 编辑：客户、名称、标签、状态、截止日期、备注及第一项待办，服务端复用 Qt 已验收的事务逻辑。
- 收件箱：接收、选择、归档；无冲突时从操作记录撤销归档。
- 待办：稿件与个人待办、优先级、日期、完成状态、编辑、软删除和撤销，返回关联稿件。
- 日期：shadcn-vue Calendar / Popover，中文月历、年月选择、手输校验、今天 / 明天 / 清除，Esc 与点击外部取消。
- 科研工具：类别抽样、均数标准差模拟、Word 汇总表识别及模拟 Excel、SHAP 数据 / 模型 / 图表参数和实际计算。各模块独立保留参数与结果。
- 设置：选择本机目录、显示并打开应用数据目录、V3 更新检查、对应系统安装包下载、SHA256 校验和打开安装包；检查失败可重试。启动自动检查，安装前等待当前计算完成。

浏览器可上传 32 MB 内的材料；桌面导入使用原生文件选择与文件路径。预览是只读的，DOCX 提取文字，图片与 PDF 内嵌展示，其他格式交由系统程序打开。任务、收件箱和图表均使用原 Python 引擎，不把设计稿里的示例状态当作保存结果。

## 验证

```sh
npm run build
.venv/bin/python -m unittest discover -s python -p 'test_*.py' -v
npm test
# 本机完整对照（需要已安装 PySide6 的 Python，以及无界面的 LibreOffice）
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/audit-qt-corpus.py
npm test
cargo check --manifest-path src-tauri/Cargo.toml
```

UI 验收默认使用无头浏览器，不通过 System Events、系统鼠标或键盘激活、控制用户桌面。原生窗口的鼠标验收应在独立虚拟机或另一台机器完成。

Playwright 启动独立的 1421 端口服务器和 `.v3-data/browser-tests` 数据；不会对当前 1420 预览中的工作空间运行测试。默认使用 Mac Chrome，可通过 `CHROME_PATH` 指定其他系统的 Chrome 可执行文件。

shadcn-vue 官方源码及 MIT 许可证保存在 `src/components/ui`，来源与原始哈希位于 `shadcn-sources.json`。`scripts/fetch-shadcn.mjs` 可重新获取官方组件；重新生成后应审查变更。

## 功能范围

科研工具第 3、4 项以当前 Qt 应用为功能依据，替换了旧 Penpot 设计中的简化流程：

- Word：五个页面（基础资料、表格匹配、文字匹配、全部字段以及来源、生成与导出）；导入前扫描原表与候选组别，可编辑识别草稿，确认组别后应用。例数默认 70，Word 例数和结局比例显式选择采用。支持无分组竖表、按原表分块编辑字段规则、正文独立编辑与冲突确认、配置保存恢复、完整 Excel 导出及后台计算取消。
- 模拟生图：四个页面（数据、模型与分类变量、样式、结果）；连续/分类变量独立表格与顺序、完整模型参数、公共样式与六类图独立继承、实际预览与已有模型重绘、结果表分页、图像放大保存和按内容选择复制/打包。数据或模型变化后，重绘要求重新完整分析。
- 运行中切换模块保留参数、进度和结果；原生关闭事件阻止中断计算。取消为协作式，当前引擎步骤完成后生效。

本轮已使用项目内 18 份 Word 完成 36 组 Qt/V3 配置与校验对照，并验证完整浏览器流程及打包引擎。详细覆盖、修复项与边界见 [Qt 对照检查记录](QA_QT_PARITY.md)。V3 采用与 Qt 类似的安装包更新方式：Windows 打开 NSIS 安装向导，Mac 解压后替换应用。不是静默热更新。个人分发包暂无商业签名或 Apple 公证。原生窗口与系统对话框未使用用户桌面进行点击测试。

## V3 发布

`.github/workflows/release-v3.yml` 在 V3 分支变更该文件时或手动触发。先构建前端、运行后端与无头浏览器测试，再在 Windows x64、Apple Silicon Mac 和 Intel Mac 分别打包 Python 引擎与 Tauri。Windows 静默安装到 CI 临时目录，再通过安装后的桌面主程序调用科学计算引擎；Mac 添加本机临时签名、验证完整性和 app 内引擎。全部通过才创建 Release、上传 Windows 安装版/便携版、两种 Mac 安装包及 SHA256SUMS.txt，再标记 latest。Qt 历史 Release 保留。

后续发布先同步修改 `package.json`、`package-lock.json`、`src-tauri/tauri.conf.json`、`src-tauri/Cargo.toml`、`src-tauri/Cargo.lock` 和 `python/releases.py` 的版本，更新发布说明后触发流程。已存在的版本拒绝覆盖，以免已下载的安装包校验变化。

GitHub 托管系统标签依据 [GitHub runner 文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job)；Windows 安装包内嵌 WebView2 离线安装程序，见 [Tauri Windows 安装文档](https://v2.tauri.app/distribute/windows-installer/)。

## V3.0.1 修订

V3.0.0 的桌面主程序错误地使用自身 Cargo feature 判断 Tauri 运行环境，发布时 CLI 开启的是依赖的 production feature，导致主程序尝试调用构建机器上的开发脚本。V3.0.1 改用 `tauri::is_dev()`，并在发布命令显式开启 production feature。原生返回的字符串错误统一转成 Error，界面可以显示真实原因并重试。

发布后测试现在运行的是 app 的 `research-studio-v3`（Windows 为 `.exe`），通过 `--bridge-request` 在不创建窗口的情况下调用与界面完全相同的 Rust → Python 函数。测试故意将开发 Python 指向不存在的路径，验证实际启用随包 Python、版本一致、中文待办以及数列、数值、Word、SHAP 四项后台任务。此检查可以发现“Python 引擎单独能用、桌面却未接通”的问题。

侧栏收起宽度不再被窄屏媒体规则覆盖；小于 700px 时自动紧凑导航。页面滚动由固定的应用容器管理，防止 WebKit 打开弹窗后切换视口宽度和媒体规则。搜索框回归使用传统滚动条并逐帧比较位置、宽度和内边距，覆盖 Chromium 与 WebKit。

V3.0.0 的桥接错误也影响应用内检查更新，升级至此修订版时请直接下载 Release 安装包替换。原有 V3 用户数据和已选择的工作空间保持兼容。

## 默认用户数据

正式 app 未指定测试配置时，Mac 使用 `~/.research-data-tools`；Windows 通过系统接口读取当前用户“文档”的真实位置（包括重定向位置），在其中创建 `.research-data-tools` 并设置隐藏属性。`profile` 保存个人待办、配置、导入会话、科学计算结果和更新缓存，`workspace` 为自动建立的默认稿件工作空间。用户另选的稿件目录会继续使用，应用数据始终独立于安装位置。设置显示数据目录并可直接打开，不再展示 Qt 数据迁移入口。

已有 V3 应用数据会一次性复制到此目录，保留原数据备份，迁移 SQLite 使用数据库备份接口；记录中指向原 V3 数据目录的内部路径也会更新。后续启动不会覆盖新数据。测试通过 `RESEARCH_V3_PROFILE` 或 `RESEARCH_V3_DATA_ROOT` 使用隔离目录，不写入真实用户目录。

## 个人工作台

工作台使用应用原图标和亲亲爱心欢迎语。提醒按本地时间切换：01:00–07:00 提醒睡觉，07:00–09:00、11:30–13:30、17:30–19:30 提醒吃饭，其余白天工作时段加油、晚间提醒休息；每 30 秒更新，并在返回工作台和恢复应用时刷新。

天气默认河南省焦作市（通过官方地名查询核对坐标），使用 [Open-Meteo 当前天气接口](https://open-meteo.com/en/docs)，显示天气、°C 气温和更新时间，可切换城市。15 分钟缓存；断网显示有标识的上次数据，没有缓存时明确显示不可用。配置与缓存保存在用户数据目录。

## 实际原生界面验收

`python scripts/test-native-ui.py <app内的research-studio-v3可执行文件> <隔离输出目录>` 启动实际 app 的隐藏、无焦点、非持久化 WebKit 窗口。测试通道只在显式 `--ui-review` 参数下启用，使用独立数据根目录，不复制真实用户资料，不发送系统鼠标和键盘事件，也不读取其他窗口。它通过真实界面控件和生产 IPC 完成首页、搜索、窄侧栏、设置、任务/材料/预览、待办、收件箱、数列、数值、Word 导入及 Excel 生成、SHAP 参数与实际出图；PNG 由 WKWebView 自身生成，输出 JSON 记录步骤与限制。Mac 发布流程会运行此检查并上传截图证据。

原生系统文件选择/保存对话框、打开 Finder 等操作没有通过系统输入自动点击；Word 和材料上传使用真实 File 对象送入同一界面处理流程，系统导出写入另有桌面桥接测试。隐藏窗口的测试控制使用原生心跳调度，避免 WebKit 后台计时器休眠影响测试。
