import pytest
import zxingcpp
from PIL import Image, ImageOps

from feishu_label_printer.labels import render, to_zpl


def test_material_barcode_decodes_exactly(config):
    image = render(config, config["profiles"][0], ["100001-A00", "Demo part", "10x20"])
    codes = zxingcpp.read_barcodes(image.convert("L"))
    assert [code.text for code in codes] == ["100001-A00"]
    assert image.size == (354, 236)


def test_prototype_qr_decodes_exact_record(config, prototype_row):
    profile = config["profiles"][1]
    image = render(config, profile, [prototype_row[f] for f in profile["fields"]])
    codes = zxingcpp.read_barcodes(image.convert("L"))
    assert [code.text for code in codes] == [prototype_row["记录链接"]]


@pytest.mark.parametrize("number", ["", "中文料号", "A" * 30])
def test_invalid_material_is_rejected(config, number):
    with pytest.raises(ValueError):
        render(config, config["profiles"][0], [number, "Demo", ""])


@pytest.mark.parametrize("mutation", ["host", "record", "table"])
def test_qr_cannot_point_to_a_different_record(config, prototype_row, mutation):
    profile = config["profiles"][1]
    link = prototype_row["记录链接"]
    link = {"host": link.replace("example.feishu.cn", "other.example"),
            "record": link.replace("recDemo001", "recOther"),
            "table": link.replace("tblDemo", "tblOther")}[mutation]
    with pytest.raises(ValueError, match="不匹配"):
        render(config, profile, ["Demo V1-001-L", link, "recDemo001"])


def test_offset_moves_ink_and_rejects_cropping(config):
    profile = dict(config["profiles"][0], vertical_offset_mm=0)
    base = render(config, profile, ["100001-A00", "Demo", "10x20"])
    profile["vertical_offset_mm"] = 1
    shifted = render(config, profile, ["100001-A00", "Demo", "10x20"])
    a = ImageOps.invert(base.convert("L")).getbbox()
    b = ImageOps.invert(shifted.convert("L")).getbbox()
    assert b == (a[0], a[1] + 12, a[2], a[3] + 12)
    profile["vertical_offset_mm"] = 10
    with pytest.raises(ValueError, match="边缘"):
        render(config, profile, ["100001-A00", "Demo", "10x20"])


def test_zpl_pixel_polarity_padding_and_single_copy():
    image = Image.new("1", (354, 236), 1)
    image.putpixel((0, 0), 0)
    raw = to_zpl(image).decode("ascii")
    data = raw.split("^GFA,10620,10620,45,")[1].split("^FS")[0]
    decoded = bytes.fromhex(data)
    assert decoded[0] == 128
    assert all(byte == 0 for byte in decoded[1:])
    assert raw.endswith("^FS^PQ1^XZ")
