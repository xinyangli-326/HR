"""Conservative company pre-review checks; these are not government eligibility rules."""
import re

SLOTS = {
    "contract": "劳动合同",
    "identity": "身份证",
    "social": "社保缴纳记录",
    "property": "无房产证明",
    "diploma": "学历证书",
    "degree": "学位证书",
    "education_report": "学信网学历验证报告",
    "degree_report": "学信网学位验证报告",
}
VERSION = "企业预审 2026.10.09 / v1"


def compact(text):
    return re.sub(r"\s+", "", text or "")


def check_materials(documents, applicant):
    checks = []

    def pages(slot):
        return [
            dict(page, file_id=doc["id"], name=doc["name"])
            for doc in documents if slot in doc["slots"]
            for page in doc.get("pages", [])
        ]

    def add(key, title, status, reason, source=None):
        evidence = []
        for page in source or []:
            evidence.append({
                "file_id": page["file_id"], "name": page["name"],
                "page": page["number"], "snippet": page.get("text", "")[:1500],
            })
        checks.append(dict(id=key, title=title, status=status, reason=reason, evidence=evidence))

    def reliable(slot):
        source = pages(slot)
        # A low-confidence page or an empty page can contain the deciding field.
        return source and all(p.get("reliable") for p in source)

    def result(key, title, slot, test):
        source = pages(slot)
        if not reliable(slot):
            add(key, title, "review", "存在空白、低置信度或无法识别的页面，需要人工核对。", source)
            return
        status, reason = test(source)
        add(key, title, status, reason, source)

    def contract(source):
        text = "".join(compact(p["text"]) for p in source)
        dates = re.findall(
            r"(?:合同(?:期限)?(?:起始|开始|生效)(?:日期|时间)?|劳动合同起始日期|合同期限[:：]?自)"
            r"[:：为自]*([12]\d{3})[年./-](\d{1,2})", text
        )
        if not dates:
            dates = re.findall(r"(?:本合同|合同期限)[^。；]{0,12}?自([12]\d{3})年(\d{1,2})月", text)
        if not dates or len(set(dates)) != 1:
            return "review", "未可靠定位唯一的合同起始日期；不能用签署日期替代。"
        year, month = dates[0]
        if not 1 <= int(month) <= 12:
            return "review", "合同日期识别异常，需要核对原件。"
        if year != "2026":
            return "fail", f"识别到合同起始月份为 {year} 年 {int(month)} 月，不符合起始年份为 2026 年的企业规则。"
        return "pass", f"合同起始月份为 2026 年 {int(month)} 月。"

    result("contract-date", "劳动合同起始年份", "contract", contract)

    def identity(source):
        front = [p for p in source if "公民身份号码" in compact(p["text"]) and "姓名" in compact(p["text"])]
        back = [p for p in source if "签发机关" in compact(p["text"]) and "有效期限" in compact(p["text"])]
        if any(p in back for p in front):
            return "pass", "身份证正反面的关键字段位于同一页；照片与遮挡情况仍需人工核对。"
        if front and back:
            return "fail", "身份证正反面分别位于不同页面。请放在同一页或同一张图片后重新上传。"
        return "review", "未可靠识别到完整正反面，需确认有无缺失、遮挡或识别错误。"

    result("identity-layout", "身份证正反面同页", "identity", identity)

    def social(source):
        text = "".join(compact(p["text"]) for p in source)
        values = re.findall(
            r"(?:查询区间|查询期间|查询起止(?:日期|年月|时间)|查询时间范围|查询(?:起始|开始)(?:日期|年月|时间))"
            r"[:：为从自]*([12]\d{3})[年./-]?(\d{2}|\d)(?:月|[./-]|\b|至|到)", text
        )
        if not values or len(set(values)) != 1:
            return "review", "未可靠识别查询区间起始月份。不会将首条缴费记录或首次参保日期用作替代。"
        year, month = values[0]
        if not 1 <= int(month) <= 12:
            return "review", "查询区间月份识别异常。"
        if year == "2025" and int(month) == 1:
            return "pass", "查询区间起始月份为 2025 年 1 月；不检查首次参保月份，也未设置截止月份限制。"
        return "fail", f"查询区间从 {year} 年 {int(month)} 月开始。请重新导出从 2025 年 1 月开始的社保记录。"

    result("social-range", "社保查询区间", "social", social)

    def housing(source):
        text = "".join(compact(p["text"]) for p in source)
        patterns = [
            r"所有权[/／、]?使用权登记信息",
            r"抵押登记信息",
            r"查封登记信息[、，,]?行政限制信息及其他登记信息",
        ]
        matches = [re.search(p, text) for p in patterns]
        if not all(matches) or not (matches[0].start() < matches[1].start() < matches[2].start()):
            return "review", "未可靠定位三个独立栏目，需要人工核对，不能仅统计“无”字数量。"
        failures, unclear = [], []
        labels = ["所有权／使用权登记信息", "抵押登记信息", "查封、行政限制及其他登记信息"]
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i < 2 else len(text)
            value = text[match.end():end]
            value = re.split(r"说明[:：]|第\d+页|北京市规划", value)[0]
            value = re.sub(r"[一二三四五六七八九十]+[、.]$", "", value).strip("：:，,。；;")
            if value == "无":
                continue
            if re.match(r"^(?:有|不动产单元号|权利人|坐落|房屋坐落|权证号)", value):
                failures.append(labels[i])
            else:
                unclear.append(labels[i])
        if failures:
            return "fail", "以下栏目不是“无”：" + "、".join(failures) + "。请核对材料；有异议可申请人工复核。"
        if unclear:
            return "review", "以下栏目结果未能可靠定位为独立的“无”：" + "、".join(unclear) + "。"
        return "pass", "三个指定栏目对应结果均识别为“无”；不代表已完成权威验真。"

    result("property-three", "无房产证明三个栏目", "property", housing)

    def report(source, degree=False):
        text = "".join(compact(p["text"]) for p in source)
        accepted = (["中国高等教育学位在线验证报告", "中国高等教育学位认证报告"] if degree
                    else ["教育部学历证书电子注册备案表", "中国高等教育学历认证报告"])
        if any(title in text for title in accepted):
            return "pass", "已识别对应报告标题；报告内容及在线真实性仍需核对。"
        if "学籍在线验证报告" in text:
            kind = "学位" if degree else "学历"
            return "fail", f"上传的是学籍在线验证报告，不能替代{kind}验证报告。请补充正确报告。"
        return "review", "未可靠识别对应的学历／学位验证报告标题。"

    result("education-report", "学历验证报告类型", "education_report", report)
    result("degree-report", "学位验证报告类型", "degree_report", lambda p: report(p, True))

    for slot, title, markers in [
        ("diploma", "学历证书", ["毕业证书"]),
        ("degree", "学位证书", ["学士学位", "硕士学位", "博士学位", "学位证书"]),
    ]:
        def certificate(source, markers=markers):
            text = "".join(compact(p["text"]) for p in source)
            if any(word in text for word in markers):
                return "pass", "已识别证书类型关键字，身份对应与原件完整性仍需核对。"
            return "review", "未可靠识别证书类型，请人工确认材料内容。"
        result(slot, title, slot, certificate)

    graduation_source = pages("diploma") + pages("education_report")
    years = set()
    for page in graduation_source:
        if page.get("reliable"):
            years.update(re.findall(r"毕业(?:日期|时间)[:：]?([12]\d{3})[年./-]", compact(page["text"])))
    if len(years) == 1:
        year = next(iter(years))
        add("graduation-year", "毕业年份", "pass" if year == "2026" else "fail",
            f"明确标注的毕业年份为 {year} 年。" + ("" if year == "2026" else "不符合 2026 年毕业的企业规则。"),
            graduation_source)
    else:
        add("graduation-year", "毕业年份", "review", "毕业日期未能唯一确认，需结合学历材料复核；不从合同推断毕业年份。", graduation_source)

    for slot in ("property", "contract", "social"):
        source = pages(slot)
        totals = set()
        numbers = []
        for page in source:
            for current, total in re.findall(r"第(\d+)页共(\d+)页", compact(page.get("text", ""))):
                if page.get("reliable"):
                    totals.add(int(total))
                    numbers.append(int(current))
        if totals and len(totals) == 1:
            total = next(iter(totals))
            if len(source) < total:
                add(f"{slot}-pages", SLOTS[slot] + "页数", "fail", f"材料标注共 {total} 页，实际仅 {len(source)} 页，请补充完整文件。", source)
            elif len(numbers) == total and set(numbers) == set(range(1, total + 1)):
                add(f"{slot}-pages", SLOTS[slot] + "页数", "pass", "已识别连续页码及对应总页数。", source)
            else:
                add(f"{slot}-pages", SLOTS[slot] + "页数", "review", "页数足够，但连续页码未能完整核对。", source)

    add("identity-match", "身份对应、遮挡与原件核对", "review",
        f"需 HR 核对各材料是否属于申请人“{applicant}”、是否存在打码或裁切，以及是否完整。当前识别不支持可靠的遮挡检测和权威验真。")
    return checks
