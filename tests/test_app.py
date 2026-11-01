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
        self.assertIn("38 本", body)

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
        self.assertIn("38 本", body)
        self.assertEqual(len(self.mod.GAMES), 38)

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
        self.assertIn("38 本", body)
        self.assertEqual(len(self.mod.GAMES), 38)

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
        self.assertIn("38 本", body)
        self.assertEqual(len(self.mod.GAMES), 38)
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
        self.assertIn("38 本", body)
        self.assertEqual(len(self.mod.GAMES), 38)

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
        self.assertIn("38 本", body)
        self.assertEqual(len(self.mod.GAMES), 38)

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
        self.assertIn("38 本", body)
        self.assertEqual(len(self.mod.GAMES), 38)

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


if __name__ == "__main__":
    unittest.main()
