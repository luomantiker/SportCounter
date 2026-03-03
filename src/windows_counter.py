import configparser
import hashlib
import json
import os
import re
import sqlite3
import sys
import tkinter as tk
from datetime import datetime
from tkinter import colorchooser, messagebox, ttk
from typing import Dict, List, Optional


def get_app_data_dir() -> str:
    app_name = "SportsCounter"
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if not base:
            base = os.path.expanduser("~")
        path = os.path.join(base, app_name)
    else:
        path = os.path.join(os.path.expanduser("~"), f".{app_name.lower()}")
    os.makedirs(path, exist_ok=True)
    return path


class AppStorage:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        self.ini_path = os.path.join(base_dir, "counter_app.ini")
        self.db_path = os.path.join(base_dir, "counter_app.db")
        self.config = configparser.ConfigParser()
        self.conn: Optional[sqlite3.Connection] = None

        self._load_ini()
        self._init_db()
        self._ensure_admin_user()

    def _load_ini(self) -> None:
        if os.path.exists(self.ini_path):
            self.config.read(self.ini_path, encoding="utf-8")

        if "system" not in self.config:
            self.config["system"] = {}
        if "login" not in self.config:
            self.config["login"] = {}

        self.config["system"].setdefault("default_inc_hotkey", "space")
        self.config["system"].setdefault("default_reset_hotkey", "r")
        self.config["system"].setdefault("default_auto_hotkey", "")
        self.config["system"].setdefault("default_auto_interval", "1.0")

        self.config["login"].setdefault("last_user", "")
        self.config["login"].setdefault("remember_password", "0")
        self.config["login"].setdefault("saved_password", "")

        self._save_ini()

    def _save_ini(self) -> None:
        with open(self.ini_path, "w", encoding="utf-8") as f:
            self.config.write(f)

    def _init_db(self) -> None:
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_config_id INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                settings_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, name),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS login_users (
                username TEXT PRIMARY KEY,
                last_login TEXT NOT NULL,
                login_count INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_admin_user(self) -> None:
        user = self.get_user_by_username("admin")
        if user:
            return

        self.create_user("admin", "admin", "系统默认管理员", is_admin=1)

    def create_user(self, username: str, password: str, description: str, is_admin: int = 0) -> int:
        if not self.conn:
            raise RuntimeError("数据库未初始化")

        now = self._now()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password_hash, description, is_admin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, self._hash_password(password), description, is_admin, now, now),
        )
        user_id = cur.lastrowid
        self.conn.commit()
        return int(user_id)

    def update_user_profile(self, user_id: int, description: str, new_password: str = "") -> None:
        if not self.conn:
            raise RuntimeError("数据库未初始化")

        now = self._now()
        cur = self.conn.cursor()
        if new_password:
            cur.execute(
                """
                UPDATE users
                SET description = ?, password_hash = ?, updated_at = ?
                WHERE id = ?
                """,
                (description, self._hash_password(new_password), now, user_id),
            )
        else:
            cur.execute(
                """
                UPDATE users
                SET description = ?, updated_at = ?
                WHERE id = ?
                """,
                (description, now, user_id),
            )
        self.conn.commit()

    def admin_update_user(self, user_id: int, description: str, new_password: str = "") -> None:
        self.update_user_profile(user_id, description, new_password)

    def admin_delete_user(self, user_id: int) -> None:
        if not self.conn:
            raise RuntimeError("数据库未初始化")

        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("用户不存在")
        if str(user["username"]) == "admin":
            raise ValueError("admin 用户不能删除")

        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_configs WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM login_users WHERE username = ?", (str(user["username"]),))
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        self.conn.commit()

    def get_user_by_username(self, username: str) -> Optional[sqlite3.Row]:
        if not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cur.fetchone()

    def get_user_by_id(self, user_id: int) -> Optional[sqlite3.Row]:
        if not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return cur.fetchone()

    def authenticate(self, username: str, password: str) -> Optional[sqlite3.Row]:
        user = self.get_user_by_username(username)
        if not user:
            return None
        if user["password_hash"] != self._hash_password(password):
            return None
        return user

    def list_users(self) -> List[sqlite3.Row]:
        if not self.conn:
            return []
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE")
        return cur.fetchall()

    def record_success_login(self, username: str) -> None:
        if not self.conn:
            return

        now = self._now()
        cur = self.conn.cursor()
        cur.execute("SELECT username, login_count FROM login_users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE login_users SET last_login = ?, login_count = ? WHERE username = ?",
                (now, int(row["login_count"]) + 1, username),
            )
        else:
            cur.execute(
                "INSERT INTO login_users (username, last_login, login_count) VALUES (?, ?, 1)",
                (username, now),
            )
        self.conn.commit()

    def list_login_users(self) -> List[sqlite3.Row]:
        if not self.conn:
            return []
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM login_users ORDER BY last_login DESC")
        return cur.fetchall()

    def has_login_history(self, username: str) -> bool:
        if not self.conn:
            return False
        cur = self.conn.cursor()
        cur.execute("SELECT username FROM login_users WHERE username = ?", (username,))
        return cur.fetchone() is not None

    def create_user_default_config(self, user_id: int, settings: Dict[str, object]) -> int:
        return self.create_user_config(
            user_id=user_id,
            name="config_default",
            description="默认配置",
            settings=settings,
            is_default=True,
        )

    def create_user_config(
        self,
        user_id: int,
        name: str,
        description: str,
        settings: Dict[str, object],
        is_default: bool = False,
    ) -> int:
        if not self.conn:
            raise RuntimeError("数据库未初始化")

        now = self._now()
        cur = self.conn.cursor()

        if is_default:
            cur.execute("UPDATE user_configs SET is_default = 0 WHERE user_id = ?", (user_id,))

        cur.execute(
            """
            INSERT INTO user_configs (user_id, name, description, is_default, settings_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, name, description, 1 if is_default else 0, json.dumps(settings, ensure_ascii=False), now, now),
        )
        config_id = cur.lastrowid

        if is_default:
            cur.execute("UPDATE users SET last_config_id = ? WHERE id = ?", (config_id, user_id))

        self.conn.commit()
        return int(config_id)

    def list_user_configs(self, user_id: int) -> List[sqlite3.Row]:
        if not self.conn:
            return []
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT * FROM user_configs
            WHERE user_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (user_id,),
        )
        return cur.fetchall()

    def get_user_config(self, config_id: int) -> Optional[sqlite3.Row]:
        if not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_configs WHERE id = ?", (config_id,))
        return cur.fetchone()

    def get_user_config_by_name(self, user_id: int, name: str) -> Optional[sqlite3.Row]:
        if not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_configs WHERE user_id = ? AND name = ?", (user_id, name))
        return cur.fetchone()

    def update_user_config_meta(self, config_id: int, name: str, description: str) -> None:
        if not self.conn:
            raise RuntimeError("数据库未初始化")
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE user_configs SET name = ?, description = ?, updated_at = ? WHERE id = ?",
            (name, description, self._now(), config_id),
        )
        self.conn.commit()

    def update_user_config_settings(self, config_id: int, settings: Dict[str, object]) -> None:
        if not self.conn:
            raise RuntimeError("数据库未初始化")
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE user_configs SET settings_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(settings, ensure_ascii=False), self._now(), config_id),
        )
        self.conn.commit()

    def set_default_config(self, user_id: int, config_id: int) -> None:
        if not self.conn:
            raise RuntimeError("数据库未初始化")
        cur = self.conn.cursor()
        cur.execute("UPDATE user_configs SET is_default = 0 WHERE user_id = ?", (user_id,))
        cur.execute("UPDATE user_configs SET is_default = 1 WHERE id = ? AND user_id = ?", (config_id, user_id))
        self.conn.commit()

    def delete_user_config(self, user_id: int, config_id: int) -> None:
        if not self.conn:
            raise RuntimeError("数据库未初始化")

        cfg = self.get_user_config(config_id)
        if not cfg or int(cfg["user_id"]) != user_id:
            raise ValueError("配置不存在")

        all_configs = self.list_user_configs(user_id)
        if len(all_configs) <= 1:
            raise ValueError("至少保留一个配置")

        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_configs WHERE id = ?", (config_id,))

        last_cfg_user = self.get_user_by_id(user_id)
        if last_cfg_user and last_cfg_user["last_config_id"] == config_id:
            cur.execute("UPDATE users SET last_config_id = NULL WHERE id = ?", (user_id,))

        self.conn.commit()

    def set_user_last_config(self, user_id: int, config_id: int) -> None:
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("UPDATE users SET last_config_id = ? WHERE id = ?", (config_id, user_id))
        self.conn.commit()

    def get_default_or_last_config(self, user_id: int) -> Optional[sqlite3.Row]:
        user = self.get_user_by_id(user_id)
        if not user:
            return None

        if user["last_config_id"]:
            cfg = self.get_user_config(int(user["last_config_id"]))
            if cfg and int(cfg["user_id"]) == user_id:
                return cfg

        if not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM user_configs WHERE user_id = ? AND is_default = 1 ORDER BY id ASC LIMIT 1",
            (user_id,),
        )
        cfg = cur.fetchone()
        if cfg:
            return cfg

        cur.execute("SELECT * FROM user_configs WHERE user_id = ? ORDER BY id ASC LIMIT 1", (user_id,))
        return cur.fetchone()

    def parse_config_settings(self, row: sqlite3.Row) -> Dict[str, object]:
        try:
            return json.loads(row["settings_json"])
        except Exception:
            return {}

    def get_next_config_name(self, user_id: int) -> str:
        configs = self.list_user_configs(user_id)
        max_idx = 0
        pattern = re.compile(r"^config_(\d+)$")
        for cfg in configs:
            name = str(cfg["name"])
            if name == "config_default":
                max_idx = max(max_idx, 0)
                continue
            m = pattern.match(name)
            if m:
                max_idx = max(max_idx, int(m.group(1)))
        return f"config_{max_idx + 1}"

    def get_saved_login_info(self) -> Dict[str, str]:
        return {
            "last_user": self.config["login"].get("last_user", ""),
            "remember_password": self.config["login"].get("remember_password", "0"),
            "saved_password": self.config["login"].get("saved_password", ""),
        }

    def save_login_info(self, username: str, remember_password: bool, password: str) -> None:
        self.config["login"]["last_user"] = username
        self.config["login"]["remember_password"] = "1" if remember_password else "0"
        self.config["login"]["saved_password"] = password if remember_password else ""
        self._save_ini()

    def save_system_defaults(self, settings: Dict[str, object]) -> None:
        self.config["system"]["default_inc_hotkey"] = str(settings.get("inc_hotkey", "space"))
        self.config["system"]["default_reset_hotkey"] = str(settings.get("reset_hotkey", "r"))
        self.config["system"]["default_auto_hotkey"] = str(settings.get("auto_toggle_hotkey", ""))
        self.config["system"]["default_auto_interval"] = str(settings.get("auto_interval", 1.0))
        self._save_ini()

    def get_system_defaults(self) -> Dict[str, object]:
        system = self.config["system"]
        try:
            interval = float(system.get("default_auto_interval", "1.0"))
        except ValueError:
            interval = 1.0
        return {
            "inc_hotkey": system.get("default_inc_hotkey", "space"),
            "reset_hotkey": system.get("default_reset_hotkey", "r"),
            "auto_toggle_hotkey": system.get("default_auto_hotkey", ""),
            "auto_interval": interval,
            "threshold_configs": [
                {"name": "预警", "threshold": 30, "color": "#ff8c00", "desc": "达到后变橙色"},
                {"name": "高强度", "threshold": 60, "color": "#cc2b2b", "desc": "达到后变红色"},
            ],
        }


class CounterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("运动计数器")
        self.root.geometry("1000x700")
        self.root.resizable(False, False)

        self.base_dir = get_app_data_dir()
        self.storage = AppStorage(self.base_dir)

        self.current_user: Optional[sqlite3.Row] = None
        self.current_config_id: Optional[int] = None

        self.count = 0
        self.normal_color = "#1f7a1f"

        self.threshold_configs: List[Dict[str, object]] = []
        self.inc_hotkey = "space"
        self.reset_hotkey = "r"
        self.auto_toggle_hotkey = ""
        self.active_bindings: Dict[str, str] = {}

        self.auto_interval_var = tk.DoubleVar(value=1.0)
        self.auto_count_enabled = False
        self.auto_job_id = None

        self._init_styles()
        self._build_ui()
        self._fit_window_height()
        self._set_controls_enabled(False)
        self._update_login_ui()

        self.root.after(50, self._try_auto_login_or_prompt)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_styles(self) -> None:
        self.root.configure(bg="#eef2f7")
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=24, font=("Microsoft YaHei", 9))
        style.configure("Treeview.Heading", font=("Microsoft YaHei", 9, "bold"))

    def _build_ui(self) -> None:
        frame = tk.Frame(self.root, padx=12, pady=12, bg="#eef2f7")
        frame.pack(fill="both", expand=True)

        top_bar = tk.Frame(frame, bg="#eef2f7")
        top_bar.pack(fill="x", pady=(0, 10))

        self.user_status_label = tk.Label(
            top_bar, text="当前用户: 未登录", font=("Microsoft YaHei", 10, "bold"), bg="#eef2f7"
        )
        self.user_status_label.pack(side="left")

        button_box = tk.Frame(top_bar, bg="#eef2f7")
        button_box.pack(side="right")
        self.login_toggle_button = tk.Button(button_box, text="登录", width=9, command=self._on_login_toggle)
        self.login_toggle_button.pack(side="left", padx=4)
        self.profile_button = tk.Button(button_box, text="我的信息", width=9, command=self._open_profile_dialog)
        self.profile_button.pack(side="left", padx=4)
        self.user_admin_button = tk.Button(button_box, text="用户管理", width=9, command=self._open_user_admin_dialog)
        self.user_admin_button.pack(side="left", padx=4)
        self.config_manager_button = tk.Button(button_box, text="配置管理", width=9, command=self._open_config_manager)
        self.config_manager_button.pack(side="left", padx=4)

        tk.Label(frame, text="运动次数", font=("Microsoft YaHei", 18, "bold"), bg="#eef2f7").pack(pady=(2, 8))

        self.count_label = tk.Label(frame, text="0", font=("Consolas", 50, "bold"), fg=self.normal_color, bg="#eef2f7")
        self.count_label.pack(pady=(0, 8))

        self.current_config_label = tk.Label(
            frame, text="当前配置: -", font=("Microsoft YaHei", 10), fg="#404040", bg="#eef2f7"
        )
        self.current_config_label.pack(pady=(0, 10))

        self.button_row = tk.Frame(frame, bg="#eef2f7")
        self.button_row.pack(pady=(0, 12))
        self.btn_inc = tk.Button(self.button_row, text="+1", width=13, command=self.increment)
        self.btn_inc.pack(side="left", padx=6)
        self.btn_reset = tk.Button(self.button_row, text="清零", width=13, command=self.reset)
        self.btn_reset.pack(side="left", padx=6)

        self.hint = tk.Label(frame, text="", font=("Microsoft YaHei", 9), fg="#555555", bg="#eef2f7")
        self.hint.pack(pady=(0, 10))

        config_frame = tk.LabelFrame(
            frame, text="配置区域", padx=10, pady=10, font=("Microsoft YaHei", 10), bd=2, relief="groove", bg="#f7f9fc"
        )
        config_frame.pack(fill="both", expand=True)

        top_row = tk.Frame(config_frame, bg="#f7f9fc")
        top_row.pack(fill="x", pady=(0, 10))

        hotkey_block = tk.LabelFrame(
            top_row,
            text="热键配置",
            padx=10,
            pady=10,
            font=("Microsoft YaHei", 10),
            bd=2,
            relief="groove",
            bg="#ffffff",
        )
        hotkey_block.pack(side="left", fill="x", expand=True, padx=(0, 10))

        tk.Label(hotkey_block, text="当前热键:", font=("Microsoft YaHei", 10), bg="#ffffff").pack(anchor="w")
        self.hotkey_summary_label = tk.Label(
            hotkey_block, text="", font=("Consolas", 10), fg="#333333", justify="left", anchor="w", bg="#ffffff"
        )
        self.hotkey_summary_label.pack(anchor="w", pady=(3, 10))
        self.hotkey_edit_button = tk.Button(hotkey_block, text="配置热键(弹窗)", width=18, command=self._open_hotkey_dialog)
        self.hotkey_edit_button.pack(anchor="w")

        auto_block = tk.LabelFrame(
            top_row,
            text="自动计数配置",
            padx=10,
            pady=10,
            font=("Microsoft YaHei", 10),
            bd=2,
            relief="groove",
            bg="#ffffff",
            width=210,
        )
        auto_block.pack(side="left", fill="y")
        auto_block.pack_propagate(False)

        interval_row = tk.Frame(auto_block, bg="#ffffff")
        interval_row.pack(anchor="w", pady=(0, 8))
        tk.Label(interval_row, text="计数间隔:", font=("Microsoft YaHei", 10), bg="#ffffff").pack(side="left")
        self.auto_interval_spinbox = tk.Spinbox(
            interval_row,
            from_=0.5,
            to=3600.0,
            increment=0.5,
            format="%.1f",
            width=7,
            textvariable=self.auto_interval_var,
            justify="center",
            command=self._on_auto_interval_changed,
        )
        self.auto_interval_spinbox.pack(side="left", padx=(6, 4))
        tk.Label(interval_row, text="秒", font=("Microsoft YaHei", 10), bg="#ffffff").pack(side="left")
        self.auto_interval_spinbox.bind("<FocusOut>", lambda _e: self._on_auto_interval_changed())

        self.auto_status_label = tk.Label(
            auto_block, text="状态: 已停止", font=("Microsoft YaHei", 10), fg="#555555", bg="#ffffff"
        )
        self.auto_status_label.pack(anchor="w", pady=(4, 8))

        self.auto_toggle_button = tk.Button(auto_block, text="启动计数", width=12, command=self._toggle_auto_count)
        self.auto_toggle_button.pack(anchor="w")

        threshold_block = tk.LabelFrame(
            config_frame,
            text="门限颜色配置",
            padx=10,
            pady=10,
            font=("Microsoft YaHei", 10),
            bd=2,
            relief="groove",
            bg="#ffffff",
        )
        threshold_block.pack(fill="both", expand=True)

        toolbar = tk.Frame(threshold_block, bg="#ffffff")
        toolbar.pack(fill="x", pady=(0, 8))
        self.threshold_add_button = tk.Button(toolbar, text="新增一项配置", width=14, command=self._add_threshold_config)
        self.threshold_add_button.pack(side="left")
        self.threshold_edit_selected_button = tk.Button(
            toolbar, text="编辑选中项", width=12, command=self._edit_selected_threshold_config
        )
        self.threshold_edit_selected_button.pack(side="left", padx=(8, 0))

        tree_wrap = tk.Frame(threshold_block, bd=1, relief="solid", bg="#ffffff", height=120)
        tree_wrap.pack(fill="both", expand=True)
        tree_wrap.pack_propagate(False)

        tree_cols = ("idx", "name", "threshold", "color", "desc", "op")
        self.threshold_tree = ttk.Treeview(tree_wrap, columns=tree_cols, show="headings", height=9)
        self.threshold_tree.heading("idx", text="编号")
        self.threshold_tree.heading("name", text="名称")
        self.threshold_tree.heading("threshold", text="门限值")
        self.threshold_tree.heading("color", text="字体颜色")
        self.threshold_tree.heading("desc", text="说明")
        self.threshold_tree.heading("op", text="操作")
        self.threshold_tree.column("idx", width=52, anchor="center")
        self.threshold_tree.column("name", width=130, anchor="w")
        self.threshold_tree.column("threshold", width=86, anchor="center")
        self.threshold_tree.column("color", width=105, anchor="center")
        self.threshold_tree.column("desc", width=320, anchor="w")
        self.threshold_tree.column("op", width=70, anchor="center")

        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.threshold_tree.yview)
        self.threshold_tree.configure(yscrollcommand=tree_scroll.set)
        self.threshold_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.threshold_tree.bind("<Double-1>", lambda _e: self._edit_selected_threshold_config())

    def _fit_window_height(self) -> None:
        self.root.update_idletasks()
        need_h = self.root.winfo_reqheight() + 10
        self.root.geometry(f"1000x{need_h}")


    def _set_controls_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        for widget in [
            self.btn_inc,
            self.btn_reset,
            self.hotkey_edit_button,
            self.threshold_add_button,
            self.threshold_edit_selected_button,
            self.auto_interval_spinbox,
            self.auto_toggle_button,
            self.config_manager_button,
            self.profile_button,
        ]:
            widget.config(state=state)
        self.threshold_tree.configure(selectmode="browse" if enabled else "none")

    def _update_login_ui(self) -> None:
        if not self.current_user:
            self.user_status_label.config(text="当前用户: 未登录")
            self.login_toggle_button.config(text="登录")
            self.user_admin_button.pack_forget()
            self.current_config_label.config(text="当前配置: -")
            return

        username = str(self.current_user["username"])
        self.user_status_label.config(text=f"当前用户: {username}")
        self.login_toggle_button.config(text="登出")

        if int(self.current_user["is_admin"]) == 1:
            if not self.user_admin_button.winfo_manager():
                self.user_admin_button.pack(side="left", padx=4)
            self.user_admin_button.config(state=tk.NORMAL)
        else:
            self.user_admin_button.pack_forget()

    def _on_login_toggle(self) -> None:
        if self.current_user:
            self._logout_user()
        else:
            self._open_login_dialog(force=True)

    def _try_auto_login_or_prompt(self) -> None:
        info = self.storage.get_saved_login_info()
        username = info.get("last_user", "")
        remember = info.get("remember_password", "0") == "1"
        password = info.get("saved_password", "")

        if username and remember and password:
            user = self.storage.authenticate(username, password)
            if user:
                self._on_login_success(user, save_login=True, remember_password=True, password=password)
                return

        self._open_login_dialog(force=True)

    def _open_login_dialog(self, force: bool = False) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("用户登录")
        dialog.geometry("440x280")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        login_users = self.storage.list_login_users()
        all_users = self.storage.list_users()

        options: List[str] = []
        seen = set()
        for row in login_users:
            name = str(row["username"])
            if name not in seen:
                options.append(name)
                seen.add(name)
        for row in all_users:
            name = str(row["username"])
            if name not in seen:
                options.append(name)
                seen.add(name)

        info = self.storage.get_saved_login_info()

        username_var = tk.StringVar(value=info.get("last_user", "") or (options[0] if options else ""))
        password_var = tk.StringVar(value=info.get("saved_password", "") if info.get("remember_password", "0") == "1" else "")
        remember_var = tk.IntVar(value=1 if info.get("remember_password", "0") == "1" else 0)

        tk.Label(dialog, text="请选择或输入用户名", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=20, pady=(16, 4))
        username_combo = ttk.Combobox(dialog, textvariable=username_var, values=options, width=36)
        username_combo.pack(anchor="w", padx=20)

        tk.Label(dialog, text="密码", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=20, pady=(10, 4))
        password_entry = tk.Entry(dialog, textvariable=password_var, show="*", width=39)
        password_entry.pack(anchor="w", padx=20)

        tk.Checkbutton(dialog, text="保存密码（下次快速登录）", variable=remember_var).pack(anchor="w", padx=20, pady=(10, 4))

        tip_label = tk.Label(dialog, text="", fg="#cc2b2b", font=("Microsoft YaHei", 9))
        tip_label.pack(anchor="w", padx=20, pady=(2, 4))

        def on_user_change(_event=None) -> None:
            selected = username_var.get().strip()
            saved = self.storage.get_saved_login_info()
            if selected and selected == saved.get("last_user", "") and saved.get("remember_password", "0") == "1":
                password_var.set(saved.get("saved_password", ""))
            else:
                if not password_var.get():
                    password_var.set("")

        username_combo.bind("<<ComboboxSelected>>", on_user_change)

        footer = tk.Frame(dialog)
        footer.pack(pady=(10, 0))

        def do_login() -> None:
            username = username_var.get().strip()
            password = password_var.get()
            if not username or not password:
                messagebox.showerror("登录失败", "用户名和密码不能为空", parent=dialog)
                return

            user = self.storage.authenticate(username, password)
            if not user:
                if self.storage.has_login_history(username):
                    tip_label.config(text="登录失败：密码可能已变更，请重新输入密码")
                else:
                    tip_label.config(text="登录失败：用户名或密码错误")
                return

            self._on_login_success(
                user=user,
                save_login=True,
                remember_password=bool(remember_var.get()),
                password=password,
            )
            dialog.destroy()

        tk.Button(footer, text="登录", width=12, command=do_login).pack(side="left", padx=6)

        def do_cancel() -> None:
            if force and not self.current_user:
                # 强制登录场景下，取消就退出程序。
                self._on_close()
                return
            dialog.destroy()

        tk.Button(footer, text="取消", width=12, command=do_cancel).pack(side="left", padx=6)

        password_entry.focus_set()
        dialog.wait_window()

    def _on_login_success(self, user: sqlite3.Row, save_login: bool, remember_password: bool, password: str) -> None:
        self.current_user = user
        self.storage.record_success_login(str(user["username"]))

        if save_login:
            self.storage.save_login_info(str(user["username"]), remember_password, password)

        self._ensure_user_has_default_config()
        self._load_user_startup_config()

        self._set_controls_enabled(True)
        self._update_login_ui()

    def _logout_user(self) -> None:
        self._stop_auto_count()

        self.current_user = None
        self.current_config_id = None
        self.count = 0
        self.count_label.config(text="0", fg=self.normal_color)
        self.threshold_configs = []

        self._clear_all_hotkeys()
        self.hint.config(text="")
        self.hotkey_summary_label.config(text="")
        self._refresh_threshold_table()

        self._set_controls_enabled(False)
        self._update_login_ui()

    def _ensure_user_has_default_config(self) -> None:
        if not self.current_user:
            return
        user_id = int(self.current_user["id"])
        configs = self.storage.list_user_configs(user_id)
        if configs:
            return

        default_settings = self.storage.get_system_defaults()
        self.storage.create_user_default_config(user_id, default_settings)

    def _load_user_startup_config(self) -> None:
        if not self.current_user:
            return

        user_id = int(self.current_user["id"])
        cfg = self.storage.get_default_or_last_config(user_id)
        if not cfg:
            return

        settings = self.storage.parse_config_settings(cfg)
        self._apply_settings(settings)

        self.current_config_id = int(cfg["id"])
        self.storage.set_user_last_config(user_id, self.current_config_id)

        self.current_config_label.config(text=f"当前配置: {cfg['name']}")

    def _default_settings(self) -> Dict[str, object]:
        return {
            "inc_hotkey": "space",
            "reset_hotkey": "r",
            "auto_toggle_hotkey": "",
            "auto_interval": 1.0,
            "threshold_configs": [
                {"name": "预警", "threshold": 30, "color": "#ff8c00", "desc": "达到后变橙色"},
                {"name": "高强度", "threshold": 60, "color": "#cc2b2b", "desc": "达到后变红色"},
            ],
        }

    def _apply_settings(self, settings: Dict[str, object]) -> None:
        defaults = self._default_settings()
        merged = dict(defaults)
        merged.update(settings or {})

        self.threshold_configs = merged.get("threshold_configs", defaults["threshold_configs"])  # type: ignore
        if not isinstance(self.threshold_configs, list):
            self.threshold_configs = defaults["threshold_configs"]  # type: ignore

        try:
            self.auto_interval_var.set(float(merged.get("auto_interval", 1.0)))
        except (ValueError, TypeError):
            self.auto_interval_var.set(1.0)

        self._apply_hotkey_config(
            str(merged.get("inc_hotkey", "space")),
            str(merged.get("reset_hotkey", "r")),
            str(merged.get("auto_toggle_hotkey", "")),
        )

        self._refresh_hotkey_summary()
        self._refresh_threshold_table()
        self._refresh_count_color()

    def _collect_settings(self) -> Dict[str, object]:
        return {
            "inc_hotkey": self.inc_hotkey,
            "reset_hotkey": self.reset_hotkey,
            "auto_toggle_hotkey": self.auto_toggle_hotkey,
            "auto_interval": float(self.auto_interval_var.get()),
            "threshold_configs": self.threshold_configs,
        }

    def _persist_current_settings(self) -> None:
        if not self.current_user or self.current_config_id is None:
            return
        settings = self._collect_settings()
        self.storage.update_user_config_settings(self.current_config_id, settings)
        self.storage.save_system_defaults(settings)

    def increment(self) -> None:
        self.count += 1
        self._update_display()

    def reset(self) -> None:
        self.count = 0
        self._update_display()

    def _token_to_binding(self, token: str) -> str:
        t = token.strip()
        if not t:
            raise ValueError("热键不能为空")
        if t.lower() == "space":
            return "<space>"
        return f"<KeyPress-{t}>"

    def _token_to_label(self, token: str) -> str:
        t = token.strip()
        if not t:
            return "未设置"
        if t.lower() == "space":
            return "空格"
        return t.upper()

    def _clear_all_hotkeys(self) -> None:
        for seq in self.active_bindings.values():
            self.root.unbind(seq)
        self.active_bindings.clear()

    def _apply_hotkey_config(self, inc_token: str, reset_token: str, auto_token: str) -> None:
        inc_token = inc_token.strip()
        reset_token = reset_token.strip()
        auto_token = auto_token.strip()

        if not inc_token or not reset_token:
            raise ValueError("加1和清零热键不能为空")

        unique_tokens = [x.lower() for x in [inc_token, reset_token, auto_token] if x]
        if len(unique_tokens) != len(set(unique_tokens)):
            raise ValueError("热键不能重复")

        bindings = {"inc": self._token_to_binding(inc_token), "reset": self._token_to_binding(reset_token)}
        if auto_token:
            bindings["auto"] = self._token_to_binding(auto_token)

        self._clear_all_hotkeys()

        self.root.bind(bindings["inc"], lambda _event: self.increment())
        self.root.bind(bindings["reset"], lambda _event: self.reset())
        self.active_bindings["inc"] = bindings["inc"]
        self.active_bindings["reset"] = bindings["reset"]

        if "auto" in bindings:
            self.root.bind(bindings["auto"], lambda _event: self._toggle_auto_count())
            self.active_bindings["auto"] = bindings["auto"]

        self.inc_hotkey = inc_token
        self.reset_hotkey = reset_token
        self.auto_toggle_hotkey = auto_token

    def _refresh_hotkey_summary(self) -> None:
        self.hint.config(
            text=(
                f"快捷键: {self._token_to_label(self.inc_hotkey)} +1，"
                f"{self._token_to_label(self.reset_hotkey)} 清零，"
                f"{self._token_to_label(self.auto_toggle_hotkey)} 自动计数启停"
            )
        )
        self.hotkey_summary_label.config(
            text=(
                f"+1 = {self._token_to_label(self.inc_hotkey)}\n"
                f"清零 = {self._token_to_label(self.reset_hotkey)}\n"
                f"自动计数启停 = {self._token_to_label(self.auto_toggle_hotkey)}"
            )
        )

    def _capture_hotkey_dialog(self, parent: tk.Toplevel, title: str) -> Optional[str]:
        dialog = tk.Toplevel(parent)
        dialog.title(title)
        dialog.geometry("300x140")
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.grab_set()

        tk.Label(dialog, text="请按下一个按键", font=("Microsoft YaHei", 11)).pack(pady=(20, 8))
        tk.Label(dialog, text="Esc 取消", font=("Microsoft YaHei", 9), fg="#666666").pack()

        result = {"token": None}

        def on_key(event) -> None:
            keysym = event.keysym
            if keysym == "Escape":
                dialog.destroy()
                return
            if keysym == "space":
                result["token"] = "space"
            else:
                result["token"] = keysym.lower() if len(keysym) == 1 else keysym
            dialog.destroy()

        dialog.bind("<KeyPress>", on_key)
        dialog.focus_force()
        dialog.wait_window()
        return result["token"]

    def _open_hotkey_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("配置热键")
        dialog.geometry("500x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        inc_var = tk.StringVar(value=self.inc_hotkey)
        reset_var = tk.StringVar(value=self.reset_hotkey)
        auto_var = tk.StringVar(value=self.auto_toggle_hotkey)

        tk.Label(dialog, text="通过点击按钮录制热键", font=("Microsoft YaHei", 10)).pack(pady=(12, 10))

        def hotkey_row(parent: tk.Toplevel, label_text: str, token_var: tk.StringVar, capture_title: str, can_clear: bool) -> None:
            row = tk.Frame(parent)
            row.pack(fill="x", padx=18, pady=(0, 10))
            tk.Label(row, text=label_text, width=14, anchor="w", font=("Microsoft YaHei", 10)).pack(side="left")
            tk.Label(row, textvariable=token_var, width=14, anchor="w", font=("Consolas", 10)).pack(side="left")

            def pick() -> None:
                token = self._capture_hotkey_dialog(dialog, capture_title)
                if token:
                    token_var.set(token)

            tk.Button(row, text="录制", width=10, command=pick).pack(side="left", padx=(8, 6))
            if can_clear:
                tk.Button(row, text="清空", width=10, command=lambda: token_var.set("")).pack(side="left")

        hotkey_row(dialog, "加1热键:", inc_var, "录制加1热键", can_clear=False)
        hotkey_row(dialog, "清零热键:", reset_var, "录制清零热键", can_clear=False)
        hotkey_row(dialog, "自动计数热键:", auto_var, "录制自动计数热键", can_clear=True)

        tk.Label(dialog, text="自动计数热键可清空（不启用）", font=("Microsoft YaHei", 9), fg="#666666").pack(
            anchor="w", padx=20, pady=(0, 8)
        )

        footer = tk.Frame(dialog)
        footer.pack(pady=(10, 0))

        def save_hotkeys() -> None:
            try:
                self._apply_hotkey_config(inc_var.get(), reset_var.get(), auto_var.get())
            except ValueError as exc:
                messagebox.showerror("配置错误", str(exc), parent=dialog)
                return

            self._refresh_hotkey_summary()
            self._persist_current_settings()
            dialog.destroy()

        tk.Button(footer, text="保存", width=12, command=save_hotkeys).pack(side="left", padx=6)
        tk.Button(footer, text="取消", width=12, command=dialog.destroy).pack(side="left", padx=6)

    def _open_threshold_editor(self, title: str, initial: Optional[Dict[str, object]] = None) -> Optional[Dict[str, object]]:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("320x310")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        name_var = tk.StringVar(value=str(initial["name"]) if initial else "")
        threshold_var = tk.IntVar(value=int(initial["threshold"]) if initial else 30)
        color_var = tk.StringVar(value=str(initial["color"]) if initial else "#ff8c00")
        desc_var = tk.StringVar(value=str(initial["desc"]) if initial else "")
        result = {"value": None}

        tk.Label(dialog, text="名称:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Entry(dialog, textvariable=name_var, width=40).pack(anchor="w", padx=16)

        tk.Label(dialog, text="门限值:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Spinbox(dialog, from_=0, to=1000000, textvariable=threshold_var, width=12).pack(anchor="w", padx=16)

        tk.Label(dialog, text="字体颜色:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
        color_row = tk.Frame(dialog)
        color_row.pack(anchor="w", padx=16)
        swatch = tk.Label(color_row, text="      ", bg=color_var.get(), relief="solid", bd=1)
        swatch.pack(side="left")
        tk.Label(color_row, textvariable=color_var, font=("Consolas", 10)).pack(side="left", padx=(8, 10))

        def pick_color() -> None:
            _, hex_color = colorchooser.askcolor(title="选择颜色", initialcolor=color_var.get(), parent=dialog)
            if hex_color:
                color_var.set(hex_color)
                swatch.config(bg=hex_color)

        tk.Button(color_row, text="选择颜色", command=pick_color).pack(side="left")

        tk.Label(dialog, text="说明:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Entry(dialog, textvariable=desc_var, width=40).pack(anchor="w", padx=16)

        footer = tk.Frame(dialog)
        footer.pack(pady=(14, 0))

        def save() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("输入错误", "名称不能为空", parent=dialog)
                return

            try:
                threshold = int(threshold_var.get())
            except ValueError:
                messagebox.showerror("输入错误", "门限必须是整数", parent=dialog)
                return
            if threshold < 0:
                messagebox.showerror("输入错误", "门限不能小于 0", parent=dialog)
                return

            color = color_var.get().strip()
            try:
                self.root.winfo_rgb(color)
            except tk.TclError:
                messagebox.showerror("输入错误", "颜色无效", parent=dialog)
                return

            result["value"] = {
                "name": name,
                "threshold": threshold,
                "color": color,
                "desc": desc_var.get().strip(),
            }
            dialog.destroy()

        tk.Button(footer, text="确定", width=10, command=save).pack(side="left", padx=6)
        tk.Button(footer, text="取消", width=10, command=dialog.destroy).pack(side="left", padx=6)

        dialog.wait_window()
        return result["value"]

    def _add_threshold_config(self) -> None:
        cfg = self._open_threshold_editor("新增门限配置")
        if not cfg:
            return
        self.threshold_configs.append(cfg)
        self._refresh_threshold_table()
        self._refresh_count_color()
        self._persist_current_settings()

    def _edit_threshold_config(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.threshold_configs):
            return
        current = self.threshold_configs[idx]
        cfg = self._open_threshold_editor("编辑门限配置", initial=current)
        if not cfg:
            return
        self.threshold_configs[idx] = cfg
        self._refresh_threshold_table()
        self._refresh_count_color()
        self._persist_current_settings()

    def _edit_selected_threshold_config(self) -> None:
        selected = self.threshold_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先在门限列表中选择一项", parent=self.root)
            return
        try:
            idx = int(selected[0])
        except ValueError:
            return
        self._edit_threshold_config(idx)

    def _refresh_threshold_table(self) -> None:
        for item in self.threshold_tree.get_children():
            self.threshold_tree.delete(item)

        if not self.threshold_configs:
            self.threshold_tree.insert("", "end", iid="empty", values=("-", "暂无配置", "-", "-", "点击新增一项配置", "-"))
            return

        for idx, cfg in enumerate(self.threshold_configs):
            self.threshold_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    idx + 1,
                    str(cfg.get("name", "")),
                    str(cfg.get("threshold", "")),
                    str(cfg.get("color", "")),
                    str(cfg.get("desc", "")),
                    "双击编辑",
                ),
            )

    def _open_profile_dialog(self) -> None:
        if not self.current_user:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("我的信息")
        dialog.geometry("380x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        pwd_var = tk.StringVar(value="")
        pwd2_var = tk.StringVar(value="")

        tk.Label(dialog, text=f"用户名: {self.current_user['username']}", font=("Microsoft YaHei", 10, "bold")).pack(
            anchor="w", padx=16, pady=(16, 8)
        )

        tk.Label(dialog, text="新密码(可空):", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(4, 4))
        tk.Entry(dialog, textvariable=pwd_var, show="*", width=42).pack(anchor="w", padx=16)

        tk.Label(dialog, text="确认新密码:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
        tk.Entry(dialog, textvariable=pwd2_var, show="*", width=42).pack(anchor="w", padx=16)

        tk.Label(dialog, text="说明:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(12, 4))
        desc_wrap = tk.Frame(dialog)
        desc_wrap.pack(anchor="w", padx=16)
        desc_text = tk.Text(desc_wrap, width=42, height=3, wrap="word")
        desc_scroll = ttk.Scrollbar(desc_wrap, orient="vertical", command=desc_text.yview)
        desc_text.configure(yscrollcommand=desc_scroll.set)
        desc_text.pack(side="left")
        desc_scroll.pack(side="left", fill="y")
        desc_text.insert("1.0", str(self.current_user["description"] or ""))

        footer = tk.Frame(dialog)
        footer.pack(pady=(16, 0))

        def save_profile() -> None:
            new_pwd = pwd_var.get()
            if new_pwd != pwd2_var.get():
                messagebox.showerror("输入错误", "两次密码输入不一致", parent=dialog)
                return

            description = desc_text.get("1.0", "end-1c").strip()
            self.storage.update_user_profile(int(self.current_user["id"]), description, new_pwd)
            refreshed = self.storage.get_user_by_id(int(self.current_user["id"]))
            if refreshed:
                self.current_user = refreshed

            if new_pwd:
                info = self.storage.get_saved_login_info()
                if info.get("last_user", "") == str(self.current_user["username"]):
                    self.storage.save_login_info(str(self.current_user["username"]), False, "")

            messagebox.showinfo("成功", "用户信息已更新", parent=dialog)
            dialog.destroy()

        tk.Button(footer, text="保存", width=12, command=save_profile).pack(side="left", padx=6)
        tk.Button(footer, text="取消", width=12, command=dialog.destroy).pack(side="left", padx=6)

    def _open_user_admin_dialog(self) -> None:
        if not self.current_user or int(self.current_user["is_admin"]) != 1:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("用户管理")
        dialog.geometry("700x430")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        cols = ("username", "is_admin", "created_at", "description", "op")
        tree = ttk.Treeview(dialog, columns=cols, show="headings", height=9)
        tree.heading("username", text="用户名")
        tree.heading("is_admin", text="管理员")
        tree.heading("created_at", text="创建时间")
        tree.heading("description", text="说明")
        tree.heading("op", text="操作")
        tree.column("username", width=100, anchor="w")
        tree.column("is_admin", width=50, anchor="center")
        tree.column("created_at", width=150, anchor="center")
        tree.column("description", width=220, anchor="w")
        tree.column("op", width=120, anchor="center")
        tree.pack(fill="x", padx=12, pady=(12, 8))

        row_map: Dict[str, int] = {}

        def refresh_users() -> None:
            row_map.clear()
            for i in tree.get_children():
                tree.delete(i)
            for u in self.storage.list_users():
                iid = tree.insert(
                    "",
                    "end",
                    values=(
                        u["username"],
                        "是" if int(u["is_admin"]) == 1 else "否",
                        u["created_at"],
                        u["description"],
                        "编辑 | 删除",
                    ),
                )
                row_map[iid] = int(u["id"])

        refresh_users()

        def selected_user() -> Optional[sqlite3.Row]:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("提示", "请先选中一个用户", parent=dialog)
                return None
            uid = row_map.get(selected[0])
            if uid is None:
                return None
            return self.storage.get_user_by_id(uid)

        def open_edit_user(target_user: sqlite3.Row) -> None:
            sub = tk.Toplevel(dialog)
            sub.title("编辑用户")
            sub.geometry("340x280")
            sub.resizable(False, False)
            sub.transient(dialog)
            sub.grab_set()

            desc_var = tk.StringVar(value=str(target_user["description"] or ""))
            pwd_var = tk.StringVar(value="")
            pwd2_var = tk.StringVar(value="")

            tk.Label(sub, text=f"用户名: {target_user['username']}", font=("Microsoft YaHei", 10, "bold")).pack(
                anchor="w", padx=16, pady=(16, 8)
            )
            tk.Label(sub, text="说明:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(2, 4))
            tk.Entry(sub, textvariable=desc_var, width=44).pack(anchor="w", padx=16)

            tk.Label(sub, text="重置密码(可空):", font=("Microsoft YaHei", 10)).pack(
                anchor="w", padx=16, pady=(10, 4)
            )
            tk.Entry(sub, textvariable=pwd_var, show="*", width=44).pack(anchor="w", padx=16)
            tk.Label(sub, text="确认密码:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
            tk.Entry(sub, textvariable=pwd2_var, show="*", width=44).pack(anchor="w", padx=16)

            footer = tk.Frame(sub)
            footer.pack(pady=(16, 0))

            def do_save() -> None:
                new_pwd = pwd_var.get()
                if new_pwd != pwd2_var.get():
                    messagebox.showerror("输入错误", "两次密码输入不一致", parent=sub)
                    return
                self.storage.admin_update_user(int(target_user["id"]), desc_var.get().strip(), new_pwd)
                refresh_users()
                messagebox.showinfo("成功", "用户信息已更新", parent=sub)
                sub.destroy()

            tk.Button(footer, text="保存", width=12, command=do_save).pack(side="left", padx=6)
            tk.Button(footer, text="取消", width=12, command=sub.destroy).pack(side="left", padx=6)

        def on_tree_click(event) -> None:
            rowid = tree.identify_row(event.y)
            col = tree.identify_column(event.x)
            if not rowid or col != "#5":
                return
            uid = row_map.get(rowid)
            if uid is None:
                return
            u = self.storage.get_user_by_id(uid)
            if not u:
                return
            col_x = tree.bbox(rowid, col)
            if not col_x:
                return
            x_in_col = event.x - col_x[0]
            if x_in_col < col_x[2] / 2:
                open_edit_user(u)
            else:
                if str(u["username"]) == "admin":
                    messagebox.showerror("删除失败", "admin 用户不能删除", parent=dialog)
                    return
                if int(u["id"]) == int(self.current_user["id"]):
                    messagebox.showerror("删除失败", "不能删除当前登录用户", parent=dialog)
                    return
                if messagebox.askyesno("确认删除", f"确定删除用户 {u['username']} 吗？", parent=dialog):
                    self.storage.admin_delete_user(int(u["id"]))
                    refresh_users()

        tree.bind("<Button-1>", on_tree_click)

        tk.Label(
            dialog,
            text="提示: 在用户列表“操作”列点击“编辑 | 删除”执行操作",
            font=("Microsoft YaHei", 9),
            fg="#666666",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        add_frame = tk.LabelFrame(dialog, text="新增用户", padx=10, pady=10)
        add_frame.pack(fill="x", padx=12, pady=(0, 10))

        name_var = tk.StringVar()
        pwd_var = tk.StringVar()
        desc_var = tk.StringVar()

        row1 = tk.Frame(add_frame)
        row1.pack(fill="x")
        tk.Label(row1, text="用户名:", width=8, anchor="w").pack(side="left")
        tk.Entry(row1, textvariable=name_var, width=18).pack(side="left", padx=(0, 8))
        tk.Label(row1, text="初始密码:", width=8, anchor="w").pack(side="left")
        tk.Entry(row1, textvariable=pwd_var, width=18).pack(side="left")

        row2 = tk.Frame(add_frame)
        row2.pack(fill="x", pady=(8, 0))
        tk.Label(row2, text="说明:", width=8, anchor="w").pack(side="left")
        tk.Entry(row2, textvariable=desc_var, width=58).pack(side="left")

        def add_user() -> None:
            username = name_var.get().strip()
            password = pwd_var.get().strip()
            desc = desc_var.get().strip()

            if not username or not password:
                messagebox.showerror("输入错误", "用户名和初始密码不能为空", parent=dialog)
                return
            if self.storage.get_user_by_username(username):
                messagebox.showerror("输入错误", "用户名已存在", parent=dialog)
                return

            try:
                user_id = self.storage.create_user(username, password, desc, is_admin=0)
                self.storage.create_user_default_config(user_id, self.storage.get_system_defaults())
            except sqlite3.IntegrityError:
                messagebox.showerror("输入错误", "用户名已存在", parent=dialog)
                return

            messagebox.showinfo("成功", f"用户 {username} 已创建", parent=dialog)
            name_var.set("")
            pwd_var.set("")
            desc_var.set("")
            refresh_users()

        tk.Button(add_frame, text="新增用户", width=10, command=add_user).pack(anchor="e", pady=(10, 0))

    def _open_config_manager(self) -> None:
        if not self.current_user:
            return

        user_id = int(self.current_user["id"])
        dialog = tk.Toplevel(self.root)
        dialog.title("配置管理")
        dialog.geometry("760x440")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        cols = ("name", "created_at", "is_default", "description")
        tree = ttk.Treeview(dialog, columns=cols, show="headings", height=13)
        tree.heading("name", text="名称")
        tree.heading("created_at", text="创建时间")
        tree.heading("is_default", text="是否默认")
        tree.heading("description", text="说明")

        tree.column("name", width=180, anchor="w")
        tree.column("created_at", width=170, anchor="center")
        tree.column("is_default", width=90, anchor="center")
        tree.column("description", width=280, anchor="w")
        tree.pack(fill="x", padx=12, pady=(12, 8))

        row_map: Dict[str, int] = {}

        def refresh_tree() -> None:
            row_map.clear()
            for i in tree.get_children():
                tree.delete(i)
            for cfg in self.storage.list_user_configs(user_id):
                item_id = tree.insert(
                    "",
                    "end",
                    values=(
                        cfg["name"],
                        cfg["created_at"],
                        "是" if int(cfg["is_default"]) == 1 else "否",
                        cfg["description"],
                    ),
                )
                row_map[item_id] = int(cfg["id"])

        refresh_tree()

        def selected_config_id() -> Optional[int]:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("提示", "请先选中一个配置", parent=dialog)
                return None
            return row_map.get(selected[0])

        button_row = tk.Frame(dialog)
        button_row.pack(fill="x", padx=12, pady=(0, 10))

        def save_current() -> None:
            if self.current_config_id is None:
                messagebox.showerror("错误", "当前没有激活配置", parent=dialog)
                return
            self._persist_current_settings()
            messagebox.showinfo("成功", "当前界面设置已保存到当前配置", parent=dialog)

        def new_config() -> None:
            default_cfg = None
            for cfg in self.storage.list_user_configs(user_id):
                if int(cfg["is_default"]) == 1:
                    default_cfg = cfg
                    break

            base_settings = self._default_settings()
            if default_cfg:
                parsed = self.storage.parse_config_settings(default_cfg)
                if parsed:
                    base_settings = parsed

            name_default = self.storage.get_next_config_name(user_id)

            sub = tk.Toplevel(dialog)
            sub.title("新建配置")
            sub.geometry("420x220")
            sub.resizable(False, False)
            sub.transient(dialog)
            sub.grab_set()

            name_var = tk.StringVar(value=name_default)
            desc_var = tk.StringVar(value="")

            tk.Label(sub, text="配置名称:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(14, 4))
            tk.Entry(sub, textvariable=name_var, width=38).pack(anchor="w", padx=16)

            tk.Label(sub, text="说明:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
            tk.Entry(sub, textvariable=desc_var, width=38).pack(anchor="w", padx=16)

            tk.Label(
                sub,
                text="新配置将基于“默认配置”的值生成",
                font=("Microsoft YaHei", 9),
                fg="#666666",
            ).pack(anchor="w", padx=16, pady=(10, 0))

            foot = tk.Frame(sub)
            foot.pack(pady=(14, 0))

            def do_create() -> None:
                name = name_var.get().strip()
                if not name:
                    messagebox.showerror("输入错误", "配置名称不能为空", parent=sub)
                    return
                if self.storage.get_user_config_by_name(user_id, name):
                    messagebox.showerror("输入错误", "配置名称已存在", parent=sub)
                    return

                try:
                    cfg_id = self.storage.create_user_config(user_id, name, desc_var.get().strip(), base_settings, is_default=False)
                except sqlite3.IntegrityError:
                    messagebox.showerror("输入错误", "配置名称已存在", parent=sub)
                    return

                refresh_tree()
                messagebox.showinfo("成功", f"已创建配置 {name}", parent=sub)
                sub.destroy()

                if self.current_config_id is None:
                    self._load_config_by_id(cfg_id)

            tk.Button(foot, text="创建", width=12, command=do_create).pack(side="left", padx=6)
            tk.Button(foot, text="取消", width=12, command=sub.destroy).pack(side="left", padx=6)

            sub.wait_window()

        def load_selected() -> None:
            cfg_id = selected_config_id()
            if cfg_id is None:
                return
            self._load_config_by_id(cfg_id)
            refresh_tree()
            messagebox.showinfo("成功", "配置已加载", parent=dialog)

        def set_default() -> None:
            cfg_id = selected_config_id()
            if cfg_id is None:
                return
            self.storage.set_default_config(user_id, cfg_id)
            refresh_tree()
            messagebox.showinfo("成功", "已设为默认配置", parent=dialog)

        def edit_selected() -> None:
            cfg_id = selected_config_id()
            if cfg_id is None:
                return
            cfg = self.storage.get_user_config(cfg_id)
            if not cfg:
                return

            sub = tk.Toplevel(dialog)
            sub.title("编辑配置信息")
            sub.geometry("420x220")
            sub.resizable(False, False)
            sub.transient(dialog)
            sub.grab_set()

            name_var = tk.StringVar(value=str(cfg["name"]))
            desc_var = tk.StringVar(value=str(cfg["description"] or ""))

            tk.Label(sub, text="配置名称:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(14, 4))
            tk.Entry(sub, textvariable=name_var, width=38).pack(anchor="w", padx=16)

            tk.Label(sub, text="说明:", font=("Microsoft YaHei", 10)).pack(anchor="w", padx=16, pady=(10, 4))
            tk.Entry(sub, textvariable=desc_var, width=38).pack(anchor="w", padx=16)

            foot = tk.Frame(sub)
            foot.pack(pady=(16, 0))

            def do_save() -> None:
                name = name_var.get().strip()
                if not name:
                    messagebox.showerror("输入错误", "配置名称不能为空", parent=sub)
                    return
                existing = self.storage.get_user_config_by_name(user_id, name)
                if existing and int(existing["id"]) != cfg_id:
                    messagebox.showerror("输入错误", "配置名称已存在", parent=sub)
                    return

                self.storage.update_user_config_meta(cfg_id, name, desc_var.get().strip())
                refresh_tree()
                if self.current_config_id == cfg_id:
                    self.current_config_label.config(text=f"当前配置: {name}")
                sub.destroy()

            tk.Button(foot, text="保存", width=12, command=do_save).pack(side="left", padx=6)
            tk.Button(foot, text="取消", width=12, command=sub.destroy).pack(side="left", padx=6)

            sub.wait_window()

        def delete_selected() -> None:
            cfg_id = selected_config_id()
            if cfg_id is None:
                return

            cfg = self.storage.get_user_config(cfg_id)
            if not cfg:
                return

            if messagebox.askyesno("确认删除", f"确认删除配置 {cfg['name']} 吗？", parent=dialog) is False:
                return

            try:
                self.storage.delete_user_config(user_id, cfg_id)
            except ValueError as exc:
                messagebox.showerror("删除失败", str(exc), parent=dialog)
                return

            if self.current_config_id == cfg_id:
                self._load_user_startup_config()

            refresh_tree()

        tk.Button(button_row, text="保存当前配置", width=12, command=save_current).pack(side="left", padx=4)
        tk.Button(button_row, text="新的配置", width=10, command=new_config).pack(side="left", padx=4)
        tk.Button(button_row, text="加载配置", width=10, command=load_selected).pack(side="left", padx=4)
        tk.Button(button_row, text="设为默认", width=10, command=set_default).pack(side="left", padx=4)
        tk.Button(button_row, text="编辑信息", width=10, command=edit_selected).pack(side="left", padx=4)
        tk.Button(button_row, text="删除配置", width=10, command=delete_selected).pack(side="left", padx=4)

    def _load_config_by_id(self, config_id: int) -> None:
        if not self.current_user:
            return
        cfg = self.storage.get_user_config(config_id)
        if not cfg or int(cfg["user_id"]) != int(self.current_user["id"]):
            return

        settings = self.storage.parse_config_settings(cfg)
        self._apply_settings(settings)

        self.current_config_id = int(cfg["id"])
        self.storage.set_user_last_config(int(self.current_user["id"]), self.current_config_id)
        self.current_config_label.config(text=f"当前配置: {cfg['name']}")

    def _get_auto_interval_ms(self) -> int:
        try:
            seconds = float(self.auto_interval_var.get())
        except (ValueError, tk.TclError):
            raise ValueError("自动计数间隔必须是数字")

        if seconds < 0.5:
            raise ValueError("自动计数间隔不能小于 0.5 秒")
        return int(seconds * 1000)

    def _on_auto_interval_changed(self) -> None:
        try:
            self._get_auto_interval_ms()
        except ValueError:
            return

        self._persist_current_settings()

    def _schedule_auto_count(self) -> None:
        interval_ms = self._get_auto_interval_ms()
        self.auto_job_id = self.root.after(interval_ms, self._auto_tick)

    def _auto_tick(self) -> None:
        self.auto_job_id = None
        if not self.auto_count_enabled:
            return
        self.increment()
        self._schedule_auto_count()

    def _start_auto_count(self) -> None:
        if self.auto_count_enabled:
            return
        self._get_auto_interval_ms()
        self.auto_count_enabled = True
        self.auto_status_label.config(text="状态: 运行中", fg="#1f7a1f")
        self.auto_toggle_button.config(text="停止计数")
        self._schedule_auto_count()

    def _stop_auto_count(self) -> None:
        self.auto_count_enabled = False
        if self.auto_job_id is not None:
            self.root.after_cancel(self.auto_job_id)
            self.auto_job_id = None
        self.auto_status_label.config(text="状态: 已停止", fg="#555555")
        self.auto_toggle_button.config(text="启动计数")

    def _toggle_auto_count(self) -> None:
        if self.auto_count_enabled:
            self._stop_auto_count()
            return

        try:
            self._start_auto_count()
        except ValueError as exc:
            messagebox.showerror("配置错误", str(exc), parent=self.root)

    def _update_display(self) -> None:
        self.count_label.config(text=str(self.count))
        self._refresh_count_color()

    def _refresh_count_color(self) -> None:
        color = self.normal_color
        try:
            ordered = sorted(self.threshold_configs, key=lambda x: int(x.get("threshold", 0)))
        except Exception:
            ordered = []

        for cfg in ordered:
            threshold = int(cfg.get("threshold", 0))
            if self.count >= threshold:
                color = str(cfg.get("color", self.normal_color))
            else:
                break
        self.count_label.config(fg=color)

    def _on_close(self) -> None:
        self._stop_auto_count()
        self.storage.close()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    CounterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
