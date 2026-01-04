# QuickTodo

一个基于命令行 + Markdown 的个人工作日志 / TODO 管理小工具。

## 核心概念

- `inbox/current.md`：
	- VS Code 中主要编辑的入口文件。
	- 包含：
		- 顶部的「TODO LIST」（TODO / DONE / DELETE / DROP 四个区域）。
		- 当天的日志模板块（`## YYYY-MM-DD` + `### LOG` / `### TODO_ADD` / `### TODO_DONE`）。
- `logs/`：按年/月/日存放每天的工作记录（只由脚本写入）。
- `todos/tasks.yaml`：结构化的任务数据库（只由脚本维护）。
- `todos/todo.md`：全局未完成任务的 Markdown 视图。
- `latest.md`：合并展示「今天 + 昨天」两天的全部日志内容。
- `scripts/update.py`：核心脚本，负责把 inbox 中的修改同步到日志和任务文件里。

## 基本使用方式

1. **在 VS Code 中编辑 current.md**

	 打开：`inbox/current.md`，你可以：

	 - 在 `## TODO LIST` 里管理任务：
		 - `### TODO`：当前待办。
		 - `### DONE`：已完成任务。
		 - `### DELETE`：不再进行但希望保留记录的任务（状态为 `canceled`）。
		 - `### DROP`：将 DONE/DELETE 中不再需要的任务条目拖到这里，下一次执行脚本时会**彻底删除任务**（从 `tasks.yaml` 中移除）。
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

	 打开终端（PowerShell 等），进入项目目录：

	 ```powershell
	 cd "c:\Users\tangyueran\工作日志\QuickTodo"
	 python .\scripts\update.py
	 ```

	 脚本会：

	 - 把当前 `## YYYY-MM-DD` 块中的 LOG 写入 `logs/<年>/<年-月>/<日期>.md`。
	 - 根据 `### TODO_ADD` 和 `### TODO_DONE` 更新 `todos/tasks.yaml` 和 `todos/todo.md`。
	 - 根据你在 `TODO LIST` 中对任务位置的调整（TODO / DONE / DELETE / DROP）同步任务状态或删除任务。
	- 处理完已有日志块后，在 `current.md` 中保留/创建当天的空模板块，方便继续记录。
	- 重新生成 `latest.md`，展示最近两天的完整日志。

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
