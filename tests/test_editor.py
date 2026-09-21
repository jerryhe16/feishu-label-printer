import http.client
import json
import re
import threading

import pytest

from feishu_label_printer.editor import TemplateStore, make_server, starter_templates


def test_store_roundtrip_and_overwrite(tmp_path,config):
    store=TemplateStore(tmp_path)
    template=starter_templates(config["fonts"])["material"]
    store.save("物料-30x20",template)
    assert store.load("物料-30x20")==template
    template["page"]["width_mm"]=40
    store.save("物料-30x20",template)
    assert store.load("物料-30x20")["page"]["width_mm"]==40
    assert len(store.list())==1


@pytest.mark.parametrize("name",["../secret","a/b","a\\b","C:secret",".",""])
def test_template_path_rejected(tmp_path,name):
    with pytest.raises(ValueError):TemplateStore(tmp_path).path(name)


@pytest.fixture
def service(config,tmp_path):
    server=make_server(config,tmp_path,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    port=server.server_address[1]
    def request(method,path,payload=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",port,timeout=5)
        body=None if payload is None else json.dumps(payload).encode()
        conn.request(method,path,body=body,headers=headers or {})
        result=conn.getresponse();data=result.read();status=result.status;conn.close()
        return status,data
    try:yield request,port
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def token_for(request):
    status,html=request("GET","/")
    assert status==200
    return re.search(rb'name="editor-token" content="([^"]+)"',html)[1].decode()


def test_http_preview_save_load_and_origin(service,config):
    request,port=service;token=token_for(request)
    headers={"X-Editor-Token":token,"Content-Type":"application/json"}
    template=starter_templates(config["fonts"])["material"]
    row={"自动料号":"100001-A00","零件名称":"Demo","规格描述":"10x20"}
    status,body=request("POST","/api/render",{"template":template,"row":row},headers)
    assert status==200 and json.loads(body)["image"].startswith("data:image/png;base64,")
    assert request("POST","/api/templates",{"name":"sample","template":template},headers)[0]==200
    status,body=request("GET","/api/templates?name=sample",headers=headers)
    assert status==200 and json.loads(body)["template"]==template
    assert request("POST","/api/templates",{"name":"sample","template":template},dict(headers,Origin="https://evil.example"))[0]==403
    assert request("GET","/api/bootstrap")[0]==403
    assert request("GET","/",headers={"Host":"evil.example"})[0]==403


def test_invalid_template_is_reported(service):
    request,_=service
    headers={"X-Editor-Token":token_for(request)}
    status,body=request("POST","/api/validate",{"template":{"version":3}},headers)
    assert status==400 and "version" in json.loads(body)["error"]
