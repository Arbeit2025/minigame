import importlib.util
import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

APP_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gameapp.py"
)


def load_app(db_path):
    spec = importlib.util.spec_from_file_location("gameapp", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.APP_DB = Path(db_path)
    module.init_db()
    return module


class MinigameTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.unlink(self.db_path)
        self.mod = load_app(self.db_path)
        self.client = self.mod.app.test_client()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def query(self, sql):
        c = sqlite3.connect(self.db_path)
        rows = c.execute(sql).fetchall()
        c.close()
        return rows

    def make_table_with_entry(self):
        self.client.post("/games/roulette/tables/create", data={"title": "ランチ抽選"})
        table_id = self.query("SELECT id FROM tables")[0][0]
        self.client.post(
            "/games/roulette/entries/add",
            data={"table_id": str(table_id), "name": "候補A", "weight": "1"},
        )
        return table_id

    def test_index_is_portal(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("自作ミニゲーム集", body)
        self.assertIn("ルーレット抽選", body)
        self.assertIn("/games/roulette", body)

    def test_healthz(self):
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)

    def test_roulette_page_ok(self):
        res = self.client.get("/games/roulette")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ルーレット抽選", res.get_data(as_text=True))

    def test_table_and_entry_flow(self):
        table_id = self.make_table_with_entry()
        self.assertEqual(len(self.query("SELECT id FROM entries")), 1)
        body = self.client.get(f"/games/roulette?table_id={table_id}").get_data(as_text=True)
        self.assertIn("候補A", body)

    def test_spin_records_result(self):
        table_id = self.make_table_with_entry()
        res = self.client.post(
            "/games/roulette/spin", data={"table_id": str(table_id), "times": "1"}
        )
        self.assertIn(res.status_code, (200, 302))
        self.assertEqual(len(self.query("SELECT id FROM spins")), 1)

    def test_legacy_post_paths_still_work(self):
        res = self.client.post("/tables/create", data={"title": "旧パス確認"})
        self.assertIn(res.status_code, (200, 302))
        self.assertEqual(len(self.query("SELECT id FROM tables")), 1)


class NewGamesTest(MinigameTest):
    def test_portal_lists_nine_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in ("roulette", "omikuji", "highlow", "number", "reaction",
                     "stopwatch", "janken", "slot", "dice"):
            self.assertIn(f"/games/{slug}", body)
        for title in ("おみくじ", "ハイ＆ロー", "数当てゲーム", "反応速度テスト",
                      "ストップウォッチ", "じゃんけん", "絵文字スロット", "サイコロ勝負"):
            self.assertIn(title, body)

    def test_portal_lists_nineteen_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in ("coinflip", "mathdrill", "memory", "typing", "stroop",
                     "concentration", "monty", "quiz", "count", "sort"):
            self.assertIn(f"/games/{slug}", body)
        for title in ("コイントス", "計算ドリル", "記憶力テスト", "タイピング",
                      "ストループ", "神経衰弱", "モンティホール", "クイズ",
                      "どっちが多い？", "数字並べ替え"):
            self.assertIn(title, body)
        self.assertIn("100 本", body)

    def test_omikuji_draw(self):
        res = self.client.get("/games/omikuji")
        self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/omikuji/draw")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        fortunes = ("大吉", "中吉", "小吉", "末吉", "大凶")
        self.assertTrue(any(f in body for f in fortunes))

    def test_highlow_flow(self):
        res = self.client.get("/games/highlow")
        self.assertEqual(res.status_code, 200)
        self.assertIn("今のカード", res.get_data(as_text=True))
        for _ in range(3):
            res = self.client.post("/games/highlow/guess", data={"choice": "high"})
            self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("連勝", body)

    def test_number_game_win_records_score(self):
        self.client.get("/games/number")
        with self.client.session_transaction() as sess:
            secret = sess["num_secret"]
        res = self.client.post("/games/number/guess", data={"guess": str(secret)})
        self.assertEqual(res.status_code, 200)
        self.assertIn("正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='number'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    def test_number_game_hint(self):
        self.client.get("/games/number")
        with self.client.session_transaction() as sess:
            secret = sess["num_secret"]
        wrong = secret % 100 + 1  # 1..100 and never the secret
        res = self.client.post("/games/number/guess", data={"guess": str(wrong)})
        body = res.get_data(as_text=True)
        self.assertTrue("もっと大きい" in body or "もっと小さい" in body)

    def test_reaction_score_saved(self):
        res = self.client.get("/games/reaction")
        self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/reaction/score", data={"ms": "250"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {"ok": True, "best": 250})
        res = self.client.post("/games/reaction/score", data={"ms": "300"})
        self.assertEqual(res.get_json()["best"], 250)
        res = self.client.post("/games/reaction/score", data={"ms": "10"})
        self.assertEqual(res.status_code, 400)
        body = self.client.get("/games/reaction").get_data(as_text=True)
        self.assertIn("250", body)

    def test_stopwatch_score_saved(self):
        res = self.client.get("/games/stopwatch")
        self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/stopwatch/score", data={"error_ms": "120"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 120})
        res = self.client.post("/games/stopwatch/score", data={"error_ms": "45"})
        self.assertEqual(res.get_json()["best"], 45)
        body = self.client.get("/games/stopwatch").get_data(as_text=True)
        self.assertIn("45", body)

    def test_janken_play(self):
        res = self.client.get("/games/janken")
        self.assertEqual(res.status_code, 200)
        for _ in range(5):
            res = self.client.post("/games/janken/play", data={"hand": "グー"})
            self.assertEqual(res.status_code, 200)
            body = res.get_data(as_text=True)
            self.assertTrue("勝ち" in body or "負け" in body or "あいこ" in body)
            self.assertIn("CPU", body)

    def test_slot_spin_and_reset(self):
        res = self.client.get("/games/slot")
        self.assertEqual(res.status_code, 200)
        self.assertIn("コイン: 100", res.get_data(as_text=True))
        res = self.client.post("/games/slot/spin")
        self.assertEqual(res.status_code, 200)
        coins = int(self.query("SELECT value FROM kv WHERE key='slot_coins'")[0][0])
        self.assertGreaterEqual(coins, 90)  # 100 - 10 + payout(>=0)
        self.assertEqual(len(self.query("SELECT id FROM scores WHERE game='slot'")), 1)
        # Drain the coins through the module API, then reset must refill.
        self.mod.set_kv("slot_coins", "0")
        res = self.client.post("/games/slot/spin")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(int(self.query("SELECT value FROM kv WHERE key='slot_coins'")[0][0]), 0)
        self.client.post("/games/slot/reset")
        self.assertEqual(int(self.query("SELECT value FROM kv WHERE key='slot_coins'")[0][0]), 100)

    def test_dice_roll_records_score(self):
        res = self.client.get("/games/dice")
        self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/dice/roll")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("CPU", body)
        self.assertTrue("勝ち" in body or "引き分け" in body)
        rows = self.query("SELECT score FROM scores WHERE game='dice'")
        self.assertEqual(len(rows), 1)
        self.assertTrue(2 <= rows[0][0] <= 18)


class MoreGamesTest(MinigameTest):
    def test_coinflip_flip(self):
        res = self.client.get("/games/coinflip")
        self.assertEqual(res.status_code, 200)
        for _ in range(4):
            res = self.client.post("/games/coinflip/flip", data={"choice": "表"})
            self.assertEqual(res.status_code, 200)
            body = res.get_data(as_text=True)
            self.assertTrue("正解" in body or "はずれ" in body)
            self.assertIn("連勝", body)

    def test_mathdrill_all_correct_records_time(self):
        res = self.client.get("/games/mathdrill")
        self.assertEqual(res.status_code, 200)
        self.assertIn("計算ドリル", res.get_data(as_text=True))
        for _ in range(10):
            with self.client.session_transaction() as sess:
                answer = sess["md_answer"]
            res = self.client.post("/games/mathdrill/answer", data={"answer": str(answer)})
            self.assertEqual(res.status_code, 200)
        self.assertIn("全10問正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='mathdrill'")
        self.assertEqual(len(rows), 1)
        self.assertGreaterEqual(rows[0][0], 1)

    def test_memory_flow(self):
        res = self.client.get("/games/memory")
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            digits = sess["mem_digits"]
            level = sess["mem_level"]
        self.assertEqual(level, 3)
        res = self.client.post("/games/memory/answer", data={"answer": digits})
        self.assertEqual(res.status_code, 200)
        self.assertIn("正解", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["mem_level"], 4)
            digits2 = sess["mem_digits"]
        res = self.client.post("/games/memory/answer", data={"answer": digits2 + "x"})
        self.assertIn("記録しました", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='memory'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 4)

    def test_typing_score_saved(self):
        res = self.client.get("/games/typing")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertTrue(any(w in body for w in self.mod.TYPING_WORDS))
        res = self.client.post("/games/typing/score", data={"ms": "5000"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 5000})
        res = self.client.post("/games/typing/score", data={"ms": "4200"})
        self.assertEqual(res.get_json()["best"], 4200)
        res = self.client.post("/games/typing/score", data={"ms": "10"})
        self.assertEqual(res.status_code, 400)

    def test_stroop_all_correct(self):
        res = self.client.get("/games/stroop")
        self.assertEqual(res.status_code, 200)
        for _ in range(10):
            with self.client.session_transaction() as sess:
                questions = sess["st_questions"]
                idx = sess["st_idx"]
            ink_name = self.mod.STROOP_COLORS[questions[idx][1]][0]
            res = self.client.post("/games/stroop/answer", data={"choice": ink_name})
            self.assertEqual(res.status_code, 200)
        self.assertIn("10 / 10 問正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='stroop'")
        self.assertEqual(len(rows), 1)
        correct, _elapsed = self.mod.stroop_decode(rows[0][0])
        self.assertEqual(correct, 10)

    def test_concentration_perfect_game(self):
        res = self.client.get("/games/concentration")
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            cards = list(sess["cc_cards"])
        pairs = {}
        for i, emoji in enumerate(cards):
            pairs.setdefault(emoji, []).append(i)
        self.assertEqual(len(pairs), 6)
        for indices in pairs.values():
            self.assertEqual(len(indices), 2)
            for i in indices:
                res = self.client.post("/games/concentration/flip", data={"index": str(i)})
                self.assertEqual(res.status_code, 200)
        self.assertIn("全部揃いました", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='concentration'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 6)

    def test_monty_flow_and_stats(self):
        res = self.client.get("/games/monty")
        self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/monty/pick", data={"door": "0"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("変える", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            self.assertIn("mt_prize", sess)
            self.assertIn("mt_opened", sess)
        res = self.client.post("/games/monty/decide", data={"choice": "switch"})
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertTrue("当たり" in body or "ハズレ" in body)
        games = self.query("SELECT value FROM kv WHERE key='monty_switch_games'")
        self.assertEqual(games[0][0], "1")
        # stay path also counts
        self.client.post("/games/monty/pick", data={"door": "1"})
        self.client.post("/games/monty/decide", data={"choice": "stay"})
        games = self.query("SELECT value FROM kv WHERE key='monty_stay_games'")
        self.assertEqual(games[0][0], "1")

    def test_quiz_all_correct(self):
        res = self.client.get("/games/quiz")
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(self.mod.QUIZ_BANK), 20)
        for _ in range(10):
            with self.client.session_transaction() as sess:
                answer = sess["qz_answer"]
            res = self.client.post("/games/quiz/answer", data={"choice": str(answer)})
            self.assertEqual(res.status_code, 200)
        self.assertIn("10 / 10 問正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='quiz'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 10)

    def test_count_correct_answer_records_streak(self):
        res = self.client.get("/games/count")
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            left, right = sess["ct_left"], sess["ct_right"]
        side = "left" if left > right else "right"
        res = self.client.post("/games/count/answer", data={"side": side})
        self.assertEqual(res.status_code, 200)
        self.assertIn("正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='count'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    def test_coinflip_result_shows_prediction(self):
        res = self.client.post("/games/coinflip/flip", data={"choice": "裏"})
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("あなたの予想は 裏 でした", body)

    def test_memory_input_disabled_while_showing(self):
        res = self.client.get("/games/memory")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('id="answer-input"', body)
        self.assertIn('placeholder="覚えた数字" disabled', body)
        self.assertIn("input.disabled = false", body)

    def test_typing_has_again_button(self):
        res = self.client.get("/games/typing")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('id="again"', body)
        self.assertIn("もう一度遊ぶ", body)
        self.assertNotIn("読み込むともう一度遊べます", body)

    def test_monty_pick_buttons_are_numbered(self):
        res = self.client.get("/games/monty")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        for n in (1, 2, 3):
            self.assertIn(f"{n}番のドア", body)

    def test_count_has_left_right_panels(self):
        res = self.client.get("/games/count")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('class="panel left"', body)
        self.assertIn('class="panel right"', body)
        self.assertIn("<h3>左（", body)
        self.assertIn("<h3>右（", body)

    def test_sort_bestline_is_separate_row(self):
        res = self.client.get("/games/sort")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn('<p class="result" id="bestline">', body)
        self.assertIn('<p class="result" id="message">次は 1 を押してね</p>', body)
        self.assertIn('id="again"', body)
        self.assertIn("もう一度遊ぶ", body)
        self.assertNotIn("読み込むともう一度遊べます", body)

    def test_sort_score_saved(self):
        res = self.client.get("/games/sort")
        self.assertEqual(res.status_code, 200)
        self.assertIn("数字並べ替え", res.get_data(as_text=True))
        res = self.client.post("/games/sort/score", data={"ms": "3000"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 3000})
        res = self.client.post("/games/sort/score", data={"ms": "2500"})
        self.assertEqual(res.get_json()["best"], 2500)
        res = self.client.post("/games/sort/score", data={"ms": "100"})
        self.assertEqual(res.status_code, 400)


class NewFourGamesTest(MinigameTest):
    def test_portal_lists_four_new_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in ("geoquiz", "escape-cocoa", "escape-science", "escape-cafe"):
            self.assertIn(f"/games/{slug}", body)
        for title in ("世界地理クイズ", "ココアの部屋からの脱出",
                      "理科室からの脱出", "喫茶店の倉庫からの脱出"):
            self.assertIn(title, body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)

    def test_geoquiz_bank_and_items(self):
        self.assertGreaterEqual(len(self.mod.GEO_BANK), 40)
        for entry in self.mod.GEO_BANK:
            self.assertTrue(entry["country"] and entry["capital"] and entry["flag"])
        res = self.client.get("/games/geoquiz")
        self.assertEqual(res.status_code, 200)
        self.assertIn("世界地理クイズ", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            items = sess["gq_items"]
        self.assertEqual(len(items), 10)
        for item in items:
            self.assertEqual(len(item["choices"]), 3)
            self.assertIn(item["answer"], (0, 1, 2))
            self.assertEqual(len(set(item["choices"])), 3)

    def test_geoquiz_all_correct(self):
        res = self.client.get("/games/geoquiz")
        self.assertEqual(res.status_code, 200)
        for _ in range(10):
            with self.client.session_transaction() as sess:
                idx = sess["gq_idx"]
                answer = sess["gq_items"][idx]["answer"]
            res = self.client.post("/games/geoquiz/answer", data={"choice": str(answer)})
            self.assertEqual(res.status_code, 200)
        self.assertIn("10 / 10 問正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='geoquiz'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 10)

    def test_geoquiz_wrong_answer(self):
        self.client.get("/games/geoquiz")
        with self.client.session_transaction() as sess:
            answer = sess["gq_items"][0]["answer"]
        wrong = (answer + 1) % 3
        res = self.client.post("/games/geoquiz/answer", data={"choice": str(wrong)})
        self.assertEqual(res.status_code, 200)
        self.assertIn("不正解", res.get_data(as_text=True))

    def escape_act(self, slug, action):
        res = self.client.post(f"/games/{slug}/act", data={"action": action})
        self.assertEqual(res.status_code, 200)
        return res.get_data(as_text=True)

    def test_escape_cocoa_clear_flow(self):
        res = self.client.get("/games/escape-cocoa")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ココアの部屋からの脱出", res.get_data(as_text=True))
        # 鍵なしでドアを開けても失敗し、記録は付かない
        body = self.escape_act("escape-cocoa", "door")
        self.assertIn("鍵がかかっている", body)
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='escape-cocoa'"), [])
        # 本棚は紙きれのヒントがないと進めない
        body = self.escape_act("escape-cocoa", "shelf")
        self.assertIn("分からない", body)
        self.escape_act("escape-cocoa", "desk")
        body = self.escape_act("escape-cocoa", "shelf")
        self.assertIn("小さな鍵", body)
        body = self.escape_act("escape-cocoa", "tin")
        self.assertIn("ドアの鍵", body)
        body = self.escape_act("escape-cocoa", "door")
        self.assertIn("脱出成功", body)
        rows = self.query("SELECT score FROM scores WHERE game='escape-cocoa'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    def test_escape_science_clear_flow(self):
        res = self.client.get("/games/escape-science")
        self.assertEqual(res.status_code, 200)
        self.assertIn("理科室からの脱出", res.get_data(as_text=True))
        # ビーカーなしでは水を汲めない
        body = self.escape_act("escape-science", "tap")
        self.assertIn("容器がいる", body)
        self.escape_act("escape-science", "board")
        self.escape_act("escape-science", "locker")
        self.escape_act("escape-science", "tap")
        body = self.escape_act("escape-science", "tank")
        self.assertIn("理科室の鍵", body)
        body = self.escape_act("escape-science", "door")
        self.assertIn("脱出成功", body)
        rows = self.query("SELECT score FROM scores WHERE game='escape-science'")
        self.assertEqual(len(rows), 1)

    def test_escape_cafe_clear_flow(self):
        res = self.client.get("/games/escape-cafe")
        self.assertEqual(res.status_code, 200)
        self.assertIn("喫茶店の倉庫からの脱出", res.get_data(as_text=True))
        # 脚立なしでは高い棚に届かない／メモなしでは冷蔵庫の横に気づかない
        body = self.escape_act("escape-cafe", "high")
        self.assertIn("手が届かない", body)
        body = self.escape_act("escape-cafe", "fridge")
        self.assertIn("何もなさそうだ", body)
        self.escape_act("escape-cafe", "shelf")
        self.escape_act("escape-cafe", "high")
        self.escape_act("escape-cafe", "tin")
        body = self.escape_act("escape-cafe", "fridge")
        self.assertIn("倉庫の鍵", body)
        body = self.escape_act("escape-cafe", "door")
        self.assertIn("脱出成功", body)
        rows = self.query("SELECT score FROM scores WHERE game='escape-cafe'")
        self.assertEqual(len(rows), 1)

    def test_escape_reset_clears_state(self):
        self.client.get("/games/escape-cocoa")
        self.escape_act("escape-cocoa", "desk")
        with self.client.session_transaction() as sess:
            self.assertIn("paper", sess.get("esc_escape-cocoa_flags", []))
        res = self.client.post("/games/escape-cocoa/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("esc_escape-cocoa_flags", sess)
            self.assertNotIn("esc_escape-cocoa_items", sess)


class FiveMoreGamesTest(MinigameTest):
    def test_portal_lists_five_more_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in ("hitblow", "shoefly", "fishing", "dodge", "snowball"):
            self.assertIn(f"/games/{slug}", body)
        for title in ("あいことば推理", "くつ飛ばし", "つりぼり図鑑",
                      "かわしサバイバー", "ゆき玉転がし"):
            self.assertIn(title, body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)

    # ---- hitblow ----
    def test_hitblow_page_ok(self):
        res = self.client.get("/games/hitblow")
        self.assertEqual(res.status_code, 200)
        self.assertIn("あいことば推理", res.get_data(as_text=True))

    def test_hitblow_guess_flow_and_win(self):
        self.client.get("/games/hitblow")
        with self.client.session_transaction() as sess:
            secret = sess["hb_secret"]
        self.assertEqual(len(secret), 4)
        self.assertEqual(len(set(secret)), 4)
        # 先頭2桁を入れ替えると 2ヒット2ブロー になる（残り2桁は位置も一致）
        guess = secret[1] + secret[0] + secret[2:]
        res = self.client.post("/games/hitblow/guess", data={"guess": guess})
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("2 ヒット / 2 ブロー", body)
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='hitblow'"), [])
        # 正解するとスコア（回数）が記録される
        res = self.client.post("/games/hitblow/guess", data={"guess": secret})
        self.assertEqual(res.status_code, 200)
        self.assertIn("正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='hitblow'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 2)

    def test_hitblow_invalid_guess(self):
        self.client.get("/games/hitblow")
        res = self.client.post("/games/hitblow/guess", data={"guess": "112"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("重複のない4桁の数字", res.get_data(as_text=True))
        res = self.client.post("/games/hitblow/guess", data={"guess": "1123"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("重複のない4桁の数字", res.get_data(as_text=True))
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='hitblow'"), [])

    def test_hitblow_reset(self):
        self.client.get("/games/hitblow")
        with self.client.session_transaction() as sess:
            self.assertIn("hb_secret", sess)
        res = self.client.post("/games/hitblow/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("hb_secret", sess)

    # ---- shoefly ----
    def test_shoefly_page_and_score(self):
        res = self.client.get("/games/shoefly")
        self.assertEqual(res.status_code, 200)
        self.assertIn("くつ飛ばし", res.get_data(as_text=True))
        res = self.client.post("/games/shoefly/score", data={"dist10": "325"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 325})
        res = self.client.post("/games/shoefly/score", data={"dist10": "250"})
        self.assertEqual(res.get_json()["best"], 325)
        res = self.client.post("/games/shoefly/score", data={"dist10": "9999"})
        self.assertEqual(res.status_code, 400)

    # ---- fishing ----
    def test_fishing_page_ok(self):
        res = self.client.get("/games/fishing")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("つりぼり図鑑", body)
        self.assertIn('<span id="kindCount">0</span>', body)
        self.assertIn("？？？", body)
        self.assertEqual(len(self.mod.FISH_KINDS), 12)

    def test_fishing_cast_escape_and_catch(self):
        self.client.get("/games/fishing")
        # 反応が遅すぎると逃げる
        res = self.client.post("/games/fishing/cast", data={"ms": "9999"})
        self.assertEqual(res.get_json(), {"ok": True, "caught": False})
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='fishing'"), [])
        # 速く反応すれば必ず何か釣れて、図鑑とスコアに残る
        res = self.client.post("/games/fishing/cast", data={"ms": "100"})
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["caught"])
        self.assertIn(data["name"], [f["name"] for f in self.mod.FISH_KINDS])
        self.assertEqual(data["kinds"], 1)
        self.assertEqual(data["total"], 12)
        rows = self.query("SELECT score FROM scores WHERE game='fishing'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], data["points"])
        # 図鑑の進み具合がページに出る
        body = self.client.get("/games/fishing").get_data(as_text=True)
        self.assertIn('<span id="kindCount">1</span>', body)
        self.assertIn(data["name"], body)
        # 不正な値は 400
        res = self.client.post("/games/fishing/cast", data={"ms": "abc"})
        self.assertEqual(res.status_code, 400)

    def test_fishing_reset(self):
        self.client.post("/games/fishing/cast", data={"ms": "100"})
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("fish_caught", [])), 1)
        res = self.client.post("/games/fishing/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("fish_caught", sess)

    # ---- dodge ----
    def test_dodge_page_and_score(self):
        res = self.client.get("/games/dodge")
        self.assertEqual(res.status_code, 200)
        self.assertIn("かわしサバイバー", res.get_data(as_text=True))
        res = self.client.post("/games/dodge/score", data={"sec10": "123"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 123})
        res = self.client.post("/games/dodge/score", data={"sec10": "100"})
        self.assertEqual(res.get_json()["best"], 123)
        res = self.client.post("/games/dodge/score", data={"sec10": "-5"})
        self.assertEqual(res.status_code, 400)

    # ---- snowball ----
    def test_snowball_page_and_score(self):
        res = self.client.get("/games/snowball")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ゆき玉転がし", res.get_data(as_text=True))
        res = self.client.post("/games/snowball/score", data={"meters": "45"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 45})
        res = self.client.post("/games/snowball/score", data={"meters": "30"})
        self.assertEqual(res.get_json()["best"], 45)
        res = self.client.post("/games/snowball/score", data={"meters": "xyz"})
        self.assertEqual(res.status_code, 400)


class ZhGachaTest(MinigameTest):
    def test_portal_lists_zhgacha(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("/games/zhgacha", body)
        self.assertIn("中国語単語ガチャ", body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)
        self.assertEqual(len(self.mod.ZH_WORDS), 110)

    def test_zhgacha_page_ok(self):
        res = self.client.get("/games/zhgacha")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("中国語単語ガチャ", body)
        self.assertIn('<span id="kindCount">0</span>', body)
        self.assertIn("/ 110 種", body)

    def test_zhgacha_draw_collects_and_scores(self):
        res = self.client.post("/games/zhgacha/draw")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("zh_collected", [])), 1)
            idx = sess["zh_last"]
        word = self.mod.ZH_WORDS[idx]
        # 引いた単語カード（簡体字・ピンイン・日本語訳）がページに出る
        body = self.client.get("/games/zhgacha").get_data(as_text=True)
        self.assertIn(word["hanzi"], body)
        self.assertIn(word["pinyin"], body)
        self.assertIn(word["meaning"], body)
        self.assertIn('<span id="kindCount">1</span>', body)
        # 種類数（1）がスコアとして記録される
        rows = self.query("SELECT score FROM scores WHERE game='zhgacha'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    def test_zhgacha_draw_duplicate_does_not_score(self):
        with self.client.session_transaction() as sess:
            sess["zh_collected"] = list(range(len(self.mod.ZH_WORDS)))
        res = self.client.post("/games/zhgacha/draw")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess["zh_collected"]), 110)
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='zhgacha'"), [])
        body = self.client.get("/games/zhgacha").get_data(as_text=True)
        self.assertIn('<span id="kindCount">110</span>', body)

    def test_zhgacha_reset(self):
        self.client.post("/games/zhgacha/draw")
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("zh_collected", [])), 1)
        res = self.client.post("/games/zhgacha/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("zh_collected", sess)
            self.assertNotIn("zh_last", sess)
        body = self.client.get("/games/zhgacha").get_data(as_text=True)
        self.assertIn('<span id="kindCount">0</span>', body)


class EnGachaTest(MinigameTest):
    def test_portal_lists_engacha(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("/games/engacha", body)
        self.assertIn("英単語ガチャ", body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)
        self.assertEqual(len(self.mod.EN_WORDS), 110)

    def test_en_words_data_valid(self):
        words = [w["word"] for w in self.mod.EN_WORDS]
        self.assertEqual(len(words), len(set(words)))
        for w in self.mod.EN_WORDS:
            self.assertTrue(w["word"])
            self.assertTrue(w["kana"])
            self.assertTrue(w["meaning"])
            self.assertTrue(w["example"])

    def test_engacha_page_ok(self):
        res = self.client.get("/games/engacha")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("英単語ガチャ", body)
        self.assertIn('<span id="kindCount">0</span>', body)
        self.assertIn("/ 110 種", body)

    def test_engacha_draw_collects_and_scores(self):
        res = self.client.post("/games/engacha/draw")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("en_collected", [])), 1)
            idx = sess["en_last"]
        word = self.mod.EN_WORDS[idx]
        # 引いた単語カード（英単語・カタカナ読み・日本語訳・例文）がページに出る
        body = self.client.get("/games/engacha").get_data(as_text=True)
        self.assertIn(word["word"], body)
        self.assertIn(word["kana"], body)
        self.assertIn(word["meaning"], body)
        self.assertIn(word["example"], body)
        self.assertIn('<span id="kindCount">1</span>', body)
        # 種類数（1）がスコアとして記録される
        rows = self.query("SELECT score FROM scores WHERE game='engacha'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    def test_engacha_draw_duplicate_does_not_score(self):
        with self.client.session_transaction() as sess:
            sess["en_collected"] = list(range(len(self.mod.EN_WORDS)))
        res = self.client.post("/games/engacha/draw")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess["en_collected"]), 110)
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='engacha'"), [])
        body = self.client.get("/games/engacha").get_data(as_text=True)
        self.assertIn('<span id="kindCount">110</span>', body)

    def test_engacha_reset(self):
        self.client.post("/games/engacha/draw")
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("en_collected", [])), 1)
        res = self.client.post("/games/engacha/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("en_collected", sess)
            self.assertNotIn("en_last", sess)
        body = self.client.get("/games/engacha").get_data(as_text=True)
        self.assertIn('<span id="kindCount">0</span>', body)


class EoGachaTest(MinigameTest):
    def test_portal_lists_eogacha(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("/games/eogacha", body)
        self.assertIn("エスペラント単語ガチャ", body)
        self.assertEqual(len(self.mod.EO_WORDS), 110)

    def test_eo_words_data_valid(self):
        words = [w["word"] for w in self.mod.EO_WORDS]
        self.assertEqual(len(words), len(set(words)))
        for w in self.mod.EO_WORDS:
            self.assertTrue(w["word"])
            self.assertTrue(w["meaning"])
            self.assertTrue(w["example"])

    def test_eogacha_page_ok(self):
        res = self.client.get("/games/eogacha")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("エスペラント単語ガチャ", body)
        self.assertIn("綴りをそのまま読める", body)
        self.assertIn('<span id="kindCount">0</span>', body)
        self.assertIn("/ 110 種", body)

    def test_eogacha_draw_collects_and_scores(self):
        res = self.client.post("/games/eogacha/draw")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("eo_collected", [])), 1)
            idx = sess["eo_last"]
        word = self.mod.EO_WORDS[idx]
        # 引いた単語カード（単語・日本語訳・例文）がページに出る
        body = self.client.get("/games/eogacha").get_data(as_text=True)
        self.assertIn(word["word"], body)
        self.assertIn(word["meaning"], body)
        self.assertIn(word["example"], body)
        self.assertIn('<span id="kindCount">1</span>', body)
        # 種類数（1）がスコアとして記録される
        rows = self.query("SELECT score FROM scores WHERE game='eogacha'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    def test_eogacha_draw_duplicate_does_not_score(self):
        with self.client.session_transaction() as sess:
            sess["eo_collected"] = list(range(len(self.mod.EO_WORDS)))
        res = self.client.post("/games/eogacha/draw")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess["eo_collected"]), 110)
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='eogacha'"), [])
        body = self.client.get("/games/eogacha").get_data(as_text=True)
        self.assertIn('<span id="kindCount">110</span>', body)

    def test_eogacha_reset(self):
        self.client.post("/games/eogacha/draw")
        with self.client.session_transaction() as sess:
            self.assertEqual(len(sess.get("eo_collected", [])), 1)
        res = self.client.post("/games/eogacha/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("eo_collected", sess)
            self.assertNotIn("eo_last", sess)
        body = self.client.get("/games/eogacha").get_data(as_text=True)
        self.assertIn('<span id="kindCount">0</span>', body)

class ShindanGamesTest(MinigameTest):
    def answer_all_for_type(self, slug, endpoint_questions, type_key):
        """指定タイプの選択肢をなるべく選んで進め、最後のページ本文を返す。

        そのタイプの選択肢がない質問では先頭の選択肢で代用する（対象タイプが
        大差で勝つ設計なので、結果は変わらない）。
        """
        body = ""
        for question in endpoint_questions:
            idx = next(
                (i for i, c in enumerate(question["choices"]) if c["type"] == type_key),
                0,
            )
            res = self.client.post(f"/games/{slug}/answer", data={"choice": str(idx)})
            self.assertIn(res.status_code, (200, 302))
        body = self.client.get(f"/games/{slug}").get_data(as_text=True)
        return body

    def test_portal_lists_shindan_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in ("shindan-trio", "shindan-snack", "shindan-study"):
            self.assertIn(f"/games/{slug}", body)
        for title in ("三人娘タイプ診断", "今日のおやつ診断", "べんきょうタイプ診断"):
            self.assertIn(title, body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)

    # ---- 三人娘タイプ診断 ----
    def test_trio_page_ok(self):
        res = self.client.get("/games/shindan-trio")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("三人娘タイプ診断", body)
        self.assertIn("第 1 問 ／ 全 8 問", body)
        self.assertEqual(len(self.mod.TRIO_QUESTIONS), 8)

    def test_trio_flow_cocoa(self):
        body = self.answer_all_for_type(
            "shindan-trio", self.mod.TRIO_QUESTIONS, "cocoa"
        )
        self.assertIn("診断結果", body)
        self.assertIn("ココア型", body)
        self.assertIn("もう一度診断する", body)
        # 数値スコアは記録されない
        self.assertEqual(
            self.query("SELECT id FROM scores WHERE game LIKE 'shindan%'"), []
        )

    def test_trio_flow_chai(self):
        body = self.answer_all_for_type(
            "shindan-trio", self.mod.TRIO_QUESTIONS, "chai"
        )
        self.assertIn("チャイ型", body)

    def test_trio_tie_breaks_by_definition_order(self):
        # cocoa と mocha が同点なら、定義順で先のココア型になる
        result = self.mod.shindan_judge(
            ["cocoa", "mocha", "chai"], {"cocoa": 2, "mocha": 2, "chai": 1}
        )
        self.assertEqual(result, "cocoa")
        result = self.mod.shindan_judge(
            ["cocoa", "mocha", "chai"], {"cocoa": 0, "mocha": 3, "chai": 3}
        )
        self.assertEqual(result, "mocha")

    def test_trio_reset(self):
        self.client.post("/games/shindan-trio/answer", data={"choice": "0"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("strio_idx"), 1)
        res = self.client.post("/games/shindan-trio/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("strio_idx", sess)
            self.assertNotIn("strio_scores", sess)
        body = self.client.get("/games/shindan-trio").get_data(as_text=True)
        self.assertIn("第 1 問 ／ 全 8 問", body)

    # ---- 今日のおやつ診断 ----
    def test_snack_page_ok(self):
        res = self.client.get("/games/shindan-snack")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("今日のおやつ診断", body)
        self.assertIn("第 1 問 ／ 全 6 問", body)
        self.assertEqual(len(self.mod.SNACK_QUESTIONS), 6)
        self.assertEqual(len(self.mod.SNACK_TYPES), 6)

    def test_snack_flow_cake(self):
        body = self.answer_all_for_type(
            "shindan-snack", self.mod.SNACK_QUESTIONS, "cake"
        )
        self.assertIn("診断結果", body)
        self.assertIn("ケーキ", body)
        self.assertEqual(
            self.query("SELECT id FROM scores WHERE game LIKE 'shindan%'"), []
        )

    def test_snack_reset(self):
        self.client.post("/games/shindan-snack/answer", data={"choice": "0"})
        res = self.client.post("/games/shindan-snack/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("ssnack_idx", sess)
        body = self.client.get("/games/shindan-snack").get_data(as_text=True)
        self.assertIn("第 1 問 ／ 全 6 問", body)

    # ---- べんきょうタイプ診断 ----
    def test_study_page_ok(self):
        res = self.client.get("/games/shindan-study")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("べんきょうタイプ診断", body)
        self.assertIn("第 1 問 ／ 全 8 問", body)
        self.assertEqual(len(self.mod.STUDY_QUESTIONS), 8)
        self.assertEqual(len(self.mod.STUDY_TYPES), 4)

    def test_study_flow_plan(self):
        body = self.answer_all_for_type(
            "shindan-study", self.mod.STUDY_QUESTIONS, "plan"
        )
        self.assertIn("診断結果", body)
        self.assertIn("計画コツコツ型", body)
        # タイプ向けの勉強のコツが添えられている
        self.assertIn("今日の分", body)

    def test_study_flow_env(self):
        body = self.answer_all_for_type(
            "shindan-study", self.mod.STUDY_QUESTIONS, "env"
        )
        self.assertIn("環境こだわり型", body)

    def test_study_reset(self):
        self.client.post("/games/shindan-study/answer", data={"choice": "0"})
        res = self.client.post("/games/shindan-study/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertNotIn("sstudy_idx", sess)
        body = self.client.get("/games/shindan-study").get_data(as_text=True)
        self.assertIn("第 1 問 ／ 全 8 問", body)


class DotboardTest(MinigameTest):
    def test_portal_lists_dotboard(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn("/games/dotboard", body)
        self.assertIn("ドット絵ボード", body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)

    def test_dotboard_page_ok(self):
        res = self.client.get("/games/dotboard")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("ドット絵ボード", body)
        # 16×16 キャンバス
        self.assertIn('<canvas id="board" width="16" height="16"', body)
        # 12色パレット（全色がスウォッチとして並ぶ）
        self.assertEqual(len(self.mod.DOTBOARD_COLORS), 12)
        for color in self.mod.DOTBOARD_COLORS:
            self.assertIn(f'data-color="{color}"', body)
        # 消しゴム・全消し・PNG保存・描けた！・お題ボタン
        self.assertIn('id="eraser"', body)
        self.assertIn("消しゴム", body)
        self.assertIn("ぜんぶ消す", body)
        self.assertIn("PNGで保存", body)
        self.assertIn("描けた！", body)
        self.assertIn('id="themeBtn"', body)
        self.assertIn("お題を引く", body)
        # お題は15〜20個で重複なし、ページ内のJSへもそのまま渡っている
        # （tojson で \uXXXX 形式にエスケープされるため、デコードして照合する）
        self.assertGreaterEqual(len(self.mod.DOTBOARD_THEMES), 15)
        self.assertLessEqual(len(self.mod.DOTBOARD_THEMES), 20)
        self.assertEqual(
            len(self.mod.DOTBOARD_THEMES), len(set(self.mod.DOTBOARD_THEMES))
        )
        m = re.search(r"var themes = (\[.*?\]);", body)
        self.assertIsNotNone(m)
        self.assertEqual(json.loads(m.group(1)), self.mod.DOTBOARD_THEMES)

    def test_dotboard_complete_records(self):
        res = self.client.post("/games/dotboard/complete")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {"ok": True, "best": 1, "count": 1})
        rows = self.query("SELECT score FROM scores WHERE game='dotboard'")
        self.assertEqual([r[0] for r in rows], [1])
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("dotboard_done"), 1)
        # 2回目の完成でセッション数とベストが伸びる
        res = self.client.post("/games/dotboard/complete")
        self.assertEqual(res.get_json(), {"ok": True, "best": 2, "count": 2})
        rows = self.query(
            "SELECT score FROM scores WHERE game='dotboard' ORDER BY id"
        )
        self.assertEqual([r[0] for r in rows], [1, 2])
        # ページにもベスト（完成作品数）が出る
        body = self.client.get("/games/dotboard").get_data(as_text=True)
        self.assertIn('id="bestCount">2<', body)
        self.assertIn('id="doneCount">2<', body)

    def test_dotboard_complete_is_per_session(self):
        # 別セッション（別ブラウザ相当）では完成数は1から数え直すが、
        # ベストはサーバー側の記録として残る
        self.client.post("/games/dotboard/complete")
        self.client.post("/games/dotboard/complete")
        other = self.mod.app.test_client()
        res = other.post("/games/dotboard/complete")
        self.assertEqual(res.get_json()["count"], 1)
        self.assertEqual(res.get_json()["best"], 2)


class NewFiveGamesTest(MinigameTest):
    def test_portal_lists_five_new_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in ("slidepuzzle", "touch25", "marubatsu", "shiritori", "balloonpop"):
            self.assertIn(f"/games/{slug}", body)
        for title in ("スライドパズル", "1→25タッチ", "まるばつ対戦",
                      "しりとり対戦", "風船わり"):
            self.assertIn(title, body)
        self.assertIn("100 本", body)
        self.assertEqual(len(self.mod.GAMES), 100)

    # ---- slidepuzzle ----
    def test_slidepuzzle_page_ok(self):
        res = self.client.get("/games/slidepuzzle")
        self.assertEqual(res.status_code, 200)
        self.assertIn("スライドパズル", res.get_data(as_text=True))

    def test_slidepuzzle_new_board_is_solvable(self):
        # 完成状態からのランダムウォーク生成なので、タイルの転倒数が
        # 常に偶数（＝解ける配置）になること、完成状態そのものにはならないこと
        for _ in range(30):
            board = self.mod.slidepuzzle_new_board()
            self.assertEqual(sorted(board), list(range(9)))
            self.assertFalse(self.mod.slidepuzzle_is_solved(board))
            tiles = [n for n in board if n != 0]
            inversions = sum(
                1
                for i in range(len(tiles))
                for j in range(i + 1, len(tiles))
                if tiles[i] > tiles[j]
            )
            self.assertEqual(inversions % 2, 0)

    def test_slidepuzzle_try_move(self):
        board = [1, 2, 3, 4, 5, 6, 7, 0, 8]
        moved = self.mod.slidepuzzle_try_move(board, 8)
        self.assertEqual(moved, [1, 2, 3, 4, 5, 6, 7, 8, 0])
        # 空きマスから遠いパネルや、空きマス自体は動かせない
        self.assertIsNone(self.mod.slidepuzzle_try_move(board, 0))
        self.assertIsNone(self.mod.slidepuzzle_try_move(board, 7))

    def test_slidepuzzle_solve_flow_records_moves(self):
        self.client.get("/games/slidepuzzle")
        with self.client.session_transaction() as sess:
            sess["sp_board"] = [1, 2, 3, 4, 5, 6, 7, 0, 8]
            sess["sp_moves"] = 4
            sess["sp_done"] = False
        res = self.client.post("/games/slidepuzzle/move", data={"index": "8"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("完成", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game='slidepuzzle'")
        self.assertEqual([r[0] for r in rows], [5])

    def test_slidepuzzle_illegal_move_keeps_state(self):
        self.client.get("/games/slidepuzzle")
        with self.client.session_transaction() as sess:
            sess["sp_board"] = [1, 2, 3, 4, 5, 6, 7, 0, 8]
            sess["sp_moves"] = 0
            sess["sp_done"] = False
        res = self.client.post("/games/slidepuzzle/move", data={"index": "0"})
        self.assertIn("動かせません", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["sp_moves"], 0)
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='slidepuzzle'"), [])

    def test_slidepuzzle_reset(self):
        self.client.get("/games/slidepuzzle")
        res = self.client.post("/games/slidepuzzle/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertIn("sp_board", sess)
            self.assertEqual(sess["sp_moves"], 0)

    # ---- touch25 ----
    def test_touch25_page_ok(self):
        res = self.client.get("/games/touch25")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("1→25タッチ", body)
        self.assertIn("スタート", body)
        for n in range(1, 26):
            self.assertIn(f'data-value="{n}"', body)

    def test_touch25_score(self):
        res = self.client.post("/games/touch25/score", data={"ds": "123"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 123})
        # ベストは最小（最速）
        res = self.client.post("/games/touch25/score", data={"ds": "100"})
        self.assertEqual(res.get_json()["best"], 100)
        res = self.client.post("/games/touch25/score", data={"ds": "150"})
        self.assertEqual(res.get_json()["best"], 100)
        # 不正な値は 400
        for bad in ("5", "abc", "-30"):
            res = self.client.post("/games/touch25/score", data={"ds": bad})
            self.assertEqual(res.status_code, 400)

    # ---- marubatsu ----
    def test_marubatsu_page_ok(self):
        res = self.client.get("/games/marubatsu")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("まるばつ対戦", body)
        self.assertIn("先手", body)
        self.assertIn("後手", body)

    def test_marubatsu_winner(self):
        m = self.mod
        self.assertEqual(m.marubatsu_winner(["○", "○", "○", "", "", "", "", "", ""]), "○")
        self.assertEqual(m.marubatsu_winner(["×", "", "", "×", "", "", "×", "", ""]), "×")
        self.assertEqual(m.marubatsu_winner(["○", "", "", "", "○", "", "", "", "○"]), "○")
        self.assertEqual(
            m.marubatsu_winner(["○", "×", "○", "○", "×", "×", "×", "○", "○"]), "draw"
        )
        self.assertIsNone(m.marubatsu_winner(["○", "", "", "", "×", "", "", "", ""]))

    def test_marubatsu_best_move_wins_and_blocks(self):
        m = self.mod
        # 勝てる手があればそこを取る
        board = ["○", "○", "", "×", "×", "", "", "", ""]
        self.assertEqual(m.marubatsu_best_move(board, "○"), 2)
        # 負けそうなら防ぐ
        board = ["×", "×", "", "○", "", "", "", "", ""]
        self.assertEqual(m.marubatsu_best_move(board, "○"), 2)

    def test_marubatsu_cpu_move_uses_empty_cell(self):
        board = ["○", "×", "○", "×", "○", "×", "", "○", "×"]
        for _ in range(20):
            self.assertEqual(self.mod.marubatsu_cpu_move(board, "×"), 6)
        full = ["○"] * 9
        self.assertIsNone(self.mod.marubatsu_cpu_move(full, "×"))

    def test_marubatsu_start_second_moves_cpu_first(self):
        res = self.client.post("/games/marubatsu/start", data={"first": "0"})
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            board = sess["mb_board"]
        self.assertEqual(board.count("×"), 1)
        self.assertEqual(board.count("○"), 0)

    def test_marubatsu_player_win_records(self):
        self.client.post("/games/marubatsu/start", data={"first": "1"})
        with self.client.session_transaction() as sess:
            sess["mb_board"] = ["○", "○", "", "×", "×", "", "", "", ""]
            sess["mb_over"] = False
        res = self.client.post("/games/marubatsu/move", data={"index": "2"})
        body = res.get_data(as_text=True)
        self.assertIn("あなたの勝ち", body)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get("mb_wins"), 1)
        rows = self.query("SELECT score FROM scores WHERE game='marubatsu'")
        self.assertEqual([r[0] for r in rows], [1])

    def test_marubatsu_occupied_cell_rejected(self):
        self.client.post("/games/marubatsu/start", data={"first": "1"})
        with self.client.session_transaction() as sess:
            sess["mb_board"] = ["○", "", "", "", "×", "", "", "", ""]
            sess["mb_over"] = False
        res = self.client.post("/games/marubatsu/move", data={"index": "0"})
        self.assertIn("埋まっています", res.get_data(as_text=True))
        self.assertEqual(self.query("SELECT id FROM scores WHERE game='marubatsu'"), [])

    # ---- shiritori ----
    def test_shiritori_page_ok(self):
        res = self.client.get("/games/shiritori")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("しりとり対戦", body)
        self.assertIn("にある単語だけ", body)

    def test_shiritori_words_valid(self):
        words = self.mod.SHIRITORI_WORDS
        self.assertGreaterEqual(len(words), 60)
        self.assertEqual(len(words), len(set(words)))
        for w in words:
            self.assertIsNotNone(re.fullmatch(r"[ぁ-んー]+", w), w)
            self.assertFalse(w.startswith("ん"), w)
            # 末尾が小さいかなの単語は入れない（次の単語が存在しなくなるため）
            self.assertNotIn(w[-1], "ゃゅょっゎ", w)

    def test_shiritori_last_kana(self):
        m = self.mod
        self.assertEqual(m.shiritori_last_kana("りんご"), "ご")
        self.assertEqual(m.shiritori_last_kana("すいか"), "か")
        # 「ー」はその前のかなの母音に読み替える
        self.assertEqual(m.shiritori_last_kana("かれー"), "え")

    def test_shiritori_check(self):
        m = self.mod
        self.assertEqual(m.shiritori_check("りんご", "", []), "ok")
        self.assertEqual(m.shiritori_check("ごりら", "ご", []), "ok")
        self.assertEqual(m.shiritori_check("りんご", "ご", []), "wrong_start")
        self.assertEqual(m.shiritori_check("ごりら", "ご", ["ごりら"]), "used")
        self.assertEqual(m.shiritori_check("そらいろ", "", []), "not_in_list")

    def test_shiritori_normalize(self):
        self.assertEqual(self.mod.shiritori_normalize("リンゴ"), "りんご")
        self.assertEqual(self.mod.shiritori_normalize(" りんご "), "りんご")

    def test_shiritori_flow_cpu_continues(self):
        self.client.get("/games/shiritori")
        res = self.client.post("/games/shiritori/play", data={"word": "りんご"})
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            chain = sess["st_chain"]
        # プレイヤー＋CPU の2語がつながり、CPU の単語は「ご」始まり
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[0], ["りんご", "あなた"])
        self.assertEqual(chain[1][1], "CPU")
        self.assertTrue(chain[1][0].startswith("ご"))
        # 使った単語の再使用は弾かれる
        res = self.client.post("/games/shiritori/play", data={"word": "りんご"})
        self.assertIn("もう使われています", res.get_data(as_text=True))
        # 次に必要な頭文字（CPU の単語末尾は「ら」か「ま」）と違う単語は弾かれる
        res = self.client.post("/games/shiritori/play", data={"word": "すいか"})
        self.assertIn("から始まる単語", res.get_data(as_text=True))
        # リストにない単語も弾かれる
        res = self.client.post("/games/shiritori/play", data={"word": "そらいろ"})
        self.assertIn("リストにありません", res.get_data(as_text=True))

    def test_shiritori_n_ending_loses(self):
        self.client.get("/games/shiritori")
        res = self.client.post("/games/shiritori/play", data={"word": "みかん"})
        body = res.get_data(as_text=True)
        self.assertIn("あなたの負け", body)
        with self.client.session_transaction() as sess:
            self.assertTrue(sess["st_over"])
        # 終了時にチェーンの長さ（1語）が記録される
        rows = self.query("SELECT score FROM scores WHERE game='shiritori'")
        self.assertEqual([r[0] for r in rows], [1])

    def test_shiritori_reset(self):
        self.client.get("/games/shiritori")
        self.client.post("/games/shiritori/play", data={"word": "りんご"})
        res = self.client.post("/games/shiritori/reset")
        self.assertIn(res.status_code, (200, 302))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["st_chain"], [])
            self.assertFalse(sess["st_over"])

    # ---- balloonpop ----
    def test_balloonpop_page_ok(self):
        res = self.client.get("/games/balloonpop")
        self.assertEqual(res.status_code, 200)
        body = res.get_data(as_text=True)
        self.assertIn("風船わり", body)
        self.assertIn("スタート", body)
        self.assertIn('id="area"', body)

    def test_balloonpop_score(self):
        res = self.client.post("/games/balloonpop/score", data={"score": "17"})
        self.assertEqual(res.get_json(), {"ok": True, "best": 17})
        # ベストは最大
        res = self.client.post("/games/balloonpop/score", data={"score": "9"})
        self.assertEqual(res.get_json()["best"], 17)
        # 不正な値は 400
        for bad in ("-1", "abc", "9999"):
            res = self.client.post("/games/balloonpop/score", data={"score": bad})
            self.assertEqual(res.status_code, 400)


class GenreFilterTest(MinigameTest):
    def test_index_has_genre_filter_buttons(self):
        body = self.client.get("/").get_data(as_text=True)
        # 「すべて」ボタンとジャンルごとのボタンがある
        self.assertIn('data-filter="all"', body)
        for name in {g["category"] for g in self.mod.GAMES}:
            self.assertIn(f'data-filter="{name}"', body)
        # 絞り込みの説明文がある
        self.assertIn("ジャンルを押すと", body)

    def test_cards_carry_category_for_filtering(self):
        body = self.client.get("/").get_data(as_text=True)
        # 全カードに data-category が付いている
        self.assertEqual(body.count('data-category="'), len(self.mod.GAMES))
        # ジャンルごとの件数が GAMES の実数と一致する
        for name in {g["category"] for g in self.mod.GAMES}:
            expected = sum(1 for g in self.mod.GAMES if g["category"] == name)
            self.assertEqual(body.count(f'data-category="{name}"'), expected)

    def test_filter_script_and_status_present(self):
        body = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="filterStatus"', body)
        self.assertIn("querySelectorAll('.cats button[data-filter]')", body)
        self.assertIn("querySelectorAll('.grid .card')", body)




class SnsNov02GamesTest(MinigameTest):
    """2026-11-02 配信の保留案から実装した15本（SNS10＋ふりーむ5）のテスト。"""

    NEW_SLUGS = ("flasksort", "cupshuffle", "colorwall", "trio-card", "flat3d",
                 "gomoku-tsume", "iceweak", "saisen", "suzuatume", "tunnelface",
                 "bagpack", "wordmonster", "mojiotoshi", "mensetsu", "suishitsu")

    def test_portal_lists_fifteen_new_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in self.NEW_SLUGS:
            self.assertIn(f"/games/{slug}", body)
        self.assertEqual(len(self.mod.GAMES), 100)
        self.assertIn("100 本", body)

    def test_new_games_categories(self):
        cats = {g["slug"]: g["category"] for g in self.mod.GAMES}
        expected = {
            "flasksort": "脳トレ", "cupshuffle": "抽選・占い", "colorwall": "アクション",
            "trio-card": "カード・数字", "flat3d": "脳トレ", "gomoku-tsume": "脳トレ",
            "iceweak": "アクション", "saisen": "アクション", "suzuatume": "アクション",
            "tunnelface": "脳トレ", "bagpack": "創作", "wordmonster": "対戦",
            "mojiotoshi": "脳トレ", "mensetsu": "クイズ・知識", "suishitsu": "クイズ・知識",
        }
        for slug, cat in expected.items():
            self.assertEqual(cats[slug], cat, slug)
        allowed = {"アクション", "脳トレ", "抽選・占い", "クイズ・知識",
                   "対戦", "脱出・謎解き", "カード・数字", "創作"}
        self.assertTrue(set(cats.values()) <= allowed)

    def check_js_score_game(self, slug, title, good, bad_values):
        res = self.client.get(f"/games/{slug}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(title, res.get_data(as_text=True))
        res = self.client.post(f"/games/{slug}/score", data={"score": good})
        self.assertEqual(res.get_json(), {"ok": True, "best": int(good)})
        for bad in bad_values:
            res = self.client.post(f"/games/{slug}/score", data={"score": bad})
            self.assertEqual(res.status_code, 400, (slug, bad))

    # ---- JS進行ゲーム（ページ＋スコア保存） ----
    def test_cupshuffle_page_and_score(self):
        self.check_js_score_game("cupshuffle", "カップシャッフル当て", "12", ("-1", "abc", "1000"))

    def test_colorwall_page_and_score(self):
        self.check_js_score_game("colorwall", "カラー壁ぬけ", "23", ("-1", "abc", "1000"))

    def test_iceweak_page_and_score(self):
        self.check_js_score_game("iceweak", "氷の弱点タップ", "9", ("-1", "abc", "1000"))

    def test_suzuatume_page_and_score(self):
        self.check_js_score_game("suzuatume", "すずあつめ落ちもの", "31", ("-1", "abc", "1000"))

    def test_tunnelface_page_and_score(self):
        self.check_js_score_game("tunnelface", "トンネル顔出し当て", "4", ("-1", "abc", "1000"))

    def test_mojiotoshi_page_and_score(self):
        self.check_js_score_game("mojiotoshi", "もじおとし", "6", ("-1", "abc", "1000"))

    def test_saisen_page_and_score(self):
        # 10投制なので上限は10
        self.check_js_score_game("saisen", "賽銭チャレンジ", "7", ("-1", "abc", "11"))
        res = self.client.post("/games/saisen/score", data={"score": "10"})
        self.assertEqual(res.get_json()["best"], 10)

    # ---- いろわけフラスコ ----
    def test_flasksort_pour_rules(self):
        m = self.mod
        # 同色の上のかたまりがまとめて移る
        out = m.flasksort_pour([[0, 0], [1], [], []], 0, 2)
        self.assertEqual(out, [[], [1], [0, 0], []])
        # 異なる色の上には注げない
        self.assertIsNone(m.flasksort_pour([[0], [1], [], []], 0, 1))
        # 空きが1つしかなければ1つだけ移る
        out = m.flasksort_pour([[0, 0, 0], [0, 0, 0], [], []], 0, 1)
        self.assertEqual(out, [[0, 0], [0, 0, 0, 0], [], []])
        # 空のフラスコからは注げない
        self.assertIsNone(m.flasksort_pour([[], [1], [], []], 0, 2))
        # 完成判定
        self.assertTrue(m.flasksort_is_solved([[0, 0, 0, 0], [1, 1, 1, 1], []]))
        self.assertFalse(m.flasksort_is_solved([[0, 0, 0], [1, 1, 1, 1], [0]]))

    def test_flasksort_new_state_invariants(self):
        m = self.mod
        for _ in range(20):
            state = m.flasksort_new_state()
            counts = {0: 0, 1: 0, 2: 0}
            for flask in state:
                self.assertLessEqual(len(flask), 4)
                for color in flask:
                    counts[color] += 1
            self.assertEqual(counts, {0: 4, 1: 4, 2: 4})
            self.assertFalse(m.flasksort_is_solved(state))

    def test_flasksort_solve_flow_records_score(self):
        res = self.client.get("/games/flasksort")
        self.assertEqual(res.status_code, 200)
        self.assertIn("いろわけフラスコ", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            sess["fs_flasks"] = [[0, 0, 0, 0], [1, 1, 1, 1], [2, 2, 2], [2]]
            sess["fs_moves"] = 0
            sess["fs_sel"] = -1
            sess["fs_done"] = False
        self.client.post("/games/flasksort/tap", data={"index": "2"})
        res = self.client.post("/games/flasksort/tap", data={"index": "3"})
        self.assertIn("完成", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game = 'flasksort'")
        self.assertEqual(rows, [(1,)])

    # ---- 三すくみカード ----
    def test_triocard_judge(self):
        j = self.mod.triocard_judge
        self.assertEqual(j("炎", 1, "草", 9), "win")   # 属性で勝ち（数字は無関係）
        self.assertEqual(j("草", 9, "炎", 1), "lose")
        self.assertEqual(j("水", 2, "炎", 8), "win")
        self.assertEqual(j("炎", 7, "炎", 3), "win")   # 同属性は数字勝負
        self.assertEqual(j("炎", 3, "炎", 7), "lose")
        self.assertEqual(j("炎", 5, "炎", 5), "draw")

    def test_triocard_five_rounds_complete(self):
        res = self.client.get("/games/trio-card")
        self.assertEqual(res.status_code, 200)
        self.assertIn("三すくみカード", res.get_data(as_text=True))
        for _ in range(4):
            res = self.client.post("/games/trio-card/play", data={"card": "0"})
            self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/trio-card/play", data={"card": "0"})
        self.assertIn("対戦終了", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game = 'trio-card'")
        self.assertEqual(len(rows), 1)
        self.assertTrue(0 <= rows[0][0] <= 5)

    # ---- 平面⇔立体パズル ----
    def test_flat3d_step_rules(self):
        m = self.mod
        start = m.flat3d_find(m.FLAT3D_MAP, "S")
        bridge = m.flat3d_find(m.FLAT3D_MAP, "b")
        self.assertIsNotNone(bridge)
        self.assertFalse(m.flat3d_can_step(m.FLAT3D_MAP, 0, 0, "flat"))     # 壁
        self.assertTrue(m.flat3d_can_step(m.FLAT3D_MAP, start[0], start[1], "flat"))
        self.assertFalse(m.flat3d_can_step(m.FLAT3D_MAP, bridge[0], bridge[1], "flat"))
        self.assertTrue(m.flat3d_can_step(m.FLAT3D_MAP, bridge[0], bridge[1], "solid"))

    def test_flat3d_goal_needs_solid_mode(self):
        from collections import deque
        m = self.mod
        start = m.flat3d_find(m.FLAT3D_MAP, "S")
        goal = m.flat3d_find(m.FLAT3D_MAP, "G")

        def reachable(use_toggle):
            modes = ("flat", "solid") if use_toggle else ("flat",)
            seen = {(start, "flat")}
            q = deque([(start, "flat")])
            while q:
                (r, c), mode = q.popleft()
                if (r, c) == goal:
                    return True
                for nm in modes:
                    if ((r, c), nm) not in seen:
                        seen.add(((r, c), nm))
                        q.append(((r, c), nm))
                for dr, dc in m.FLAT3D_DIRS.values():
                    nr, nc = r + dr, c + dc
                    if m.flat3d_can_step(m.FLAT3D_MAP, nr, nc, mode) and ((nr, nc), mode) not in seen:
                        seen.add(((nr, nc), mode))
                        q.append(((nr, nc), mode))
            return False

        self.assertFalse(reachable(use_toggle=False))  # 平面だけでは届かない
        self.assertTrue(reachable(use_toggle=True))    # 切替を使えば届く

    def test_flat3d_page_and_toggle(self):
        res = self.client.get("/games/flat3d")
        self.assertEqual(res.status_code, 200)
        self.assertIn("平面⇔立体パズル", res.get_data(as_text=True))
        res = self.client.post("/games/flat3d/toggle")
        self.assertIn("立体", res.get_data(as_text=True))
        res = self.client.post("/games/flat3d/move", data={"dir": "right"})
        self.assertEqual(res.status_code, 200)

    # ---- ゴモク一手詰め ----
    def test_gomoku_winning_moves(self):
        m = self.mod
        board = ["." * 9 for _ in range(9)]
        row = list(board[4])
        for c in (2, 3, 4, 5):
            row[c] = "B"
        board[4] = "".join(row)
        wins = m.gomoku_winning_moves(board, "B")
        self.assertIn((4, 1), wins)
        self.assertIn((4, 6), wins)
        # 間に空きがある四つ並びは真ん中が勝ち手
        row = list(board[6])
        for c in (2, 3, 5, 6):
            row[c] = "B"
        board[6] = "".join(row)
        self.assertIn((6, 4), m.gomoku_winning_moves(board, "B"))
        self.assertFalse(m.gomoku_five(board, "B"))

    def test_gomoku_new_puzzle_is_unique(self):
        m = self.mod
        for _ in range(5):
            board, answer = m.gomoku_new_puzzle()
            wins = m.gomoku_winning_moves(board, "B")
            self.assertEqual(len(wins), 1)
            self.assertEqual(wins[0], answer)
            self.assertFalse(m.gomoku_five(board, "B"))
            self.assertFalse(m.gomoku_five(board, "W"))

    def test_gomoku_answer_flow(self):
        res = self.client.get("/games/gomoku-tsume")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ゴモク一手詰め", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            answer = sess["gm_answer"]
        res = self.client.post(
            "/games/gomoku-tsume/move", data={"cell": f"{answer[0]}-{answer[1]}"}
        )
        self.assertIn("正解", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game = 'gomoku-tsume'")
        self.assertEqual(rows, [(1,)])

    # ---- バッグ詰めパズルバトル ----
    def test_bagpack_place_and_rotate(self):
        m = self.mod
        grid = [[0] * 6 for _ in range(6)]
        vertical = [(0, 0), (0, 1), (0, 2)]
        rotated = m.bagpack_rotate(vertical)
        self.assertEqual(rotated, [(0, 0), (1, 0), (2, 0)])
        self.assertTrue(m.bagpack_can_place(grid, vertical, 0, 0))
        grid2 = m.bagpack_place(grid, vertical, 0, 0, 1)
        self.assertEqual(m.bagpack_count(grid2), 3)
        self.assertFalse(m.bagpack_can_place(grid2, vertical, 0, 0))  # 重なる
        wide = [(0, 0), (0, 1), (0, 2), (0, 3)]
        self.assertFalse(m.bagpack_can_place(grid, wide, 0, 3))        # はみ出す
        self.assertTrue(m.bagpack_can_place(grid, wide, 0, 2))

    def test_bagpack_cpu_fill(self):
        for _ in range(5):
            filled = self.mod.bagpack_cpu_fill(self.mod.BAGPACK_ITEMS)
            self.assertTrue(0 < filled <= 36)

    def test_bagpack_skip_all_finishes_round(self):
        res = self.client.get("/games/bagpack")
        self.assertEqual(res.status_code, 200)
        self.assertIn("バッグ詰めパズルバトル", res.get_data(as_text=True))
        for _ in range(len(self.mod.BAGPACK_ITEMS)):
            res = self.client.post("/games/bagpack/skip")
            self.assertEqual(res.status_code, 200)
        self.assertIn("vs CPU", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            self.assertTrue(sess["bp_over"])

    # ---- 3ワードモンスター ----
    def test_wordmonster_stats_deterministic(self):
        m = self.mod
        a = m.wordmonster_stats("ほのお", "ドラゴン", "まじめ")
        b = m.wordmonster_stats("ほのお", "ドラゴン", "まじめ")
        self.assertEqual(a, b)
        self.assertEqual(a["type"], "炎")
        self.assertTrue(40 <= a["hp"] <= 80)
        self.assertTrue(10 <= a["atk"] <= 30)
        self.assertTrue(5 <= a["spd"] <= 20)

    def test_wordmonster_battle_outcomes(self):
        m = self.mod
        strong = {"hp": 80, "atk": 30, "spd": 20, "type": "炎"}
        weak = {"hp": 40, "atk": 10, "spd": 5, "type": "草"}
        self.assertEqual(m.wordmonster_battle(strong, weak), "win")
        self.assertEqual(m.wordmonster_battle(weak, strong), "lose")

    def test_wordmonster_flow(self):
        res = self.client.get("/games/wordmonster")
        self.assertEqual(res.status_code, 200)
        self.assertIn("3ワードモンスター", res.get_data(as_text=True))
        res = self.client.post(
            "/games/wordmonster/battle",
            data={"属性": "ほのお", "体": "ドラゴン", "性格": "まじめ"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("CPU のモンスター", res.get_data(as_text=True))
        res = self.client.post(
            "/games/wordmonster/battle",
            data={"属性": "そら", "体": "ドラゴン", "性格": "まじめ"},
        )
        self.assertIn("言葉を3つ選んでください", res.get_data(as_text=True))

    # ---- 面接吹き出しジャッジ ----
    def test_mensetsu_grade(self):
        g = self.mod.mensetsu_grade
        self.assertEqual(g(60), "S")
        self.assertEqual(g(55), "S")
        self.assertEqual(g(54), "A")
        self.assertEqual(g(45), "A")
        self.assertEqual(g(44), "B")
        self.assertEqual(g(30), "B")
        self.assertEqual(g(29), "C")
        self.assertEqual(g(15), "C")
        self.assertEqual(g(14), "D")
        self.assertEqual(g(0), "D")

    def test_mensetsu_all_best_answers_give_s(self):
        res = self.client.get("/games/mensetsu")
        self.assertEqual(res.status_code, 200)
        self.assertIn("面接吹き出しジャッジ", res.get_data(as_text=True))
        for _ in range(len(self.mod.MENSETSU_QUESTIONS)):
            with self.client.session_transaction() as sess:
                choices = sess["ms_choices"]
            best_idx = choices.index(max(choices))
            res = self.client.post("/games/mensetsu/answer", data={"choice": str(best_idx)})
            self.assertEqual(res.status_code, 200)
        self.assertIn("評価は S", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game = 'mensetsu'")
        self.assertEqual(rows, [(5,)])

    # ---- 水質バランス処理 ----
    def test_suishitsu_apply_and_range(self):
        m = self.mod
        state = {"turbidity": 50, "ph": 105, "bacteria": 50, "cost": 0}
        out = m.suishitsu_apply(state, "filter")
        self.assertEqual(out["turbidity"], 20)
        self.assertEqual(out["bacteria"], 45)
        self.assertEqual(out["cost"], 8)
        out = m.suishitsu_apply(state, "chlorine")
        self.assertEqual(out["bacteria"], 10)
        self.assertEqual(out["ph"], 107)
        self.assertTrue(m.suishitsu_in_range({"turbidity": 20, "ph": 85, "bacteria": 10}))
        self.assertFalse(m.suishitsu_in_range({"turbidity": 21, "ph": 85, "bacteria": 10}))
        self.assertFalse(m.suishitsu_in_range({"turbidity": 0, "ph": 54, "bacteria": 0}))

    def test_suishitsu_round_score(self):
        m = self.mod
        center = {"turbidity": 10, "ph": 70, "bacteria": 5, "cost": 0}
        self.assertAlmostEqual(m.suishitsu_round_score(center), 35.0, places=5)
        costly = dict(center, cost=10)
        self.assertAlmostEqual(m.suishitsu_round_score(costly), 25.0, places=5)
        out = {"turbidity": 99, "ph": 70, "bacteria": 5, "cost": 0}
        self.assertEqual(m.suishitsu_round_score(out), 0.0)

    def test_suishitsu_ship_flow(self):
        res = self.client.get("/games/suishitsu")
        self.assertEqual(res.status_code, 200)
        self.assertIn("水質バランス処理", res.get_data(as_text=True))
        with self.client.session_transaction() as sess:
            sess["ss_water"] = {"turbidity": 50, "ph": 105, "bacteria": 50, "cost": 0}
            sess["ss_round"] = 1
            sess["ss_total10"] = 0
            sess["ss_over"] = False
            sess["ss_log"] = []
        self.client.post("/games/suishitsu/act", data={"action": "filter"})
        self.client.post("/games/suishitsu/act", data={"action": "acid"})
        self.client.post("/games/suishitsu/act", data={"action": "acid"})
        self.client.post("/games/suishitsu/act", data={"action": "chlorine"})
        res = self.client.post("/games/suishitsu/ship")
        self.assertEqual(res.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["ss_round"], 2)
            self.assertGreater(sess["ss_total10"], 0)



class SnsNov03GamesTest(MinigameTest):
    """2026-11-03 配信の保留案から実装した15本（SNS10＋ふりーむ5）のテスト。"""

    NEW_SLUGS = ("boomerang", "timing-tennis", "secret-name", "current-shot",
                 "tier-party", "shodo", "rousoku", "shield-moji", "ramen-oil",
                 "ikasama", "machigai-card", "poyon-rhythm", "bubble-shot",
                 "draw-poker", "ronpa")

    def test_portal_lists_fifteen_new_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in self.NEW_SLUGS:
            self.assertIn(f"/games/{slug}", body)
        self.assertEqual(len(self.mod.GAMES), 100)
        self.assertIn("100 本", body)

    def test_new_games_categories(self):
        cats = {g["slug"]: g["category"] for g in self.mod.GAMES}
        expected = {
            "boomerang": "アクション", "timing-tennis": "アクション",
            "secret-name": "クイズ・知識", "current-shot": "アクション",
            "tier-party": "創作", "shodo": "創作", "rousoku": "アクション",
            "shield-moji": "アクション", "ramen-oil": "アクション",
            "ikasama": "カード・数字", "machigai-card": "カード・数字",
            "poyon-rhythm": "アクション", "bubble-shot": "アクション",
            "draw-poker": "カード・数字", "ronpa": "脱出・謎解き",
        }
        for slug, cat in expected.items():
            self.assertEqual(cats[slug], cat, slug)
        allowed = {"アクション", "脳トレ", "抽選・占い", "クイズ・知識",
                   "対戦", "脱出・謎解き", "カード・数字", "創作"}
        self.assertTrue(set(cats.values()) <= allowed)

    def check_js_score_game(self, slug, title, good, bad_values):
        res = self.client.get(f"/games/{slug}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(title, res.get_data(as_text=True))
        res = self.client.post(f"/games/{slug}/score", data={"score": good})
        self.assertEqual(res.get_json(), {"ok": True, "best": int(good)})
        for bad in bad_values:
            res = self.client.post(f"/games/{slug}/score", data={"score": bad})
            self.assertEqual(res.status_code, 400, (slug, bad))

    # ---- JS進行ゲーム（ページ＋スコア保存） ----
    def test_boomerang_page_and_score(self):
        self.check_js_score_game("boomerang", "ブーメラン軌道アタック", "12", ("-1", "abc", "1000"))

    def test_timing_tennis_page_and_score(self):
        self.check_js_score_game("timing-tennis", "タイミング返球テニス", "25", ("-1", "abc", "1000"))

    def test_current_shot_page_and_score(self):
        self.check_js_score_game("current-shot", "海流ながれ弾シューティング", "18", ("-1", "abc", "1000"))

    def test_shodo_page_and_score(self):
        # 採点は 0〜100
        self.check_js_score_game("shodo", "おてほん書道採点", "80", ("-1", "abc", "101"))

    def test_rousoku_page_and_score(self):
        self.check_js_score_game("rousoku", "一息ろうそく消し", "9", ("-1", "abc", "100"))

    def test_shield_moji_page_and_score(self):
        self.check_js_score_game("shield-moji", "胸ポケットの盾文字", "21", ("-1", "abc", "1000"))

    def test_ramen_oil_page_and_score(self):
        self.check_js_score_game("ramen-oil", "ラーメン油あつめ", "20", ("-1", "abc", "100"))

    def test_poyon_rhythm_page_and_score(self):
        self.check_js_score_game("poyon-rhythm", "2ボタンぽよんリズム", "1500", ("-1", "abc", "10000"))

    def test_bubble_shot_page_and_score(self):
        self.check_js_score_game("bubble-shot", "カラフルバブルシュート", "350", ("-1", "abc", "10000"))

    # ---- ひみつネーム即死当て ----
    def test_secretname_feedback(self):
        fb = self.mod.secretname_feedback
        self.assertEqual(fb("ライオン", "ライオン"), ["exact"] * 4)
        self.assertEqual(fb("ライオン", "シマウマ"),
                         ["absent", "absent", "absent", "absent"])
        self.assertEqual(fb("アルパカ", "アカパル"),
                         ["exact", "present", "exact", "present"])
        # 同じ文字が複数ある場合は、まず位置一致を優先して数える
        self.assertEqual(fb("シマウマ", "ママママ"),
                         ["absent", "exact", "absent", "exact"])

    def test_secretname_win_score(self):
        self.assertEqual(self.mod.secretname_win_score(1), 120)
        self.assertEqual(self.mod.secretname_win_score(3), 80)
        self.assertEqual(self.mod.secretname_win_score(6), 20)

    def _fix_secretname(self, secret="ライオン", trap="ペンギン"):
        self.client.get("/games/secret-name")
        with self.client.session_transaction() as sess:
            sess["sn_secret"] = secret
            sess["sn_trap"] = trap
            sess["sn_tries"] = []
            sess["sn_over"] = False
            sess["sn_win"] = False
            sess["sn_dead"] = False

    def test_secretname_flow_win(self):
        self._fix_secretname()
        res = self.client.post("/games/secret-name/guess", data={"guess": "ライオン"})
        self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'secret-name'")
        self.assertEqual(rows, [(120,)])

    def test_secretname_trap_instant_death(self):
        self._fix_secretname()
        res = self.client.post("/games/secret-name/guess", data={"guess": "ペンギン"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("即死", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game = 'secret-name'")
        self.assertEqual(rows, [(0,)])

    def test_secretname_bad_input_not_recorded(self):
        self._fix_secretname()
        res = self.client.post("/games/secret-name/guess", data={"guess": "abc"})
        self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'secret-name'")
        self.assertEqual(rows, [])

    # ---- ティアならべパーティ ----
    def test_tierparty_score(self):
        s = self.mod.tierparty_score
        theme = self.mod.TIERPARTY_THEMES[0]
        # 全一致＋全ティア使用ボーナス
        self.assertEqual(s(theme["consensus"], theme["consensus"]), 85)
        # 全て A(1)：consensus [0,0,1,2,1,1,3,2] との差で 46 点
        self.assertEqual(s([1] * 8, theme["consensus"]), 46)
        # 全て C(3)
        self.assertEqual(s([3] * 8, theme["consensus"]), 18)

    def test_tierparty_submit_flow(self):
        res = self.client.get("/games/tier-party")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ティアならべパーティ", res.get_data(as_text=True))
        data = {f"item{i}": "1" for i in range(8)}
        res = self.client.post("/games/tier-party/submit", data=data)
        self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'tier-party'")
        self.assertEqual(len(rows), 1)
        self.assertTrue(0 <= rows[0][0] <= 85)

    # ---- イカサマ割合ハイボール ----
    def test_ikasama_judge_and_profit(self):
        m = self.mod
        self.assertEqual(m.ikasama_profit(30), 50)
        self.assertEqual(m.ikasama_profit(70), 10)
        self.assertEqual(m.ikasama_judge(29, 30), (True, "busted"))
        self.assertEqual(m.ikasama_judge(30, 30), (False, "close"))
        self.assertEqual(m.ikasama_judge(40, 30), (False, "ok"))
        self.assertEqual(m.ikasama_judge(50, 30), (False, "rich"))

    def test_ikasama_serve_flow_ten_customers(self):
        self.client.get("/games/ikasama")
        # 割合70%ならどの客の許容ライン（最大55%）も下回らない
        for _ in range(10):
            res = self.client.post("/games/ikasama/serve", data={"ratio": "70"})
            self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'ikasama'")
        self.assertEqual(rows, [(100,)])

    def test_ikasama_invalid_ratio(self):
        self.client.get("/games/ikasama")
        res = self.client.post("/games/ikasama/serve", data={"ratio": "abc"})
        self.assertEqual(res.status_code, 200)
        res = self.client.post("/games/ikasama/serve", data={"ratio": "1"})
        self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'ikasama'")
        self.assertEqual(rows, [])

    # ---- まちがいカード見抜き ----
    def test_machigai_claim_rules(self):
        import random as _random
        rng = _random.Random(42)
        cs, cr = self.mod.machigai_make_claim("ハート", 7, False, rng)
        self.assertEqual((cs, cr), ("ハート", 7))
        for _ in range(30):
            cs, cr = self.mod.machigai_make_claim("ハート", 7, True, rng)
            self.assertTrue(
                self.mod.machigai_is_wrong(("ハート", 7), (cs, cr)))

    def test_machigai_flow_ten_rounds_all_correct(self):
        self.client.get("/games/machigai-card")
        for _ in range(10):
            with self.client.session_transaction() as sess:
                card = sess["mg_card"]
                claim = sess["mg_claim"]
            wrong = self.mod.machigai_is_wrong(card, claim)
            res = self.client.post(
                "/games/machigai-card/answer",
                data={"answer": "wrong" if wrong else "right"})
            self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'machigai-card'")
        self.assertEqual(rows, [(10,)])

    # ---- 1回交換ドローポーカー ----
    def test_drawpoker_evaluate(self):
        e = self.mod.drawpoker_evaluate
        # ストレートフラッシュ（Aハイ）
        self.assertEqual(e([(0, 10), (0, 11), (0, 12), (0, 13), (0, 1)]), (8, (14,)))
        # ストレートフラッシュ（ホイール A-2-3-4-5）
        self.assertEqual(e([(0, 1), (0, 2), (0, 3), (0, 4), (0, 5)]), (8, (5,)))
        # フォーカード
        self.assertEqual(e([(0, 9), (1, 9), (2, 9), (3, 9), (0, 13)]), (7, (9, 13)))
        # フルハウス
        self.assertEqual(e([(0, 5), (1, 5), (2, 5), (0, 9), (1, 9)]), (6, (5, 9)))
        # フラッシュ
        self.assertEqual(e([(2, 2), (2, 5), (2, 7), (2, 9), (2, 11)]),
                         (5, (11, 9, 7, 5, 2)))
        # ストレート
        self.assertEqual(e([(0, 5), (1, 6), (2, 7), (3, 8), (0, 9)]), (4, (9,)))
        # スリーカード
        self.assertEqual(e([(0, 7), (1, 7), (2, 7), (0, 13), (1, 2)]), (3, (7, 13, 2)))
        # ツーペア（A がキッカー）
        self.assertEqual(e([(0, 4), (1, 4), (2, 11), (3, 11), (0, 1)]), (2, (11, 4, 14)))
        # ワンペア
        self.assertEqual(e([(0, 10), (1, 10), (2, 3), (3, 5), (0, 1)]),
                         (1, (10, 14, 5, 3)))
        # ハイカード
        self.assertEqual(e([(0, 2), (1, 5), (2, 7), (3, 9), (0, 12)]),
                         (0, (12, 9, 7, 5, 2)))
        # 比較：Aハイのストレートフラッシュ > ホイール
        self.assertEqual(self.mod.drawpoker_compare((8, (14,)), (8, (5,))), 1)
        self.assertEqual(self.mod.drawpoker_compare((1, (10, 14, 5, 3)),
                                                    (1, (10, 14, 5, 3))), 0)

    def test_drawpoker_cpu_discards_keeps_pair(self):
        d = self.mod.drawpoker_cpu_discards(
            [(0, 8), (1, 8), (2, 3), (3, 5), (0, 12)])
        self.assertNotIn(0, d)
        self.assertNotIn(1, d)
        self.assertLessEqual(len(d), 3)
        # 無役なら高い2枚を残して3枚交換
        d2 = self.mod.drawpoker_cpu_discards(
            [(0, 2), (1, 5), (2, 7), (3, 9), (0, 11)])
        self.assertEqual(len(d2), 3)
        self.assertNotIn(4, d2)  # J は残す
        self.assertNotIn(3, d2)  # 9 は残す

    def test_drawpoker_flow_five_rounds(self):
        res = self.client.get("/games/draw-poker")
        self.assertEqual(res.status_code, 200)
        self.assertIn("1回交換ドローポーカー", res.get_data(as_text=True))
        for _ in range(5):
            res = self.client.post("/games/draw-poker/exchange", data={})
            self.assertEqual(res.status_code, 200)
            res = self.client.post("/games/draw-poker/next")
            self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'draw-poker'")
        self.assertEqual(len(rows), 1)
        self.assertTrue(0 <= rows[0][0] <= 15)

    # ---- 手がかり論破レスバ ----
    def test_ronpa_data_integrity(self):
        self.assertEqual(len(self.mod.RONPA_SCENARIOS), 3)
        for sc in self.mod.RONPA_SCENARIOS:
            correct = [e for e in sc["evidences"] if e["correct"]]
            self.assertEqual(len(correct), 1, sc["title"])
            self.assertEqual(len(sc["evidences"]), 3, sc["title"])
            self.assertGreaterEqual(len(sc["posts"]), 4, sc["title"])

    def test_ronpa_flow_all_first_try(self):
        res = self.client.get("/games/ronpa")
        self.assertEqual(res.status_code, 200)
        self.assertIn("手がかり論破レスバ", res.get_data(as_text=True))
        for sc in self.mod.RONPA_SCENARIOS:
            correct_idx = next(
                i for i, e in enumerate(sc["evidences"]) if e["correct"])
            res = self.client.post("/games/ronpa/present",
                                   data={"ev": str(correct_idx)})
            self.assertEqual(res.status_code, 200)
            res = self.client.post("/games/ronpa/next")
            self.assertEqual(res.status_code, 200)
        rows = self.query("SELECT score FROM scores WHERE game = 'ronpa'")
        self.assertEqual(rows, [(90,)])

    def test_ronpa_wrong_then_correct_scores_less(self):
        self.client.get("/games/ronpa")
        sc = self.mod.RONPA_SCENARIOS[0]
        wrong_idx = next(
            i for i, e in enumerate(sc["evidences"]) if not e["correct"])
        correct_idx = next(
            i for i, e in enumerate(sc["evidences"]) if e["correct"])
        self.client.post("/games/ronpa/present", data={"ev": str(wrong_idx)})
        self.assertEqual(
            self.query("SELECT score FROM scores WHERE game = 'ronpa'"), [])
        self.client.post("/games/ronpa/present", data={"ev": str(correct_idx)})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["rp_points"], 20)
            self.assertTrue(sess["rp_solved"])


class SnsNov04GamesTest(MinigameTest):
    """2026-11-04 配信の保留案から実装した15本（SNS10＋ふりーむ5）のテスト。"""

    NEW_SLUGS = ("curling-tsume", "prism-mirror", "eyeball-sokoban",
                 "ushi-tomato", "oyatsu-kaba", "swipe-ushi", "kyushin-judge",
                 "kagiban", "block-survive", "meiga-naoshi", "fukuwarai",
                 "majyo-suiri", "hikigiwa-dungeon", "draft-meate",
                 "color-hamekomi")

    def test_portal_lists_fifteen_new_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in self.NEW_SLUGS:
            self.assertIn(f"/games/{slug}", body)
        self.assertEqual(len(self.mod.GAMES), 100)
        self.assertIn("100 本", body)

    def test_new_games_categories(self):
        cats = {g["slug"]: g["category"] for g in self.mod.GAMES}
        expected = {
            "curling-tsume": "脳トレ", "prism-mirror": "脳トレ",
            "eyeball-sokoban": "脳トレ", "ushi-tomato": "アクション",
            "oyatsu-kaba": "アクション", "swipe-ushi": "アクション",
            "kyushin-judge": "クイズ・知識", "kagiban": "脳トレ",
            "block-survive": "アクション", "meiga-naoshi": "創作",
            "fukuwarai": "クイズ・知識", "majyo-suiri": "脱出・謎解き",
            "hikigiwa-dungeon": "カード・数字", "draft-meate": "クイズ・知識",
            "color-hamekomi": "脳トレ",
        }
        for slug, cat in expected.items():
            self.assertEqual(cats[slug], cat, slug)
        allowed = {"アクション", "脳トレ", "抽選・占い", "クイズ・知識",
                   "対戦", "脱出・謎解き", "カード・数字", "創作"}
        self.assertTrue(set(cats.values()) <= allowed)

    def check_js_score_game(self, slug, title, good, bad_values):
        res = self.client.get(f"/games/{slug}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(title, res.get_data(as_text=True))
        res = self.client.post(f"/games/{slug}/score", data={"score": good})
        self.assertEqual(res.get_json(), {"ok": True, "best": int(good)})
        for bad in bad_values:
            res = self.client.post(f"/games/{slug}/score", data={"score": bad})
            self.assertEqual(res.status_code, 400, (slug, bad))

    # ---- JS進行ゲーム（ページ＋スコア保存） ----
    def test_ushi_tomato_page_and_score(self):
        self.check_js_score_game("ushi-tomato", "ウシおどかしトマト", "120",
                                 ("-1", "abc", "1000"))

    def test_oyatsu_kaba_page_and_score(self):
        self.check_js_score_game("oyatsu-kaba", "おやつカバ60秒", "350",
                                 ("-1", "abc", "10000"))

    def test_swipe_ushi_page_and_score(self):
        self.check_js_score_game("swipe-ushi", "スワイプ加速ウシ", "54321",
                                 ("-1", "abc", "1000000"))

    def test_block_survive_page_and_score(self):
        self.check_js_score_game("block-survive", "ブロック側サバイバル", "1234",
                                 ("-1", "abc", "100000"))

    def test_meiga_naoshi_page_and_score(self):
        # 採点は 0〜100
        self.check_js_score_game("meiga-naoshi", "名画おなおしミニ", "85",
                                 ("-1", "abc", "101"))

    def test_fukuwarai_page_and_score(self):
        # 採点は 0〜100
        self.check_js_score_game("fukuwarai", "証言ふくわらい捜査", "72",
                                 ("-1", "abc", "101"))

    # ---- カーリング一投詰め ----
    def test_curling_points_cases(self):
        cp = self.mod.curling_points
        self.assertEqual(cp([(0.0, 2.0, True), (6.0, 2.0, False)]), 40)
        self.assertEqual(cp([(0.0, 10.0, True), (30.0, 0.0, False)]), 20)
        self.assertEqual(cp([(0.0, 5.0, True), (0.0, 3.0, False)]), 0)

    def test_curling_simulate_known_throws(self):
        m = self.mod
        self.assertEqual(
            m.curling_points(m.curling_simulate([[6, 2]], 0, 80, 0)), 40)
        self.assertEqual(
            m.curling_points(m.curling_simulate([[0, 0], [10, 8]], -16, 84, 10)), 30)

    def test_curling_flow_records_total(self):
        self.client.get("/games/curling-tsume")
        throws = [("0", "80", "0"), ("-19", "82", "10"), ("-16", "84", "10")]
        for ang, pw, cu in throws:
            self.client.post("/games/curling-tsume/throw",
                             data={"angle": ang, "power": pw, "curl": cu})
            self.client.post("/games/curling-tsume/next")
        rows = self.query("SELECT score FROM scores WHERE game = 'curling-tsume'")
        self.assertEqual(rows, [(100,)])

    # ---- プリズム鏡あわせ ----
    def test_prism_solutions_light_all_crystals(self):
        m = self.mod
        for stage in m.PRISM_STAGES:
            mirrors = {tuple(x[:2]): x[2] for x in stage["mirrors"]}
            lit, _path = m.prism_trace(mirrors, stage["emitter"], stage["crystals"])
            self.assertEqual(lit, {tuple(c) for c in stage["crystals"]})
            # 初期配置（スクランブル）では1つも光らない
            init = {tuple(x[:2]): stage["init"][i]
                    for i, x in enumerate(stage["mirrors"])}
            lit0, _ = m.prism_trace(init, stage["emitter"], stage["crystals"])
            self.assertEqual(lit0, set())

    def test_prism_flow_records_total(self):
        self.client.get("/games/prism-mirror")
        for toggles in ([0, 1], [0, 1, 2], [0, 1, 2, 3]):
            for idx in toggles:
                self.client.post("/games/prism-mirror/toggle",
                                 data={"cell": str(idx)})
            self.client.post("/games/prism-mirror/next")
        rows = self.query("SELECT score FROM scores WHERE game = 'prism-mirror'")
        self.assertEqual(rows, [(136,)])

    # ---- 目玉みはり倉庫番 ----
    def test_sokoban_solutions_solve_all_stages(self):
        m = self.mod
        sols = ["RR", "UULDULD", "RRRLLDDRR"]
        for stage, sol in zip(m.EYEBALL_STAGES, sols):
            walls, goals, boxes, player, eyeballs = m.eyeball_parse(stage)
            gaze = m.eyeball_gaze_cells(walls, eyeballs,
                                         len(stage["lines"]),
                                         len(stage["lines"][0]))
            prev = None
            cur_boxes = frozenset(boxes)
            for ch in sol:
                old = player
                player, cur_boxes, moved = m.eyeball_try_move(
                    player, cur_boxes, prev, ch, walls, eyeballs, gaze)
                self.assertTrue(moved, (stage, sol, ch))
                prev = old
            self.assertTrue(goals <= set(cur_boxes))

    def test_sokoban_flow_records_total(self):
        self.client.get("/games/eyeball-sokoban")
        for sol in ("RR", "UULDULD", "RRRLLDDRR"):
            for ch in sol:
                self.client.post("/games/eyeball-sokoban/move", data={"dir": ch})
            self.client.post("/games/eyeball-sokoban/next")
        rows = self.query("SELECT score FROM scores WHERE game = 'eyeball-sokoban'")
        self.assertEqual(rows, [(162,)])

    # ---- 球審ジャッジ ----
    def test_kyushin_is_strike_cases(self):
        f = self.mod.kyushin_is_strike
        self.assertTrue(f(0, 0))
        self.assertTrue(f(15, 18))
        self.assertTrue(f(-15, -18))
        self.assertFalse(f(16, 0))
        self.assertFalse(f(0, 19))
        self.assertFalse(f(-20, -25))

    def test_kyushin_flow_records_correct_on_three_misses(self):
        self.client.get("/games/kyushin-judge")
        with self.client.session_transaction() as sess:
            sess["kj_x"] = 0
            sess["kj_y"] = 0
        self.client.post("/games/kyushin-judge/answer", data={"judge": "strike"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["kj_correct"], 1)
            sess["kj_x"] = 0
            sess["kj_y"] = 0
            sess["kj_miss"] = 2
        self.client.post("/games/kyushin-judge/answer", data={"judge": "ball"})
        rows = self.query("SELECT score FROM scores WHERE game = 'kyushin-judge'")
        self.assertEqual(rows, [(1,)])

    # ---- カギバンさばき ----
    def test_kagiban_should_approve_rules(self):
        f = self.mod.kagiban_should_approve
        clean = {"icon": True, "posts": 10, "bio": "よろしく",
                 "link": False, "days": 100}
        self.assertTrue(f(clean, 5))
        self.assertTrue(f({**clean, "icon": False}, 0))
        self.assertFalse(f({**clean, "icon": False}, 1))
        self.assertTrue(f({**clean, "posts": 0}, 1))
        self.assertFalse(f({**clean, "posts": 0}, 2))
        self.assertFalse(f({**clean, "bio": ""}, 3))
        self.assertFalse(f({**clean, "link": True}, 4))
        self.assertTrue(f({**clean, "days": 2}, 4))
        self.assertFalse(f({**clean, "days": 2}, 5))

    def test_kagiban_flow_records_done(self):
        clean = {"name": "テスト", "icon": True, "posts": 10, "bio": "よろしく",
                 "link": False, "days": 100}
        self.client.get("/games/kagiban")
        with self.client.session_transaction() as sess:
            sess["kb_profile"] = clean
        self.client.post("/games/kagiban/answer", data={"act": "approve"})
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["kb_done"], 1)
            sess["kb_profile"] = {**clean, "icon": False}
            sess["kb_miss"] = 2
        self.client.post("/games/kagiban/answer", data={"act": "approve"})
        rows = self.query("SELECT score FROM scores WHERE game = 'kagiban'")
        self.assertEqual(rows, [(1,)])

    # ---- 憑依まじょ推理 ----
    def test_majyo_scenarios_integrity(self):
        for sc in self.mod.MAJYO_SCENARIOS:
            self.assertEqual(len(sc["villagers"]), 4)
            self.assertEqual(
                sum(1 for v in sc["villagers"] if v["possessed"]), 1)
            self.assertGreaterEqual(len(sc["facts"]), 2)

    def test_majyo_flow_all_first_try(self):
        self.client.get("/games/majyo-suiri")
        for sc in self.mod.MAJYO_SCENARIOS:
            target = next(i for i, v in enumerate(sc["villagers"])
                          if v["possessed"])
            self.client.post("/games/majyo-suiri/accuse",
                             data={"v": str(target)})
            self.client.post("/games/majyo-suiri/next")
        rows = self.query("SELECT score FROM scores WHERE game = 'majyo-suiri'")
        self.assertEqual(rows, [(90,)])

    # ---- 引き際ダンジョンすごろく ----
    def test_hikigiwa_battle_result_cases(self):
        f = self.mod.hikigiwa_battle_result
        self.assertEqual(f(9, 5), (True, 15))
        self.assertEqual(f(5, 5), (True, 15))
        self.assertEqual(f(3, 7), (False, 5))

    def test_hikigiwa_retreat_records_gold(self):
        self.client.get("/games/hikigiwa-dungeon")
        with self.client.session_transaction() as sess:
            sess["hd_gold"] = 25
        self.client.post("/games/hikigiwa-dungeon/retreat")
        rows = self.query(
            "SELECT score FROM scores WHERE game = 'hikigiwa-dungeon'")
        self.assertEqual(rows, [(25,)])

    def test_hikigiwa_roll_loop_records_once(self):
        self.client.get("/games/hikigiwa-dungeon")
        for _ in range(40):
            with self.client.session_transaction() as sess:
                over = sess.get("hd_over", False)
                battle = sess.get("hd_battle")
            if over:
                break
            if battle:
                self.client.post("/games/hikigiwa-dungeon/fight",
                                 data={"card": "0"})
            else:
                self.client.post("/games/hikigiwa-dungeon/roll")
        rows = self.query(
            "SELECT score FROM scores WHERE game = 'hikigiwa-dungeon'")
        self.assertEqual(len(rows), 1)

    # ---- ドラフト目利き ----
    def test_draft_candidates_invariants(self):
        import random as _random_module
        rng = _random_module.Random(7)
        cands = self.mod.draft_make_candidates(rng)
        self.assertEqual(len(cands), 3)
        noises = [n for _s, n in self.mod.DRAFT_SCOUTS]
        for cand in cands:
            self.assertTrue(25 <= cand["actual"] <= 98)
            for rep, noise in zip(cand["reports"], noises):
                self.assertLessEqual(abs(rep - cand["actual"]), noise)
            self.assertLessEqual(abs(cand["sub"] - cand["actual"]), 15)

    def test_draft_flow_records_total(self):
        fixed = [
            {"name": "候補A", "pos": "投手", "actual": 80,
             "reports": [80, 80, 80], "sub": 80},
            {"name": "候補B", "pos": "捕手", "actual": 50,
             "reports": [50, 50, 50], "sub": 50},
            {"name": "候補C", "pos": "外野手", "actual": 30,
             "reports": [30, 30, 30], "sub": 30},
        ]
        self.client.get("/games/draft-meate")
        for _ in range(5):
            with self.client.session_transaction() as sess:
                sess["dm_candidates"] = fixed
            self.client.post("/games/draft-meate/pick", data={"c": "0"})
        rows = self.query("SELECT score FROM scores WHERE game = 'draft-meate'")
        self.assertEqual(rows, [(400,)])

    # ---- 回してはめこみカラー探し ----
    def test_hamekomi_rotate_roundtrip(self):
        cells = [[0, 0, 1], [0, 1, 1], [1, 0, 2]]
        rotated = self.mod.hamekomi_rotate(cells, 4)
        self.assertEqual(sorted(map(tuple, rotated)),
                         sorted(map(tuple, cells)))
        once = self.mod.hamekomi_rotate(cells, 1)
        self.assertEqual(sorted(once), [(0, 0, 2), (0, 1, 1), (1, 1, 1)])

    def test_hamekomi_targets_cover_pieces(self):
        m = self.mod
        for stage in m.HAMEKOMI_STAGES:
            targets = m.hamekomi_targets(stage)
            total = sum(len(p["cells"]) for p in stage["pieces"])
            # 目標マスに重なりがないこと
            self.assertEqual(len(targets), total)
            occupied = {}
            for piece in stage["pieces"]:
                cells = m.hamekomi_rotate(piece["cells"], 0)
                ar, ac = piece["anchor"]
                self.assertTrue(
                    m.hamekomi_can_place(targets, occupied, cells, ar, ac))
                for (r, c, col) in cells:
                    occupied[(ar + r, ac + c)] = col
            self.assertEqual(set(occupied), set(targets))

    def test_hamekomi_flow_records_total(self):
        self.client.get("/games/color-hamekomi")
        for stage in self.mod.HAMEKOMI_STAGES:
            for piece in stage["pieces"]:
                for _ in range((4 - piece["init_rot"]) % 4):
                    self.client.post("/games/color-hamekomi/rotate")
                ar, ac = piece["anchor"]
                self.client.post("/games/color-hamekomi/put",
                                 data={"cell": f"{ar}-{ac}"})
            self.client.post("/games/color-hamekomi/next")
        rows = self.query(
            "SELECT score FROM scores WHERE game = 'color-hamekomi'")
        self.assertEqual(rows, [(128,)])

    # ---- 証言ふくわらい捜査（事件データの整合性） ----
    def test_fukuwarai_case_consistency(self):
        case = self.mod.FUKUWARAI_CASE
        self.assertEqual(len(case["parts"]), 5)
        targets = {p["key"]: p["target"] for p in case["parts"]}
        for p in case["parts"]:
            r, c = p["target"]
            self.assertTrue(0 <= r < 10 and 0 <= c < 8)
        # 正解の配置は全ての証言を満たすこと
        for s in case["statements"]:
            t = targets[s["part"]]
            v = t[0] if s["axis"] == "r" else t[1]
            self.assertTrue(s["min"] <= v <= s["max"], s["text"])

class SnsNov05GamesTest(MinigameTest):
    """2026-11-05 配信分（SNS10件＋ふりーむ5件）の追加ゲーム。"""

    NEW_SLUGS = ("paper-shoot", "antique-eye", "ivy-climb", "flower-match",
                 "spell-duel", "emoji-quiz", "pref-drop", "wiki-derby",
                 "ice-escape", "majority-gate", "micro-trio", "era-gacha",
                 "idle-craft", "kaiju-td", "last-minute")

    def test_portal_lists_fifteen_new_games(self):
        body = self.client.get("/").get_data(as_text=True)
        for slug in self.NEW_SLUGS:
            self.assertIn(f"/games/{slug}", body)
        self.assertEqual(len(self.mod.GAMES), 100)
        self.assertIn("100 本", body)

    def test_new_games_categories(self):
        cats = {g["slug"]: g["category"] for g in self.mod.GAMES}
        expected = {
            "paper-shoot": "アクション", "antique-eye": "クイズ・知識",
            "ivy-climb": "アクション", "flower-match": "脳トレ",
            "spell-duel": "対戦", "emoji-quiz": "クイズ・知識",
            "pref-drop": "脳トレ", "wiki-derby": "抽選・占い",
            "ice-escape": "アクション", "majority-gate": "脳トレ",
            "micro-trio": "アクション", "era-gacha": "抽選・占い",
            "idle-craft": "創作", "kaiju-td": "アクション",
            "last-minute": "脳トレ",
        }
        for slug, cat in expected.items():
            self.assertEqual(cats[slug], cat, slug)
        allowed = {"アクション", "脳トレ", "抽選・占い", "クイズ・知識",
                   "対戦", "脱出・謎解き", "カード・数字", "創作"}
        self.assertTrue(set(cats.values()) <= allowed)

    def check_js_score_game(self, slug, title, good, bad_values):
        res = self.client.get(f"/games/{slug}")
        self.assertEqual(res.status_code, 200)
        self.assertIn(title, res.get_data(as_text=True))
        res = self.client.post(f"/games/{slug}/score", data={"score": good})
        self.assertEqual(res.get_json(), {"ok": True, "best": int(good)})
        for bad in bad_values:
            res = self.client.post(f"/games/{slug}/score", data={"score": bad})
            self.assertEqual(res.status_code, 400, (slug, bad))

    # ---- JS進行ゲーム（ページ＋スコア保存） ----
    def test_paper_shoot_page_and_score(self):
        self.check_js_score_game("paper-shoot", "紙くずゴミ箱シュート", "80",
                                 ("-1", "abc", "101"))

    def test_ivy_climb_page_and_score(self):
        self.check_js_score_game("ivy-climb", "ツタのぼりワンタッチ", "25",
                                 ("-1", "abc", "1001"))

    def test_flower_match_page_and_score(self):
        self.check_js_score_game("flower-match", "花あわせ青いバラ", "640",
                                 ("-1", "abc", "10000"))

    def test_pref_drop_page_and_score(self):
        self.check_js_score_game("pref-drop", "都道府県くっつけ落ちもの", "300",
                                 ("-1", "abc", "10000"))

    def test_ice_escape_page_and_score(self):
        self.check_js_score_game("ice-escape", "トルコアイス逃がし", "240",
                                 ("-1", "abc", "36001"))

    def test_micro_trio_page_and_score(self):
        self.check_js_score_game("micro-trio", "3番勝負エンディング", "100",
                                 ("-1", "abc", "121"))

    def test_idle_craft_page_and_score(self):
        self.check_js_score_game("idle-craft", "60秒放置クラフト＆転生", "1234",
                                 ("-1", "abc", "100000"))

    def test_kaiju_td_page_and_score(self):
        self.check_js_score_game("kaiju-td", "ちび怪獣タワーディフェンス", "450",
                                 ("-1", "abc", "10000"))

    # ---- 深夜の骨董目利き ----
    def test_antique_data_integrity(self):
        self.assertEqual(len(self.mod.ANTIQUE_ROUNDS), 6)
        for rnd in self.mod.ANTIQUE_ROUNDS:
            self.assertEqual(len(rnd["items"]), 5)
            self.assertEqual(sum(1 for it in rnd["items"] if it["real"]), 1)

    def test_antique_flow_all_correct(self):
        self.client.get("/games/antique-eye")
        for _ in range(6):
            with self.client.session_transaction() as sess:
                pos = sess["ae_real_pos"]
            self.client.post("/games/antique-eye/answer", data={"pos": str(pos)})
        rows = self.query("SELECT score FROM scores WHERE game = 'antique-eye'")
        self.assertEqual(rows, [(60,)])

    def test_antique_timeout_counts_wrong(self):
        self.client.get("/games/antique-eye")
        with self.client.session_transaction() as sess:
            pos = sess["ae_real_pos"]
            sess["ae_qstart"] = sess["ae_qstart"] - 100
        res = self.client.post("/games/antique-eye/answer", data={"pos": str(pos)})
        self.assertIn("時間切れ", res.get_data(as_text=True))

    # ---- 呪文くみたて読み合い ----
    def test_spell_multiplier_cases(self):
        m = self.mod
        fire = [{"label": "炎の", "element": "火", "power": 12}]
        wind = [{"label": "疾風の", "element": "風", "power": 13}]
        water = [{"label": "氷の", "element": "水", "power": 11}]
        plain = [{"label": "弾", "element": None, "power": 10}]
        self.assertEqual(m.spell_multiplier(fire, wind), 1.5)
        self.assertEqual(m.spell_multiplier(wind, fire), 0.75)
        self.assertEqual(m.spell_multiplier(fire, water), 0.75)
        self.assertEqual(m.spell_multiplier(water, fire), 1.5)
        self.assertEqual(m.spell_multiplier(fire, fire), 1.0)
        self.assertEqual(m.spell_multiplier(plain, fire), 1.0)
        self.assertEqual(m.spell_total(fire + plain), 22)

    def test_spell_flow_five_rounds(self):
        self.client.get("/games/spell-duel")
        for _ in range(5):
            for _ in range(3):
                self.client.post("/games/spell-duel/pick", data={"idx": "0"})
        rows = self.query("SELECT score FROM scores WHERE game = 'spell-duel'")
        self.assertEqual(len(rows), 1)
        self.assertTrue(0 <= rows[0][0] <= 100)

    # ---- 絵文字列あてクイズ ----
    def test_emoji_quiz_data_integrity(self):
        self.assertEqual(len(self.mod.EMOJI_QUIZ), 8)
        for q in self.mod.EMOJI_QUIZ:
            self.assertEqual(len(q["choices"]), 3)
            self.assertIn(q["answer"], q["choices"])

    def test_emoji_quiz_flow_all_correct(self):
        self.client.get("/games/emoji-quiz")
        for q in self.mod.EMOJI_QUIZ:
            self.client.post("/games/emoji-quiz/answer",
                             data={"choice": q["answer"]})
        rows = self.query("SELECT score FROM scores WHERE game = 'emoji-quiz'")
        self.assertEqual(rows, [(80,)])

    # ---- 情報量ダービー予想 ----
    def test_derby_points_cases(self):
        dp = self.mod.derby_points
        self.assertEqual([dp(r) for r in (1, 2, 3, 4, 5)], [50, 30, 20, 10, 0])

    def test_derby_flow_best_bets(self):
        chars = {a["title"]: a["chars"] for a in self.mod.WIKI_ARTICLES}
        self.client.get("/games/wiki-derby")
        for _ in range(5):
            with self.client.session_transaction() as sess:
                field = sess["wd_field"]
            pick = max(field, key=lambda t: chars[t])
            self.client.post("/games/wiki-derby/bet", data={"title": pick})
        rows = self.query("SELECT score FROM scores WHERE game = 'wiki-derby'")
        self.assertEqual(rows, [(250,)])

    # ---- 多数派ゲート生き残り ----
    def test_majority_side_cases(self):
        ms = self.mod.majority_side
        self.assertEqual(ms([60, 55, 70, 40, 65]), "A")
        self.assertEqual(ms([30, 45, 20, 49, 40]), "B")

    def test_majority_flow_all_correct(self):
        self.client.get("/games/majority-gate")
        for _ in range(10):
            with self.client.session_transaction() as sess:
                q = sess["mg_questions"][sess["mg_idx"]]
            side = self.mod.majority_side(q["snaps"])
            self.client.post("/games/majority-gate/answer", data={"side": side})
        rows = self.query("SELECT score FROM scores WHERE game = 'majority-gate'")
        self.assertEqual(rows, [(100,)])

    # ---- 時代ガチャ人生1周 ----
    def test_era_prob_bounds(self):
        p = self.mod.era_success_prob
        self.assertEqual(p(10, 1), 95)
        self.assertEqual(p(1, 10), 5)
        self.assertTrue(5 <= p(5, 5) <= 95)

    def test_era_flow_two_lives(self):
        self.client.get("/games/era-gacha")
        self.client.post("/games/era-gacha/gacha")
        for _ in range(6):
            self.client.post("/games/era-gacha/choose", data={"opt": "0"})
        rows = self.query("SELECT score FROM scores WHERE game = 'era-gacha'")
        self.assertEqual(len(rows), 1)
        self.client.post("/games/era-gacha/gacha")
        for _ in range(6):
            self.client.post("/games/era-gacha/choose", data={"opt": "1"})
        rows = self.query("SELECT score FROM scores WHERE game = 'era-gacha'")
        self.assertEqual(len(rows), 2)
        body = self.client.get("/games/era-gacha").get_data(as_text=True)
        self.assertIn("平行人生", body)

    # ---- あと1分・見直し配分 ----
    def test_lastminute_score_cases(self):
        problems = [
            {"q": "1 + 1", "shown": 2, "correct": 2, "is_correct": True},
            {"q": "2 + 2", "shown": 5, "correct": 4, "is_correct": False},
            {"q": "3 + 3", "shown": 6, "correct": 6, "is_correct": True},
        ]
        s = self.mod.lastminute_score
        self.assertEqual(s(problems, [False, False, False]), 20)
        self.assertEqual(s(problems, [False, True, False]), 30)
        # 正解の問題を「直す」と壊れて不正解になる
        self.assertEqual(s(problems, [True, True, False]), 20)

    def test_lastminute_flow_fix_and_submit(self):
        self.client.get("/games/last-minute")
        with self.client.session_transaction() as sess:
            problems = [dict(p) for p in sess["lm_problems"]]
            problems[0]["is_correct"] = False
            problems[0]["shown"] = problems[0]["correct"] + 1
            sess["lm_problems"] = problems
        self.client.post("/games/last-minute/fix", data={"idx": "0"})
        res = self.client.post("/games/last-minute/submit")
        self.assertIn("提出しました", res.get_data(as_text=True))
        expected = self.mod.lastminute_score(
            problems, [i == 0 for i in range(10)])
        rows = self.query("SELECT score FROM scores WHERE game = 'last-minute'")
        self.assertEqual(rows, [(expected,)])

    def test_lastminute_expiry_finalizes(self):
        self.client.get("/games/last-minute")
        with self.client.session_transaction() as sess:
            sess["lm_start"] = sess["lm_start"] - 120
        res = self.client.get("/games/last-minute")
        self.assertIn("時間切れ", res.get_data(as_text=True))
        rows = self.query("SELECT score FROM scores WHERE game = 'last-minute'")
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
