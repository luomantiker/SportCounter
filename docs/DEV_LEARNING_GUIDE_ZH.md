# SportsCounter 开发过程学习手册

本手册面向“会写 Python 脚本，但第一次做桌面应用发布”的开发者。

目标：从脚本使用者进阶为界面开发者与发布者。

---

## 1. 全流程总览
从脚本到可发布程序，建议分 5 个阶段：
1. 业务逻辑脚本化
2. GUI 事件化
3. 本地数据持久化
4. 可执行文件打包
5. 安装包发布

对应本项目文件：
- 源码：`src/windows_counter.py`
- exe 打包：`scripts/build_windows_exe.bat`
- 安装包脚本：`installer/SportsCounter.iss`
- 安装包构建：`scripts/build_windows_installer.bat`

---

## 2. 阶段一：脚本思维到状态机思维

脚本特点：一次执行、顺序结束。
GUI 应用特点：常驻、事件驱动、状态持续变化。

在本项目中，`CounterApp` 就是状态机容器：
- 用户状态：`current_user`
- 配置状态：`current_config_id`、`threshold_configs`
- 计数状态：`count`
- 运行状态：`auto_count_enabled`、`auto_job_id`

关键点：
- 所有按钮操作都应变成“状态变化函数”。
- 界面更新通过统一刷新函数（如 `_update_display` / `_refresh_count_color`）。

---

## 3. 阶段二：Tkinter 机制与关键组件

### 3.1 关键机制
1. 事件循环：`root.mainloop()`
2. 事件绑定：`bind(...)`
3. 延时任务：`after(...)` / `after_cancel(...)`
4. 弹窗：`Toplevel + transient + grab_set`

### 3.2 本项目关键组件
1. `Label`：显示计数、状态文字
2. `Button`：触发行为（+1、清零、登录、配置）
3. `Spinbox`：自动计数间隔
4. `ttk.Treeview`：门限与用户配置列表
5. `Text + Scrollbar`：多行说明编辑

### 3.3 典型示例：自动计数定时器
核心过程：
1. 点击“启动计数”
2. 校验间隔参数
3. `after(interval_ms, _auto_tick)`
4. `_auto_tick` 内 +1 后继续安排下一次
5. 停止时 `after_cancel`

这就是 GUI 的“非阻塞循环任务”典型写法。

---

## 4. 阶段三：数据层设计（INI + SQLite）

### 4.1 为什么混合存储
- INI：轻量、可读、适合全局偏好
- SQLite：结构化关系数据（用户、多配置、登录记录）

### 4.2 表结构思路
1. `users`：账号主表
2. `user_configs`：每用户多配置
3. `login_users`：登录历史

### 4.3 典型机制：默认配置与最近配置
登录后优先加载：
1. 用户上次使用配置
2. 默认配置
3. 若无配置则自动创建 `config_default`

这保证了“用户首次可用”和“再次登录无缝恢复”。

### 4.4 路径机制（部署关键）
数据不应写到程序目录，而写到用户目录：
- Windows：`%APPDATA%\SportsCounter`

这样可避免：
- Program Files 写权限问题
- onefile 临时目录写入丢失

---

## 5. 阶段四：打包为 exe

### 5.1 PyInstaller 原理
PyInstaller 会把 Python 解释器、依赖、脚本打包成分发产物。

常见参数：
- `--windowed`：GUI 程序不弹黑窗
- `--onefile`：单文件分发
- `--clean`：清理历史缓存

### 5.2 本项目命令入口
- `scripts/build_windows_exe.bat`

构建输出：
- `dist/SportsCounter.exe`

### 5.3 典型问题
1. 缺模块：检查 pip 安装
2. 启动无响应：查看是否异常被吞（可先去掉 `--windowed` 调试）
3. 数据不保存：确认写到了 `%APPDATA%` 而非程序目录

---

## 6. 阶段五：Installer 发布

### 6.1 为什么要安装包
- 统一安装目录
- 快捷方式/卸载项完整
- 家庭用户体验更接近标准软件

### 6.2 Inno Setup 关键段落
1. `[Setup]`：版本、目录、权限
2. `[Files]`：把 exe 放入安装目录
3. `[Icons]`：开始菜单/桌面快捷方式
4. `[Run]`：安装完成后启动

### 6.3 管理员安装策略
当前脚本采用：
- `PrivilegesRequired=admin`
- 安装时触发 UAC 请求
- 安装目录为 Program Files

运行数据仍在 `%APPDATA%`，可保证升级不丢用户信息。

---

## 7. 典型工程架构（本项目最终版）

- `src/`：应用源码
- `scripts/`：构建与运行脚本
- `installer/`：安装器脚本
- `docs/`：用户与开发文档
- `dist/ build/ release/`：构建产物（构建时生成）

这套结构便于：
- 开发与发布职责分离
- 新成员快速定位文件
- CI/CD 自动化接入

---

## 8. 进阶建议

1. 密码哈希升级为 `bcrypt/argon2`
2. 增加日志与错误上报
3. 增加自动更新机制
4. 引入单元测试（数据层优先）
5. 把 GUI 层与数据层进一步解耦（MVC/MVVM）

---

## 9. 实战复盘

从这次案例你已经掌握：
1. 如何把“脚本功能”拆到 GUI 状态和事件
2. 如何用 SQLite 支撑多用户多配置
3. 如何处理桌面应用部署路径与权限
4. 如何从 exe 走到 installer 级别发布

你现在已经不只是脚本使用者，而是能交付桌面应用的开发者。
