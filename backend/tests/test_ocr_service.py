"""OCR 服务单元测试：字段抽取 / 新能源判定 / 质量评分 / 自动校验。"""

import pytest

from app.services import ocr

SAMPLE_FULL = """
被保险人：张三
车牌号：粤B88888
厂牌型号：特斯拉Model Y
保险公司：中国平安
保费合计：6800.00元
保险期间：2026-09-15
险种：交强险+车损险
"""

SAMPLE_EV_BY_MODEL = """
车牌号 沪C66666
车辆型号：比亚迪汉EV
承保机构：太平洋财产保险
"""

SAMPLE_FUEL = """
车牌号：京A12345
车辆类型：宝马530Li
燃料类型：汽油
"""


class TestExtractFields:
    def test_车牌号(self):
        assert ocr.extract_fields(SAMPLE_FULL)["plate_number"] == "粤B88888"

    def test_被保险人(self):
        assert ocr.extract_fields(SAMPLE_FULL)["owner_name"] == "张三"

    def test_厂牌型号(self):
        assert ocr.extract_fields(SAMPLE_FULL)["vehicle_model"].startswith("特斯拉")

    def test_保险公司(self):
        assert ocr.extract_fields(SAMPLE_FULL)["insurance_company"] == "中国平安"

    def test_保费(self):
        assert ocr.extract_fields(SAMPLE_FULL)["premium"] == 6800.0

    def test_投保日期(self):
        assert ocr.extract_fields(SAMPLE_FULL)["insurance_date"] == "2026-09-15"

    def test_新能源_文本关键字(self):
        assert ocr.extract_fields(SAMPLE_FULL)["is_new_energy"] is True

    def test_新能源_车型匹配(self):
        assert ocr.extract_fields(SAMPLE_EV_BY_MODEL)["is_new_energy"] is True

    def test_燃油车判定(self):
        assert ocr.extract_fields(SAMPLE_FUEL)["is_new_energy"] is False

    def test_空文本不报错(self):
        fields = ocr.extract_fields("")
        assert fields["plate_number"] is None


class TestCalcQualityScore:
    def test_全字段满分(self):
        assert ocr.calc_quality_score({"a": "x", "b": 1, "c": True}) == 100.0

    def test_部分字段(self):
        fields = {"a": "x", "b": None, "c": True, "d": "", "e": False, "f": "y"}
        # 4/6 已填充（False 计为已填充）
        assert ocr.calc_quality_score(fields) == 66.7

    def test_空字段不计入(self):
        assert ocr.calc_quality_score({"a": None, "b": "", "c": False}) == 33.3


class TestHasPolicyInfo:
    def test_命中关键字段(self):
        assert ocr.has_policy_info({"plate_number": "粤B12345"}) is True

    def test_全部为空(self):
        assert ocr.has_policy_info({"plate_number": None, "premium": None}) is False


class TestValidateFields:
    def test_可疑车牌给出提示(self):
        warnings = ocr.validate_fields({"plate_number": "ABC"})
        assert any("车牌号" in w for w in warnings)

    def test_保费越界给出提示(self):
        warnings = ocr.validate_fields({"premium": 9_999_999})
        assert any("保费" in w for w in warnings)


class TestProcessPipeline:
    def test_无文件应报错(self):
        with pytest.raises(ValueError):
            ocr.process_policy_image(None)


# ── 真实「机动车商业保险保险单（电子保单）」版式回归 ──
# 该版式的坑：标签与取值分行、多数标签无冒号、保险公司写作「公司名称」、
# 合计栏金额前置 RMB、险种是「投保险别」多行表格、投保人为空。
SAMPLE_PINGAN_EPOLICY = """
中国平安 PINGAN
机动车商业保险保险单（电子保单）
保单验真码：rAEkrzHMlwSfVZhwWQ
投保人：
行驶证车主：仁
保险单号：13390003902878678213
被保
姓名：侯
险人
性别:
初登日期
2023-03-27
号牌号码
晋A-L
厂牌型号
吉利美日MR6471D12多用途乘用车
使用性质
非营业
机动车种类
六座以下客车
保险期间
自2025年3月26日00：00时起至2026年3月25日24:00时止
投保险别
保险金额/责任限额
保费小计（元）
绝对免赔率
保费合计（元）
594.14
机动车损失保险
92837.40元
594. 14
机动车第三者责任保险
3000000.00元
344.19
344.19
车上人员责任险（司机）
12. 45
10000.00元
12. 45
附加医保外医疗费用责任险（三者）
500000.00元
24. 28
24. 28
共享保额
1. 44
附加机动车增值服
务特约条款
1次
道路救援服务特约条款
7次
车损险每次事故绝对免赔额
0元/次
RMB1012.19元（不含税保费：954.90元，税额：57.29元）
（大写）人民币壹仟零壹
保险费合计
拾贰元壹角玖分
特别约定
公司名称：
中国平安财产保险股份有限公司太原中心支公司
"""

PINGAN_FIELDS = ocr.extract_fields(SAMPLE_PINGAN_EPOLICY)


class TestPingAnEPolicyLayout:
    def test_保单号(self):
        assert PINGAN_FIELDS["policy_number"] == "13390003902878678213"

    def test_厂牌型号_标签无冒号且值在下一行(self):
        assert PINGAN_FIELDS["vehicle_model"] == "吉利美日MR6471D12多用途乘用车"

    def test_品牌_从厂牌型号反推(self):
        assert PINGAN_FIELDS["vehicle_brand"] == "吉利"

    def test_保险公司_标签为公司名称(self):
        assert PINGAN_FIELDS["insurance_company"] == "中国平安"

    def test_总保费_不抓表格里的保费小计(self):
        # 表格首行的保费小计是 594.14，真值是合计 1012.19
        assert PINGAN_FIELDS["premium"] == 1012.19

    def test_投保日期_取保险期间而非初登日期(self):
        # 文中另有「初登日期 2023-03-27」，不能误取
        assert PINGAN_FIELDS["insurance_date"] == "2025-03-26"

    def test_险种_从投保险别表格提取多行(self):
        coverage = PINGAN_FIELDS["coverage"]
        assert "机动车损失保险" in coverage
        assert "机动车第三者责任保险" in coverage
        assert "车上人员责任险（司机）" in coverage
        assert "道路救援服务特约条款" in coverage
        # 金额行 / 列头 / OCR 断行碎片都不应混入
        items = coverage.split("+")
        assert "594" not in coverage
        assert "共享保额" not in coverage
        # 「务特约条款」「附加机动车增值服」是 OCR 断行碎片，不能独立成项
        #（注意不能对外层字符串做 in 判断：「道路救援服务特约条款」本身就含「务特约条款」）
        assert "务特约条款" not in items
        assert "附加机动车增值服" not in items

    def test_投保人为空时不误抓下一个标签(self):
        assert PINGAN_FIELDS["insured_name"] is None

    def test_被保险人取姓名(self):
        assert PINGAN_FIELDS["owner_name"] == "侯"

    def test_燃油车判定(self):
        assert PINGAN_FIELDS["is_new_energy"] is False

    def test_脱敏车牌仍能收下并触发复核提示(self):
        assert PINGAN_FIELDS["plate_number"] == "晋A-L"
        assert any("车牌号" in w for w in ocr.validate_fields(PINGAN_FIELDS))