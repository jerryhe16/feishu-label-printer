import copy
import json
import base64
import io

import pytest
import zxingcpp
from PIL import Image, ImageOps

from feishu_label_printer.editor import starter_templates
from feishu_label_printer.labels import render, to_zpl
from feishu_label_printer.templates import render_template, required_fields, validate


@pytest.fixture
def row():
    return {"自动料号":"100001-A00","零件名称":"Demo part","规格描述":"10x20",
            "样机编号":"Demo V1-001-L","记录链接":"https://example.feishu.cn/base/BASE_DEMO?table=tblDemo&record=recDemo001"}


@pytest.fixture
def template(config):
    return starter_templates(config["fonts"])["material"]


def test_template_barcode_decodes(config, template, row):
    image, warnings = render_template(config, template, row)
    assert not warnings
    assert image.size == (354,236)
    assert [x.text for x in zxingcpp.read_barcodes(image.convert("L"))] == [row["自动料号"]]


def test_template_qr_decodes(config,row):
    image,warnings=render_template(config,starter_templates(config["fonts"])["prototype"],row)
    assert not warnings
    assert [x.text for x in zxingcpp.read_barcodes(image.convert("L"))] == [row["记录链接"]]


def test_size_dpi_and_zpl(config,template,row):
    template["page"].update(width_mm=50,height_mm=30,dpi=600)
    image,_=render_template(config,template,row)
    assert image.size==(1181,709)
    assert b"^PW1181^LL709" in to_zpl(image)


def test_offset_and_margin_are_additive(config,template,row):
    image,_=render_template(config,template,row)
    first=ImageOps.invert(image.convert("L")).getbbox()
    template["page"]["height_mm"]=30
    template["page"]["offset_y_mm"]=1
    template["page"]["margins_mm"]["top"]=2
    shifted,_=render_template(config,template,row)
    second=ImageOps.invert(shifted.convert("L")).getbbox()
    assert second[1]-first[1] in (23,24)


def test_disabled_field_not_required(config,template,row):
    template["elements"][2]["enabled"]=False
    row.pop("规格描述")
    render_template(config,template,row)
    assert required_fields(template)==["自动料号","零件名称"]


def test_missing_field_explicit_error(config,template,row):
    row.pop("零件名称")
    with pytest.raises(ValueError,match="缺少字段"):
        render_template(config,template,row)


def test_text_overflow_rejected(config,template,row):
    template["elements"][1]["font_size_pt"]=40
    with pytest.raises(ValueError,match="文字超出"):
        render_template(config,template,row)


def test_overlap_warns_and_printing_rejects(config,template,row,tmp_path):
    template["elements"][1]["y_mm"]=0
    _,warnings=render_template(config,template,row)
    assert any("重叠" in item for item in warnings)
    path=tmp_path/"template.json";path.write_text(json.dumps(template),encoding="utf-8")
    profile={"kind":"template","template_path":str(path),"fields":list(row)}
    with pytest.raises(ValueError,match="重叠"):
        render(config,profile,list(row.values()))


def test_worker_template_supports_arbitrary_fields(config,template,row,tmp_path):
    path=tmp_path/"template.json";path.write_text(json.dumps(template),encoding="utf-8")
    profile={"kind":"template","template_path":str(path),"fields":list(row)}
    assert render(config,profile,list(row.values())).size==(354,236)


@pytest.mark.parametrize("value",[float("nan"),float("inf"),-1,"30",True])
def test_invalid_numbers_rejected(template,value):
    template["page"]["width_mm"]=value
    with pytest.raises(ValueError):validate(template)


def test_offset_cannot_crop(config,template,row):
    template["page"]["offset_y_mm"]=10
    with pytest.raises(ValueError,match="超出纸张"):
        render_template(config,template,row)


def test_qr_requires_integer_modules(config,row):
    template=starter_templates(config["fonts"])["prototype"]
    template["elements"][1]["width_mm"]=4
    with pytest.raises(ValueError,match="二维码太密"):
        render_template(config,template,row)


def test_duplicate_ids_rejected(template):
    template["elements"].append(copy.deepcopy(template["elements"][0]))
    with pytest.raises(ValueError,match="唯一"):
        validate(template)


def test_embedded_logo_transparency(config):
    logo = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    logo.paste((0, 0, 0, 255), (5, 5, 15, 15))
    stream = io.BytesIO()
    logo.save(stream, format="PNG")
    template = starter_templates(config["fonts"])["blank"]
    template["elements"] = [{"id":"logo", "type":"image", "width_mm":10,
        "height_mm":10, "data_url":"data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()}]
    image, warnings = render_template(config, template, {})
    assert not warnings
    ink = ImageOps.invert(image.convert("L"))
    assert ink.getbbox() is not None
    assert ink.histogram()[255] == 100


def test_invalid_font_rejected(template):
    template["elements"][0]["font"] = []
    with pytest.raises(ValueError, match="字体名称"):
        validate(template)
