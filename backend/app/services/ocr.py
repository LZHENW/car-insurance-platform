"""OCR 服务：多格式读取（图片 / PDF）→ 引擎识别 → 字段抽取 → 自动校验 → 质量评分。"""

import os
import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from app.models import FIELD_LABELS, FIELD_NAMES


class OCREngineUnavailable(Exception):
    """上传了文件但 OCR 引擎不可用（未安装 / 加载失败）时抛出。"""


class UnsupportedFileType(Exception):
    """上传了既不是图片也不是 PDF 的文件。"""


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
PDF_EXTS = {".pdf"}


# ──────────────────────── OCR 引擎 ────────────────────────

def _run_paddle(image_path: str) -> str:
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    result = ocr.ocr(image_path, cls=True)
    lines = []
    if result and result[0]:
        for line in result[0]:
            lines.append(line[1][0])
    return "\n".join(lines)


def _run_rapidocr(image_path: str) -> str:
    from rapidocr_onnxruntime import RapidOCR

    result, _ = RapidOCR()(image_path)
    if not result:
        return ""
    return "\n".join(line[1] for line in result)


def run_ocr(image_path: str) -> str:
    """对单张图片执行 OCR：优先 PaddleOCR，未安装则回退 RapidOCR。"""
    if not image_path:
        raise ValueError("未提供图片，无法进行 OCR")

    try:
        return _run_paddle(image_path)
    except ImportError:
        pass
    except Exception as e:
        raise OCREngineUnavailable(f"PaddleOCR 识别失败：{e}")

    try:
        return _run_rapidocr(image_path)
    except ImportError:
        raise OCREngineUnavailable(
            "未安装 OCR 引擎（paddleocr 或 rapidocr-onnxruntime），无法识别上传的文件"
        )
    except Exception as e:
        raise OCREngineUnavailable(f"RapidOCR 识别失败：{e}")


def _render_pdf_to_images(pdf_path: str, out_dir: str) -> List[str]:
    """把 PDF 每一页渲染为 PNG，返回图片路径列表（支持多页逐页识别）。"""
    try:
        import pymupdf as fitz  # PyMuPDF（新包名）
    except ImportError:
        try:
            import fitz  # PyMuPDF（旧包名）
        except ImportError:
            raise OCREngineUnavailable(
                "未安装 PDF 解析库 PyMuPDF，无法处理 PDF。请执行：pip install pymupdf"
            )

    if not out_dir:
        out_dir = os.path.dirname(os.path.abspath(pdf_path))
    os.makedirs(out_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(pdf_path))[0]
    images: List[str] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise UnsupportedFileType(f"PDF 打开失败，文件可能已损坏：{e}")

    try:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x 放大提升小字识别率
            path = os.path.join(out_dir, f"{base}_p{i}.png")
            pix.save(path)
            images.append(path)
    finally:
        doc.close()
    return images


def run_ocr_on_file(file_path: str, out_dir: Optional[str] = None) -> Dict[str, str]:
    """统一入口：图片直接识别；PDF 先逐页转图片再识别。

    返回 {"raw_text": 全文, "preview_image": 可预览的首张图片路径}
    """
    if not file_path:
        raise ValueError("未提供文件，无法进行 OCR")

    ext = os.path.splitext(file_path)[1].lower()

    if ext in PDF_EXTS:
        images = _render_pdf_to_images(file_path, out_dir)
        if not images:
            raise UnsupportedFileType("PDF 中没有可识别的页面")
        raw_text = "\n".join(run_ocr(img) for img in images)
        return {"raw_text": raw_text, "preview_image": images[0]}

    if ext in IMAGE_EXTS or ext == "":
        return {"raw_text": run_ocr(file_path), "preview_image": file_path}

    raise UnsupportedFileType(
        f"不支持的文件类型：{ext or '未知'}，仅支持 JPG / PNG / PDF 等"
    )


# ──────────────────────── 字段抽取 ────────────────────────
#
# 真实保单以「表格版式」为主，标签与取值常见三种排布：
#   ① 同行：                 保险公司：中国平安
#   ② 标签独占一行，值在下一行：厂牌型号 \n 吉利美日MR6471D12多用途乘用车
#   ③ 值在标签上方（电子保单合计栏常见）
# 因此这里先按「行」定位标签再取值，而不是把全文压成一行做正则——
# 压成一行会跨行误抓下一个标签（例：投保人为空时抓到「行驶证车主」）。

PLATE_PATTERN = (
    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]"
    r"[A-Z][A-Z0-9]{4,5}[A-Z0-9挂学警港澳]?"
)

# 车牌脱敏 / 遮挡后可能只剩「晋A-L」这类残缺串
PLATE_PARTIAL_PATTERN = (
    r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼]"
    r"[A-Za-z0-9\-]{1,8}"
)

DATE_PATTERN = r"(20\d{2})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})"

# 命中这些词说明取到的是「标签」而不是「值」
_LABEL_WORDS = re.compile(
    r"(姓名|车主|被保险|投保|证件|联系|地址|号码|日期|类型|性质|种类"
    r"|金额|公司|型号|品牌|保额|期间|机构|条款|险别|免赔|载客|载质量"
    r"|使用|初登|确认|验真|流水)"
)

# 已知品牌：保单通常没有独立的「品牌」字段，需从厂牌型号反推
KNOWN_BRANDS = [
    "丰田", "本田", "日产", "大众", "奥迪", "宝马", "奔驰", "别克", "雪佛兰",
    "福特", "现代", "起亚", "沃尔沃", "凯迪拉克", "雷克萨斯",
    "特斯拉", "比亚迪", "蔚来", "小鹏", "理想", "极氪", "问界", "欧拉", "埃安",
    "哪吒", "零跑", "深蓝", "岚图", "阿维塔", "腾势", "智己",
    "吉利", "长城", "哈弗", "长安", "奇瑞", "荣威", "名爵", "五菱",
    "红旗", "捷途", "领克", "北汽", "江淮", "东风", "广汽", "上汽",
]

# 保险公司别名 → 规范名（与报表口径一致，便于按公司聚合）
COMPANY_ALIASES = [
    ("平安", "中国平安"),
    ("太平洋", "太平洋保险"),
    ("人民财产保险", "中国人保"),
    ("人保", "中国人保"),
    ("人寿", "中国人寿"),
    ("国寿", "中国人寿"),
    ("太平", "太平保险"),
    ("大地", "大地保险"),
    ("阳光", "阳光保险"),
    ("中华联合", "中华联合"),
    ("永安", "永安保险"),
    ("华安", "华安保险"),
    ("众安", "众安保险"),
    ("天安", "天安保险"),
]

# 险种名：后缀固定且前缀至少 3 字。用于从「投保险别」表格中挑出险种行，
# 同时排除金额行、列头，以及 OCR 断行产生的碎片（如「务特约条款」）
_COVERAGE_NAME = re.compile(
    r"^.{3,}(?:保险|责任险|特约条款)(?:[（(][^）)]*[）)]?)?$"
)


def _compact(text: str) -> str:
    """去掉所有空白字符，便于比对含空格 / 跨行的取值。"""
    return re.sub(r"\s+", "", text or "")


def _looks_like_label(value: str) -> bool:
    """判断取值是否其实是「另一个标签」（标签通常较短且含标签词）。"""
    return bool(_LABEL_WORDS.search(value)) and len(value) <= 12


def _accept(value: str, reject_colon: bool, reject_labelish: bool) -> bool:
    if not value:
        return False
    # 必须含实际内容（排除纯标点 / 括号）
    if not re.search(r"[0-9A-Za-z\u4e00-\u9fa5]", value):
        return False
    # 取值里再出现冒号 → 抓到的是下一个标签，例：投保人：\n行驶证车主：仁
    if reject_colon and ("：" in value or ":" in value):
        return False
    if reject_labelish and _looks_like_label(value):
        return False
    return True


def _label_values(
    lines, labels, *, reject_colon: bool = True, reject_labelish: bool = True
):
    """按行定位标签并返回值候选，兼容同行 / 下一行 / 上一行三种版式。"""
    found = []
    for i, line in enumerate(lines):
        compact = _compact(line)
        for label in labels:
            value = None
            # ① 同行：标签[：:]值
            #    注意「公司名称：」这类只有冒号的行，正则也会命中（值为「：」），
            #    被拒后必须继续走 ②，否则会漏掉下一行的真正取值。
            m = re.match(rf"^{label}\s*[：:]?\s*(.+)$", compact)
            if m:
                candidate = m.group(1).strip()
                if _accept(candidate, reject_colon, reject_labelish):
                    value = candidate
            # ② 标签独占一行 → 先看下一行，再看上一行
            if value is None and compact in (label, f"{label}：", f"{label}:"):
                for j in (i + 1, i - 1):
                    if 0 <= j < len(lines):
                        cand = _compact(lines[j])
                        if _accept(cand, reject_colon, reject_labelish):
                            value = cand
                            break
            if value:
                found.append(value)
                break
    return found


def _to_amount(value):
    """取出文本中的第一个数字金额。"""
    m = re.search(r"([0-9][0-9,]*(?:\.[0-9]+)?)", value or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _to_date(value):
    m = re.search(DATE_PATTERN, value or "")
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def infer_brand(vehicle_model: Optional[str]) -> Optional[str]:
    """从厂牌型号反推品牌。

    例：吉利美日MR6471D12多用途乘用车 → 吉利；特斯拉Model Y → 特斯拉
    """
    model = _compact(vehicle_model)
    if not model:
        return None
    lowered = model.lower()
    for brand in KNOWN_BRANDS:
        if lowered.startswith(brand.lower()):
            return brand
    m = re.match(r"[\u4e00-\u9fa5]{2,3}", model)
    return m.group(0) if m else None


def normalize_company(name: Optional[str]) -> Optional[str]:
    """把「中国平安财产保险股份有限公司太原中心支公司」归一到「中国平安」。"""
    if not name:
        return name
    for alias, canonical in COMPANY_ALIASES:
        if alias in name:
            return canonical
    return name


def _extract_coverage(lines) -> Optional[str]:
    """险种：优先显式标签，其次从「投保险别」表格区提取多行险种名。"""
    for value in _label_values(
        lines, ["险种", "承保险别", "投保险别", "承保内容"], reject_colon=False
    ):
        if "险" in value or "条款" in value:
            return value

    names = []
    in_table = False
    for line in lines:
        compact = _compact(line)
        if re.match(r"^(投保险别|承保险别|承保内容)", compact):
            in_table = True
            continue
        if not in_table:
            continue
        if re.match(r"^(特别约定|重要提示|保险费合计|公司名称|被保险人)", compact):
            break
        if re.search(r"\d", compact):  # 金额 / 数量行跳过
            continue
        if _COVERAGE_NAME.match(compact):
            # 补回 OCR 丢掉的反括号，例：责任险（车上人员司机
            if compact.count("（") > compact.count("）"):
                compact += "）"
            if compact not in names:
                names.append(compact)
    return "+".join(names) if names else None


def extract_fields(text: str) -> dict:
    """从 OCR 原始文本中抽取 11 个结构化字段。"""
    raw = text or ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    flat = _compact(raw)

    def first(patterns):
        for pat in patterns:
            m = re.search(pat, flat)
            if m:
                return (m.group(1) if m.lastindex else m.group(0)).strip()
        return None

    # 保单号：确认码 / 验真码都不算保单号，只认「保险单号 / 保单号」
    policy_number = first([
        r"保险单号[码]?[：:]?\s*([A-Za-z0-9\-]{6,40})",
        r"保单号[码]?[：:]?\s*([A-Za-z0-9\-]{6,40})",
        r"保单编号[：:]?\s*([A-Za-z0-9\-]{6,40})",
    ])

    # 车牌号：标签优先（含「号牌号码」），其次全文扫描完整车牌
    plate_number = None
    for cand in _label_values(lines, ["号牌号码", "车牌号码", "车牌号"]):
        cleaned = cand.replace("·", "").replace(".", "").replace("－", "-")
        m = re.search(PLATE_PATTERN, cleaned)
        if m:
            plate_number = m.group(0)
            break
        # 脱敏车牌（如晋A-L）先收下，由校验环节提示人工复核
        if re.fullmatch(PLATE_PARTIAL_PATTERN, cleaned):
            plate_number = cleaned
            break
    if not plate_number:
        m = re.search(PLATE_PATTERN, flat)
        plate_number = m.group(0) if m else None

    # 被保险人：保单里多写作「姓名」，其次才是「车主 / 行驶证车主」。
    # 必须按「标签优先级」逐个查找，不能把标签放进同一次调用——
    # 那样会按「行顺序」取值，而真实保单常把「行驶证车主：仁」排在
    # 「姓名：侯」前面，会把车主误当成被保险人。
    owner_name = None
    for label in ("被保险人", "被保人", "姓名", "车主", "行驶证车主"):
        for cand in _label_values(lines, [label]):
            if 1 <= len(cand) <= 6:
                owner_name = cand
                break
        if owner_name:
            break

    insured_name = None
    for cand in _label_values(lines, ["投保人名称", "投保人"]):
        if 1 <= len(cand) <= 6:
            insured_name = cand
            break

    # 厂牌型号：标签后无冒号、值单独成行是常态
    vehicle_model = None
    for cand in _label_values(
        lines, ["厂牌型号", "品牌型号", "车辆型号", "规格型号", "车型", "车辆类型"]
    ):
        if len(cand) >= 2:
            vehicle_model = cand
            break

    vehicle_brand = None
    for cand in _label_values(lines, ["品牌"]):
        if len(cand) >= 2:
            vehicle_brand = cand
            break
    if not vehicle_brand:
        vehicle_brand = infer_brand(vehicle_model)

    # 保险公司：平安等电子保单的标签是「公司名称」
    insurance_company = None
    for cand in _label_values(
        lines, ["公司名称", "保险公司", "承保公司", "承保机构", "保险机构"]
    ):
        if len(cand) >= 4:
            insurance_company = normalize_company(cand)
            break

    # 总保费：只认「合计口径」标签，避免抓到表格里单条的保费小计
    premium = None
    total_labels = [
        "保险费合计", "总保费（元）", "总保费(元)", "总保费", "保费合计",
        "实收保费", "签单保费", "应收保费", "合计保费",
    ]
    for cand in _label_values(lines, total_labels, reject_colon=False):
        amount = _to_amount(cand)
        if amount is not None:
            premium = amount
            break
    if premium is None:
        # 电子保单常在合计行前置 RMB，例：RMB1012.19元（不含税保费：954.90…）
        m = re.search(r"RMB\s*([0-9][0-9,]*(?:\.[0-9]+)?)", flat)
        if m:
            premium = float(m.group(1).replace(",", ""))
    if premium is None:
        # 兜底：普通「保险费 / 保费」同行取值
        for cand in _label_values(lines, ["保险费", "保费"], reject_colon=False):
            amount = _to_amount(cand)
            if amount is not None:
                premium = amount
                break

    # 投保日期：优先保险期间起始，其次投保 / 签单日期，最后才全文兜底
    insurance_date = None
    for label in ("保险期间", "保险期限", "保单期间", "承保期间"):
        for cand in _label_values(lines, [label], reject_colon=False):
            insurance_date = _to_date(cand)
            if insurance_date:
                break
        if insurance_date:
            break
    if not insurance_date:
        for label in ("投保日期", "签单日期", "出单日期", "生效日期", "起保日期"):
            for cand in _label_values(lines, [label], reject_colon=False):
                insurance_date = _to_date(cand)
                if insurance_date:
                    break
            if insurance_date:
                break
    if not insurance_date:
        insurance_date = _to_date(flat)

    # 新能源判定：先看文本关键字，再看车型关键字
    ev_keywords = ["新能源", "纯电动", "插电混动", "增程式", "BEV", "PHEV"]
    lowered = flat.lower()
    is_new_energy = any(kw.lower() in lowered for kw in ev_keywords)
    # EV 需独立成词，避免命中 E-Mail 之类的普通文本
    if not is_new_energy:
        is_new_energy = re.search(r"(?<![a-z])ev(?![a-z])", lowered) is not None
    if vehicle_model:
        model_ev = [
            "Model", "特斯拉", "比亚迪", "蔚来", "小鹏", "理想", "极氪", "欧拉",
            "埃安", "问界", "哪吒", "零跑", "深蓝", "岚图", "阿维塔", "腾势", "智己",
        ]
        is_new_energy = is_new_energy or any(
            kw.lower() in vehicle_model.lower() for kw in model_ev
        )

    coverage = _extract_coverage(lines)

    return {
        "policy_number": policy_number,
        "plate_number": plate_number,
        "owner_name": owner_name,
        "insured_name": insured_name,
        "vehicle_model": vehicle_model,
        "vehicle_brand": vehicle_brand,
        "insurance_company": insurance_company,
        "premium": premium,
        "is_new_energy": is_new_energy,
        "insurance_date": insurance_date,
        "coverage": coverage,
    }


# ──────────────────────── 质量评分与自动校验 ────────────────────────

def calc_quality_score(fields: dict) -> float:
    """质量分 = 已填充字段数 / 总字段数 × 100。

    False 是有意义的业务取值（is_new_energy=False 表示燃油车），计为已填充。
    """
    filled = sum(1 for v in fields.values() if v is not None and v != "")
    total = len(fields) or 1
    return round(filled / total * 100, 1)


# 判定"文件里确实有保单"的关键字段，至少命中一个才算识别成功
KEY_FIELDS = ("policy_number", "plate_number", "insurance_company", "premium")


def has_policy_info(fields: dict) -> bool:
    return any(fields.get(k) for k in KEY_FIELDS)


def validate_fields(fields: dict) -> List[str]:
    """自动校验：返回可疑 / 缺失字段的中文提示，供前端高亮人工复核。"""
    warnings: List[str] = []

    plate = fields.get("plate_number")
    if plate and not re.fullmatch(PLATE_PATTERN, plate):
        warnings.append(f"车牌号格式可疑：{plate}")

    premium = fields.get("premium")
    if premium is not None and not (0 < premium < 1_000_000):
        warnings.append(f"保费金额超出合理范围：{premium}")

    pdate = fields.get("insurance_date")
    if pdate:
        try:
            d = datetime.strptime(pdate, "%Y-%m-%d").date()
            if not (date(2000, 1, 1) <= d <= date.today() + timedelta(days=365)):
                warnings.append(f"投保日期超出合理范围：{pdate}")
        except ValueError:
            warnings.append(f"投保日期格式错误：{pdate}")

    pno = fields.get("policy_number")
    if pno and not re.fullmatch(r"[A-Za-z0-9\-]{6,40}", pno):
        warnings.append(f"保单号格式可疑：{pno}")

    for key in FIELD_NAMES:
        if key == "is_new_energy":
            continue
        if fields.get(key) in (None, ""):
            warnings.append(f"未识别到「{FIELD_LABELS[key]}」，建议人工补录")

    return warnings


def process_policy_image(file_path: str, out_dir: Optional[str] = None) -> dict:
    """完整识别流水线：多格式读取 → OCR → 字段抽取 → 质量评分 → 自动校验。"""
    ocr = run_ocr_on_file(file_path, out_dir=out_dir)
    fields = extract_fields(ocr["raw_text"])
    return {
        "raw_text": ocr["raw_text"],
        "preview_image": ocr["preview_image"],
        "fields": fields,
        "quality_score": calc_quality_score(fields),
        "warnings": validate_fields(fields),
    }