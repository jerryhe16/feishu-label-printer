# 飞书队列与按钮配置

每种模板使用一张专用打印队列表。按钮工作流把源记录的值复制进队列，程序只读取队列，不修改源数据。

## 队列字段

所有列均用文本字段即可：

| 队列 | 必需字段 |
| --- | --- |
| 标签打印队列 | 自动料号、零件名称、规格描述、状态、处理结果 |
| 样机标签打印队列 | 样机编号、记录链接、来源记录、状态、处理结果 |

状态初始值必须精确为 `待打印`。程序回写 `处理中`、`已发送`、`排版失败` 或 `需核对`。

## 界面配置方式

1. 在源物料/样机表中新增按钮列，如“打印物料标签”或“打印样机标签”。
2. 创建自动化/工作流，触发条件为点击这列按钮。
3. 添加“新增记录”动作，目标为专用打印队列。
4. 将当前行的料号、名称、规格或样机编号、记录链接、记录ID映射到队列对应字段。
5. 状态填写固定文本“待打印”；每次只新增一条队列记录。
6. 启用工作流，在本机配置中填写队列表ID。

样机的“记录链接”须为已有行链接公式值，形如：

```text
https://YOUR_TENANT.feishu.cn/base/BASE_TOKEN?table=TABLE_ID&record=RECORD_ID
```

二维码须引用当前行本身，不是整张表的视图URL。程序检查域名、Base、表和记录ID一致性。使用者扫码后仍须具备飞书访问权限；本项目不启用公开分享。

## CLI配置方式

以物料模板为例。先用 `base +url-resolve`、`+table-list`、`+field-list` 核对真实表名和字段ID。以下变量均为你自己的数据，示例文件中的 `fld...` 均为占位符。

```powershell
$cli = 'C:\Users\YOUR_USER\AppData\Roaming\npm\node_modules\@larksuite\cli\bin\lark-cli.exe'
$base = 'YOUR_BASE_TOKEN'
$sourceTable = 'YOUR_SOURCE_TABLE_ID'
$fields = Get-Content examples/material-queue-fields.json -Raw
& $cli base +table-create --base-token $base --name '标签打印队列' --fields $fields --as user
```

保存返回的 `data.table.id`。修改 `examples/material-workflow.json` 的源表名和三个源字段ID，并更换唯一的 `client_token`，然后执行：

```powershell
& $cli base +workflow-create --base-token $base --json '@examples/material-workflow.json' --as user
$button = '{"name":"打印物料标签","type":"button","button_config":{"title":"打印标签"}}'
& $cli base +field-create --base-token $base --table-id $sourceTable --json $button --as user
```

保存工作流返回的 `data.workflow_id`（wkf开头）及按钮返回的 `data.field.id`：

```powershell
$workflow = 'wkfREPLACE'
$field = 'fldREPLACE'
& $cli base +button-rule-bind --base-token $base --table-id $sourceTable --field-id $field --workflow-id $workflow --as user
& $cli base +workflow-enable --base-token $base --workflow-id $workflow --as user
& $cli base +button-rule-get --base-token $base --table-id $sourceTable --field-id $field --as user
```

样机模板对应 `prototype-queue-fields.json`、`prototype-workflow.json`。替换样机编号字段与行链接字段ID。`$.click.recordId`是触发器提供的当前行记录ID，不需要自己生成。

这些命令会修改飞书表。不要对已部署的同一目标重复执行创建命令；创建部分成功时保留已返回ID，从未完成步骤继续。CLI需要当前用户对源表、队列和工作流有相应权限。
