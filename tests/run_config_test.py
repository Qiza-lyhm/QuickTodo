import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_ROOT = Path(__file__).resolve().parent / "tmp_test_project"
FIXTURE = Path(__file__).resolve().parent / "fixture"


def prepare():
    if TEST_ROOT.exists():
        shutil.rmtree(TEST_ROOT)
    TEST_ROOT.mkdir(parents=True)
    # create subdirs
    (TEST_ROOT / "inbox").mkdir()
    (TEST_ROOT / "logs").mkdir()
    (TEST_ROOT / "todos").mkdir()
    # copy fixture files
    shutil.copy(FIXTURE / "config_test.yaml", TEST_ROOT / "config.yaml")
    shutil.copy(FIXTURE / "current_test.md", TEST_ROOT / "inbox" / "current.md")


def run():
    # run update.py with --config pointing to TEST_ROOT/config.yaml
    cmd = [sys.executable, str(ROOT / "scripts" / "update.py"), "--config", str(TEST_ROOT / "config.yaml")]
    print("Running:", " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(ROOT))
    return p.returncode


def validate():
    # check logs created
    log_file = TEST_ROOT / "logs" / "2026" / "2026-01" / "2026-01-08.md"
    latest = TEST_ROOT / "latest.md"
    ok = True
    if not log_file.exists():
        print("FAIL: log file not created:", log_file)
        ok = False
    else:
        text = log_file.read_text(encoding="utf-8")
        if "添加TODO项目：测试任务" not in text:
            print("FAIL: log file does not contain added todo line")
            ok = False
    if not latest.exists():
        print("FAIL: latest.md not created")
        ok = False
    else:
        lt = latest.read_text(encoding="utf-8")
        if "测试任务" not in lt:
            print("FAIL: latest.md does not mention the test task")
            ok = False
    if ok:
        print("TEST PASSED")
        return 0
    else:
        return 2


if __name__ == '__main__':
    prepare()
    rc = run()
    if rc != 0:
        print("update.py failed with rc", rc)
        sys.exit(3)
    sys.exit(validate())
