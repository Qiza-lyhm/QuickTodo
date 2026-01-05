# QuickTodo

一个基于命令行 + Markdown 的个人工作日志 / TODO 管理小工具。

## 核心概念

- `inbox/current.md`：
	- VS Code 中主要编辑的入口文件。
	- 包含：
		- 顶部的「TODO LIST」（TODO / DONE / DELETE / DROP 四个区域）。
		- 当天的日志模板块（`## YYYY-MM-DD` + `### LOG` / `### TODO_ADD` / `### TODO_DONE`）。
- `logs/`：按年/月/日存放每天的工作记录（只由脚本写入）。
- `todos/tasks.yaml`：结构化的任务数据库（只由脚本维护），包含：标题、状态、优先级、标签、截止日期、创建/更新时间等。
- `todos/todo.md`：全局未完成任务的 Markdown 视图，按配置的排序规则（默认按优先级）展示。
- `latest.md`：合并展示「今天 + 昨天」两天的日志：
	- 每天一个 `## 日期` 块。
	- 其中 `### LOG` 部分展示普通日志条目，按时间倒序（最近的在上方）。
	- `### TODO 操作` 部分只展示「添加/完成/删除/彻底删除 TODO 项」之类的操作日志，同样按时间倒序。
- `scripts/update.py`：核心脚本，负责把 inbox 中的修改同步到日志和任务文件里，并根据配置生成视图。

## 基本使用方式

1. **在 VS Code 中编辑 current.md**

	 打开：`inbox/current.md`，你可以：

	 - 在 `## TODO LIST` 里管理任务：
		 - `### TODO`：当前待办。
		 - `### DONE`：已完成任务。
		 - `### DELETE`：不再进行但希望保留记录的任务（状态为 `canceled`）。
		 - `### DROP`：将 DONE/DELETE 中不再需要的任务条目拖到这里，下一次执行脚本时会**彻底删除任务**（从 `tasks.yaml` 中移除）。
		 - 三个主列表中的每一行形如：
			 - `- [ ] {5} 做一件事 (@tag1,@tag2, due:2026-01-05) (id:xxxxx)`
			 - `[ ] / [v] / [x]`：分别表示 TODO / DONE / DELETE，脚本会据此更新任务状态。
			 - `{数字}`：优先级，允许直接修改，例如 `{5}` 改成 `{2}`。
			 - `@tag1,@tag2`：标签列表，允许直接增删修改。
			 - `due:YYYY-MM-DD`：可选截止日期，允许直接修改。
	 - 在当天的日期块下填写日志与任务：

		 ```markdown
		 ## 2026-01-04

		 ### LOG
		 - 设计日志系统结构

		 ### TODO_ADD
		 - 完成接口 X 的单元测试 @projectX due:2026-01-05

		 ### TODO_DONE
		 - 修复登录接口 Bug
		 ```

	 不需要手动填写时间，脚本会用系统当前时间写入日志与任务时间戳。

2. **在命令行中运行更新脚本**

	 打开终端（PowerShell 等），进入本项目根目录（包含 README.md 的那个目录）：

	 ```powershell
	 cd path\to\QuickTodo   # 将 path\to\QuickTodo 替换为你本地的实际路径
	 python .\scripts\update.py
	 ```

	 脚本会：

	 - 把当前 `## YYYY-MM-DD` 块中的 LOG 写入 `logs/<年>/<年-月>/<日期>.md`。
	 - 根据 `### TODO_ADD` 和 `### TODO_DONE` 更新 `todos/tasks.yaml` 和 `todos/todo.md`。
	 - 根据你在 `TODO LIST` 中对任务位置的调整（TODO / DONE / DELETE / DROP）同步任务状态或删除任务。
	 - 解析你在 `TODO LIST` 行中手动修改的优先级 `{N}`、标签 `@tag`、截止日期 `due:YYYY-MM-DD`，并写回 `tasks.yaml`。
	- 处理完已有日志块后，在 `current.md` 中保留/创建当天的空模板块，方便继续记录。
	- 重新生成 `latest.md`，展示最近两天的日志概要：普通 LOG 与 TODO 操作分区展示，均按时间倒序（最近的在上方）。

## 在 VS Code 中的推荐使用场景

- **日常写日志 / 计划**：
	- 在 VS Code 中长期打开 `inbox/current.md`：
		- 顶部看当前 TODO 列表，直接通过拖动行在 TODO / DONE / DELETE / DROP 之间移动任务。
		- 在下面的日期块中按需追加 LOG / TODO_ADD / TODO_DONE 内容。
- **查看最近两天的整体记录**：
	- 打开 `latest.md`，可以一次性浏览今天和昨天的全部工作记录（含时间戳）。
- **偶尔查看全局任务**：
	- 如果只想看未完成任务列表，可查看 `todos/todo.md`（只读，不建议手动编辑）。

## Git 与隐私说明

本项目建议作为一个 git 仓库使用，但为了避免上传个人工作记录：

- `.gitignore` 中已经忽略了：
	- `logs/`
	- `todos/`
	- `latest.md`
	- `inbox/current.md`

因此你可以安全地把仓库同步到远端（例如 GitHub），而不会上传具体的日志和任务内容，只同步脚本和配置。 
