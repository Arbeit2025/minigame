# gameapp.py
# Flask + SQLite 自作ミニゲーム集ポータル（完全1ファイル）
# トップページがゲーム一覧ポータル、各ゲームは /games/<slug> で遊べる。
# 収録ゲームはすべて作者の自作。新しいゲームは GAMES リストへ1件足して追加する。
# 起動:  python gameapp.py
# URL:  http://127.0.0.1:5000

from __future__ import annotations

import os
import sqlite3
import random
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import Flask, request, redirect, url_for, flash, render_template_string, session

APP_DB = Path("roulette.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")  # ローカル用途。環境変数 SECRET_KEY で変更可


# ============================
# HTML（埋め込みテンプレ）
# ============================
TEMPLATE = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ルーレット抽選｜自作ミニゲーム集</title>
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
  <p style="margin:0 0 8px;"><a href="{{ url_for('index') }}">← ゲーム一覧へ戻る</a></p>
  <h1>🎲 ルーレット抽選</h1>

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

      <form method="get" action="{{ url_for('roulette') }}" class="row" style="margin-bottom:10px;">
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
# ゲーム登録リスト（ポータルの元データ）
# 新しいゲームを足すときは、ここに1件追加し、対応するルートと
# テンプレートを用意するだけで、トップとジャンル別一覧に自動で並ぶ。
# ============================
GAMES = [
    {
        "slug": "roulette",
        "title": "ルーレット抽選",
        "category": "抽選・占い",
        "icon": "🎲",
        "description": "候補を登録してルーレット抽選。重み（当たりやすさ）も付けられ、結果は履歴に残ります。ランチ決めや順番決めにも。",
        "endpoint": "roulette",
    },
    {
        "slug": "omikuji",
        "title": "おみくじ",
        "category": "抽選・占い",
        "icon": "🔮",
        "description": "ボタンを押すと今日の運勢が出ます。大吉から大凶まで重み付き抽選で、一言メッセージ付き。",
        "endpoint": "omikuji",
    },
    {
        "slug": "highlow",
        "title": "ハイ＆ロー",
        "category": "カード・数字",
        "icon": "🃏",
        "description": "今のカードの次が大きいか小さいか当てるゲーム。連続正解を伸ばそう。同じ数は引き分けで連勝継続。",
        "endpoint": "highlow",
    },
    {
        "slug": "number",
        "title": "数当てゲーム",
        "category": "カード・数字",
        "icon": "🔢",
        "description": "1〜100の秘密の数をヒントを頼りに当てるゲーム。少ない試行回数で当てるほど良い記録になります。",
        "endpoint": "number",
    },
    {
        "slug": "reaction",
        "title": "反応速度テスト",
        "category": "アクション",
        "icon": "⚡",
        "description": "画面が緑になった瞬間にクリック。反応速度をミリ秒で計測し、ベスト記録を残せます。",
        "endpoint": "reaction",
    },
    {
        "slug": "stopwatch",
        "title": "ストップウォッチ・チャレンジ",
        "category": "アクション",
        "icon": "⏱️",
        "description": "10.00秒ぴったりを狙って止めるゲーム。誤差（ミリ秒）の小ささを競います。",
        "endpoint": "stopwatch",
    },
    {
        "slug": "janken",
        "title": "じゃんけん",
        "category": "対戦",
        "icon": "✊",
        "description": "CPU とじゃんけん対戦。勝ち続けて連勝記録を伸ばそう。あいこは連勝継続です。",
        "endpoint": "janken",
    },
    {
        "slug": "slot",
        "title": "絵文字スロット",
        "category": "抽選・占い",
        "icon": "🎰",
        "description": "コインで回す絵文字スロット。3つ揃えば大当たり、ペアでも配当あり。コインは保存されます。",
        "endpoint": "slot",
    },
    {
        "slug": "dice",
        "title": "サイコロ勝負",
        "category": "対戦",
        "icon": "🎯",
        "description": "自分と CPU がサイコロ2個ずつで勝負。合計勝負で、ゾロ目にはボーナス付き。ベスト合計を記録します。",
        "endpoint": "dice",
    },
]


# ============================
# HTML（ポータルトップ）
# ============================
PORTAL_TEMPLATE = r"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>自作ミニゲーム集｜ブラウザで遊べる無料ゲーム</title>
  <meta name="description" content="全部、作者が自分で作ったミニゲームだけを集めたポータルサイト。登録不要・無料でブラウザからそのまま遊べます。" />
  <style>
    body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 24px; line-height: 1.6; background: #fbfaf7; color: #222; }
    .wrap { max-width: 980px; margin: 0 auto; }
    h1 { font-size: 26px; margin: 0 0 6px; }
    .lead { color: #555; margin: 0 0 20px; }
    h2 { font-size: 18px; margin: 26px 0 10px; }
    .cats { display: flex; gap: 8px; flex-wrap: wrap; padding: 0; list-style: none; margin: 0; }
    .cats li { border: 1px solid #ddd; background: #fff; border-radius: 999px; padding: 4px 12px; font-size: 14px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 16px; background: #fff; display: flex; flex-direction: column; gap: 8px; }
    .icon { font-size: 40px; line-height: 1; }
    .card h3 { margin: 0; font-size: 17px; }
    .card p { margin: 0; color: #555; font-size: 14px; flex: 1; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid #ddd; font-size: 12px; color: #444; align-self: flex-start; }
    .play { display: inline-block; text-align: center; padding: 9px 12px; border: 1px solid #444; border-radius: 8px; background: #f7f7f7; color: #222; text-decoration: none; font-weight: 600; }
    .play:hover { background: #eee; }
    .muted { color: #666; font-size: 13px; }
    footer { margin-top: 36px; border-top: 1px solid #e5e5e5; padding-top: 12px; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>🎮 自作ミニゲーム集</h1>
  <p class="lead">ここにあるのは、全部わたし（作者）が自分で作ったゲームだけです。登録不要・無料で、ブラウザからそのまま遊べます。少しずつ増やしていく予定です。</p>

  <h2>ジャンル</h2>
  <ul class="cats">
    {% for name, count in categories %}
      <li>{{ name }}（{{ count }}）</li>
    {% endfor %}
  </ul>

  <h2>ゲーム一覧</h2>
  <div class="grid">
    {% for game in games %}
      <div class="card">
        <div class="icon">{{ game.icon }}</div>
        <h3>{{ game.title }}</h3>
        <span class="pill">{{ game.category }}</span>
        <p>{{ game.description }}</p>
        <a class="play" href="{{ url_for(game.endpoint) }}">▶ 遊ぶ</a>
      </div>
    {% endfor %}
  </div>

  <h2>これから</h2>
  <p class="muted">新しいゲームを作ったら、ここに追加していきます。いま遊べるのは上の {{ games|length }} 本です。</p>

  <footer class="muted">
    ルーレット抽選で作ったテーブルや抽選結果はサーバーに保存されますが、サービスの再起動・再デプロイで消えることがあります。大事な抽選の結果はメモしておいてください。
  </footer>
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game TEXT NOT NULL,
                score INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
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
    # 旧ルーレットの URL（/?table_id=...）で来た場合はルーレットへ案内する
    legacy_table_id = request.args.get("table_id", "").strip()
    if legacy_table_id:
        return redirect(url_for("roulette", table_id=legacy_table_id))
    categories = {}
    for game in GAMES:
        categories[game["category"]] = categories.get(game["category"], 0) + 1
    return render_template_string(
        PORTAL_TEMPLATE,
        games=GAMES,
        categories=sorted(categories.items()),
    )


@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200


@app.route("/games/roulette", methods=["GET"])
def roulette():
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


@app.route("/games/roulette/tables/create", methods=["POST"])
@app.route("/tables/create", methods=["POST"])
def tables_create():
    title = request.form.get("title", "").strip()
    try:
        table_id = create_table(title)
        flash("テーブルを作成しました。", "ok")
        return redirect(url_for("roulette", table_id=table_id))
    except Exception as e:
        flash(f"作成できませんでした: {e}", "ng")
        return redirect(url_for("roulette"))


@app.route("/games/roulette/tables/delete", methods=["POST"])
@app.route("/tables/delete", methods=["POST"])
def tables_delete():
    table_id_raw = request.form.get("table_id", "").strip()
    if not table_id_raw.isdigit():
        flash("削除対象が不正です。", "ng")
        return redirect(url_for("roulette"))
    delete_table(int(table_id_raw))
    flash("テーブルを削除しました。", "ok")
    return redirect(url_for("roulette"))


@app.route("/games/roulette/entries/add", methods=["POST"])
@app.route("/entries/add", methods=["POST"])
def entries_add():
    table_id_raw = request.form.get("table_id", "").strip()
    name = request.form.get("name", "").strip()
    weight_raw = request.form.get("weight", "").strip()

    if not table_id_raw.isdigit():
        flash("テーブル指定が不正です。", "ng")
        return redirect(url_for("roulette"))

    table_id = int(table_id_raw)
    weight = int(weight_raw) if weight_raw.isdigit() else 1

    try:
        add_entry(table_id, name, weight)
        flash("候補を追加しました。", "ok")
    except Exception as e:
        flash(f"追加できませんでした: {e}", "ng")

    return redirect(url_for("roulette", table_id=table_id))


@app.route("/games/roulette/entries/update", methods=["POST"])
@app.route("/entries/update", methods=["POST"])
def entries_update():
    table_id_raw = request.form.get("table_id", "").strip()
    entry_id_raw = request.form.get("entry_id", "").strip()
    name = request.form.get("name", "").strip()
    weight_raw = request.form.get("weight", "").strip()

    if not (table_id_raw.isdigit() and entry_id_raw.isdigit()):
        flash("更新対象が不正です。", "ng")
        return redirect(url_for("roulette"))

    table_id = int(table_id_raw)
    entry_id = int(entry_id_raw)
    weight = int(weight_raw) if weight_raw.isdigit() else 1

    try:
        update_entry(entry_id, name, weight)
        flash("候補を更新しました。", "ok")
    except Exception as e:
        flash(f"更新できませんでした: {e}", "ng")

    return redirect(url_for("roulette", table_id=table_id))


@app.route("/games/roulette/entries/delete", methods=["POST"])
@app.route("/entries/delete", methods=["POST"])
def entries_delete():
    table_id_raw = request.form.get("table_id", "").strip()
    entry_id_raw = request.form.get("entry_id", "").strip()

    if not (table_id_raw.isdigit() and entry_id_raw.isdigit()):
        flash("削除対象が不正です。", "ng")
        return redirect(url_for("roulette"))

    table_id = int(table_id_raw)
    entry_id = int(entry_id_raw)

    delete_entry(entry_id)
    flash("候補を削除しました。", "ok")
    return redirect(url_for("roulette", table_id=table_id))


@app.route("/games/roulette/spin", methods=["POST"])
@app.route("/spin", methods=["POST"])
def spin():
    table_id_raw = request.form.get("table_id", "").strip()
    times_raw = request.form.get("times", "").strip()

    if not table_id_raw.isdigit():
        flash("テーブル指定が不正です。", "ng")
        return redirect(url_for("roulette"))

    table_id = int(table_id_raw)
    times = int(times_raw) if times_raw.isdigit() else 1
    times = 1 if times < 1 else (50 if times > 50 else times)

    entries = list_entries(table_id)
    if not entries:
        flash("候補が空なので回せません。", "ng")
        return redirect(url_for("roulette", table_id=table_id))

    results = []
    for _ in range(times):
        picked = weighted_pick(entries)
        results.append(record_spin(table_id, picked))

    if times == 1:
        flash(f"結果: {results[0]}", "ok")
    else:
        flash(f"{times}回 回しました。最新: {results[-1]}", "ok")

    return redirect(url_for("roulette", table_id=table_id))


# ============================
# 追加ゲーム共通（スコア保存・簡易KV）
# scores: ゲームごとのスコア記録（ベスト表示に使う）
# kv: スロットのコイン残高など小さな状態の保存
# ============================
def record_score(game: str, score: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO scores(game, score, created_at) VALUES(?, ?, ?)",
            (game, int(score), now_iso()),
        )


def best_score(game: str, mode: str = "max") -> Optional[int]:
    column = "MAX(score)" if mode == "max" else "MIN(score)"
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {column} AS v FROM scores WHERE game = ?", (game,)
        ).fetchone()
    return None if row is None or row["v"] is None else int(row["v"])


def recent_scores(game: str, limit: int = 10) -> List[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT score, created_at FROM scores WHERE game = ? ORDER BY id DESC LIMIT ?",
            (game, limit),
        ).fetchall()


def get_kv(key: str, default: Optional[str] = None) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return default if row is None else str(row["value"])


def set_kv(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO kv(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


_GAME_CSS = """
    body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 24px; line-height: 1.6; background: #fbfaf7; color: #222; }
    .wrap { max-width: 720px; margin: 0 auto; }
    h1 { font-size: 24px; margin: 0 0 6px; }
    .howto { color: #555; margin: 0 0 16px; }
    .card { border: 1px solid #ddd; border-radius: 12px; padding: 18px; background: #fff; margin-bottom: 16px; }
    button { padding: 10px 16px; border: 1px solid #444; border-radius: 8px; background: #f7f7f7; cursor: pointer; font-size: 16px; }
    button:hover { background: #eee; }
    .big { font-size: 44px; text-align: center; margin: 10px 0; }
    .mid { font-size: 22px; text-align: center; margin: 8px 0; }
    .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; justify-content: center; }
    .muted { color: #666; font-size: 13px; }
    .flash { padding: 10px 12px; border-radius: 10px; margin: 0 0 12px; border: 1px solid #ddd; }
    .flash.ok { background: #f3fff3; border-color: #bfe8bf; }
    .flash.ng { background: #fff3f3; border-color: #e8bfbf; }
    .result { font-size: 20px; text-align: center; margin: 10px 0; }
    input[type="number"] { padding: 9px; border: 1px solid #ccc; border-radius: 8px; width: 120px; font-size: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; }
"""

_FLASH_BLOCK = """
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, msg in messages %}
        <div class="flash {{ category }}">{{ msg }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}
"""


def game_page(title: str, body: str) -> str:
    """共通の見た目でゲームページを描く（body は描画済みHTML）。"""
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}｜自作ミニゲーム集</title>
  <style>{_GAME_CSS}</style>
</head>
<body>
<div class="wrap">
  <p style="margin:0 0 8px;"><a href="{url_for('index')}">← ゲーム一覧へ戻る</a></p>
{body}
</div>
</body>
</html>"""


# ============================
# おみくじ
# ============================
OMIKUJI_FORTUNES = [
    ("大吉", 5),
    ("中吉", 15),
    ("小吉", 20),
    ("吉", 25),
    ("末吉", 20),
    ("凶", 10),
    ("大凶", 5),
]

OMIKUJI_MESSAGES = {
    "大吉": ["何をやってもうまくいく日。思い切って挑戦してみよう。", "願いは叶う。笑顔を忘れずに。"],
    "中吉": ["コツコツ進めれば良い結果に。焦らないのがコツ。", "小さな良いことが重なる日。"],
    "小吉": ["ささやかな幸運あり。身近な人を大切に。", "いつも通りが一番の近道。"],
    "吉": ["穏やかに過ごせる日。新しいことに少しだけ手を伸ばして。", "困ったら周りに相談すると吉。"],
    "末吉": ["後半にかけて運気は上向き。準備を丁寧に。", "落とし物に注意。足元を見直そう。"],
    "凶": ["今日は無理をしない日。早めに休もう。", "慎重に。大きな決断は明日に回して正解。"],
    "大凶": ["嵐の日もある。じっと耐えれば必ず晴れる。", "今日は守りの日。温かい飲み物で一息つこう。"],
}


def pick_omikuji() -> tuple:
    total = sum(w for _, w in OMIKUJI_FORTUNES)
    r = random.randint(1, total)
    acc = 0
    for name, w in OMIKUJI_FORTUNES:
        acc += w
        if r <= acc:
            return name, random.choice(OMIKUJI_MESSAGES[name])
    return OMIKUJI_FORTUNES[0][0], OMIKUJI_MESSAGES[OMIKUJI_FORTUNES[0][0]][0]


OMIKUJI_TEMPLATE = r"""
  <h1>🔮 おみくじ</h1>
  <p class="howto">ボタンを押すと今日の運勢が出ます。大吉から大凶まで、重み付きで抽選しています。</p>
  __FLASH__
  <div class="card">
    {% if result %}
      <div class="big">{{ result.fortune }}</div>
      <p class="result">{{ result.message }}</p>
    {% else %}
      <p class="mid">まだ引いていません</p>
    {% endif %}
    <form method="post" action="{{ url_for('omikuji_draw') }}" class="row">
      <button type="submit">おみくじを引く</button>
    </form>
  </div>
"""


@app.route("/games/omikuji", methods=["GET"])
def omikuji():
    body = render_template_string(OMIKUJI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK), result=None)
    return game_page("おみくじ", body)


@app.route("/games/omikuji/draw", methods=["POST"])
def omikuji_draw():
    fortune, message = pick_omikuji()
    body = render_template_string(
        OMIKUJI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        result={"fortune": fortune, "message": message},
    )
    return game_page("おみくじ", body)


# ============================
# ハイ＆ロー
# ============================
def card_label(value: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(value, str(value))


HIGHLOW_TEMPLATE = r"""
  <h1>🃏 ハイ＆ロー</h1>
  <p class="howto">今のカード（1〜13）の次の数が、大きいか小さいか当てるゲーム。連続正解がスコアです。同じ数が出たら引き分けで連勝は続きます。</p>
  __FLASH__
  <div class="card">
    <p class="mid">今のカード</p>
    <div class="big">{{ card_label }}</div>
    {% if last %}
      <p class="result">{{ last.message }}</p>
      <p class="mid">前のカード {{ last.prev_label }} → 次のカード {{ last.next_label }}</p>
    {% endif %}
    <p class="result">現在の連勝: {{ streak }} ／ ベスト: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('highlow_guess') }}" class="row">
      <button type="submit" name="choice" value="high">⬆ 次は大きい</button>
      <button type="submit" name="choice" value="low">⬇ 次は小さい</button>
    </form>
    <form method="post" action="{{ url_for('highlow_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
  </div>
"""


def render_highlow(last=None):
    if "hl_card" not in session:
        session["hl_card"] = random.randint(1, 13)
        session["hl_streak"] = 0
    body = render_template_string(
        HIGHLOW_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        card_label=card_label(int(session["hl_card"])),
        streak=int(session.get("hl_streak", 0)),
        best=best_score("highlow", "max"),
        last=last,
    )
    return game_page("ハイ＆ロー", body)


@app.route("/games/highlow", methods=["GET"])
def highlow():
    return render_highlow()


@app.route("/games/highlow/guess", methods=["POST"])
def highlow_guess():
    if "hl_card" not in session:
        session["hl_card"] = random.randint(1, 13)
        session["hl_streak"] = 0
    choice = request.form.get("choice", "")
    current = int(session["hl_card"])
    nxt = random.randint(1, 13)
    streak = int(session.get("hl_streak", 0))
    if nxt == current:
        message = "同じ数！引き分け（連勝は続きます）"
    elif (choice == "high" and nxt > current) or (choice == "low" and nxt < current):
        streak += 1
        record_score("highlow", streak)
        message = f"正解！ {streak} 連勝中"
    else:
        streak = 0
        message = "はずれ… 連勝はリセットされました"
    session["hl_card"] = nxt
    session["hl_streak"] = streak
    last = {
        "prev_label": card_label(current),
        "next_label": card_label(nxt),
        "message": message,
    }
    return render_highlow(last=last)


@app.route("/games/highlow/reset", methods=["POST"])
def highlow_reset():
    session.pop("hl_card", None)
    session.pop("hl_streak", None)
    flash("リセットしました。", "ok")
    return redirect(url_for("highlow"))


# ============================
# 数当てゲーム
# ============================
NUMBER_TEMPLATE = r"""
  <h1>🔢 数当てゲーム</h1>
  <p class="howto">1〜100の秘密の数を当てるゲーム。「もっと大きい／小さい」のヒントを頼りに、少ない試行回数で当てるほど良いスコアです。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">試行回数: {{ tries }} ／ ベスト（最少試行）: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('number_guess') }}" class="row">
      <input type="number" name="guess" min="1" max="100" required placeholder="1〜100" />
      <button type="submit">当てる</button>
    </form>
    <form method="post" action="{{ url_for('number_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">新しい数で始める</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（試行回数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 回</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_number(message=None):
    if "num_secret" not in session:
        session["num_secret"] = random.randint(1, 100)
        session["num_tries"] = 0
    body = render_template_string(
        NUMBER_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        tries=int(session.get("num_tries", 0)),
        best=best_score("number", "min"),
        history=recent_scores("number", 10),
        message=message,
    )
    return game_page("数当てゲーム", body)


@app.route("/games/number", methods=["GET"])
def number():
    return render_number()


@app.route("/games/number/guess", methods=["POST"])
def number_guess():
    if "num_secret" not in session:
        session["num_secret"] = random.randint(1, 100)
        session["num_tries"] = 0
    raw = request.form.get("guess", "").strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 100):
        flash("1〜100の数を入力してください。", "ng")
        return render_number()
    guess = int(raw)
    secret = int(session["num_secret"])
    tries = int(session.get("num_tries", 0)) + 1
    session["num_tries"] = tries
    if guess == secret:
        record_score("number", tries)
        session.pop("num_secret", None)
        session.pop("num_tries", None)
        return render_number(message=f"🎉 正解！ 答えは {secret} でした（{tries} 回目）。新しいゲームが始まっています。")
    hint = "もっと大きいです" if guess < secret else "もっと小さいです"
    return render_number(message=f"{guess} … {hint}")


@app.route("/games/number/reset", methods=["POST"])
def number_reset():
    session.pop("num_secret", None)
    session.pop("num_tries", None)
    flash("新しい数にしました。", "ok")
    return redirect(url_for("number"))


# ============================
# 反応速度テスト
# ============================
REACTION_TEMPLATE = r"""
  <h1>⚡ 反応速度テスト</h1>
  <p class="howto">スタートを押して待機し、画面が緑になったらすぐクリック。小さいミリ秒ほど速い反応です。</p>
  __FLASH__
  <div class="card">
    <div id="stage" style="border-radius:12px; padding:44px 12px; text-align:center; font-size:22px; background:#eee; cursor:pointer; user-select:none;">ここを押してスタート</div>
    <p class="result" id="message">ベスト（最速）: {{ best if best is not none else '—' }}{% if best is not none %} ms{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} ms</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var message = document.getElementById("message");
  var state = "idle"; // idle | waiting | ready
  var timer = null, startedAt = 0;
  function setStage(bg, text){ stage.style.background = bg; stage.textContent = text; }
  stage.addEventListener("click", function(){
    if (state === "idle") {
      state = "waiting";
      setStage("#e8bfbf", "待って…緑になったらクリック");
      timer = setTimeout(function(){
        state = "ready";
        startedAt = performance.now();
        setStage("#bfe8bf", "今だ！クリック");
      }, 1500 + Math.random() * 2500);
    } else if (state === "waiting") {
      clearTimeout(timer);
      state = "idle";
      setStage("#eee", "早すぎます。ここを押してやり直し");
    } else if (state === "ready") {
      var ms = Math.round(performance.now() - startedAt);
      state = "idle";
      setStage("#eee", "記録: " + ms + " ms（ここを押してもう一度）");
      var form = new FormData();
      form.append("ms", String(ms));
      fetch("{{ url_for('reaction_score') }}", {method: "POST", body: form})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d && d.ok) { message.textContent = "ベスト（最速）: " + d.best + " ms"; }
        })
        .catch(function(){});
    }
  });
})();
</script>
"""


@app.route("/games/reaction", methods=["GET"])
def reaction():
    body = render_template_string(
        REACTION_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("reaction", "min"),
        history=recent_scores("reaction", 10),
    )
    return game_page("反応速度テスト", body)


@app.route("/games/reaction/score", methods=["POST"])
def reaction_score():
    raw = request.form.get("ms", "").strip()
    if not raw.isdigit() or not (50 <= int(raw) <= 10000):
        return {"ok": False, "error": "invalid ms"}, 400
    record_score("reaction", int(raw))
    return {"ok": True, "best": best_score("reaction", "min")}


# ============================
# ストップウォッチ・チャレンジ
# ============================
STOPWATCH_TEMPLATE = r"""
  <h1>⏱️ ストップウォッチ・チャレンジ</h1>
  <p class="howto">スタートして、10.00秒ぴったりだと思ったところでストップ。誤差（ミリ秒）が小さいほど良い記録です。</p>
  __FLASH__
  <div class="card">
    <div class="big" id="display">0.00</div>
    <div class="row">
      <button id="startBtn" type="button">スタート</button>
      <button id="stopBtn" type="button" disabled>ストップ</button>
    </div>
    <p class="result" id="message">ベスト（最小誤差）: {{ best if best is not none else '—' }}{% if best is not none %} ms{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（誤差）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} ms</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var display = document.getElementById("display");
  var message = document.getElementById("message");
  var startBtn = document.getElementById("startBtn");
  var stopBtn = document.getElementById("stopBtn");
  var startedAt = 0, raf = null;
  function tick(){
    var elapsed = performance.now() - startedAt;
    display.textContent = (elapsed / 1000).toFixed(2);
    raf = requestAnimationFrame(tick);
  }
  startBtn.addEventListener("click", function(){
    startedAt = performance.now();
    startBtn.disabled = true;
    stopBtn.disabled = false;
    tick();
  });
  stopBtn.addEventListener("click", function(){
    cancelAnimationFrame(raf);
    var elapsed = performance.now() - startedAt;
    var error = Math.round(Math.abs(elapsed - 10000));
    display.textContent = (elapsed / 1000).toFixed(2);
    startBtn.disabled = false;
    stopBtn.disabled = true;
    var form = new FormData();
    form.append("error_ms", String(error));
    fetch("{{ url_for('stopwatch_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "結果: " + (elapsed/1000).toFixed(2) + " 秒（誤差 " + error + " ms）／ベスト（最小誤差）: " + d.best + " ms";
        }
      })
      .catch(function(){});
  });
})();
</script>
"""


@app.route("/games/stopwatch", methods=["GET"])
def stopwatch():
    body = render_template_string(
        STOPWATCH_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("stopwatch", "min"),
        history=recent_scores("stopwatch", 10),
    )
    return game_page("ストップウォッチ・チャレンジ", body)


@app.route("/games/stopwatch/score", methods=["POST"])
def stopwatch_score():
    raw = request.form.get("error_ms", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 10000):
        return {"ok": False, "error": "invalid error_ms"}, 400
    record_score("stopwatch", int(raw))
    return {"ok": True, "best": best_score("stopwatch", "min")}


# ============================
# じゃんけん
# ============================
JANKEN_HANDS = ["グー", "チョキ", "パー"]
JANKEN_EMOJI = {"グー": "✊", "チョキ": "✌️", "パー": "✋"}
JANKEN_BEATS = {"グー": "チョキ", "チョキ": "パー", "パー": "グー"}


def judge_janken(player: str, cpu: str) -> str:
    if player == cpu:
        return "draw"
    return "win" if JANKEN_BEATS[player] == cpu else "lose"


JANKEN_TEMPLATE = r"""
  <h1>✊ じゃんけん</h1>
  <p class="howto">手を選ぶと CPU と対戦します。勝ち続けると連勝スコアが伸びます（あいこは連勝継続）。</p>
  __FLASH__
  <div class="card">
    {% if last %}
      <p class="big">{{ last.player_emoji }} vs {{ last.cpu_emoji }}</p>
      <p class="result">あなた: {{ last.player }} ／ CPU: {{ last.cpu }} → {{ last.message }}</p>
    {% else %}
      <p class="mid">手を選んでください</p>
    {% endif %}
    <p class="result">現在の連勝: {{ streak }} ／ ベスト: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('janken_play') }}" class="row">
      <button type="submit" name="hand" value="グー">✊ グー</button>
      <button type="submit" name="hand" value="チョキ">✌️ チョキ</button>
      <button type="submit" name="hand" value="パー">✋ パー</button>
    </form>
  </div>
"""


def render_janken(last=None):
    body = render_template_string(
        JANKEN_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        streak=int(session.get("jk_streak", 0)),
        best=best_score("janken", "max"),
        last=last,
    )
    return game_page("じゃんけん", body)


@app.route("/games/janken", methods=["GET"])
def janken():
    return render_janken()


@app.route("/games/janken/play", methods=["POST"])
def janken_play():
    player = request.form.get("hand", "")
    if player not in JANKEN_HANDS:
        flash("手が不正です。", "ng")
        return render_janken()
    cpu = random.choice(JANKEN_HANDS)
    result = judge_janken(player, cpu)
    streak = int(session.get("jk_streak", 0))
    if result == "win":
        streak += 1
        record_score("janken", streak)
        message = f"勝ち！ {streak} 連勝中"
    elif result == "lose":
        streak = 0
        message = "負け… 連勝はリセットされました"
    else:
        message = "あいこ（連勝は続きます）"
    session["jk_streak"] = streak
    last = {
        "player": player,
        "cpu": cpu,
        "player_emoji": JANKEN_EMOJI[player],
        "cpu_emoji": JANKEN_EMOJI[cpu],
        "message": message,
    }
    return render_janken(last=last)


# ============================
# 絵文字スロット
# ============================
SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🔔", "⭐", "7️⃣"]
SLOT_TRIPLE = {"7️⃣": 200, "⭐": 100, "🔔": 80, "🍇": 60, "🍋": 50, "🍒": 50}
SLOT_PAIR_PAYOUT = 20
SLOT_COST = 10
SLOT_START_COINS = 100


def slot_coins() -> int:
    raw = get_kv("slot_coins")
    if raw is None or not raw.lstrip("-").isdigit():
        set_kv("slot_coins", str(SLOT_START_COINS))
        return SLOT_START_COINS
    return int(raw)


def judge_slot(reels) -> int:
    if reels[0] == reels[1] == reels[2]:
        return SLOT_TRIPLE[reels[0]]
    if reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        return SLOT_PAIR_PAYOUT
    return 0


SLOT_TEMPLATE = r"""
  <h1>🎰 絵文字スロット</h1>
  <p class="howto">1回 {{ cost }} コインで回せます。3つ揃えば大当たり（絵文字ごとに配当）、2つ揃えば {{ pair }} コイン。コインはサーバーに保存され、{{ cost }} 未満になったらリセットできます。</p>
  __FLASH__
  <div class="card">
    <div class="big">{{ reels[0] }} {{ reels[1] }} {{ reels[2] }}</div>
    {% if last %}
      <p class="result">{{ last.message }}</p>
    {% endif %}
    <p class="result">コイン: {{ coins }} ／ 最大コイン: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('slot_spin') }}" class="row">
      <button type="submit">回す（{{ cost }}コイン）</button>
    </form>
    {% if coins < cost %}
      <form method="post" action="{{ url_for('slot_reset') }}" class="row" style="margin-top:10px;">
        <button type="submit">コインを {{ start }} にリセット</button>
      </form>
    {% endif %}
  </div>
"""


def render_slot(reels=("❓", "❓", "❓"), last=None):
    body = render_template_string(
        SLOT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        reels=reels,
        coins=slot_coins(),
        best=best_score("slot", "max"),
        cost=SLOT_COST,
        pair=SLOT_PAIR_PAYOUT,
        start=SLOT_START_COINS,
        last=last,
    )
    return game_page("絵文字スロット", body)


@app.route("/games/slot", methods=["GET"])
def slot():
    return render_slot()


@app.route("/games/slot/spin", methods=["POST"])
def slot_spin():
    coins = slot_coins()
    if coins < SLOT_COST:
        flash(f"コインが足りません（{SLOT_COST}コイン必要）。リセットしてください。", "ng")
        return render_slot()
    coins -= SLOT_COST
    reels = [random.choice(SLOT_SYMBOLS) for _ in range(3)]
    payout = judge_slot(reels)
    coins += payout
    set_kv("slot_coins", str(coins))
    record_score("slot", coins)
    if payout >= 50:
        message = f"🎉 大当たり！ +{payout} コイン"
    elif payout > 0:
        message = f"ペア！ +{payout} コイン"
    else:
        message = "はずれ"
    return render_slot(reels=reels, last={"message": message})


@app.route("/games/slot/reset", methods=["POST"])
def slot_reset():
    if slot_coins() < SLOT_COST:
        set_kv("slot_coins", str(SLOT_START_COINS))
        flash(f"コインを {SLOT_START_COINS} にリセットしました。", "ok")
    else:
        flash("まだ回せるコインがあります。", "ng")
    return redirect(url_for("slot"))


# ============================
# サイコロ勝負
# ============================
DICE_FACES = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
DICE_DOUBLES_BONUS = 6


def dice_effective(dice) -> int:
    total = sum(dice)
    return total + DICE_DOUBLES_BONUS if dice[0] == dice[1] else total


DICE_TEMPLATE = r"""
  <h1>🎯 サイコロ勝負</h1>
  <p class="howto">自分と CPU がサイコロを2個ずつ振り、合計の大きい方が勝ち。ゾロ目が出ると +{{ bonus }} ボーナスが付きます。</p>
  __FLASH__
  <div class="card">
    {% if last %}
      <p class="mid">あなた: {{ last.player_faces }} 合計 {{ last.player_total }}{% if last.player_doubles %}（ゾロ目 +{{ bonus }}）{% endif %} → {{ last.player_eff }}</p>
      <p class="mid">CPU: {{ last.cpu_faces }} 合計 {{ last.cpu_total }}{% if last.cpu_doubles %}（ゾロ目 +{{ bonus }}）{% endif %} → {{ last.cpu_eff }}</p>
      <p class="result">{{ last.message }}</p>
    {% else %}
      <p class="mid">ボタンを押して対戦開始</p>
    {% endif %}
    <p class="result">あなたのベスト合計: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('dice_roll') }}" class="row">
      <button type="submit">サイコロを振る</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の自分の合計</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }}</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_dice(last=None):
    body = render_template_string(
        DICE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("dice", "max"),
        history=recent_scores("dice", 10),
        bonus=DICE_DOUBLES_BONUS,
        last=last,
    )
    return game_page("サイコロ勝負", body)


@app.route("/games/dice", methods=["GET"])
def dice():
    return render_dice()


@app.route("/games/dice/roll", methods=["POST"])
def dice_roll():
    player = [random.randint(1, 6), random.randint(1, 6)]
    cpu = [random.randint(1, 6), random.randint(1, 6)]
    player_eff = dice_effective(player)
    cpu_eff = dice_effective(cpu)
    record_score("dice", player_eff)
    if player_eff > cpu_eff:
        message = "🎉 あなたの勝ち！"
    elif player_eff < cpu_eff:
        message = "CPU の勝ち…"
    else:
        message = "引き分け"
    last = {
        "player_faces": " ".join(DICE_FACES[d - 1] for d in player),
        "cpu_faces": " ".join(DICE_FACES[d - 1] for d in cpu),
        "player_total": sum(player),
        "cpu_total": sum(cpu),
        "player_doubles": player[0] == player[1],
        "cpu_doubles": cpu[0] == cpu[1],
        "player_eff": player_eff,
        "cpu_eff": cpu_eff,
        "message": message,
    }
    return render_dice(last=last)

# gunicorn 等で起動した場合にも DB を用意する（作成済みなら何もしない）
init_db()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
