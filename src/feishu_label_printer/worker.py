import json
import logging
import os
import sqlite3
import time
from contextlib import contextmanager

from .config import resolve
from .feishu import Feishu
from .labels import render, to_zpl
from .printer import send_raw


class Processor:
    """One consumer per queue; durable local claim before the irreversible spool call."""
    def __init__(self, config, api, database, sender=send_raw, renderer=render):
        self.config, self.api = config, api
        self.sender, self.renderer = sender, renderer
        self.db = sqlite3.connect(database)
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            key TEXT PRIMARY KEY, base TEXT, queue TEXT, record TEXT,
            state TEXT, detail TEXT, synced INTEGER NOT NULL DEFAULT 0)""")
        self.db.commit()

    def close(self):
        self.db.close()

    def sync(self, profile, key, record, state, detail):
        self.api.status(profile, record, state, detail)
        self.db.execute("UPDATE jobs SET synced=1 WHERE key=?", (key,))
        self.db.commit()

    def reconcile(self, profile):
        # Retry status writes, never the printer send. Handles lost acknowledgements/crashes.
        for key, record, state, detail in self.db.execute(
            "SELECT key,record,state,detail FROM jobs WHERE base=? AND queue=? AND synced=0",
            (profile["base_token"], profile["queue_table"]),
        ).fetchall():
            self.sync(profile, key, record, state, detail)

    def process(self, profile, row):
        record = row["record_id"]
        key = json.dumps([profile["base_token"], profile["queue_table"], record])
        old = self.db.execute("SELECT state,detail FROM jobs WHERE key=?", (key,)).fetchone()
        if old:
            self.sync(profile, key, record, *old)
            return
        try:
            image = self.renderer(self.config, profile, [row.get(f, "") for f in profile["fields"]])
        except (ValueError, OSError) as error:
            self.api.status(profile, record, "排版失败", str(error))
            return
        uncertain = "发送阶段中断或结果未知；核对实物后重新点击按钮，不自动重发"
        self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,0)",
                        (key, profile["base_token"], profile["queue_table"], record, "需核对", uncertain))
        self.db.commit()
        # A failed status update leaves an uncertain local claim, but never causes a duplicate send.
        self.api.status(profile, record, "处理中", "已由本机接收，请勿重复点击")
        try:
            job = self.sender(profile["printer"], to_zpl(image), f"Feishu label {record}")
            state, detail = "已发送", f"Windows打印任务 {job}；已交给打印队列，请检查实物"
        except Exception as error:
            state, detail = "需核对", f"{type(error).__name__}: {error}; 核对打印队列及实物后再提交新任务"
        self.db.execute("UPDATE jobs SET state=?,detail=?,synced=0 WHERE key=?", (state, detail[:500], key))
        self.db.commit()
        self.sync(profile, key, record, state, detail[:500])
        logging.info("profile=%s record=%s state=%s", profile["name"], record, state)


@contextmanager
def single_instance(directory):
    if os.name != "nt":
        raise RuntimeError("Queue worker runs on Windows only; preview and tests are cross-platform")
    import msvcrt
    lock = open(directory / "worker.lock", "a+b")
    try:
        if lock.seek(0, 2) == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("Another worker already owns this runtime directory") from None
        yield
    finally:
        lock.close()


def runtime_path(config):
    return resolve(config, config.get("runtime_dir", "runtime")).resolve()


def run(config, once=False):
    directory = runtime_path(config)
    directory.mkdir(parents=True, exist_ok=True)
    stop = directory / "STOP"
    if stop.exists():
        raise RuntimeError("STOP marker exists; remove it only when ready to resume queued printing")
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(directory / "bridge.log", maxBytes=2_000_000,
                                                     backupCount=3, encoding="utf-8")])
    with single_instance(directory):
        cli = config["cli_path"]
        if "/" in cli or "\\" in cli:
            cli = str(resolve(config, cli))
        api = Feishu(cli, directory)
        processor = Processor(config, api, directory / "jobs.sqlite3")
        failures = 0
        try:
            logging.info("Worker started with %s profile(s)", len(config["profiles"]))
            while not stop.exists():
                for profile in config["profiles"]:
                    if stop.exists():
                        break
                    try:
                        processor.reconcile(profile)
                        for row in api.pending(profile):
                            if stop.exists():
                                break
                            processor.process(profile, row)
                    except Exception:
                        failures += 1
                        logging.exception("Profile poll failed: %s", profile["name"])
                if once:
                    break
                time.sleep(float(config.get("poll_seconds", 5)))
        finally:
            processor.close()
        if once and failures:
            raise RuntimeError("One or more queue operations failed; see runtime/bridge.log")
