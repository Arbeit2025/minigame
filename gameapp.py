# app.py
# Flask + SQLite ルーレット/抽選テーブル（完全1ファイル）
# 起動:  py app.py
# URL:  http://127.0.0.1:5000

from __future__ import annotations

import sqlite3
import random
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import Flask, request, redirect, url_for, flash, render_template_string

APP_DB = Path("roulette.db")

app = Flask(__name__)
app.secret_key = "dev-secret-key"  # ローカル用途。必要なら変えてOK


# ============================
# HTML（埋め込みテンプレ）
# ============================
TEMPLATE = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ルーレット（Flask）</title>
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 24px; line-height: 1.5; }
    .wrap { max-width: 980px; margin: 0 auto; }
    h1 { font-size: 20px; margin: 0 0 16px; }
    .grid { display: grid; grid-template-columns: 1fr 2fr; gap: 16px; align-items: start; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 14px; background: #fff; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    input[type="text"], input[type="number"], select {
      padding: 8px; border: 1px solid #ccc; border-radius: 8px; min-width: 180px;
    }
    button { padding: 8px 12px; border: 1px solid #444; border-radius: 8px; background: #f7f7f7; cursor: pointer; }
    button:hover { background: #eee; }
    .muted { color: #666; font-size: 12px; }
    .flash { padding: 10px 12px; border-radius: 10px; margin: 0 0 12px; border: 1px solid #ddd; }
    .flash.ok { background: #f3fff3; border-color: #bfe8bf; }
    .flash.ng { background: #fff3f3; border-color: #e8bfbf; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #eee; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #fafafa; }
    .small { width: 90px; }
    .danger { border-color: #b00; color: #b00; }
    .danger:hover { background: #ffecec; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid #ddd; font-size: 12px; color: #444; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>🎲 ルーレット（Flask + SQLite / 1ファイル）</h1>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, msg in messages %}
        <div class="flash {{ category }}">{{ msg }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <div class="grid">

    <!-- 左: テーブル操作 -->
    <div class="card">
      <h2 style="font-size:16px; margin:0 0 10px;">テーブル</h2>

      <form method="post" action="{{ url_for('tables_create') }}" class="row" style="margin-bottom:10px;">
        <input type="text" name="title" placeholder="新規テーブル名" />
        <button type="submit">作成</button>
      </form>

      <div class="muted" style="margin-bottom:8px;">選択すると右側で候補編集・抽選できます。</div>

      <form method="get" action="{{ url_for('index') }}" class="row" style="margin-bottom:10px;">
        <select name="table_id">
          <option value="">-- 選択 --</option>
          {% for t in tables %}
            <option value="{{ t.id }}" {% if selected_table and selected_table.id == t.id %}selected{% endif %}>
              {{ t.title }} ({{ t.entry_count }})
            </option>
          {% endfor %}
        </select>
        <button type="submit">開く</button>
      </form>

      {% if selected_table %}
        <div class="row" style="justify-content: space-between; align-items:center;">
          <div>
            <div><strong>{{ selected_table.title }}</strong></div>
            <div class="muted">作成: {{ selected_table.created_at }}</div>
          </div>
          <form method="post" action="{{ url_for('tables_delete') }}">
            <input type="hidden" name="table_id" value="{{ selected_table.id }}">
            <button type="submit" class="danger" onclick="return confirm('このテーブルを削除します。よろしいですか？')">削除</button>
          </form>
        </div>
      {% else %}
        <div class="muted">まだ選択されていません。</div>
      {% endif %}
    </div>

    <!-- 右: 候補 + 抽選 + 履歴 -->
    <div class="card">
      <h2 style="font-size:16px; margin:0 0 10px;">候補 / 抽選</h2>

      {% if not selected_table %}
        <div class="muted">左でテーブルを選択してください。</div>
      {% else %}

        <!-- 抽選 -->
        <form method="post" action="{{ url_for('spin') }}" class="row" style="margin-bottom:12px;">
          <input type="hidden" name="table_id" value="{{ selected_table.id }}">
          <span class="pill">回す</span>
          <input type="number" name="times" min="1" max="50" value="1" class="small" />
          <button type="submit">抽選</button>
          <span class="muted">（1〜50回）</span>
        </form>

        <!-- 追加 -->
        <form method="post" action="{{ url_for('entries_add') }}" class="row" style="margin-bottom:12px;">
          <input type="hidden" name="table_id" value="{{ selected_table.id }}">
          <input type="text" name="name" placeholder="候補名" />
          <input type="number" name="weight" min="1" max="999" value="1" class="small" />
          <button type="submit">追加</button>
          <span class="muted">重み=当たりやすさ</span>
        </form>

        <!-- 一覧 -->
        <table>
          <thead>
            <tr>
              <th>候補</th>
              <th class="small">重み</th>
              <th class="small">操作</th>
            </tr>
          </thead>
          <tbody>
          {% if entries|length == 0 %}
            <tr><td colspan="3" class="muted">候補が空です。追加してください。</td></tr>
          {% endif %}

          {% for e in entries %}
            <tr>
              <td>
                <form method="post" action="{{ url_for('entries_update') }}" class="row" style="gap:6px;">
                  <input type="hidden" name="table_id" value="{{ selected_table.id }}">
                  <input type="hidden" name="entry_id" value="{{ e.id }}">
                  <input type="text" name="name" value="{{ e.name }}" />
              </td>
              <td>
                  <input type="number" name="weight" min="1" max="999" value="{{ e.weight }}" class="small" />
              </td>
              <td class="row" style="gap:6px;">
                  <button type="submit">更新</button>
                </form>

                <form method="post" action="{{ url_for('entries_delete') }}">
                  <input type="hidden" name="table_id" value="{{ selected_table.id }}">
                  <input type="hidden" name="entry_id" value="{{ e.id }}">
                  <button type="submit" class="danger" onclick="return confirm('この候補を削除します。よろしいですか？')">削除</button>
                </form>
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>

        <!-- 履歴 -->
        <h3 style="font-size:14px; margin:16px 0 8px;">直近の結果（最新20件）</h3>
        {% if spins|length == 0 %}
          <div class="muted">まだ履歴がありません。</div>
        {% else %}
          <table>
            <thead>
              <tr>
                <th>結果</th>
                <th style="width:220px;">日時</th>
              </tr>
            </thead>
            <tbody>
              {% for s in spins %}
                <tr>
                  <td>{{ s.result_text }}</td>
                  <td class="muted">{{ s.created_at }}</td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
        {% endif %}

      {% endif %}
    </div>

  </div>

  <div class="muted" style="margin-top:14px;">
    DBファイル: roulette.db（同じフォルダに自動生成）
  </div>
</div>
</body>
</html>
"""


# ============================
# DB
# ============================
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                weight INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(table_id) REFERENCES tables(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id INTEGER NOT NULL,
                entry_id INTEGER,
                result_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(table_id) REFERENCES tables(id) ON DELETE CASCADE,
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE SET NULL
            )
            """
        )


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ============================
# Queries
# ============================
def list_tables() -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT t.id, t.title, t.created_at,
                   (SELECT COUNT(*) FROM entries e WHERE e.table_id = t.id) AS entry_count
            FROM tables t
            ORDER BY t.id DESC
            """
        ).fetchall()


def get_table(table_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, title, created_at FROM tables WHERE id = ?",
            (table_id,),
        ).fetchone()


def list_entries(table_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT id, name, weight, created_at
            FROM entries
            WHERE table_id = ?
            ORDER BY id ASC
            """,
            (table_id,),
        ).fetchall()


def list_spins(table_id: int, limit: int = 20) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT s.id, s.result_text, s.created_at
            FROM spins s
            WHERE s.table_id = ?
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (table_id, limit),
        ).fetchall()


def create_table(title: str) -> int:
    title = title.strip()
    if not title:
        raise ValueError("テーブル名が空です。")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tables(title, created_at) VALUES(?, ?)",
            (title, now_iso()),
        )
        return int(cur.lastrowid)


def delete_table(table_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM tables WHERE id = ?", (table_id,))


def add_entry(table_id: int, name: str, weight: int) -> None:
    name = name.strip()
    if not name:
        raise ValueError("候補名が空です。")
    weight = 1 if weight < 1 else (999 if weight > 999 else weight)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO entries(table_id, name, weight, created_at) VALUES(?, ?, ?, ?)",
            (table_id, name, weight, now_iso()),
        )


def update_entry(entry_id: int, name: str, weight: int) -> None:
    name = name.strip()
    if not name:
        raise ValueError("候補名が空です。")
    weight = 1 if weight < 1 else (999 if weight > 999 else weight)
    with get_conn() as conn:
        conn.execute(
            "UPDATE entries SET name = ?, weight = ? WHERE id = ?",
            (name, weight, entry_id),
        )


def delete_entry(entry_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))


def weighted_pick(entries: List[sqlite3.Row]) -> Optional[sqlite3.Row]:
    if not entries:
        return None
    total = 0
    weights = []
    for e in entries:
        w = int(e["weight"])
        if w < 1:
            w = 1
        total += w
        weights.append(w)

    r = random.randint(1, total)
    acc = 0
    for e, w in zip(entries, weights):
        acc += w
        if r <= acc:
            return e
    return None


def record_spin(table_id: int, entry: Optional[sqlite3.Row]) -> str:
    if entry is None:
        result_text = "（抽選失敗）"
        entry_id = None
    else:
        result_text = str(entry["name"])
        entry_id = int(entry["id"])

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO spins(table_id, entry_id, result_text, created_at) VALUES(?, ?, ?, ?)",
            (table_id, entry_id, result_text, now_iso()),
        )
    return result_text


# ============================
# Routes
# ============================
@app.route("/", methods=["GET"])
def index():
    tables = list_tables()
    selected_id_raw = request.args.get("table_id", "").strip()

    selected_id = int(selected_id_raw) if selected_id_raw.isdigit() else None
    selected_table = get_table(selected_id) if selected_id else None
    entries = list_entries(selected_id) if selected_table else []
    spins = list_spins(selected_id, limit=20) if selected_table else []

    return render_template_string(
        TEMPLATE,
        tables=tables,
        selected_table=selected_table,
        entries=entries,
        spins=spins,
    )


@app.route("/tables/create", methods=["POST"])
def tables_create():
    title = request.form.get("title", "").strip()
    try:
        table_id = create_table(title)
        flash("テーブルを作成しました。", "ok")
        return redirect(url_for("index", table_id=table_id))
    except Exception as e:
        flash(f"作成できませんでした: {e}", "ng")
        return redirect(url_for("index"))


@app.route("/tables/delete", methods=["POST"])
def tables_delete():
    table_id_raw = request.form.get("table_id", "").strip()
    if not table_id_raw.isdigit():
        flash("削除対象が不正です。", "ng")
        return redirect(url_for("index"))
    delete_table(int(table_id_raw))
    flash("テーブルを削除しました。", "ok")
    return redirect(url_for("index"))


@app.route("/entries/add", methods=["POST"])
def entries_add():
    table_id_raw = request.form.get("table_id", "").strip()
    name = request.form.get("name", "").strip()
    weight_raw = request.form.get("weight", "").strip()

    if not table_id_raw.isdigit():
        flash("テーブル指定が不正です。", "ng")
        return redirect(url_for("index"))

    table_id = int(table_id_raw)
    weight = int(weight_raw) if weight_raw.isdigit() else 1

    try:
        add_entry(table_id, name, weight)
        flash("候補を追加しました。", "ok")
    except Exception as e:
        flash(f"追加できませんでした: {e}", "ng")

    return redirect(url_for("index", table_id=table_id))


@app.route("/entries/update", methods=["POST"])
def entries_update():
    table_id_raw = request.form.get("table_id", "").strip()
    entry_id_raw = request.form.get("entry_id", "").strip()
    name = request.form.get("name", "").strip()
    weight_raw = request.form.get("weight", "").strip()

    if not (table_id_raw.isdigit() and entry_id_raw.isdigit()):
        flash("更新対象が不正です。", "ng")
        return redirect(url_for("index"))

    table_id = int(table_id_raw)
    entry_id = int(entry_id_raw)
    weight = int(weight_raw) if weight_raw.isdigit() else 1

    try:
        update_entry(entry_id, name, weight)
        flash("候補を更新しました。", "ok")
    except Exception as e:
        flash(f"更新できませんでした: {e}", "ng")

    return redirect(url_for("index", table_id=table_id))


@app.route("/entries/delete", methods=["POST"])
def entries_delete():
    table_id_raw = request.form.get("table_id", "").strip()
    entry_id_raw = request.form.get("entry_id", "").strip()

    if not (table_id_raw.isdigit() and entry_id_raw.isdigit()):
        flash("削除対象が不正です。", "ng")
        return redirect(url_for("index"))

    table_id = int(table_id_raw)
    entry_id = int(entry_id_raw)

    delete_entry(entry_id)
    flash("候補を削除しました。", "ok")
    return redirect(url_for("index", table_id=table_id))


@app.route("/spin", methods=["POST"])
def spin():
    table_id_raw = request.form.get("table_id", "").strip()
    times_raw = request.form.get("times", "").strip()

    if not table_id_raw.isdigit():
        flash("テーブル指定が不正です。", "ng")
        return redirect(url_for("index"))

    table_id = int(table_id_raw)
    times = int(times_raw) if times_raw.isdigit() else 1
    times = 1 if times < 1 else (50 if times > 50 else times)

    entries = list_entries(table_id)
    if not entries:
        flash("候補が空なので回せません。", "ng")
        return redirect(url_for("index", table_id=table_id))

    results = []
    for _ in range(times):
        picked = weighted_pick(entries)
        results.append(record_spin(table_id, picked))

    if times == 1:
        flash(f"結果: {results[0]}", "ok")
    else:
        flash(f"{times}回 回しました。最新: {results[-1]}", "ok")

    return redirect(url_for("index", table_id=table_id))


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=True)
