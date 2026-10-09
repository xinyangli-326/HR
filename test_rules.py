import unittest
from rules import check_materials, SLOTS


def doc(slot, texts, reliable=True):
    return {"id": slot, "name": slot + ".pdf", "slots": [slot],
            "pages": [{"number": i + 1, "text": text, "reliable": reliable} for i, text in enumerate(texts)]}


def result(slot, texts, rule, reliable=True):
    checks = check_materials([doc(slot, texts, reliable)], "测试申请人")
    return next(c for c in checks if c["id"] == rule)


class RulesTests(unittest.TestCase):
    def test_query_range_not_first_payment(self):
        check = result("social", ["查询区间：2025年01月至2026年09月\n首次参保日期：2026年07月01日"], "social-range")
        self.assertEqual(check["status"], "pass")

    def test_wrong_query_range(self):
        self.assertEqual(result("social", ["查询区间：2026年01月至2026年09月"], "social-range")["status"], "fail")

    def test_payment_date_is_not_range(self):
        self.assertEqual(result("social", ["首次参保日期：2025年01月01日"], "social-range")["status"], "review")

    def test_low_confidence_never_rejects(self):
        self.assertEqual(result("social", ["查询区间：2026年01月至2026年09月"], "social-range", False)["status"], "review")

    def test_contract_date(self):
        for year, expected in [("2026", "pass"), ("2025", "fail")]:
            self.assertEqual(result("contract", [f"合同起始日期：{year}年07月01日"], "contract-date")["status"], expected)

    def test_signature_not_start(self):
        self.assertEqual(result("contract", ["签署日期：2026年07月01日"], "contract-date")["status"], "review")

    def test_id_same_page(self):
        self.assertEqual(result("identity", ["姓名 公民身份号码 签发机关 有效期限"], "identity-layout")["status"], "pass")

    def test_id_different_pages(self):
        self.assertEqual(result("identity", ["姓名 公民身份号码", "签发机关 有效期限"], "identity-layout")["status"], "fail")

    def test_three_distinct_none(self):
        text = "一、所有权/使用权登记信息\n无\n二、抵押登记信息\n无\n三、查封登记信息、行政限制信息及其他登记信息\n无\n说明：其他"
        self.assertEqual(result("property", [text], "property-three")["status"], "pass")

    def test_three_words_not_enough(self):
        self.assertEqual(result("property", ["无无无"], "property-three")["status"], "review")

    def test_enrollment_report(self):
        self.assertEqual(result("education_report", ["教育部学籍在线验证报告"], "education-report")["status"], "fail")

    def test_correct_report(self):
        self.assertEqual(result("education_report", ["教育部学历证书电子注册备案表"], "education-report")["status"], "pass")

    def test_missing_page(self):
        self.assertEqual(result("property", ["第 1 页 共 2 页"], "property-pages")["status"], "fail")

    def test_duplicates_do_not_prove_completeness(self):
        self.assertEqual(result("property", ["第1页共2页", "第1页共2页"], "property-pages")["status"], "review")

    def test_graduation_date(self):
        self.assertEqual(result("diploma", ["毕业日期：2026年06月30日"], "graduation-year")["status"], "pass")

    def test_always_requires_human_identity_check(self):
        checks = check_materials([], "测试")
        self.assertEqual(next(c for c in checks if c["id"] == "identity-match")["status"], "review")


if __name__ == "__main__":
    unittest.main()
