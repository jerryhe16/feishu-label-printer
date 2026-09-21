# 安装与配置

## 1. 准备打印机与CLI

安装Zebra Windows驱动，选择ZPL驱动，连接USB并装入30×20mm标签。确认实际打印机为300 dpi。

```powershell
Get-Printer | Select-Object Name, DriverName, PortName
npm install -g @larksuite/cli
lark-cli --version
lark-cli config init --new
lark-cli auth login --domain base
lark-cli auth status --json --verify
```

初始化和登录需在飞书官方页面完成。只申请多维表格业务域；本程序不需要邮箱、消息等其他域权限。CLI配置流程以[官方说明](https://github.com/larksuite/cli)为准。本项目最初使用lark-cli 1.0.96验证；CLI接口变化时先测试再升级生产环境。

Windows配置中必须指向真正的 `lark-cli.exe`，不要使用npm生成的 `.cmd` 包装器，以免URL中的 `&` 和JSON参数被shell解释。通常路径为：

```text
C:/Users/YOUR_USER/AppData/Roaming/npm/node_modules/@larksuite/cli/bin/lark-cli.exe
```

## 2. 配置项目

复制 `config.example.json` 为 `config.local.json`。路径以配置文件所在目录为基准，可使用绝对路径。

| 配置项 | 用途 |
| --- | --- |
| `cli_path` | 官方CLI可执行文件路径 |
| `runtime_dir` | 日志、去重数据库和临时记录文件目录 |
| `poll_seconds` | 轮询间隔，默认5秒；多队列和网络调用会增加总延迟 |
| `fonts.text` / `fonts.mono` | 本机中文字体、料号字体；不随仓库分发 |
| `fonts.dot` | 随仓库附带的Doto点阵字体 |
| `profiles[].name` | 配置内唯一名称 |
| `kind` | `material`、`prototype` 或 `template` |
| `template_path` | `kind=template` 时必填，编辑器保存的JSON模板路径；见[排版工具](editor.md) |
| `base_token` | 所在多维表格应用token |
| `source_table` | 物料/样机源表ID |
| `queue_table` | **专用打印队列表ID**，不能填源表 |
| `printer` | Windows打印机名称，必须完全匹配 |
| `fields` | 队列字段有序列表；物料为料号/名称/规格，样机为编号/URL/源记录ID |
| `vertical_offset_mm` | 正值下移，负值上移；默认1mm约12 dots |
| `status_field` / `result_field` | 可选，默认“状态”与“处理结果” |
| `feishu_host` | 样机链接的确切租户域名 |
| `logo_path` | 样机Logo PNG路径 |

只需要一种模板时删除另一个profile。将自己的Logo保存为 `private-assets/logo.png` 并设置 `logo_path`。建议使用透明或白底黑色图案；程序会按比例缩至154×80像素范围。SVG应先在本机导出PNG，仓库不包含任何具体公司的Logo。

请保留真实配置、Logo、数据库和日志在git忽略目录中。CLI凭证由官方CLI管理，不写入项目配置，也不需要复制access token。

## 3. 启动与停止

先在终端前台启动，点击飞书一条测试记录，确认队列回写与实物：

```powershell
.\.venv\Scripts\python.exe -m feishu_label_printer --config config.local.json run
```

确认后可关闭前台程序，再启动隐藏后台窗口：

```powershell
.\scripts\start.ps1
.\scripts\install-startup.ps1
```

启动项属于当前Windows用户，在该用户登录时运行，不是Windows系统服务；不需要管理员权限。

```powershell
# 请求停止；当前网络/打印操作可能继续完成
.\.venv\Scripts\python.exe -m feishu_label_printer --config config.local.json stop

# 确认旧进程退出后解除停止状态并重新启动
.\.venv\Scripts\python.exe -m feishu_label_printer --config config.local.json resume
.\scripts\start.ps1

# 移除登录启动项，不会停止已运行的进程
.\scripts\remove-startup.ps1
```

STOP标记不会被后台启动自动清除，因此停机维护后需显式 `resume`。正常退出的等待时间取决于当前CLI调用（超时90秒）和Windows打印API。不要通过删除锁文件启动第二个消费者。

## 4. 从原先两套脚本迁移

当前项目不会自动修改或停止旧服务。迁移时：

1. 复制原来的两个Base/源表/队列表ID到本机配置，配置现有队列字段和本机Logo。
2. 停止旧物料及样机后台程序，移除它们各自的Windows登录启动快捷方式。
3. 检查队列，把遗留的“处理中”或“需核对”任务逐条核对。不要将已发送任务重置为“待打印”。
4. 原数据库格式与新项目不同，不直接覆盖新数据库；保留旧库作历史记录。
5. 先预览，再运行新程序，点击一条新的任务验证后安装新启动项。

绝不能让旧程序和新程序同时消费同一队列，否则可能重复打印。
