"""Versioned, millimetre-based label templates shared by editor and queue worker."""
import base64
import io
import math

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.graphics.barcode.code128 import Code128

from .config import resolve

MAX_PIXELS = 12_000_000


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int,float)):
        raise ValueError(f"{name} 必须是数值")
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是数值") from None
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} 须在 {low} 至 {high} 之间")
    return value


def validate(template):
    if not isinstance(template, dict) or template.get("version") != 1:
        raise ValueError("仅支持 version=1 的标签模板")
    if not isinstance(template.get("name"), str) or not template["name"].strip():
        raise ValueError("请输入模板名称")
    page = template.get("page", {})
    if not isinstance(page, dict):
        raise ValueError("page 必须为对象")
    width = number(page.get("width_mm"), "标签宽度", 10, 200)
    height = number(page.get("height_mm"), "标签高度", 10, 200)
    dpi = page.get("dpi", 300)
    if dpi not in (203, 300, 600):
        raise ValueError("分辨率仅支持203、300、600 dpi，请与打印机匹配")
    if round(width * dpi / 25.4) * round(height * dpi / 25.4) > MAX_PIXELS:
        raise ValueError("标签像素过大，请减小尺寸或分辨率")
    margins = page.get("margins_mm", {})
    if not isinstance(margins, dict):
        raise ValueError("margins_mm 必须为对象")
    for key in ("left", "right", "top", "bottom"):
        number(margins.get(key, 0), "页边距", 0, 100)
    if margins.get("left", 0) + margins.get("right", 0) >= width or margins.get("top", 0) + margins.get("bottom", 0) >= height:
        raise ValueError("页边距不能占满标签")
    for key in ("offset_x_mm", "offset_y_mm"):
        number(page.get(key, 0), "打印偏移", -100, 100)
    elements = template.get("elements")
    if not isinstance(elements, list) or len(elements) > 60:
        raise ValueError("elements 必须为数组，最多60个元素")
    ids = set()
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError("元素必须为对象")
        eid = element.get("id")
        if not isinstance(eid, str) or not eid or eid in ids:
            raise ValueError("元素ID必须为非空且唯一的字符串")
        ids.add(eid)
        if element.get("type") not in ("text", "barcode", "qr", "image"):
            raise ValueError("元素类型须为text、barcode、qr或image")
        if "enabled" in element and not isinstance(element["enabled"], bool):
            raise ValueError("enabled 必须为布尔值")
        for key in ("x_mm", "y_mm"):
            number(element.get(key, 0), "元素位置", 0, 200)
        for key in ("width_mm", "height_mm"):
            number(element.get(key), "元素尺寸", 0.5, 200)
        if element["type"] != "image":
            source = element.get("source", {})
            if not isinstance(source, dict) or source.get("kind") not in ("field", "literal"):
                raise ValueError("元素必须绑定字段或固定内容")
            key = "key" if source["kind"] == "field" else "value"
            if not isinstance(source.get(key), str) or len(source[key]) > 4000:
                raise ValueError("字段名/固定内容必须为字符串，最多4000字符")
        if element["type"] in ("text", "barcode"):
            number(element.get("font_size_pt", 7), "字号", 2, 72)
            if not isinstance(element.get("font", "text"), str):
                raise ValueError("字体名称必须为字符串")
            if element.get("align", "left") not in ("left", "center", "right"):
                raise ValueError("文字对齐方式无效")
        if element["type"] == "image":
            data = element.get("data_url", "")
            if not isinstance(data, str) or len(data) > 3_000_000 or not data.startswith("data:image/png;base64,"):
                raise ValueError("Logo须为嵌入的PNG图片且小于2MB")
    return template


def required_fields(template):
    validate(template)
    return list(dict.fromkeys(e["source"]["key"] for e in template["elements"]
                             if e.get("enabled", True) and e["type"] != "image"
                             and e["source"]["kind"] == "field"))


def _content(element, row):
    source = element["source"]
    if source["kind"] == "literal":
        return source["value"]
    if source["key"] not in row:
        raise ValueError(f"缺少字段「{source['key']}」，请补充预览数据或队列字段")
    value = row[source["key"]]
    if value is None:
        return ""
    return str(value) if not isinstance(value, (dict, list)) else json_value(value)


def json_value(value):
    import json
    return json.dumps(value, ensure_ascii=False)


def _font(config, element, dpi):
    key = element.get("font", "text")
    if key not in config.get("fonts", {}):
        raise ValueError(f"字体配置不存在：{key}")
    size = max(1, round(float(element.get("font_size_pt", 7)) * dpi / 72))
    font = ImageFont.truetype(str(resolve(config, config["fonts"][key])), size)
    if key == "dot":
        try:
            axes = font.get_variation_axes()
            font.set_variation_by_axes([min(a["maximum"], max(a["minimum"], 800)) if a["name"] == b"Weight" else a["default"] for a in axes])
        except OSError:
            pass
    return font


def _text(box, value, font, align, wrap):
    draw = ImageDraw.Draw(box)
    lines = []
    for paragraph in value.split("\n"):
        current = ""
        for char in paragraph:
            if draw.textlength(current + char, font=font) > box.width:
                if not wrap or not current:
                    raise ValueError("文字超出宽度，请增大元素宽度或减小字号")
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    line_height = max(1, font.getbbox("Ag国", anchor="lt")[3]) + 2
    for i, line in enumerate(lines):
        y = i * line_height
        width = draw.textlength(line, font=font)
        if width > box.width or (line and draw.textbbox((0, y), line, font=font, anchor="lt")[3] > box.height):
            raise ValueError("文字超出元素高度，请增大高度或减小字号")
        x = {"left": 0, "center": (box.width-width)/2, "right": box.width-width}[align]
        draw.text((x, y), line, font=font, fill=0, anchor="lt")


def render_template(config, template, row):
    validate(template)
    if not isinstance(row, dict):
        raise ValueError("预览数据必须是JSON对象")
    page = template["page"]
    dpi = page.get("dpi", 300)
    scale = dpi / 25.4
    width, height = [round(page[key] * scale) for key in ("width_mm", "height_mm")]
    result = Image.new("L", (width, height), 255)
    margins = page.get("margins_mm", {})
    warnings, boxes = [], []
    for element in template["elements"]:
        if not element.get("enabled", True):
            continue
        name = element.get("name") or element["id"]
        ew, eh = [max(1, round(element[key]*scale)) for key in ("width_mm", "height_mm")]
        if ew * eh > MAX_PIXELS:
            raise ValueError(f"{name}：元素过大")
        x_mm, y_mm = element.get("x_mm", 0), element.get("y_mm", 0)
        if x_mm + element["width_mm"] > page["width_mm"]-margins.get("left", 0)-margins.get("right", 0)+0.001 or y_mm + element["height_mm"] > page["height_mm"]-margins.get("top", 0)-margins.get("bottom", 0)+0.001:
            raise ValueError(f"{name}：元素超出页边距内的可用区域")
        x = round((margins.get("left", 0)+page.get("offset_x_mm", 0)+x_mm)*scale)
        y = round((margins.get("top", 0)+page.get("offset_y_mm", 0)+y_mm)*scale)
        if x < 0 or y < 0 or x+ew > width or y+eh > height:
            raise ValueError(f"{name}：偏移后元素超出纸张，请调整偏移或元素位置")
        box = Image.new("L", (ew, eh), 255)
        try:
            value = "" if element["type"] == "image" else _content(element, row)
            if not value and element["type"] != "image":
                raise ValueError("内容为空")
            if element["type"] == "text":
                _text(box, value, _font(config, element, dpi), element.get("align", "left"), element.get("wrap", True))
            elif element["type"] == "barcode":
                if any(ord(c)<32 or ord(c)>126 for c in value):
                    raise ValueError("Code128仅支持可打印ASCII字符")
                barcode = Code128(value, barWidth=1, humanReadable=False)
                barcode.validate(); barcode.encode(); pattern = barcode.decompose()
                modules = sum(ord(c.lower())-96 for c in pattern)
                unit = ew // (modules+20)
                if unit < 2:
                    raise ValueError("条码太密，请加宽元素；最窄条需至少2打印点")
                draw = ImageDraw.Draw(box)
                text_height = 0
                if element.get("show_text", True):
                    font = _font(config, element, dpi)
                    text_height = font.getbbox(value, anchor="lt")[3]+5
                    if draw.textlength(value, font=font) > ew:
                        raise ValueError("条码下方文字太宽，请减小字号")
                bar_height = eh-text_height
                if bar_height < round(2*scale):
                    raise ValueError("条码高度不足，请增加元素高度或减小字号")
                cursor = (ew-modules*unit)//2
                for char in pattern:
                    size = (ord(char.lower())-96)*unit
                    if char.isupper():
                        draw.rectangle((cursor, 0, cursor+size-1, bar_height-1), fill=0)
                    cursor += size
                if text_height:
                    draw.text(((ew-draw.textlength(value,font=font))/2, bar_height+3), value, font=font, fill=0, anchor="lt")
            elif element["type"] == "qr":
                qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
                qr.add_data(value); qr.make(fit=True)
                module_count = qr.modules_count+8
                unit = min(ew, eh)//module_count
                if unit < 3:
                    raise ValueError("二维码太密，请增大元素；每模块需至少3打印点")
                qr.box_size = unit
                code = qr.make_image(fill_color="black", back_color="white").convert("L")
                box.paste(code, ((ew-code.width)//2, (eh-code.height)//2))
            else:
                raw = base64.b64decode(element["data_url"].split(",",1)[1], validate=True)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format != "PNG" or source.width*source.height > MAX_PIXELS:
                        raise ValueError("Logo必须是合理尺寸的PNG")
                    rgba = source.convert("RGBA")
                    white = Image.new("RGBA", rgba.size, "white")
                    white.alpha_composite(rgba)
                    logo = white.convert("L")
                logo.thumbnail((ew, eh), Image.Resampling.LANCZOS)
                box.paste(logo, ((ew-logo.width)//2, (eh-logo.height)//2))
        except (ValueError, OSError, Image.DecompressionBombError, qrcode.exceptions.DataOverflowError) as error:
            raise ValueError(f"{name}：{error}") from None
        for previous, px, py, pw, ph in boxes:
            if x < px+pw and x+ew > px and y < py+ph and y+eh > py:
                warnings.append(f"「{name}」与「{previous}」区域重叠")
        boxes.append((name,x,y,ew,eh))
        # Transparent white: an upper layer cannot accidentally erase a barcode below.
        ink = ImageOps.invert(box)
        result.paste(0, (x,y,x+ew,y+eh), ink)
    if not boxes:
        warnings.append("没有启用的元素，当前为一张空白标签")
    return result.point(lambda v: 0 if v<160 else 255,"1"), warnings
