import json
from pathlib import Path
import pytest
from feishu_label_printer import editor_source as source
from feishu_label_printer.editor import starter_templates


def test_connect_resolves_table_and_filters_types(monkeypatch):
    def cli(config, command, *args, **kwargs):
        if command == '+url-resolve': return {'base_token':'baseDemo','block_id':'tblDemo','block_type':'table','block_name':'Demo'}
        return {'fields':[{'id':'fld1','name':'编号','type':'text'},{'id':'fld2','name':'按钮','type':'button'}]}
    monkeypatch.setattr(source,'cli',cli)
    result=source.connect({},'https://example.feishu.cn/base/baseDemo?table=tblDemo&view=vewDemo')
    assert result['table_id']=='tblDemo' and result['view_id']=='vewDemo'
    assert not result['fields'][1]['supported']


@pytest.mark.parametrize('url',['http://example.feishu.cn/base/a','https://evil.test/base/a','https://feishu.cn.evil.test/base/a'])
def test_reject_non_feishu_url(url):
    with pytest.raises(ValueError):source.connect({},url)


def test_records_project_selected_fields_and_honor_view(monkeypatch):
    def cli(config,command,*args,cwd=None):
        assert command=='+record-list'
        assert args[args.index('--view-id')+1]=='vewDemo'
        assert args.count('--field-id')==1
        assert args[args.index('--field-id')+1]=='fld1'
        Path(cwd,'rows.ndjson').write_text(json.dumps({'record_id':'recDemo','编号':['A','B']})+'\n',encoding='utf-8')
        return {'has_more':True,'next_offset':20}
    monkeypatch.setattr(source,'cli',cli)
    data={'base_token':'baseDemo','table_id':'tblDemo','view_id':'vewDemo','fields':[{'id':'fld1','name':'编号','supported':True}]}
    result=source.records({},data,['fld1'])
    assert result['records'][0]['values']=={'编号':'A、B'}
    assert result['has_more'] and result['next_offset']==20
    with pytest.raises(ValueError):source.records({},data,['missing'])


def test_readiness_does_not_claim_workflow_verified():
    template=starter_templates({})['material']
    template['data_source']={'base_token':'baseDemo','table_id':'tblDemo'}
    config={'profiles':[{'name':'demo','base_token':'baseDemo','source_table':'tblDemo','fields':['自动料号'],'kind':'material'}]}
    message=source.readiness(config,template)
    assert '零件名称' in message and '规格描述' in message and '尚未验证' in message
    assert '尚未匹配' in source.readiness({},template)
