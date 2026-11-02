# 科研数据工具集

当前主线为 **Vue 3 + shadcn-vue + Tauri 2 + Python** 的 V3 版本，提供自定义类别数列、均数/标准差模拟数据、Word 转 Excel、模拟数据生图，以及稿件工作空间和待办。

## 分支与目录

- [`master`](https://github.com/Gotta-This/shap-studio-desktop/tree/master)：Vue V3 开发主线，应用入口为 `vue_app/`。
- [`master-qt`](https://github.com/Gotta-This/shap-studio-desktop/tree/master-qt)：保留 Qt v1.1.2 源码及历史，用于查阅和维护旧版本。
- 原 `main` 和 `codex/vue3-v3-ui` 分支在迁移后删除；其提交历史仍由上述两个分支保留。

V3 仍复用 `desktop_app/clinical_studio/` 中的 Python 科学计算、Word 解析和数据存储模块；主线保留这个目录是为了让 V3 自包含运行。Qt 旧应用以 `master-qt` 为准。

## 本地工作空间

```sh
git clone --branch master https://github.com/Gotta-This/shap-studio-desktop.git
cd shap-studio-desktop
git branch -vv
```

本地 `master` 跟踪 `origin/master`。需要查看旧版时可读取 `origin/master-qt`，或另外创建工作树；不在当前工作区覆盖未提交的文件。

运行、依赖安装、四个工具和用户数据位置见 [Vue V3 使用说明](vue_app/README.md)。当前功能验收记录见 [V3 当前验收](vue_app/QA_CURRENT_VUE.md)。

## 验证与发布

推送源码只运行验证，不生成安装包或发布 Release。用户完成本地试用并确认后，才在 `master` 手动运行 `Build test and release Vue V3`，通过各平台检查后发布。历史 Release 保留，已有版本不可覆盖。
