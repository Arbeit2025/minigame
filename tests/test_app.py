import importlib.util
import os
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
        self.assertIn("23 本", body)

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
        self.assertIn("23 本", body)
        self.assertEqual(len(self.mod.GAMES), 23)

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


if __name__ == "__main__":
    unittest.main()
