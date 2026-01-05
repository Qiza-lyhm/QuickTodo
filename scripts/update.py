import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
INBOX_FILE = BASE_DIR / "inbox" / "current.md"
LOGS_DIR = BASE_DIR / "logs"
TODOS_DIR = BASE_DIR / "todos"
TASKS_FILE = TODOS_DIR / "tasks.yaml"
TODO_MD_FILE = TODOS_DIR / "todo.md"
LATEST_FILE = BASE_DIR / "latest.md"
CONFIG_FILE = BASE_DIR / "config.yaml"


def load_tasks():
    if not TASKS_FILE.exists():
        return []
    text = TASKS_FILE.read_text(encoding="utf-8").strip()
    if not text or text == "[]":
        return []
    return yaml.safe_load(text) or []


def load_config():
    """Load configuration from config.yaml, return a dict.

    Structure example:

    todo:
      sort_mode: priority | created_at | tag
      tag_index_for_sort: 0
      default_priority: 5
    """
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data or {}


def _get_todo_config():
    cfg = load_config()
    todo_cfg = cfg.get("todo") or {}
    return {
        "sort_mode": todo_cfg.get("sort_mode", "priority"),
        "tag_index_for_sort": int(todo_cfg.get("tag_index_for_sort", 0) or 0),
        "default_priority": int(todo_cfg.get("default_priority", 5) or 5),
    }


def save_tasks(tasks):
    TASKS_FILE.write_text(
        yaml.safe_dump(tasks, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def regenerate_todo_md(tasks):
    cfg = _get_todo_config()

    def _sort_tasks(ts):
        mode = cfg["sort_mode"]
        tag_idx = cfg["tag_index_for_sort"]
        default_pri = cfg["default_priority"]

        def first_tag(task):
            tags = task.get("tags") or []
            if 0 <= tag_idx < len(tags):
                return tags[tag_idx]
            return tags[0] if tags else ""

        def pri(task):
            p = task.get("priority")
            try:
                return int(p)
            except (TypeError, ValueError):
                return default_pri

        def key(task):
            created = task.get("created_at") or ""
            title = task.get("title") or ""
            if mode == "created_at":
                return (created, title)
            if mode == "tag":
                return (first_tag(task), pri(task), created, title)
            # default: priority
            return (pri(task), created, title)

        return sorted(ts, key=key)

    lines = ["# 当前 TODO 列表（未完成）", "",]
    open_tasks = _sort_tasks([t for t in tasks if t.get("status") == "open"])
    if not open_tasks:
        lines.append("_暂无未完成任务。_")
    else:
        for t in open_tasks:
            title = t.get("title", "(无标题)")
            tags = t.get("tags") or []
            due = t.get("due")
            priority = t.get("priority")
            meta_parts = []
            if priority:
                meta_parts.append(f"!{priority}")
            if tags:
                meta_parts.append("@" + ",@".join(tags))
            if due:
                meta_parts.append(f"due:{due}")
            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            lines.append(f"- [ ] {title}{meta}")
    TODO_MD_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


TODO_LIST_HEADER_RE = re.compile(r"^##\s+TODO LIST\s*$", re.IGNORECASE)


def parse_inbox_todo_section(text):
    """Parse the TODO LIST section from inbox/current.md.

    Expected structure:

    ## TODO LIST

    ### TODO
    - ... (id:123)

    ### DONE
    - ... (id:456)

    ### DELETE
    - ... (id:789)

    支持从行内解析：
    - 方括号中的状态标记：[ ] / [v] / [x]
    - 优先级：例如 "{3} 标题"
    - 标签：例如 "(@tag1,@tag2, ...)"
    - 截止日期：例如 "due:2026-01-05"

    Returns: {task_id: {"section", "box", "priority", "tags", "due"}}
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if TODO_LIST_HEADER_RE.match(line.strip()):
            start = i
            break
    if start is None:
        return {}

    # find end (next "## " header after TODO LIST)
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## ") and not TODO_LIST_HEADER_RE.match(lines[j].strip()):
            end = j
            break

    section = None
    mapping = {}
    for k in range(start + 1, end):
        l = lines[k].strip()
        if l.startswith("### "):
            name = l[4:].strip().upper()
            if name in {"TODO", "DONE", "DELETE", "DROP"}:
                section = name
            else:
                section = None
            continue
        if not l or section is None:
            continue
        # Extract checkbox value if present: "- [ ]", "- [v]", "- [x]" etc.
        box = " "
        m_box = re.match(r"^[-*]\s*\[([^\]]?)\]", l)
        if m_box:
            box = (m_box.group(1) or " ").strip() or " "

        # lines like "- [ ] {3} title (@tag1,@tag2, due:YYYY-MM-DD) (id:xxxx)"
        m = re.search(r"\(id:([^\)]+)\)", l)
        if m:
            task_id = m.group(1).strip()
            if task_id:
                # 解析优先级 {N}
                priority = None
                m_pri = re.search(r"\{(\d+)\}", l)
                if m_pri:
                    try:
                        priority = int(m_pri.group(1))
                    except ValueError:
                        priority = None

                # 解析标签 @tag1,@tag2
                tags = []
                m_tags = re.search(r"@(\w+(?:,@\w+)*)", l)
                if m_tags:
                    tag_str = m_tags.group(1)
                    if tag_str:
                        # 形如 "tag1,@tag2" -> ["tag1", "tag2"]
                        tags = [part.lstrip("@") for part in tag_str.split(",@") if part]

                # 解析截止日期 due:YYYY-MM-DD
                due = None
                m_due = re.search(r"due:(\d{4}-\d{2}-\d{2})", l)
                if m_due:
                    due = m_due.group(1)

                mapping[task_id] = {
                    "section": section,
                    "box": box,
                    "priority": priority,
                    "tags": tags,
                    "due": due,
                }
    return mapping


def apply_inbox_todo_changes(text, tasks):
    """Apply user's manual moves in TODO LIST (TODO/DONE/DELETE) to tasks.

    We only update tasks whose id appears in the TODO LIST section.
    """
    mapping = parse_inbox_todo_section(text)
    if not mapping:
        return tasks

    tasks_by_id = {t.get("id"): t for t in tasks if t.get("id")}
    dropped_ids = set()
    log_events: list[str] = []

    for task_id, info in mapping.items():
        section = info["section"]
        box = (info.get("box") or " ").lower()
        t = tasks_by_id.get(task_id)
        if not t:
            continue
        old_status = t.get("status")
        title = t.get("title", "(无标题)")

        # 从 TODO LIST 行中解析出的元信息（优先级、标签、截止日期）
        new_priority = info.get("priority")
        new_tags = info.get("tags") or []
        new_due = info.get("due")

        # DROP 区域保持之前的安全逻辑：只有来自 DONE/DELETE 的任务才允许彻底删除
        if section == "DROP":
            if t.get("status") in {"done", "canceled"}:
                dropped_ids.add(task_id)
                log_events.append(f"彻底删除TODO项目：{title}")
            # DROP 区域仅用于彻底删除，不更新优先级/标签/截止日期
            continue

        # 其他区域：根据方括号内的值决定状态
        # [ ] -> open; [v] -> done; [x] -> canceled
        if box == "v":
            new_status = "done"
        elif box == "x":
            new_status = "canceled"
        else:
            new_status = "open"

        any_change = False

        # 状态变更
        if new_status != old_status:
            t["status"] = new_status
            any_change = True
            if new_status == "done":
                log_events.append(f"完成TODO项目：{title}")
            elif new_status == "canceled":
                log_events.append(f"删除TODO项目：{title}")
            elif new_status == "open":
                # 从 DONE/DELETE 回到 TODO 时可选择不记录日志，避免噪音
                pass

        # 优先级变更（如果用户在行内写了 {N}）
        if new_priority is not None and new_priority != t.get("priority"):
            t["priority"] = new_priority
            any_change = True

        # 标签变更（如果用户在行内写了 @tag）
        if new_tags and new_tags != (t.get("tags") or []):
            t["tags"] = new_tags
            any_change = True

        # 截止日期变更（如果用户在行内写了 due:YYYY-MM-DD）
        if new_due and new_due != t.get("due"):
            t["due"] = new_due
            any_change = True

        # 如果有任何字段变更，更新 updated_at 时间戳
        if any_change:
            now = datetime.now()
            t["updated_at"] = now.strftime("%Y-%m-%d %H:%M")

    if dropped_ids:
        tasks = [t for t in tasks if t.get("id") not in dropped_ids]

    # 将 TODO 状态变更操作写入今天的 LOG
    if log_events:
        append_to_daily_log(date.today(), log_events)

    return tasks


def render_todo_section(tasks):
    """Render the TODO LIST section for inbox/current.md from tasks.yaml."""
    cfg = _get_todo_config()

    def _sort_tasks(ts):
        mode = cfg["sort_mode"]
        tag_idx = cfg["tag_index_for_sort"]
        default_pri = cfg["default_priority"]

        def first_tag(task):
            tags = task.get("tags") or []
            if 0 <= tag_idx < len(tags):
                return tags[tag_idx]
            return tags[0] if tags else ""

        def pri(task):
            p = task.get("priority")
            try:
                return int(p)
            except (TypeError, ValueError):
                return default_pri

        def key(task):
            created = task.get("created_at") or ""
            title = task.get("title") or ""
            if mode == "created_at":
                return (created, title)
            if mode == "tag":
                return (first_tag(task), pri(task), created, title)
            # default: priority
            return (pri(task), created, title)

        return sorted(ts, key=key)

    lines = [
        "## TODO LIST",
        "",
    ]

    def task_line(task, checkbox):
        title = task.get("title", "(无标题)")
        tags = task.get("tags") or []
        due = task.get("due")
        priority = task.get("priority")
        # 优先级放在开头，使用大括号表示，例如 {3}
        pri_prefix = f"{{{priority}}} " if priority is not None else ""
        meta_parts = []
        if tags:
            meta_parts.append("@" + ",@".join(tags))
        if due:
            meta_parts.append(f"due:{due}")
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        return f"- [{checkbox}] {pri_prefix}{title}{meta} (id:{task.get('id')})"

    # Group tasks by status and sort
    open_tasks = _sort_tasks([t for t in tasks if t.get("status") == "open"])
    done_tasks = _sort_tasks([t for t in tasks if t.get("status") == "done"])
    deleted_tasks = _sort_tasks([t for t in tasks if t.get("status") == "canceled"])

    lines.append("### TODO")
    lines.append("")
    if not open_tasks:
        lines.append("- [ ] (暂无 TODO)")
    else:
        for t in open_tasks:
            lines.append(task_line(t, " "))

    lines.append("")
    lines.append("### DONE")
    lines.append("")
    if not done_tasks:
        lines.append("- [ ] (暂无 DONE)")
    else:
        for t in done_tasks:
            # 使用 [v] 表示已完成任务
            lines.append(task_line(t, "v"))

    lines.append("")
    lines.append("### DELETE")
    lines.append("")
    if not deleted_tasks:
        lines.append("- [ ] (暂无 DELETE)")
    else:
        for t in deleted_tasks:
            # 使用 [x] 表示 DELETE 区域的任务
            lines.append(task_line(t, "x"))

    lines.append("")
    lines.append("### DROP")
    lines.append("")
    # DROP 区域不列出具体任务，仅作为用户从 DONE/DELETE 中拖动条目以彻底删除的目标区域
    lines.append("- [ ] (将 DONE/DELETE 中不再需要的任务移入此处以彻底删除)")
    lines.append("")
    return "\n".join(lines)


def upsert_todo_section(inbox_text, tasks):
    """Insert or replace the TODO LIST section in inbox/current.md."""
    lines = inbox_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if TODO_LIST_HEADER_RE.match(line.strip()):
            start = i
            break

    new_section = render_todo_section(tasks).splitlines()

    if start is None:
        # Insert TODO LIST near the top: after first level-1 heading if present
        insert_at = 0
        if lines and lines[0].startswith("# "):
            insert_at = 1
            # skip possible blank line after title
            if len(lines) > 1 and not lines[1].strip():
                insert_at = 2
        new_lines = lines[:insert_at] + new_section + [""] + lines[insert_at:]
        return "\n".join(new_lines) + ("\n" if new_lines else "")

    # Replace existing TODO LIST section
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## ") and not TODO_LIST_HEADER_RE.match(lines[j].strip()):
            end = j
            break

    new_lines = lines[:start] + new_section + [""] + lines[end:]
    return "\n".join(new_lines) + ("\n" if new_lines else "")


UPDATE_HEADER_RE = re.compile(r"^##\s+(?P<dt>\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)\s*$")


def parse_inbox_blocks(text):
    """Yield blocks: {"header_line", "datetime", "lines"}.

    Blocks start with lines like: "## 2026-01-04 09:30".
    """
    lines = text.splitlines()
    blocks = []
    current = None
    for line in lines:
        m = UPDATE_HEADER_RE.match(line)
        if m:
            if current is not None:
                blocks.append(current)
            dt_str = m.group("dt")
            # datetime: if no time, default 09:00
            if " " in dt_str:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            else:
                dt = datetime.strptime(dt_str, "%Y-%m-%d")
            current = {"header_line": line, "datetime": dt, "lines": []}
        else:
            if current is not None:
                current["lines"].append(line)
    if current is not None:
        blocks.append(current)
    return blocks


def append_to_daily_log(dt, log_items):
    """Append LOG items to that day's markdown file.

    Format (simple daily granularity):

    # YYYY-MM-DD

    ## LOG
    - HH:MM text
    """
    # dt here is used only for date component
    date_str = dt.strftime("%Y-%m-%d")
    year = dt.strftime("%Y")
    year_month = dt.strftime("%Y-%m")
    day_file = LOGS_DIR / year / year_month / f"{date_str}.md"
    day_file.parent.mkdir(parents=True, exist_ok=True)

    if day_file.exists():
        content = day_file.read_text(encoding="utf-8")
    else:
        content = f"# {date_str}\n\n## LOG\n\n"

    # Ensure there is a LOG section
    if "\n## LOG" not in content:
        content = content.rstrip() + "\n\n## LOG\n\n"

    # Append items: one bullet per log item, 时间使用系统当前时间
    now = datetime.now()
    time_str = now.strftime("%H:%M")
    lines = content.splitlines()
    if log_items:
        for item in log_items:
            lines.append(f"- {time_str} {item}")
    day_file.write_text("\n".join(lines), encoding="utf-8")


def parse_todo_line(raw):
    """Parse a TODO line into (title, tags, due, priority).

    Example: "完成模块 A 的单元测试 @projectA !3 due:2026-01-05"
    优先级使用 !1-!9，数字越小优先级越高。
    """
    line = raw.strip()
    # remove leading checkbox "- [ ]" or "- [x]" or "- [v]" if present
    line = re.sub(r"^[-*]\s*\[(?: |x|X|v|V)\]\s*", "", line)
    # Extract due:YYYY-MM-DD
    due = None
    m_due = re.search(r"due:(\d{4}-\d{2}-\d{2})", line)
    if m_due:
        due = m_due.group(1)
        line = line.replace(m_due.group(0), "").strip()
    # Extract priority !1-!9
    priority = None
    m_pri = re.search(r"!(\d)", line)
    if m_pri:
        priority = int(m_pri.group(1))
        line = line.replace(m_pri.group(0), "").strip()
    # Extract @tags
    tags = re.findall(r"@(\w+)", line)
    # Remove @tags from title
    title = re.sub(r"@(\w+)", "", line).strip()
    return title, tags, due, priority


def find_task_by_title(tasks, title):
    """Simple fuzzy match by title substring."""
    norm = title.strip()
    for t in tasks:
        if t.get("title", "").strip() == norm:
            return t
    for t in tasks:
        if norm and norm in t.get("title", ""):
            return t
    return None


def process_block(block, tasks):
    block_dt = block["datetime"]
    lines = block["lines"]

    # We parse simple sections: ### LOG / ### TODO_ADD / ### TODO_DONE
    section = None
    section_lines = {"LOG": [], "TODO_ADD": [], "TODO_DONE": []}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            name = stripped[4:].strip().upper()
            if name in section_lines:
                section = name
            else:
                section = None
        else:
            if section in section_lines and stripped:
                section_lines[section].append(stripped)

    # 如果这个块中 LOG/TODO_* 都是空的，把它当作“模板块”，不处理、不删除
    if not any(section_lines.values()):
        return False

    # LOG → daily markdown
    if section_lines["LOG"]:
        # remove leading "- " if present
        items = [re.sub(r"^[-*]\s*", "", s).strip() for s in section_lines["LOG"]]
        # 使用块日期作为归档到哪一天，时间使用当前系统时间
        append_to_daily_log(block_dt.date(), items)

    # TODO_ADD → tasks.yaml (status=open)
    todo_log_events: list[str] = []
    cfg = _get_todo_config()
    default_priority = cfg["default_priority"]

    for raw in section_lines["TODO_ADD"]:
        title, tags, due, priority = parse_todo_line(raw)
        if not title:
            continue
        now = datetime.now()
        task_id = now.strftime("%Y%m%d-%H%M-%f")
        created_at = now.strftime("%Y-%m-%d %H:%M")
        tasks.append(
            {
                "id": task_id,
                "title": title,
                "status": "open",
                "created_at": created_at,
                "updated_at": created_at,
                "due": due,
                "tags": tags,
                "priority": priority if priority is not None else default_priority,
            }
        )
        todo_log_events.append(f"添加TODO项目：{title}")

    # TODO_DONE → mark done if possible; otherwise create done task
    for raw in section_lines["TODO_DONE"]:
        title, tags, due, priority = parse_todo_line(raw)
        if not title:
            continue
        task = find_task_by_title(tasks, title)
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M")
        if task is not None:
            task["status"] = "done"
            task["updated_at"] = ts
            if due and not task.get("due"):
                task["due"] = due
            if tags:
                old_tags = set(task.get("tags") or [])
                task["tags"] = sorted(old_tags.union(tags))
            if priority is not None:
                task["priority"] = priority
        else:
            # 为新建的已完成任务使用当前时间生成 id
            task_id = now.strftime("%Y%m%d-%H%M-%f") + "-done"
            tasks.append(
                {
                    "id": task_id,
                    "title": title,
                    "status": "done",
                    "created_at": ts,
                    "updated_at": ts,
                    "due": due,
                    "tags": tags,
                    "priority": priority if priority is not None else default_priority,
                }
            )
        todo_log_events.append(f"完成TODO项目：{title}")
    # 将本块中的 TODO 操作也写入对应日期的 LOG
    if todo_log_events:
        append_to_daily_log(block_dt.date(), todo_log_events)
    return True


def clean_inbox(text, processed_blocks):
    """Remove processed blocks from inbox content."""
    if not processed_blocks:
        return text

    lines = text.splitlines()
    to_remove_indices = set()

    # Build map of header line → datetime string for quick lookup
    headers = {b["header_line"]: b["datetime"] for b in processed_blocks}

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m = UPDATE_HEADER_RE.match(line)
        if m and line in headers:
            start = i
            i += 1
            while i < n and not UPDATE_HEADER_RE.match(lines[i]):
                i += 1
            for j in range(start, i):
                to_remove_indices.add(j)
        else:
            i += 1

    new_lines = [l for idx, l in enumerate(lines) if idx not in to_remove_indices]
    return "\n".join(new_lines) + ("\n" if new_lines else "")


def main():
    if not INBOX_FILE.exists():
        print(f"Inbox file not found: {INBOX_FILE}")
        sys.exit(1)

    text = INBOX_FILE.read_text(encoding="utf-8")
    blocks = parse_inbox_blocks(text)

    tasks = load_tasks()

    # 先根据 current.md 中 TODO LIST 区域的 TODO/DONE/DELETE 变更更新任务状态
    tasks = apply_inbox_todo_changes(text, tasks)

    processed = []
    for block in blocks:
        # process_block 返回 True 表示这个块里有实际内容被处理
        if process_block(block, tasks):
            processed.append(block)

    # 如果没有任何实际 update（只有空模板块和 TODO 变更）
    if not processed:
        today = date.today().strftime("%Y-%m-%d")
        lines = text.splitlines()
        new_lines = []
        header_updated = False
        for line in lines:
            m = UPDATE_HEADER_RE.match(line)
            if m and not header_updated:
                # 只更新第一个头部的日期为今天（不保留时间）
                new_lines.append(f"## {today}")
                header_updated = True
            else:
                new_lines.append(line)

        # 如果原来连一个头部都没有，就在末尾加一个新的今天模板
        if not header_updated:
            if new_lines and new_lines[-1].strip():
                new_lines.append("")
            new_lines.append(f"## {today}")
            new_lines.append("")
            new_lines.append("### LOG")
            new_lines.append("")
            new_lines.append("### TODO_ADD")
            new_lines.append("")
            new_lines.append("### TODO_DONE")
            new_lines.append("")

        rolled_text = "\n".join(new_lines) + ("\n" if new_lines else "")

        # 保存任务状态并同步 todos/todo.md
        save_tasks(tasks)
        regenerate_todo_md(tasks)

        # 在 rolled_text 中插入/更新 TODO LIST 区域
        rolled_text = upsert_todo_section(rolled_text, tasks)
        INBOX_FILE.write_text(rolled_text, encoding="utf-8")

        # 即使没有新的日志块，也更新 latest.md（保持和 logs 当前状态一致）
        _generate_latest()

        print("No update blocks (## YYYY-MM-DD ...) found in inbox.")
        return

    # 有实际处理的块：更新任务 / 清理 inbox，并为当天补一个空模板块
    save_tasks(tasks)
    regenerate_todo_md(tasks)

    new_inbox = clean_inbox(text, processed)

    # 清理后如果没有任何日期块（## YYYY-MM-DD），为最近一次处理的日期添加一个新的模板块
    lines_after_clean = new_inbox.splitlines()
    has_date_header = any(UPDATE_HEADER_RE.match(l) for l in lines_after_clean)
    if not has_date_header:
        last_date = max(b["datetime"].date() for b in processed)
        date_str = last_date.strftime("%Y-%m-%d")
        template_lines = [
            f"## {date_str}",
            "",
            "### LOG",
            "",
            "### TODO_ADD",
            "",
            "### TODO_DONE",
            "",
        ]
        if lines_after_clean and lines_after_clean[-1].strip():
            lines_after_clean.append("")
        lines_after_clean.extend(template_lines)
        new_inbox = "\n".join(lines_after_clean)

    # 在 new_inbox 中插入/更新 TODO LIST 区域
    new_inbox = upsert_todo_section(new_inbox, tasks)

    INBOX_FILE.write_text(new_inbox, encoding="utf-8")

    # 同时生成 latest 文件：包含今天和昨天的全部日志内容
    _generate_latest()

    print(f"Processed {len(processed)} update block(s).")


def _generate_latest():
    """Generate latest.md containing today and yesterday logs.

    在 latest.md 中将普通 LOG 记录与 TODO 操作记录分开展示：
    - 上方：LOG 记录
    - 下方：TODO 操作（添加/完成/删除/彻底删除 TODO 项）
    """
    today = date.today()
    yesterday = today - timedelta(days=1)
    parts = ["# 最近两天工作记录", ""]

    for d in (today, yesterday):
        date_str = d.strftime("%Y-%m-%d")
        year = d.strftime("%Y")
        year_month = d.strftime("%Y-%m")
        day_file = LOGS_DIR / year / year_month / f"{date_str}.md"
        if not day_file.exists():
            continue

        raw_lines = day_file.read_text(encoding="utf-8").splitlines()
        # 跳过文件内第一行的日期标题，以避免重复
        if raw_lines and raw_lines[0].startswith("# "):
            raw_lines = raw_lines[1:]

        # 拆分为普通 LOG 与 TODO 操作两部分
        log_lines: list[str] = []
        todo_op_lines: list[str] = []

        for line in raw_lines:
            stripped = line.strip()
            # TODO 操作行是 append_to_daily_log 写入的，形如：
            # - HH:MM 添加TODO项目：XXX
            # - HH:MM 完成TODO项目：XXX
            # - HH:MM 删除TODO项目：XXX
            # - HH:MM 彻底删除TODO项目：XXX
            if re.match(r"^- \d{2}:\d{2} (?:添加TODO项目|完成TODO项目|删除TODO项目|彻底删除TODO项目)：", stripped):
                todo_op_lines.append(line)
            else:
                # 其余全部视为普通 LOG（包含原来的 ## LOG 标题等）
                log_lines.append(line)

        parts.append(f"## {date_str}")
        parts.append("")

        # 普通 LOG 记录（在 latest.md 中按时间逆序展示条目，最近的在最上方）
        if log_lines:
            parts.append("### LOG")
            parts.append("")

            # 拆分为“普通文本/标题行”和“具体 LOG 条目行”（形如 "- HH:MM 文本"）
            log_entry_re = re.compile(r"^- \d{2}:\d{2} ")
            log_entry_lines = []
            log_other_lines = []
            for line in log_lines:
                stripped = line.strip()
                if log_entry_re.match(stripped):
                    log_entry_lines.append(line)
                else:
                    log_other_lines.append(line)

            # 先保持非条目行的原始顺序（例如空行、原文件中的 ## LOG 标题等）
            if log_other_lines:
                parts.extend(log_other_lines)
                if log_other_lines[-1].strip():
                    parts.append("")

            # 再把具体 LOG 条目按时间逆序输出，最近的在最上方
            if log_entry_lines:
                for line in reversed(log_entry_lines):
                    parts.append(line)
                parts.append("")

        # TODO 操作记录（按时间逆序显示，最近的在最上方）
        if todo_op_lines:
            parts.append("### TODO 操作")
            parts.append("")
            for line in reversed(todo_op_lines):
                parts.append(line)
            parts.append("")

    LATEST_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
