"""Synthetic fixtures only. No real names, ID numbers, seals or verification codes."""
import base64
import pymupdf as fitz


def make_pdf(lines, extra_pages=None):
    doc = fitz.open()
    for page_lines in [lines] + (extra_pages or []):
        page = doc.new_page()
        page.insert_text((45, 50), "TEST ONLY / FICTIONAL MATERIAL", fontsize=11)
        y = 100
        for line in page_lines:
            page.insert_text((45, y), line, fontname="china-s", fontsize=14)
            y += 35
        page.insert_text((45, 800), "TEST ONLY - NOT AN OFFICIAL DOCUMENT", fontsize=10)
    content = doc.tobytes()
    doc.close()
    return content


def fixtures():
    samples = [
        ("contract", "测试-劳动合同.pdf", ["劳动合同", "姓名：测试申请人", "合同起始日期：2026年07月01日", "合同终止日期：2029年06月30日"]),
        ("identity", "测试-身份证正反面分开.pdf", ["姓名：测试申请人", "公民身份号码：虚构测试，非真实证件"],
         [["居民身份证", "签发机关：测试机关", "有效期限：2020.01.01-2040.01.01"]]),
        ("social", "测试-社保查询区间.pdf", ["社会保险个人权益记录", "姓名：测试申请人", "查询区间：2025年01月至2026年09月", "首次参保日期：2026年07月01日", "缴费记录：2026年07月"]),
        ("property", "测试-无房产证明.pdf", ["不动产登记信息查询结果告知单", "姓名：测试申请人", "一、所有权/使用权登记信息", "无", "二、抵押登记信息", "无", "三、查封登记信息、行政限制信息及其他登记信息", "无", "说明：测试材料，非正式证明"]),
        ("diploma", "测试-学历证书.pdf", ["毕业证书", "姓名：测试申请人", "毕业日期：2026年06月30日"]),
        ("degree", "测试-学位证书.pdf", ["学士学位证书", "姓名：测试申请人", "授予日期：2026年06月30日"]),
        ("education_report", "测试-错误学籍报告.pdf", ["教育部学籍在线验证报告", "姓名：测试申请人"]),
        ("degree_report", "测试-学位验证报告.pdf", ["中国高等教育学位在线验证报告", "姓名：测试申请人"]),
    ]
    return [
        dict(slot=s[0], name=s[1], data=base64.b64encode(make_pdf(s[2], s[3] if len(s) > 3 else None)).decode())
        for s in samples
    ]
