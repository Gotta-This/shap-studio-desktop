# Windows x64 构建与验证

目标：Windows x64，内置 Python；交付便携压缩包和安装程序。Mac 的 `.app` 不能作为 Windows 可执行文件。

## GitHub Actions

仓库根目录保留 `.github/workflows/windows-build.yml`，应用源码放在 `desktop_app/`。

推送到 `main` 或在 Actions 中手动运行 **Build and verify Windows desktop app**。流程会：

1. 在 Windows runner 安装 Python 3.12 x64、固定版本依赖和安装程序编译器。
2. 执行数值兼容、界面参数读写、导出与重绘测试。
3. 构建 `SHAPStudio.exe`，将解释器、分析库和字体一起打包。
4. 直接运行打包后的 EXE，验证默认分析和颜色、字体、字号、线宽核对。
5. 在后台 Qt 窗口中操作完整界面：修改所有数据参数、六张图的独立样式、点击生成，通过文件对话框保存配置、单图与完整结果，并独立重算数据逐项比对。
6. 只有以上步骤全部通过，才上传正式 Windows 便携包和安装程序；验证报告、截图作为独立附件保留。

成功后在该次 Actions 运行的 Artifacts 下载：

- `SHAPStudio-Windows-x64`：包含便携压缩包、SHA256 校验文件、`SHAPStudio-Setup-Windows-x64.exe` 安装程序。
- `Windows-verification-evidence`：打包运行、界面修改、数据与样式比对的报告和截图。

便携版解压后运行 `SHAPStudio/SHAPStudio.exe`；整个目录必须保留，不能只复制 EXE。安装版运行 Setup EXE。

GitHub 仓库必须先创建并授权访问。本地浏览器登录不等于本工具已获得仓库写入或 Actions 权限。尚未成功执行 Actions 时，源码包和构建脚本不应标记为已验证的 Windows 成品。

## 在 Windows 本地构建

先安装 Python 3.12 x64（包含 pip，确保 `python` 命令可用），双击 `build_windows.cmd`。脚本会创建隔离的 `.venv-win`、安装依赖、构建并验证便携版。

如需安装程序，再安装 Inno Setup 后运行：

```powershell
./build_windows.ps1 -RequireInstaller
```

无需管理员权限即可安装应用到当前用户目录。当前构建流程没有附加代码签名证书。

## 后台界面验证说明

`--ui-verify` 使用打包 App 自己的 Qt 控件，发送鼠标/键盘/输入法事件，并操作文件对话框；不会直接给分析函数塞一份配置来冒充界面操作。

使用 `QT_QPA_PLATFORM=offscreen` 时，窗口在后台渲染，不控制使用者的桌面。报告中会明确记录 `runtime=bundled` 和 `qt_platform=offscreen`。截图是 App 自身渲染的窗口，不是用户屏幕截取。
