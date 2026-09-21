"""Pure raster layouts. Black pixels are printed; no inverted ribbon assumptions."""
from urllib.parse import parse_qs, urlparse

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from reportlab.graphics.barcode.code128 import Code128

from .config import resolve

WIDTH, HEIGHT, DPI = 354, 236, 300  # 30 x 20 mm, rounded to device dots


def _font(config, key, size):
    return ImageFont.truetype(str(resolve(config, config["fonts"][key])), size)


def _finish(image, offset_mm):
    image = image.point(lambda v: 0 if v < 160 else 255, "1")
    offset = round(float(offset_mm) * DPI / 25.4)
    bounds = ImageOps.invert(image.convert("L")).getbbox()
    if bounds and (bounds[1] + offset < 0 or bounds[3] + offset > HEIGHT):
        raise ValueError("偏移后内容超出标签边缘，请调整版式或偏移量")
    shifted = Image.new("1", (WIDTH, HEIGHT), 1)
    shifted.paste(image, (0, offset))
    return shifted


def _wrap(draw, text, font):
    lines, current = [], ""
    for char in " ".join(str(text or "").split()):
        if draw.textlength(current + char, font=font) > WIDTH - 24:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def material(config, profile, values):
    part, name, spec = (str(x or "") for x in values)
    if not part or any(ord(c) < 32 or ord(c) > 126 for c in part):
        raise ValueError("自动料号须为非空可打印ASCII字符")
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    barcode = Code128(part, barWidth=1, humanReadable=False)
    barcode.validate()
    barcode.encode()
    pattern = barcode.decompose()
    modules = sum(ord(c.lower()) - 96 for c in pattern)
    unit = WIDTH // (modules + 20)  # includes 10-module quiet zones on both sides
    if unit < 2:
        raise ValueError("料号过长，30mm宽度无法保持至少2点的条码模块宽度")
    x = (WIDTH - modules * unit) // 2
    for char in pattern:
        width = (ord(char.lower()) - 96) * unit
        if char.isupper():
            draw.rectangle((x, 12, x + width - 1, 73), fill=0)
        x += width
    font = _font(config, "mono", 22)
    width = draw.textlength(part, font=font)
    if width > WIDTH - 24:
        raise ValueError("料号文字超出标签宽度")
    draw.text(((WIDTH - width) / 2, 79), part, font=font, fill=0, anchor="lt")
    for text, y, largest, smallest in [(name, 109, 24, 18), (spec, 169, 22, 17)]:
        for size in range(largest, smallest - 1, -1):
            font = _font(config, "text", size)
            lines = _wrap(draw, text, font)
            if len(lines) <= 2:
                break
        else:
            raise ValueError("名称或规格过长，无法完整显示；请精简内容或增大标签")
        for i, line in enumerate(lines):
            draw.text((12, y + i * (size + 3)), line, font=font, fill=0, anchor="lt")
    return _finish(image, profile.get("vertical_offset_mm", 1))


def prototype(config, profile, values):
    number, link, record = (str(x or "").strip() for x in values)
    if not number or any(ord(c) < 32 or ord(c) > 126 for c in number):
        raise ValueError("样机编号须为非空可打印ASCII字符，避免点阵字体缺字")
    parsed = urlparse(link)
    query = parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.hostname != profile["feishu_host"]
            or parsed.username or parsed.password
            or parsed.path != "/base/" + profile["base_token"]
            or query.get("table") != [profile["source_table"]]
            or query.get("record") != [record] or not record):
        raise ValueError("记录链接与当前样机记录不匹配")
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=3, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white").convert("1")
    if qr_image.width > 165:
        raise ValueError("记录链接过长，二维码超出30×20mm版式")
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    image.paste(qr_image, (WIDTH - 8 - qr_image.width, 12))
    with Image.open(resolve(config, profile["logo_path"])) as source:
        rgba = source.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, "white")
        canvas.alpha_composite(rgba)
        logo = canvas.convert("L")
    logo.thumbnail((154, 80), Image.Resampling.LANCZOS)
    image.paste(logo, (12, 12 + (qr_image.height - logo.height) // 2))
    draw = ImageDraw.Draw(image)
    for size in range(38, 25, -1):
        font = _font(config, "dot", size)
        try:
            axes = font.get_variation_axes()
        except OSError:
            axes = []
        if axes:
            font.set_variation_by_axes([
                min(a["maximum"], max(a["minimum"], 800)) if a["name"] == b"Weight" else a["default"]
                for a in axes
            ])
        width = draw.textlength(number, font=font)
        if width <= 330:
            break
    else:
        raise ValueError("样机编号过长，无法保持点阵字体清晰度")
    draw.text(((WIDTH - width) / 2, 181), number, font=font, fill=0, anchor="lt")
    return _finish(image, profile.get("vertical_offset_mm", 1))


def render(config, profile, values):
    if profile["kind"] == "template":
        import json
        from .templates import render_template
        template = json.loads(resolve(config, profile["template_path"]).read_text(encoding="utf-8-sig"))
        image, warnings = render_template(config, template, dict(zip(profile["fields"], values)))
        if warnings:
            raise ValueError("；".join(warnings))
        return image
    return {"material": material, "prototype": prototype}[profile["kind"]](config, profile, values)


def to_zpl(image):
    width, height = image.size
    if min(width, height) < 1 or width*height > 12_000_000:
        raise ValueError("Invalid label pixel dimensions")
    padded = Image.new("1", ((width + 7) // 8 * 8, height), 1)
    padded.paste(image.convert("1"), (0, 0))
    data = bytes(b ^ 255 for b in padded.tobytes())
    return (f"^XA^PW{width}^LL{height}^LH0,0^FO0,0^GFA,{len(data)},{len(data)},{(width + 7)//8},"
            + data.hex().upper() + "^FS^PQ1^XZ").encode("ascii")
