"""Adjust tone: more formal / shorter / friendlier, plus free-form instructions."""
from __future__ import annotations

import unittest

import _tpi_server as srv
from _tpi_compose_util import ComposeCase, use_cli_agent

EN = ("Hey Samira,\n\nI hope this email finds you well. I just wanted to say that I'm really happy with the slides! "
      "We can't cut the third one though. It's basically the core of the pitch. I'll send the final version by "
      "Thursday. Let me know if that's OK.\n\nCheers,\nAlex")
ZH = "嗨 Samira，\n\n謝啦！你的簡報沒問題喔～我們禮拜四前給你最終版。\n\n先這樣，再聊！\nAlex"


def rewrite(**body):
    return srv.post("/api/compose/rewrite", body)


class ToneTest(ComposeCase):
    def test_formal(self):
        status, r = rewrite(body=EN, tone="formal")
        self.assertEqual(status, 200)
        self.assertEqual((r["source"], r["applied"], r["changed"]), ("heuristic", ["formal"], True))
        text = r["text"]
        self.assertTrue(text.startswith("Dear Samira,"))
        for gone in ("I'm", "can't", "It's", "I'll", "!", "Cheers"):
            self.assertNotIn(gone, text)
        for kept in ("I am", "We cannot", "It is", "I will", "by Thursday", "Best regards,\nAlex"):
            self.assertIn(kept, text)

    def test_shorter_drops_filler_and_keeps_dates(self):
        _, r = rewrite(body=EN, tone="shorter")
        text = r["text"]
        self.assertLess(len(text), len(EN))
        self.assertNotIn("I hope this email finds you well", text)
        self.assertNotIn("basically", text)
        self.assertIn("by Thursday", text)
        self.assertIn("Let me know", text)
        self.assertTrue(text.startswith("Hey Samira,") and text.endswith("Cheers,\nAlex"))

    def test_friendlier(self):
        formal = "Dear Samira,\n\nThank you for the slides. We will keep all three.\n\nBest regards,\nAlex"
        _, r = rewrite(body=formal, tone="friendlier")
        self.assertTrue(r["text"].startswith("Hi Samira,\n\nHope your week is going well!"))
        self.assertIn("Thanks so much for the slides.", r["text"])
        self.assertTrue(r["text"].endswith("Thanks so much,\nAlex"))

    def test_chinese_formal_and_friendlier(self):
        _, f = rewrite(body=ZH, tone="formal", lang="zh-Hant")
        self.assertEqual(f["text"], "Samira 您好：\n\n謝謝。您的簡報沒有問題。我們禮拜四前給您最終版。\n\n敬祝 順心\nAlex")
        _, w = rewrite(body=f["text"], tone="friendlier", lang="zh-Hant")
        self.assertTrue(w["text"].startswith("Samira 你好：\n\n希望你這週一切順利！"))
        self.assertIn("你的簡報", w["text"])
        self.assertTrue(w["text"].endswith("謝謝你，祝順心！\nAlex"))

    def test_chinese_shorter(self):
        long_zh = ("Maya 你好：\n\n希望你一切都好。其實我們這邊基本上都準備好了。設計稿已經更新。"
                   "請在週五前回覆是否可以。如有任何問題，歡迎隨時與我聯繫。\n\n謝謝！\nAlex")
        _, r = rewrite(body=long_zh, tone="shorter", lang="zh-Hant")
        self.assertLess(len(r["text"]), len(long_zh))
        self.assertNotIn("希望你一切都好", r["text"])
        self.assertNotIn("其實", r["text"])
        self.assertIn("請在週五前回覆是否可以。", r["text"])


class InstructionTest(ComposeCase):
    def test_known_instructions_without_llm(self):
        _, r = rewrite(body=EN, instruction="make it bullet points and add a thank-you")
        self.assertEqual(r["applied"], ["bullets", "thanks"])
        self.assertIn("\n- We can't cut the third one though.\n", r["text"])
        self.assertIn("Thank you for your help.", r["text"])
        self.assertEqual(r["note"], "")
        _, lines = rewrite(body="Hi Sam,\n\nOn slides: [TBD]\nOn the budget: [TBD]\n\nBest,\nAlex", instruction="bullets")
        self.assertIn("\n- On slides: [TBD]\n- On the budget: [TBD]\n", lines["text"], "each line is its own bullet")
        _, zh = rewrite(body=ZH, instruction="語氣正式一點，並且道歉", lang="zh-Hant")
        self.assertEqual(zh["applied"], ["formal", "apology"])
        self.assertIn("造成不便，敬請見諒。", zh["text"])

    def test_unknown_instruction_says_it_needs_an_llm(self):
        _, r = rewrite(body=EN, instruction="translate to French")
        self.assertFalse(r["changed"])
        self.assertEqual(r["text"].strip(), EN.strip())
        self.assertIn("needs an LLM", r["note"])
        _, zh = rewrite(body=EN, instruction="翻成法文", lang="zh-Hant")
        self.assertIn("需要接 LLM", zh["note"])

    def test_agent_rewrites_with_the_instruction(self):
        use_cli_agent(self, "import sys, json; p = json.load(sys.stdin)['ask']; "
                            "print('Bonjour Samira' if 'translate to French' in p and 'shorter' in p and 'cannot' not in p "
                            "else 'missing')")
        _, r = rewrite(body=EN, tone="shorter")
        self.assertEqual(r["source"], "agent")
        _, r = rewrite(body=EN, instruction="translate to French and make it shorter")
        self.assertEqual((r["text"], r["source"], r["label"]), ("Bonjour Samira", "agent", "AI draft · cli"))

    def test_validation(self):
        self.assertEqual(rewrite(body="", tone="formal")[0], 400)
        self.assertEqual(rewrite(body="hi")[0], 400)
        self.assertEqual(rewrite(body="hi", tone="angrier")[0], 400)
        self.assertEqual(rewrite(body="hi", tone="formal", style="loud")[0], 400)


if __name__ == "__main__":
    unittest.main()
