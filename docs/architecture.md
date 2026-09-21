# 代码与开发说明

| 文件 | 职责 |
| --- | --- |
| config.py | 加载路径、验证profile与队列配置 |
| labels.py | 纯函数标签排版、边界检查、Code128/QR编码、单张ZPL |
| feishu.py | 调用官方CLI，投影必要字段，读取NDJSON并更新状态 |
| printer.py | Windows RAW打印API，完整写入检查与失败中止 |
| worker.py | 队列消费、SQLite去重、结果回写恢复、进程锁、轮转日志 |
| cli.py | editor/preview/run/stop/resume入口 |
| templates.py | 毫米制模板校验、字段绑定、可变尺寸渲染 |
| editor.py / web/ | 本机HTTP编辑器、模板存储、可视化排版界面 |

## 任务协议

队列任务记录ID是幂等键的一部分：`[base_token, queue_table, record_id]`。同一源记录每次按钮点击产生新的队列ID，因此支持显式重印。队列保存点击时字段快照，后来修改源记录不会改变已提交任务。

顺序为：排版 → SQLite持久化“需核对”占位 → 云端标记处理中 → RAW打印 → SQLite保存结果 → 云端回写。崩溃后的占位记录不重新发送，只回写需核对。结果回写失败只重试状态同步。

这种设计优先防止静默重复打印；无法原子提交飞书、SQLite与Windows打印机三套系统。发出前状态更新失败也会要求人工核对，而不是自动重试打印。

本地锁仅保护同一runtime目录；不同电脑或不同runtime目录不能共同消费同一队列。一个worker可顺序处理多个profile；每轮每个profile最多50条，再从首批剩余待打印任务继续。暂不保证严格FIFO。

## 数据与网络

队列worker只向飞书发起出站请求，不监听端口；单独启动的编辑器仅监听本机回环地址，不开放公网端口。临时NDJSON、日志和SQLite留在被git忽略的runtime目录；日志记录任务ID和错误信息，不主动输出凭证。异常消息也可能含业务信息，不应把完整runtime目录上传公开仓库。

## 开发测试

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
```

测试使用虚构示例、模拟Feishu/Windows打印调用，以及独立ZXing解码器。Linux可运行测试及预览，但实际队列worker与打印只支持Windows。

普通新布局可通过编辑器保存JSON模板，profile使用kind=template及template_path；字段数量可配置。特殊固定模板可在labels.py定义纯渲染函数。不要在render中调用外部服务或实际打印。

ZPL以单色位图 `^GFA` 发送，避免打印机缺少中文字体。`^PW`、`^LL`取渲染图像的像素宽高，`^PQ1`指定一张副本。位图字节按ZPL极性翻转，行尾填白。

编辑器仅监听127.0.0.1，校验Host、Origin和随机页面token，不提供打印接口。模板文件名受限，原子保存；HTML/JS/CSS随Python包分发。浏览器草稿可能包含预览数据；保存的模板不包含预览行，Logo以PNG嵌入模板。

参考：[Windows RAW打印接口](https://learn.microsoft.com/en-us/windows/win32/printdocs/sending-data-directly-to-a-printer)、[Zebra ZPL手册](https://cpws.zebra.com/cpws/docs/zpl/zpl_manual.pdf)、[飞书CLI](https://github.com/larksuite/cli)。
