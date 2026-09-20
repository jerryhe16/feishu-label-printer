# 代码与开发说明

| 文件 | 职责 |
| --- | --- |
| config.py | 加载路径、验证profile与队列配置 |
| labels.py | 纯函数标签排版、边界检查、Code128/QR编码、单张ZPL |
| feishu.py | 调用官方CLI，投影必要字段，读取NDJSON并更新状态 |
| printer.py | Windows RAW打印API，完整写入检查与失败中止 |
| worker.py | 队列消费、SQLite去重、结果回写恢复、进程锁、轮转日志 |
| cli.py | preview/run/stop/resume入口 |

## 任务协议

队列任务记录ID是幂等键的一部分：`[base_token, queue_table, record_id]`。同一源记录每次按钮点击产生新的队列ID，因此支持显式重印。队列保存点击时字段快照，后来修改源记录不会改变已提交任务。

顺序为：排版 → SQLite持久化“需核对”占位 → 云端标记处理中 → RAW打印 → SQLite保存结果 → 云端回写。崩溃后的占位记录不重新发送，只回写需核对。结果回写失败只重试状态同步。

这种设计优先防止静默重复打印；无法原子提交飞书、SQLite与Windows打印机三套系统。发出前状态更新失败也会要求人工核对，而不是自动重试打印。

本地锁仅保护同一runtime目录；不同电脑或不同runtime目录不能共同消费同一队列。一个worker可顺序处理多个profile；每轮每个profile最多50条，再从首批剩余待打印任务继续。暂不保证严格FIFO。

## 数据与网络

后台只向飞书发起出站请求，不启动HTTP服务器或开放公网端口。临时NDJSON、日志和SQLite留在被git忽略的runtime目录；日志记录任务ID和错误信息，不主动输出凭证。异常消息也可能含业务信息，不应把完整runtime目录上传公开仓库。

## 开发测试

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
```

测试使用虚构示例、模拟Feishu/Windows打印调用，以及独立ZXing解码器。Linux可运行测试及预览，但实际队列worker与打印只支持Windows。

添加新模板时在labels.py定义纯渲染函数、增加配置校验和注册入口，明确三个队列输入字段，补充真实解码或内容完整性测试。不要在render中调用外部服务或实际打印。

ZPL以单色位图 `^GFA` 发送，避免打印机缺少中文字体。`^PW354`、`^LL236`和`^PQ1`分别指定宽度、长度和一张副本。位图字节按ZPL极性翻转，行尾填白。

参考：[Windows RAW打印接口](https://learn.microsoft.com/en-us/windows/win32/printdocs/sending-data-directly-to-a-printer)、[Zebra ZPL手册](https://cpws.zebra.com/cpws/docs/zpl/zpl_manual.pdf)、[飞书CLI](https://github.com/larksuite/cli)。
