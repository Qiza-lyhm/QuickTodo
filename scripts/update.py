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


def load_tasks():
    if not TASKS_FILE.exists():
        return []
    text = TASKS_FILE.read_text(encoding="utf-8").strip()
    if not text or text == "[]":
        return []
    return yaml.safe_load(text) or []


def save_tasks(tasks):
    TASKS_FILE.write_text(
        yaml.safe_dump(tasks, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def regenerate_todo_md(tasks):
    lines = ["# 当前 TODO 列表（未完成）", "",]
    open_tasks = [t for t in tasks if t.get("status") == "open"]
    if not open_tasks:
        lines.append("_暂无未完成任务。_")
    else:
        for t in open_tasks:
            title = t.get("title", "(无标题)")
            tags = t.get("tags") or []
            due = t.get("due")
            meta_parts = []
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

    Returns: {task_id: section_name}
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
        # lines like "- [ ] title (id:xxxx)" or "- title (id:xxxx)"
        m = re.search(r"\(id:([^\)]+)\)", l)
        if m:
            task_id = m.group(1).strip()
            if task_id:
                mapping[task_id] = section
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

    for task_id, section in mapping.items():
        t = tasks_by_id.get(task_id)
        if not t:
            continue
        if section == "TODO":
            # 回到 TODO，即重新标记为 open
            t["status"] = "open"
        elif section == "DONE":
            t["status"] = "done"
        elif section == "DELETE":
            t["status"] = "canceled"
        elif section == "DROP":
            # 只有来自 DONE 或 DELETE（canceled）的任务才允许真正删除
            if t.get("status") in {"done", "canceled"}:
                dropped_ids.add(task_id)

    if dropped_ids:
        tasks = [t for t in tasks if t.get("id") not in dropped_ids]

    return tasks


def render_todo_section(tasks):
    """Render the TODO LIST section for inbox/current.md from tasks.yaml."""
    lines = [
        "## TODO LIST",
        "",
    ]

    def task_line(task, checkbox):
        title = task.get("title", "(无标题)")
        tags = task.get("tags") or []
        due = task.get("due")
        meta_parts = []
        if tags:
            meta_parts.append("@" + ",@".join(tags))
        if due:
            meta_parts.append(f"due:{due}")
        meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
        return f"- [{checkbox}] {title}{meta} (id:{task.get('id')})"

    # Group tasks by status
    open_tasks = [t for t in tasks if t.get("status") == "open"]
    done_tasks = [t for t in tasks if t.get("status") == "done"]
    deleted_tasks = [t for t in tasks if t.get("status") == "canceled"]

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
            lines.append(task_line(t, "x"))

    lines.append("")
    lines.append("### DELETE")
    lines.append("")
    if not deleted_tasks:
        lines.append("- [ ] (暂无 DELETE)")
    else:
        for t in deleted_tasks:
            lines.append(task_line(t, " "))

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
    """Parse a TODO line into (title, tags, due).

    Example: "完成模块 A 的单元测试 @projectA due:2026-01-05"
    """
    line = raw.strip()
    # remove leading checkbox "- [ ]" or "- [x]" if present
    line = re.sub(r"^[-*]\s*\[(?: |x|X)\]\s*", "", line)
    # Extract due:YYYY-MM-DD
    due = None
    m_due = re.search(r"due:(\d{4}-\d{2}-\d{2})", line)
    if m_due:
        due = m_due.group(1)
        line = line.replace(m_due.group(0), "").strip()
    # Extract @tags
    tags = re.findall(r"@(\w+)", line)
    # Remove @tags from title
    title = re.sub(r"@(\w+)", "", line).strip()
    return title, tags, due


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
    for raw in section_lines["TODO_ADD"]:
        title, tags, due = parse_todo_line(raw)
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
            }
        )

    # TODO_DONE → mark done if possible; otherwise create done task
    for raw in section_lines["TODO_DONE"]:
        title, tags, due = parse_todo_line(raw)
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
                }
            )
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
    """Generate latest.md containing today and yesterday logs."""
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
        content = day_file.read_text(encoding="utf-8").splitlines()
        # 跳过文件内第一行的日期标题，以避免重复
        if content and content[0].startswith("# "):
            content = content[1:]
        parts.append(f"## {date_str}")
        parts.append("")
        parts.extend(content)
        parts.append("")

    LATEST_FILE.write_text("\n".join(parts) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
