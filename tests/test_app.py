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


if __name__ == "__main__":
    unittest.main()
