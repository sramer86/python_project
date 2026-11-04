"""Debug build: lazily load database search results in 100-row pages."""

from __future__ import annotations

import argparse
import ctypes
import importlib
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk
import traceback
from typing import Any


DATABASE = "[cwbase1].[lc0019999].[LSWLZD]"
DISPLAY_FIELDS = (
    "LSWLZD_WLBH",
    "LSWLZD_WLMC",
    "LSWLZD_U2",
    "LSWLZD_C1",
    "LSWLZD_C5",
    "LSWLZD_CKDJ",
)
DISPLAY_TITLES = ("料号", "物料名称", "库存", "厂商", "级别", "价格")
PAGE_SIZE = 100

LEVEL_OPTIONS = (
    ("所有等级", ""),
    ("民用级/商业级", "0"),
    ("工业级", "1"),
    ("普军级", "2"),
    ("七专", "3"),
    ("国军标", "4"),
)
FILTER_OPTIONS = (
    ("所有筛选状态", ""),
    ("未筛选", "0"),
    ("二院标准", "1"),
    ("三院标准", "2"),
    ("二院标准在三院筛选", "3"),
    ("771所筛选", "4"),
    ("一院DPA分析后", "5"),
    ("电子部四所", "6"),
    ("三院抽筛", "D"),
)
ROHS_OPTIONS = (("全部", ""), ("有铅", "0"), ("无铅", "1"))


def _absolute_path(path: Path) -> Path:
    """Make a path absolute without resolving mapped/network drive targets."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _startup_log_path() -> Path:
    """Return a writable per-user location for frozen-app diagnostics."""
    app_data = os.environ.get("LOCALAPPDATA")
    base = Path(app_data) if app_data else Path(tempfile.gettempdir())
    return base / "Y2MaterialSearch" / "startup_error.log"


def _report_startup_error(context: str, error: BaseException) -> Path:
    """Persist startup and callback failures so windowed builds remain diagnosable."""
    log_path = _startup_log_path()
    details = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"\n[{context}]\n{details}\n")
        return log_path
    except OSError:
        fallback_path = Path(tempfile.gettempdir()) / "database_search_error.log"
        with fallback_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"\n[{context}]\n{details}\n")
        return fallback_path


def _show_error_dialog(title: str, message: str) -> None:
    """Show an error even if Tk initialization itself is broken."""
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except (AttributeError, OSError):
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message, parent=root)
        root.destroy()


def _sql_literal(value: str) -> str:
    """Quote a user-supplied SQL string while preserving LIKE wildcards."""
    return "'" + value.replace("'", "''") + "'"


def build_search_sql(
    search_text: str,
    *,
    mode: str = "number",
    level: str = "",
    filter_status: str = "",
    rohs: str = "",
    only_in_stock: bool = False,
    fuzzy: bool = False,
) -> str:
    """Build the material lookup used by Unit1's regular or fuzzy search."""
    text = search_text.strip()

    fields = ", ".join(f"[{field}]" for field in DISPLAY_FIELDS)
    sql = f"SELECT {fields} FROM {DATABASE}"

    if not text:
        conditions = []
    elif fuzzy:
        pattern = _sql_literal(f"%{text}%")
        sql += (
            " WHERE UPPER([LSWLZD_WLMC]) LIKE UPPER("
            + pattern
            + ") OR [LSWLZD_C1] LIKE "
            + pattern
            + " OR [LSWLZD_WLBH] LIKE "
            + pattern
        )
        return sql
    elif mode == "number":
        conditions = [
            f"[LSWLZD_WLBH] LIKE {_sql_literal(text + '%')}"
        ]
    elif mode == "description":
        description_pattern = "%" + text.replace("*", "%") + "%"
        number_pattern = "__________" + (level or "_") + (
            filter_status or "_"
        ) + (rohs or "_")
        conditions = [
            "UPPER([LSWLZD_WLMC]) LIKE UPPER("
            + _sql_literal(description_pattern)
            + ")",
            f"[LSWLZD_WLBH] LIKE {_sql_literal(number_pattern)}",
        ]
    else:
        raise ValueError(f"不支持的搜索模式：{mode}")

    if only_in_stock:
        conditions.append("[LSWLZD_U2] <> 0")

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    return sql


def build_page_sql(sql: str, offset: int, limit: int = PAGE_SIZE) -> str:
    """Wrap a material query in stable SQL Server row-number pagination."""
    if offset < 0:
        raise ValueError("offset 不能小于 0。")
    if limit <= 0:
        raise ValueError("limit 必须大于 0。")

    select_clause, separator, from_clause = sql.partition(" FROM ")
    expected_select = "SELECT " + ", ".join(
        f"[{field}]" for field in DISPLAY_FIELDS
    )
    if not separator or select_clause != expected_select:
        raise ValueError("无法为当前查询生成分页 SQL。")

    fields = ", ".join(f"[{field}]" for field in DISPLAY_FIELDS)
    order_by = ", ".join(f"[{field}]" for field in DISPLAY_FIELDS)
    upper_bound = offset + limit
    return (
        f"SELECT {fields} FROM ("
        f"SELECT ROW_NUMBER() OVER (ORDER BY {order_by}) AS [__row_number], "
        f"{fields} FROM {from_clause}"
        f") AS [paged] WHERE [__row_number] > {offset} "
        f"AND [__row_number] <= {upper_bound} "
        "ORDER BY [__row_number]"
    )


def default_udl_path() -> Path:
    """Find external or bundled UDL files in script and frozen app layouts."""
    if getattr(sys, "frozen", False):
        executable_udl = _absolute_path(Path(sys.executable)).with_name(
            "public_dbcon.udl"
        )
        if executable_udl.is_file():
            return executable_udl

        bundle_dir = getattr(sys, "_MEIPASS", None)
        if bundle_dir:
            bundled_udl = _absolute_path(Path(bundle_dir) / "public_dbcon.udl")
            if bundled_udl.is_file():
                return bundled_udl
        return executable_udl

    script_path = Path(os.path.abspath(__file__))
    local_udl = script_path.with_name("public_dbcon.udl")
    if local_udl.is_file():
        return local_udl

    return (
        script_path.parents[2]
        / "20210303 y2_bom_soft v3.1"
        / "public_dbcon.udl"
    )


class MaterialDatabase:
    """Small ADO reader that opens the existing UDL connection definition."""

    def __init__(self, udl_path: Path) -> None:
        self.udl_path = udl_path
        self._connection: Any = None

    def _open_connection(self) -> None:
        if self._connection is not None:
            return
        try:
            win32com_client = importlib.import_module("win32com.client")
        except ImportError as exc:
            raise RuntimeError(
                "当前 Python 环境未安装 pywin32。请运行："
                "python -m pip install pywin32"
            ) from exc

        connection = win32com_client.Dispatch("ADODB.Connection")
        connection.ConnectionTimeout = 10
        connection.CommandTimeout = 30
        connection.Open(f"File Name={self.udl_path}")
        self._connection = connection

    def search(self, sql: str) -> list[tuple[str, ...]]:
        self._open_connection()
        recordset: Any = None
        try:
            recordset = self._connection.Execute(sql)[0]
            rows: list[tuple[str, ...]] = []
            while not recordset.EOF:
                row = tuple(
                    ""
                    if value is None
                    else str(int(value))
                    if index == 2
                    else str(value)
                    for index in range(len(DISPLAY_FIELDS))
                    for value in (recordset.Fields.Item(index).Value,)
                )
                rows.append(row)
                recordset.MoveNext()
            return rows
        finally:
            if recordset is not None:
                recordset.Close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.Close()
            self._connection = None


class MaterialSearchApp:
    def __init__(self, root: tk.Tk, udl_path: Path) -> None:
        self.root = root
        self.database = MaterialDatabase(udl_path)
        self._search_job: str | None = None
        self._load_job: str | None = None
        self._query_sql: str | None = None
        self._loaded_count = 0
        self._has_more = False
        self._loading = False
        self.root.title("物料数据库检索（分页调试版）")
        self.root.geometry("1020x620")
        self.root.minsize(760, 420)

        self.search_text = tk.StringVar()
        self.search_mode = tk.StringVar(value="number")
        self.level = tk.StringVar(value=LEVEL_OPTIONS[0][0])
        self.filter_status = tk.StringVar(value=FILTER_OPTIONS[0][0])
        self.rohs = tk.StringVar(value=ROHS_OPTIONS[0][0])
        self.only_in_stock = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value=f"UDL: {udl_path}")

        self._build_widgets()
        self.root.report_callback_exception = self._report_callback_exception
        for variable in (
            self.search_mode,
            self.level,
            self.filter_status,
            self.rohs,
            self.only_in_stock,
        ):
            variable.trace_add("write", self._schedule_search)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.status_text.set("正在加载物料数据…")
        self.root.after(100, self._search)

    def _report_callback_exception(
        self,
        error_type: type[BaseException],
        error: BaseException,
        error_traceback: Any,
    ) -> None:
        error.__traceback__ = error_traceback
        log_path = _report_startup_error("Tk callback", error)
        _show_error_dialog(
            "程序运行错误",
            f"{error_type.__name__}: {error}\n\n详细信息已写入：{log_path}",
        )

    def _build_widgets(self) -> None:
        controls = ttk.Frame(self.root, padding=10)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="搜索内容：").grid(
            row=0, column=0, sticky=tk.W, padx=(0, 5), pady=4
        )
        search_entry = ttk.Entry(
            controls, textvariable=self.search_text, width=48
        )
        search_entry.grid(row=0, column=1, columnspan=4, sticky=tk.EW, pady=4)
        search_entry.bind("<Return>", self._on_return)
        search_entry.bind("<KeyRelease>", self._on_search_input)

        ttk.Radiobutton(
            controls,
            text="料号前缀",
            variable=self.search_mode,
            value="number",
            command=self._schedule_search,
        ).grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Radiobutton(
            controls,
            text="物料描述",
            variable=self.search_mode,
            value="description",
            command=self._schedule_search,
        ).grid(row=1, column=2, sticky=tk.W, pady=4)
        ttk.Button(controls, text="搜索", command=self._search).grid(
            row=0, column=5, padx=(10, 4), pady=4
        )
        ttk.Button(
            controls, text="模糊搜索", command=lambda: self._search(fuzzy=True)
        ).grid(row=1, column=5, padx=(10, 4), pady=4)

        self._add_combobox(
            controls, "等级：", LEVEL_OPTIONS, self.level, row=2, column=0
        )
        self._add_combobox(
            controls,
            "筛选：",
            FILTER_OPTIONS,
            self.filter_status,
            row=2,
            column=2,
        )
        self._add_combobox(
            controls, "RoHS：", ROHS_OPTIONS, self.rohs, row=2, column=4
        )
        ttk.Checkbutton(
            controls,
            text="只显示有库存",
            variable=self.only_in_stock,
            command=self._schedule_search,
        ).grid(row=3, column=1, sticky=tk.W, pady=4)

        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)

        result_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        result_frame.pack(fill=tk.BOTH, expand=True)
        self.results = ttk.Treeview(
            result_frame,
            columns=DISPLAY_FIELDS,
            show="headings",
            selectmode="browse",
        )
        widths = (180, 330, 100, 130, 100, 100)
        for field, title, width in zip(
            DISPLAY_FIELDS, DISPLAY_TITLES, widths
        ):
            self.results.heading(field, text=title)
            self.results.column(field, width=width, minwidth=70, anchor=tk.W)

        vertical_scroll = ttk.Scrollbar(
            result_frame, orient=tk.VERTICAL, command=self.results.yview
        )
        self.vertical_scroll = vertical_scroll
        horizontal_scroll = ttk.Scrollbar(
            result_frame, orient=tk.HORIZONTAL, command=self.results.xview
        )
        self.results.configure(
            yscrollcommand=self._on_results_scroll,
            xscrollcommand=horizontal_scroll.set,
        )
        self.results.grid(row=0, column=0, sticky=tk.NSEW)
        vertical_scroll.grid(row=0, column=1, sticky=tk.NS)
        horizontal_scroll.grid(row=1, column=0, sticky=tk.EW)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        ttk.Label(
            self.root, textvariable=self.status_text, anchor=tk.W, padding=8
        ).pack(fill=tk.X)

    def _add_combobox(
        self,
        parent: ttk.Frame,
        label: str,
        options: tuple[tuple[str, str], ...],
        variable: tk.StringVar,
        *,
        row: int,
        column: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row, column=column, sticky=tk.W, padx=(0, 4), pady=4
        )
        combo = ttk.Combobox(
            parent,
            textvariable=variable,
            values=tuple(option[0] for option in options),
            state="readonly",
            width=22,
        )
        combo.grid(
            row=row, column=column + 1, sticky=tk.EW, padx=(0, 10), pady=4
        )
        combo.bind("<<ComboboxSelected>>", self._on_filter_selected)

    def _search(self, *, fuzzy: bool = False) -> None:
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
            self._search_job = None
        if self._load_job is not None:
            self.root.after_cancel(self._load_job)
            self._load_job = None
        try:
            sql = build_search_sql(
                self.search_text.get(),
                mode=self.search_mode.get(),
                level=self._selected_value(LEVEL_OPTIONS, self.level.get()),
                filter_status=self._selected_value(
                    FILTER_OPTIONS, self.filter_status.get()
                ),
                rohs=self._selected_value(ROHS_OPTIONS, self.rohs.get()),
                only_in_stock=self.only_in_stock.get(),
                fuzzy=fuzzy,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self.status_text.set("查询失败")
            messagebox.showerror("数据库查询失败", str(exc), parent=self.root)
            return

        self._has_more = False
        self._query_sql = None
        self.results.delete(*self.results.get_children())
        self.results.yview_moveto(0)
        self._query_sql = sql
        self._loaded_count = 0
        self._has_more = True
        self._loading = False
        self.status_text.set("正在加载前 100 条…")
        self._load_next_page()

    def _load_next_page(self) -> None:
        self._load_job = None
        if (
            self._loading
            or not self._has_more
            or self._query_sql is None
        ):
            return

        self._loading = True
        try:
            page_sql = build_page_sql(
                self._query_sql, self._loaded_count, PAGE_SIZE
            )
            rows = self.database.search(page_sql)
        except Exception as exc:
            self._has_more = False
            self.status_text.set(
                f"已加载 {self._loaded_count} 条；后续加载失败"
            )
            messagebox.showerror(
                "数据库查询失败",
                f"{type(exc).__name__}: {exc}",
                parent=self.root,
            )
            return
        finally:
            self._loading = False

        for row in rows:
            self.results.insert("", tk.END, values=row)
        self._loaded_count += len(rows)
        self._has_more = len(rows) == PAGE_SIZE
        if self._has_more:
            self.status_text.set(
                f"已加载 {self._loaded_count} 条，滚动到底部加载更多…"
            )
        else:
            self.status_text.set(f"已加载全部 {self._loaded_count} 条")

    def _on_results_scroll(self, first: str, last: str) -> None:
        self.vertical_scroll.set(first, last)
        if (
            float(last) >= 0.98
            and self._has_more
            and not self._loading
            and self._load_job is None
        ):
            self._load_job = self.root.after_idle(self._load_next_page)

    def _schedule_search(self, *_args: str) -> None:
        if _args and _args[-1] != "write":
            return
        if self._search_job is not None:
            self.root.after_cancel(self._search_job)
            self._search_job = None
        self._search_job = self.root.after(350, self._run_scheduled_search)

    def _run_scheduled_search(self) -> None:
        self._search_job = None
        self._search()

    def _on_search_input(self, event: tk.Event) -> None:
        if event.keysym != "Return":
            self._schedule_search()

    def _on_filter_selected(self, event: tk.Event) -> None:
        if event.widget is not None:
            self._schedule_search()

    def _on_return(self, event: tk.Event) -> str:
        if event.keysym != "Return":
            return ""
        self._search()
        return "break"

    @staticmethod
    def _selected_value(
        options: tuple[tuple[str, str], ...], selected_label: str
    ) -> str:
        for label, value in options:
            if label == selected_label:
                return value
        raise ValueError(f"无效的筛选选项：{selected_label}")

    def _close(self) -> None:
        try:
            self.database.close()
        except Exception as exc:
            messagebox.showerror(
                "关闭数据库连接失败",
                f"{type(exc).__name__}: {exc}",
                parent=self.root,
            )
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="调试版：通过 UDL 检索物料数据并按 100 条分页加载"
    )
    parser.add_argument(
        "--udl",
        type=Path,
        default=default_udl_path(),
        help="UDL 文件路径；默认使用项目目录中的 public_dbcon.udl",
    )
    args = parser.parse_args()
    udl_path = _absolute_path(args.udl)
    if not udl_path.is_file():
        error = FileNotFoundError(
            f"找不到 UDL 文件：{udl_path}\n\n"
            "请将 public_dbcon.udl 放在 EXE 同目录，或在 auto-py-to-exe "
            "的 Additional Files 中添加该文件（目标目录填写 .）。"
        )
        log_path = _report_startup_error("Startup", error)
        _show_error_dialog(
            "无法启动数据库检索",
            f"{error}\n\n诊断日志：{log_path}",
        )
        return

    try:
        root = tk.Tk()
        MaterialSearchApp(root, udl_path)
        root.mainloop()
    except Exception as error:
        log_path = _report_startup_error("Startup", error)
        _show_error_dialog(
            "程序启动失败",
            f"{type(error).__name__}: {error}\n\n详细信息已写入：{log_path}",
        )


if __name__ == "__main__":
    main()