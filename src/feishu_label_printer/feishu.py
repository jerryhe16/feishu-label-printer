import json
import os
import shutil
import subprocess
from pathlib import Path


class Feishu:
    def __init__(self, cli_path, directory):
        path = Path(cli_path).expanduser()
        located = str(path.resolve()) if path.is_file() else shutil.which(cli_path)
        if not located:
            raise ValueError("找不到lark-cli；请在cli_path配置lark-cli.exe绝对路径")
        if os.name == "nt" and Path(located).suffix.lower() in (".cmd", ".bat", ".ps1"):
            raise ValueError("Windows请使用lark-cli.exe，避免shell破坏JSON和URL参数")
        self.executable = located
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def call(self, profile, command, *args):
        result = subprocess.run(
            [self.executable, "base", command, "--base-token", profile["base_token"],
             "--as", "user", *args], cwd=self.directory,
            capture_output=True, encoding="utf-8", timeout=90,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            obj = json.loads(result.stdout)
        except ValueError:
            raise RuntimeError(f"lark-cli {command} failed (exit {result.returncode}); inspect CLI auth status") from None
        if result.returncode or obj.get("ok") is False:
            error = obj.get("error", {})
            raise RuntimeError(f"{command}: {error.get('type', 'error')}: {error.get('message', 'request failed')}")
        return obj.get("data", obj)

    def pending(self, profile):
        args = [arg for name in profile["fields"] for arg in ("--field-id", name)]
        status_field = profile.get("status_field", "状态")
        self.call(profile, "+record-list", "--table-id", profile["queue_table"], *args,
                  "--field-id", status_field, "--filter-json",
                  json.dumps({"conditions": [[status_field, "==", "待打印"]]}, ensure_ascii=False),
                  "--limit", "50", "--format", "ndjson", "--output", "pending.ndjson", "--overwrite")
        return [json.loads(line) for line in (self.directory / "pending.ndjson").read_text(encoding="utf-8").splitlines() if line]

    def status(self, profile, record_id, state, detail):
        fields = {profile.get("status_field", "状态"): state,
                  profile.get("result_field", "处理结果"): detail}
        self.call(profile, "+record-batch-update", "--table-id", profile["queue_table"],
                  "--json", json.dumps({"update_records": {record_id: fields}}, ensure_ascii=False))
