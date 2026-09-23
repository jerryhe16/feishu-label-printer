"""Read-only Feishu data source for the local label editor."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse, parse_qs

from .templates import required_fields


def cli(config, command, *args, cwd=None):
    configured = config.get('cli_path', '')
    candidates = [configured, str(Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@larksuite/cli/bin/lark-cli.exe'), shutil.which('lark-cli')]
    executable = next((p for p in candidates if p and Path(p).is_file() and (os.name != 'nt' or Path(p).suffix.lower() == '.exe')), None)
    if not executable:
        raise ValueError('找不到飞书 CLI，请在配置中设置 cli_path 并完成用户登录。')
    result = subprocess.run([executable, 'base', command, '--as', 'user', *args], cwd=cwd,
        capture_output=True, encoding='utf-8', timeout=90, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise ValueError('飞书 CLI 未返回有效结果，请检查登录和网络。') from None
    if result.returncode or data.get('ok') is False:
        raise ValueError('读取飞书失败，请检查 CLI 用户登录、表格访问权限和网络。')
    return data.get('data', data)


def connect(config, url):
    if not isinstance(url, str) or len(url) > 3000:
        raise ValueError('请输入多维表格链接')
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or not any(parsed.hostname.endswith('.'+d) for d in ('feishu.cn','larksuite.com','larkoffice.com')):
        raise ValueError('请输入飞书或 Lark 的 HTTPS 多维表格链接')
    resolved = cli(config, '+url-resolve', '--url', url)
    base = resolved.get('base_token')
    table = resolved.get('table_id') or (resolved.get('block_id') if resolved.get('block_type') == 'table' else None)
    if not base or not table:
        raise ValueError('链接没有定位到数据表，请复制打开具体数据表后的链接（含 table 参数）。')
    data = cli(config, '+field-list', '--base-token', base, '--table-id', table)
    fields = [{'id': f['id'], 'name': f['name'], 'type': f.get('type',''), 'supported': f.get('type') not in ('button','attachment')} for f in data['fields']]
    return {'base_token':base,'table_id':table,'view_id':resolved.get('view_id') or parse_qs(parsed.query).get('view',[''])[0],
            'url':url,'name':resolved.get('block_name') or table,'fields':fields}


def cell(value):
    if value is None: return ''
    if isinstance(value, bool): return '是' if value else '否'
    if isinstance(value, list): return '、'.join(cell(v) for v in value)
    if isinstance(value, dict): return str(value.get('text') or value.get('name') or value.get('url') or value.get('id') or json.dumps(value,ensure_ascii=False))
    return str(value)


def records(config, source, field_ids, offset=0):
    available = {f['id']: f for f in source['fields'] if f['supported']}
    if not isinstance(field_ids,list) or not 1 <= len(field_ids) <= 60 or any(not isinstance(f,str) or f not in available for f in field_ids):
        raise ValueError('请勾选 1 至 60 个可预览字段')
    if not isinstance(offset,int) or isinstance(offset,bool) or not 0 <= offset <= 100000:
        raise ValueError('无效分页位置')
    args = ['--base-token',source['base_token'],'--table-id',source['table_id'],'--limit','20','--offset',str(offset)]
    if source.get('view_id'): args += ['--view-id',source['view_id']]
    for fid in dict.fromkeys(field_ids): args += ['--field-id',fid]
    with tempfile.TemporaryDirectory(prefix='label-preview-') as directory:
        meta = cli(config,'+record-list',*args,'--format','ndjson','--output','rows.ndjson','--overwrite',cwd=directory)
        rows = [json.loads(line) for line in (Path(directory)/'rows.ndjson').read_text(encoding='utf-8').splitlines() if line]
    return {'records':[{'id':r['record_id'],'values':{available[f]['name']:cell(r.get(available[f]['name'],r.get(f))) for f in field_ids}} for r in rows],
            'has_more':bool(meta.get('has_more')),'next_offset':meta.get('next_offset',offset+len(rows))}


def readiness(config, template):
    required = required_fields(template)
    source = template.get('data_source') or {}
    profiles = [p for p in config.get('profiles',[]) if source.get('base_token') == p.get('base_token') and source.get('table_id') == p.get('source_table')]
    if not profiles:
        return '尚未匹配本机打印队列配置。需要接入的字段：' + ('、'.join(required) or '无动态字段') + '。保存模板不会自动修改飞书工作流。'
    details = []
    for p in profiles:
        missing = [f for f in required if f not in p.get('fields',[])]
        details.append(p['name'] + ('：配置缺少字段 '+ '、'.join(missing) if missing else '：所需字段已列入本机配置') + ('；仍使用固定版式' if p.get('kind') != 'template' else '；请核对 template_path 指向本模板'))
    return '；'.join(details) + '。尚未验证飞书工作流是否复制这些字段，请先测试新任务。'
