"""Loopback-only label editor; no remote fonts, telemetry or printing endpoints."""
import base64
import io
import json
import re
import secrets
import subprocess
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .labels import to_zpl
from .templates import render_template, required_fields, validate
from . import editor_source


def editor_config(path=None):
    root = Path.cwd()
    if path and Path(path).is_file():
        root = Path(path).resolve().parent
        config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    else:
        config = {"fonts": {"text": "C:/Windows/Fonts/msyh.ttc", "mono": "C:/Windows/Fonts/consola.ttf",
                            "dot": "assets/fonts/Doto.ttf"}}
    config["_root"] = root
    fallback = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    fonts = {}
    for key, value in config.get("fonts", {}).items():
        font = Path(value)
        font = font if font.is_absolute() else root / font
        if font.is_file():
            fonts[key] = str(font)
        elif fallback.is_file() and key in ("text", "mono"):
            fonts[key] = str(fallback)
    if "text" not in fonts:
        raise ValueError("找不到文字字体，请用 --config 指定含 fonts.text 的配置文件")
    fonts.setdefault("mono", fonts["text"])
    config["fonts"] = fonts
    return config


def starter_templates(fonts):
    page = {"width_mm":30,"height_mm":20,"dpi":300,"margins_mm":{"left":1,"right":1,"top":1,"bottom":1},
            "offset_x_mm":0,"offset_y_mm":0}
    def field(eid, name, kind, key, x,y,w,h, **extra):
        return {"id":eid,"name":name,"type":kind,"enabled":True,"source":{"kind":"field","key":key},
                "x_mm":x,"y_mm":y,"width_mm":w,"height_mm":h,**extra}
    material = {"version":1,"name":"物料标签 · 30×20","page":page,"elements":[
        field("code","料号条码","barcode","自动料号",0,0,28,8,font="mono",font_size_pt=5.5,show_text=True),
        field("name","零件名称","text","零件名称",0,9,28,4,font="text",font_size_pt=6.5),
        field("spec","规格描述","text","规格描述",0,14,28,4,font="text",font_size_pt=5.5)]}
    prototype = {"version":1,"name":"样机标签 · 30×20","page":page,"elements":[
        {"id":"logo-text","name":"Logo占位文字","type":"text","enabled":True,"source":{"kind":"literal","value":"YOUR LOGO"},
         "x_mm":0,"y_mm":6,"width_mm":12.5,"height_mm":3,"font":"mono","font_size_pt":5,"align":"center"},
        field("qr","记录二维码","qr","记录链接",13,0,15,15),
        field("serial","样机编号","text","样机编号",0,15,28,3,font="dot" if "dot" in fonts else "mono",font_size_pt=7.5,align="center")]}
    blank = {"version":1,"name":"新标签","page":page,"elements":[]}
    return {"material":material,"prototype":prototype,"blank":blank}


class TemplateStore:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def path(self, name):
        if not isinstance(name,str) or not re.fullmatch(r"[\w\- ]{1,80}", name, flags=re.UNICODE):
            raise ValueError("文件名仅可用中英文、数字、空格、下划线和短横线，最多80字")
        path = (self.directory / (name+".json")).resolve()
        if path.parent != self.directory:
            raise ValueError("无效的模板路径")
        return path

    def list(self):
        return [{"file":p.stem,"modified":int(p.stat().st_mtime)} for p in sorted(self.directory.glob("*.json"))[:200]
                if not p.is_symlink()]

    def load(self, name):
        return validate(json.loads(self.path(name).read_text(encoding="utf-8-sig")))

    def save(self, name, template):
        validate(template)
        path = self.path(name)
        with self.lock:
            with tempfile.NamedTemporaryFile(mode="w",suffix=".tmp",dir=self.directory,encoding="utf-8",delete=False) as out:
                json.dump(template,out,ensure_ascii=False,indent=2)
                temporary = Path(out.name)
            try:
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)


def make_server(config, directory, port=8765):
    store = TemplateStore(directory)
    token = secrets.token_urlsafe(32)
    sources = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, kind="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body,ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'")
            self.end_headers()
            self.wfile.write(body)

        def permitted(self, api=False):
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}",f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                self.send(403,{"error":"仅允许本机访问"}); return False
            if api and not secrets.compare_digest(self.headers.get("X-Editor-Token", ""), token):
                self.send(403,{"error":"请重新打开编辑器页面"}); return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://"+h for h in hosts}:
                self.send(403,{"error":"禁止跨站请求"}); return False
            return True

        def do_GET(self):
            url = urlparse(self.path)
            if not self.permitted(url.path.startswith("/api/")): return
            try:
                if url.path == "/api/bootstrap":
                    self.send(200,{"templates":starter_templates(config["fonts"]),"fonts":list(config["fonts"]),
                                   "saved":store.list(),"sample":{"自动料号":"100001-A00","零件名称":"演示零件","规格描述":"DEMO 10x20",
                                   "样机编号":"Demo V1-001-L","记录链接":"https://example.feishu.cn/base/BASE_DEMO?table=tblDemo&record=recDemo001"}})
                elif url.path == "/api/templates":
                    name = parse_qs(url.query).get("name",[None])[0]
                    self.send(200,{"template":store.load(name)} if name else {"saved":store.list()})
                elif url.path in ("/","/app.js","/style.css"):
                    name = "index.html" if url.path == "/" else url.path[1:]
                    body = files("feishu_label_printer").joinpath("web",name).read_bytes()
                    if name == "index.html": body = body.replace(b"__EDITOR_TOKEN__",token.encode())
                    kind = {"index.html":"text/html; charset=utf-8","app.js":"application/javascript; charset=utf-8","style.css":"text/css; charset=utf-8"}[name]
                    self.send(200,body,kind)
                else:
                    self.send(404,{"error":"Not found"})
            except (ValueError, OSError, TypeError, KeyError) as error:
                self.send(400,{"error":str(error)})

        def do_POST(self):
            if not self.permitted(True): return
            try:
                size = int(self.headers.get("Content-Length",0))
                if not 0 < size <= 6_000_000:
                    self.send(413,{"error":"请求过大（最多6MB）"}); return
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload,dict): raise ValueError("请求必须是对象")
                if self.path == "/api/source/connect":
                    source = editor_source.connect(config, payload.get("url"))
                    source_id = secrets.token_urlsafe(16)
                    if len(sources) >= 30: sources.pop(next(iter(sources)))
                    sources[source_id] = source
                    self.send(200, {**source, "connection_id":source_id})
                    return
                if self.path == "/api/source/records":
                    source = sources.get(payload.get("connection_id", ""))
                    if not source: raise ValueError("请先连接或重新连接数据表")
                    self.send(200, editor_source.records(config, source, payload.get("fields"), payload.get("offset",0)))
                    return
                template = payload["template"]
                if self.path == "/api/source/check":
                    self.send(200, {"message":editor_source.readiness(config, template)})
                    return
                if self.path == "/api/validate":
                    validate(template)
                    self.send(200,{"valid":True,"fields":required_fields(template)})
                elif self.path == "/api/templates":
                    store.save(payload["name"],template)
                    self.send(200,{"saved":store.list(),"file":payload["name"]})
                elif self.path in ("/api/render","/api/export-zpl"):
                    issues = [] if self.path == "/api/render" else None
                    image, warnings = render_template(config,template,payload.get("row",{}), issues=issues)
                    if self.path == "/api/export-zpl":
                        if warnings: raise ValueError("请先处理排版提示："+"；".join(warnings))
                        self.send(200,to_zpl(image),"application/octet-stream")
                    else:
                        output = io.BytesIO(); image.save(output,format="PNG")
                        self.send(200,{"image":"data:image/png;base64,"+base64.b64encode(output.getvalue()).decode(),
                                       "width":image.width,"height":image.height,"warnings":warnings,"issues":issues,"fields":required_fields(template)})
                else:
                    self.send(404,{"error":"Not found"})
            except (ValueError, OSError, TypeError, KeyError, OverflowError, subprocess.TimeoutExpired) as error:
                self.send(400,{"error":str(error)})
    server = ThreadingHTTPServer(("127.0.0.1",port),Handler)
    server.daemon_threads = True
    return server


def serve(config, directory, port, open_browser=True):
    server = make_server(config,directory,port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Label editor: {url}\nTemplates: {Path(directory).resolve()}\nCtrl+C to stop.",flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
