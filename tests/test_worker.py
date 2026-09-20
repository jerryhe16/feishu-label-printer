from unittest.mock import Mock

import pytest
from PIL import Image

from feishu_label_printer.worker import Processor


@pytest.fixture
def profile(config):
    return config["profiles"][0]


@pytest.fixture
def row():
    return {"record_id": "recTest", "自动料号": "100001-A00", "零件名称": "Demo", "规格描述": "10x20"}


def make(config, tmp_path, api, sender):
    return Processor(config, api, tmp_path / "jobs.sqlite3", sender,
                     renderer=lambda *args: Image.new("1", (354, 236), 1))


def test_duplicate_and_restart_do_not_reprint(config, profile, row, tmp_path):
    api, sender = Mock(), Mock(return_value=123)
    worker = make(config, tmp_path, api, sender)
    worker.process(profile, row)
    worker.process(profile, row)
    worker.close()
    worker = make(config, tmp_path, api, sender)
    worker.process(profile, row)
    worker.close()
    sender.assert_called_once()
    assert api.status.call_args.args[2] == "已发送"


def test_spooler_failure_is_not_retried(config, profile, row, tmp_path):
    api, sender = Mock(), Mock(side_effect=OSError("spooler unavailable"))
    worker = make(config, tmp_path, api, sender)
    worker.process(profile, row)
    worker.process(profile, row)
    worker.close()
    sender.assert_called_once()
    assert api.status.call_args.args[2] == "需核对"


def test_lost_cloud_ack_reconciles_without_reprinting(config, profile, row, tmp_path):
    api, sender = Mock(), Mock(return_value=123)
    api.status.side_effect = [None, RuntimeError("network"), None]
    worker = make(config, tmp_path, api, sender)
    with pytest.raises(RuntimeError):
        worker.process(profile, row)
    worker.close()
    worker = make(config, tmp_path, api, sender)
    worker.reconcile(profile)
    worker.close()
    sender.assert_called_once()
    assert api.status.call_args.args[2] == "已发送"


def test_failure_after_claim_does_not_send_on_restart(config, profile, row, tmp_path):
    api, sender = Mock(), Mock()
    api.status.side_effect = RuntimeError("network")
    worker = make(config, tmp_path, api, sender)
    with pytest.raises(RuntimeError):
        worker.process(profile, row)
    worker.close()
    api.status.side_effect = None
    worker = make(config, tmp_path, api, sender)
    worker.reconcile(profile)
    worker.process(profile, row)
    worker.close()
    sender.assert_not_called()
    assert api.status.call_args.args[2] == "需核对"


def test_invalid_layout_does_not_send(config, profile, row, tmp_path):
    api, sender = Mock(), Mock()
    worker = make(config, tmp_path, api, sender)
    worker.renderer = Mock(side_effect=ValueError("too long"))
    worker.process(profile, row)
    worker.close()
    sender.assert_not_called()
    assert api.status.call_args.args[2] == "排版失败"
