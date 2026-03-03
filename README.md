# SportsCounter 工程目录

## 目录结构

- `src/`：应用源码
  - `windows_counter.py`
- `scripts/`：运行/构建脚本
  - `run_counter.bat`
  - `build_windows_exe.bat`
  - `build_windows_installer.bat`
- `installer/`：安装包配置
  - `SportsCounter.iss`
- `docs/`：文档
  - `USER_MANUAL_ZH.md`（用户使用手册）
  - `DEV_LEARNING_GUIDE_ZH.md`（开发过程学习手册）
- `dist/`、`build/`、`release/`：构建输出目录（构建时生成）

## 快速开始（Windows）

1. 运行源码：双击 `scripts\run_counter.bat`
2. 打包 EXE：双击 `scripts\build_windows_exe.bat`
3. 打包安装器：双击 `scripts\build_windows_installer.bat`

安装器语言规则：
- 检测到 `ChineseSimplified.isl` 时，自动使用中文安装界面
- 未检测到时，自动回退为默认英文界面

## 数据目录

运行数据保存在：
- `%APPDATA%\SportsCounter`

包含：
- `counter_app.ini`
- `counter_app.db`

安装升级不会清空该目录。
