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


if __name__ == "__main__":
    unittest.main()
