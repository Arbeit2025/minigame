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
import time
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
    {
        "slug": "coinflip",
        "title": "コイントス",
        "category": "抽選・占い",
        "icon": "🪙",
        "description": "コインの表か裏かを予想して投げるシンプルな運試し。連続で当てて連勝記録を伸ばそう。",
        "endpoint": "coinflip",
    },
    {
        "slug": "mathdrill",
        "title": "計算ドリル",
        "category": "脳トレ",
        "icon": "➗",
        "description": "四則演算を10問連続で解くドリル。全問正解までの速さを競います。割り算は割り切れる問題だけ。",
        "endpoint": "mathdrill",
    },
    {
        "slug": "memory",
        "title": "記憶力テスト",
        "category": "脳トレ",
        "icon": "🧠",
        "description": "表示された数字列を覚えて入力。正解するたびに桁数が増えていきます。何桁まで覚えられる？",
        "endpoint": "memory",
    },
    {
        "slug": "typing",
        "title": "タイピング",
        "category": "アクション",
        "icon": "⌨️",
        "description": "表示されたローマ字の単語5語を正確にタイプ。合計時間の速さを競います。",
        "endpoint": "typing",
    },
    {
        "slug": "stroop",
        "title": "ストループ",
        "category": "脳トレ",
        "icon": "🎨",
        "description": "色の名前を「文字の意味」ではなく「文字の色」で答える心理テスト系ゲーム。10問の正解数と速さを競います。",
        "endpoint": "stroop",
    },
    {
        "slug": "concentration",
        "title": "神経衰弱",
        "category": "脳トレ",
        "icon": "🂡",
        "description": "12枚の絵文字カードから6ペアを揃える定番ゲーム。少ない手数で揃えるほど良い記録です。",
        "endpoint": "concentration",
    },
    {
        "slug": "monty",
        "title": "モンティホール",
        "category": "脳トレ",
        "icon": "🚪",
        "description": "3つのドアの確率パズル。選んだ後にハズレが1つ開いたとき、変える？変えない？勝率の集計も表示します。",
        "endpoint": "monty",
    },
    {
        "slug": "quiz",
        "title": "クイズ",
        "category": "クイズ・知識",
        "icon": "❓",
        "description": "一般常識・雑学の4択クイズ10問。正解数を競います。問題は20問以上からランダム出題。",
        "endpoint": "quiz",
    },
    {
        "slug": "count",
        "title": "どっちが多い？",
        "category": "脳トレ",
        "icon": "🔍",
        "description": "左右に並んだ2種類の絵文字、多い方を当てるゲーム。連続正解を伸ばそう。",
        "endpoint": "count",
    },
    {
        "slug": "sort",
        "title": "数字並べ替え",
        "category": "アクション",
        "icon": "🔟",
        "description": "シャッフルされた1〜9の数字ボタンを小さい順にクリック。速さと正確さを競います。",
        "endpoint": "sort",
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
    input[type="text"] { padding: 9px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; }
    .colorword { font-size: 52px; text-align: center; font-weight: 700; margin: 12px 0; }
    .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .cards button { font-size: 30px; padding: 16px 0; }
    .cards button.matched { background: #f3fff3; border-color: #bfe8bf; cursor: default; }
    .emojis { font-size: 26px; line-height: 1.35; text-align: center; overflow-wrap: break-word; }
    .split { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .numgrid { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
    .numgrid button { width: 64px; height: 64px; font-size: 24px; }
    .numgrid button.done { background: #bfe8bf; border-color: #7ab87a; }
    .doors { display: flex; gap: 12px; justify-content: center; }
    .doors button { font-size: 40px; padding: 18px 22px; }
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

# ============================
# コイントス
# ============================
COIN_SIDES = ["表", "裏"]

COINFLIP_TEMPLATE = r"""
  <h1>🪙 コイントス</h1>
  <p class="howto">コインの表か裏かを予想して投げる運試し。連続で当てるほど連勝スコアが伸びます。</p>
  __FLASH__
  <div class="card">
    {% if last %}
      <div class="big">🪙 {{ last.result }}</div>
      <p class="result">{{ last.message }}</p>
    {% else %}
      <div class="big">🪙</div>
      <p class="mid">表か裏かを選んで投げよう</p>
    {% endif %}
    <p class="result">現在の連勝: {{ streak }} ／ ベスト: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('coinflip_flip') }}" class="row">
      <button type="submit" name="choice" value="表">表と予想して投げる</button>
      <button type="submit" name="choice" value="裏">裏と予想して投げる</button>
    </form>
  </div>
"""


def render_coinflip(last=None):
    body = render_template_string(
        COINFLIP_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        streak=int(session.get("cf_streak", 0)),
        best=best_score("coinflip", "max"),
        last=last,
    )
    return game_page("コイントス", body)


@app.route("/games/coinflip", methods=["GET"])
def coinflip():
    return render_coinflip()


@app.route("/games/coinflip/flip", methods=["POST"])
def coinflip_flip():
    choice = request.form.get("choice", "")
    if choice not in COIN_SIDES:
        flash("表か裏かを選んでください。", "ng")
        return render_coinflip()
    result = random.choice(COIN_SIDES)
    streak = int(session.get("cf_streak", 0))
    if result == choice:
        streak += 1
        record_score("coinflip", streak)
        message = f"🎉 正解！ {streak} 連勝中"
    else:
        streak = 0
        message = "はずれ… 連勝はリセットされました"
    session["cf_streak"] = streak
    return render_coinflip(last={"result": result, "message": message})


# ============================
# 計算ドリル
# ============================
MATHDRILL_TOTAL = 10


def make_math_question() -> tuple:
    op = random.choice(["+", "-", "×", "÷"])
    if op == "+":
        a, b = random.randint(11, 999), random.randint(11, 999)
        return f"{a} + {b}", a + b
    if op == "-":
        a = random.randint(11, 999)
        b = random.randint(11, a)
        return f"{a} - {b}", a - b
    if op == "×":
        a, b = random.randint(2, 12), random.randint(2, 12)
        return f"{a} × {b}", a * b
    divisor = random.randint(2, 12)
    quotient = random.randint(2, 12)
    return f"{divisor * quotient} ÷ {divisor}", quotient


def mathdrill_new_question() -> None:
    text, answer = make_math_question()
    session["md_text"] = text
    session["md_answer"] = answer


def render_mathdrill(message=None):
    if "md_text" not in session:
        session["md_num"] = 1
        session["md_correct"] = 0
        session["md_start"] = time.time()
        mathdrill_new_question()
    body = render_template_string(
        MATHDRILL_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        text=session["md_text"],
        num=int(session.get("md_num", 1)),
        total=MATHDRILL_TOTAL,
        correct=int(session.get("md_correct", 0)),
        best=best_score("mathdrill", "min"),
        history=recent_scores("mathdrill", 10),
        message=message,
    )
    return game_page("計算ドリル", body)


MATHDRILL_TEMPLATE = r"""
  <h1>➗ 計算ドリル</h1>
  <p class="howto">四則演算の問題を {{ total }} 問連続で解きます。全問正解すると、かかった秒数が記録されます（ベスト＝最速）。割り算は割り切れる問題だけです。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="mid">{{ num }} 問目 ／ {{ total }} 問（正解 {{ correct }}）</p>
    <div class="big">{{ text }} = ?</div>
    <form method="post" action="{{ url_for('mathdrill_answer') }}" class="row">
      <input type="number" name="answer" required placeholder="答え" />
      <button type="submit">答える</button>
    </form>
    <form method="post" action="{{ url_for('mathdrill_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    <p class="result">ベスト（最速・全問正解）: {{ best if best is not none else '—' }}{% if best is not none %} 秒{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（秒）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 秒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


@app.route("/games/mathdrill", methods=["GET"])
def mathdrill():
    return render_mathdrill()


@app.route("/games/mathdrill/answer", methods=["POST"])
def mathdrill_answer():
    if "md_text" not in session:
        return render_mathdrill()
    raw = request.form.get("answer", "").strip()
    answer = int(session["md_answer"])
    num = int(session.get("md_num", 1))
    correct = int(session.get("md_correct", 0))
    if raw.lstrip("-").isdigit() and int(raw) == answer:
        correct += 1
        feedback = "⭕ 正解！"
    else:
        feedback = f"❌ 不正解（正解は {answer}）"
    session["md_correct"] = correct
    if num >= MATHDRILL_TOTAL:
        elapsed = max(1, round(time.time() - float(session.get("md_start", time.time()))))
        if correct == MATHDRILL_TOTAL:
            record_score("mathdrill", elapsed)
            result = f"🎉 全{correct}問正解！ {elapsed} 秒で記録しました。新しいドリルが始まっています。"
        else:
            result = f"終了：{correct} / {MATHDRILL_TOTAL} 問正解（記録は全問正解時のみ）。新しいドリルが始まっています。"
        for key in ("md_text", "md_answer", "md_num", "md_correct", "md_start"):
            session.pop(key, None)
        return render_mathdrill(message=f"{feedback} {result}")
    session["md_num"] = num + 1
    mathdrill_new_question()
    return render_mathdrill(message=feedback)


@app.route("/games/mathdrill/reset", methods=["POST"])
def mathdrill_reset():
    for key in ("md_text", "md_answer", "md_num", "md_correct", "md_start"):
        session.pop(key, None)
    flash("最初からやり直します。", "ok")
    return redirect(url_for("mathdrill"))


# ============================
# 記憶力テスト
# ============================
MEMORY_START_LEVEL = 3
MEMORY_SHOW_MS = 3000


def memory_new_digits(level: int) -> str:
    return "".join(str(random.randint(0, 9)) for _ in range(level))


def render_memory(message=None):
    if "mem_digits" not in session:
        session["mem_level"] = MEMORY_START_LEVEL
        session["mem_digits"] = memory_new_digits(MEMORY_START_LEVEL)
    digits = str(session["mem_digits"])
    body = render_template_string(
        MEMORY_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        digits=digits,
        level=int(session.get("mem_level", MEMORY_START_LEVEL)),
        show_ms=MEMORY_SHOW_MS,
        best=best_score("memory", "max"),
        history=recent_scores("memory", 10),
        message=message,
    )
    return game_page("記憶力テスト", body)


MEMORY_TEMPLATE = r"""
  <h1>🧠 記憶力テスト</h1>
  <p class="howto">数字列が {{ show_ms // 1000 }} 秒だけ表示されて隠れます。覚えた数字を入力してください。正解すると桁数が1つ増え、失敗すると到達した桁数が記録されます。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="mid">いまは {{ level }} 桁</p>
    <div class="big" id="digits">{{ digits }}</div>
    <p class="mid muted" id="hint">覚えて…</p>
    <form method="post" action="{{ url_for('memory_answer') }}" class="row">
      <input type="text" name="answer" inputmode="numeric" autocomplete="off" required placeholder="覚えた数字" />
      <button type="submit">答える</button>
    </form>
    <form method="post" action="{{ url_for('memory_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    <p class="result">ベスト（最大到達桁数）: {{ best if best is not none else '—' }}{% if best is not none %} 桁{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（到達桁数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 桁</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var digits = document.getElementById("digits");
  var hint = document.getElementById("hint");
  var text = digits.textContent;
  setTimeout(function(){
    digits.textContent = "●".repeat(text.length);
    hint.textContent = "隠れました。覚えた数字を入力してね";
  }, {{ show_ms }});
})();
</script>
"""


@app.route("/games/memory", methods=["GET"])
def memory():
    return render_memory()


@app.route("/games/memory/answer", methods=["POST"])
def memory_answer():
    if "mem_digits" not in session:
        return render_memory()
    digits = str(session["mem_digits"])
    level = int(session.get("mem_level", MEMORY_START_LEVEL))
    guess = request.form.get("answer", "").strip()
    if guess == digits:
        session["mem_level"] = level + 1
        session["mem_digits"] = memory_new_digits(level + 1)
        return render_memory(message=f"⭕ 正解！ 次は {level + 1} 桁です。")
    record_score("memory", level)
    session.pop("mem_digits", None)
    session.pop("mem_level", None)
    return render_memory(
        message=f"❌ 残念、正解は {digits} でした。{level} 桁到達を記録しました。新しいテストが始まっています。"
    )


@app.route("/games/memory/reset", methods=["POST"])
def memory_reset():
    session.pop("mem_digits", None)
    session.pop("mem_level", None)
    flash("最初からやり直します。", "ok")
    return redirect(url_for("memory"))


# ============================
# タイピング
# ============================
TYPING_WORDS = [
    "sakura", "sushi", "tokyo", "ninja", "ramen",
    "osaka", "kyoto", "fuji", "manga", "anime",
    "sumo", "tatami", "katana", "onsen", "mochi", "wasabi",
]
TYPING_WORD_COUNT = 5

TYPING_TEMPLATE = r"""
  <h1>⌨️ タイピング</h1>
  <p class="howto">表示されるローマ字の単語 {{ count }} 語を、正確にタイピングしてください。最初の入力から最後の単語を打ち終えるまでの時間を記録します（ベスト＝最速）。</p>
  __FLASH__
  <div class="card">
    <p class="mid"><span id="progress">1 / {{ count }}</span> 語目</p>
    <div class="big" id="word"></div>
    <div class="row">
      <input type="text" id="typein" autocomplete="off" placeholder="ここに入力" style="width:260px; text-align:center;" />
    </div>
    <p class="result" id="message">ベスト（最速）: {{ best if best is not none else '—' }}{% if best is not none %} 秒{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ '%.1f' % (s.score / 1000) }} 秒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var words = {{ words|tojson }};
  var wordEl = document.getElementById("word");
  var input = document.getElementById("typein");
  var progress = document.getElementById("progress");
  var message = document.getElementById("message");
  var idx = 0, startedAt = 0;
  function show(){
    wordEl.textContent = words[idx];
    progress.textContent = (idx + 1) + " / " + words.length;
    input.value = "";
    input.focus();
  }
  input.addEventListener("input", function(){
    if (!startedAt) { startedAt = performance.now(); }
    var target = words[idx];
    var value = input.value;
    input.style.borderColor = target.indexOf(value) === 0 ? "#ccc" : "#d33";
    if (value === target) {
      idx += 1;
      if (idx < words.length) {
        show();
      } else {
        var ms = Math.round(performance.now() - startedAt);
        input.disabled = true;
        wordEl.textContent = "🎉 完了！";
        var form = new FormData();
        form.append("ms", String(ms));
        fetch("{{ url_for('typing_score') }}", {method: "POST", body: form})
          .then(function(r){ return r.json(); })
          .then(function(d){
            if (d && d.ok) {
              message.textContent = "記録: " + (ms / 1000).toFixed(1) + " 秒 ／ ベスト（最速）: " + (d.best / 1000).toFixed(1) + " 秒（読み込むともう一度遊べます）";
            }
          })
          .catch(function(){});
      }
    }
  });
  show();
})();
</script>
"""


@app.route("/games/typing", methods=["GET"])
def typing():
    words = random.sample(TYPING_WORDS, TYPING_WORD_COUNT)
    best_ms = best_score("typing", "min")
    body = render_template_string(
        TYPING_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        words=words,
        count=TYPING_WORD_COUNT,
        best=("%.1f" % (best_ms / 1000)) if best_ms is not None else None,
        history=recent_scores("typing", 10),
    )
    return game_page("タイピング", body)


@app.route("/games/typing/score", methods=["POST"])
def typing_score():
    raw = request.form.get("ms", "").strip()
    if not raw.isdigit() or not (500 <= int(raw) <= 600000):
        return {"ok": False, "error": "invalid ms"}, 400
    record_score("typing", int(raw))
    return {"ok": True, "best": best_score("typing", "min")}


# ============================
# ストループ
# ============================
STROOP_COLORS = [
    ("あか", "#d33"),
    ("あお", "#36c"),
    ("みどり", "#2a2"),
    ("きいろ", "#e6b800"),
    ("むらさき", "#93c"),
]
STROOP_TOTAL = 10
# スコアは「正解数 * 10^7 + (10^7 - 1 - 経過ミリ秒)」で1つの整数に符号化する。
# MAX を取ると、正解数が多いものを優先し、同点なら速い方（経過が小さい方）が残る。
STROOP_UNIT = 10 ** 7


def stroop_encode(correct: int, elapsed_ms: int) -> int:
    elapsed_ms = max(0, min(int(elapsed_ms), STROOP_UNIT - 2))
    return correct * STROOP_UNIT + (STROOP_UNIT - 1 - elapsed_ms)


def stroop_decode(score: int) -> tuple:
    correct = int(score) // STROOP_UNIT
    elapsed_ms = STROOP_UNIT - 1 - (int(score) % STROOP_UNIT)
    return correct, elapsed_ms


def stroop_new_questions() -> None:
    questions = []
    for _ in range(STROOP_TOTAL):
        word = random.randrange(len(STROOP_COLORS))
        ink = random.randrange(len(STROOP_COLORS))
        while ink == word:
            ink = random.randrange(len(STROOP_COLORS))
        questions.append([word, ink])
    session["st_questions"] = questions
    session["st_idx"] = 0
    session["st_correct"] = 0
    session["st_start"] = time.time()


def render_stroop(message=None):
    if "st_questions" not in session:
        stroop_new_questions()
    questions = session["st_questions"]
    idx = int(session.get("st_idx", 0))
    word_idx, ink_idx = questions[idx]
    best_raw = best_score("stroop", "max")
    best = None
    if best_raw is not None:
        c, ms = stroop_decode(best_raw)
        best = {"correct": c, "seconds": "%.1f" % (ms / 1000)}
    history = []
    for row in recent_scores("stroop", 10):
        c, ms = stroop_decode(int(row["score"]))
        history.append({"correct": c, "seconds": "%.1f" % (ms / 1000), "created_at": row["created_at"]})
    body = render_template_string(
        STROOP_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        word=STROOP_COLORS[word_idx][0],
        ink_color=STROOP_COLORS[ink_idx][1],
        colors=[name for name, _ in STROOP_COLORS],
        num=idx + 1,
        total=STROOP_TOTAL,
        correct=int(session.get("st_correct", 0)),
        best=best,
        history=history,
        message=message,
    )
    return game_page("ストループ", body)


STROOP_TEMPLATE = r"""
  <h1>🎨 ストループ</h1>
  <p class="howto">色の名前が書かれていますが、答えるのは「文字の意味」ではなく「文字の色」です。例：赤い字で「あお」と書かれていたら答えは「あか」。{{ total }} 問の正解数と速さを競います。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="mid">{{ num }} 問目 ／ {{ total }} 問（正解 {{ correct }}）</p>
    <div class="colorword" style="color: {{ ink_color }};">{{ word }}</div>
    <form method="post" action="{{ url_for('stroop_answer') }}" class="row">
      {% for name in colors %}
        <button type="submit" name="choice" value="{{ name }}">{{ name }}</button>
      {% endfor %}
    </form>
    <form method="post" action="{{ url_for('stroop_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    <p class="result">ベスト: {% if best %}{{ best.correct }} 問正解 ／ {{ best.seconds }} 秒{% else %}—{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.correct }} 問正解 ／ {{ s.seconds }} 秒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


@app.route("/games/stroop", methods=["GET"])
def stroop():
    return render_stroop()


@app.route("/games/stroop/answer", methods=["POST"])
def stroop_answer():
    if "st_questions" not in session:
        return render_stroop()
    questions = session["st_questions"]
    idx = int(session.get("st_idx", 0))
    ink_name = STROOP_COLORS[questions[idx][1]][0]
    choice = request.form.get("choice", "")
    correct = int(session.get("st_correct", 0))
    if choice == ink_name:
        correct += 1
        feedback = "⭕ 正解！"
    else:
        feedback = f"❌ 不正解（文字の色は「{ink_name}」）"
    session["st_correct"] = correct
    if idx + 1 >= STROOP_TOTAL:
        elapsed_ms = int((time.time() - float(session.get("st_start", time.time()))) * 1000)
        record_score("stroop", stroop_encode(correct, elapsed_ms))
        result = f"終了：{correct} / {STROOP_TOTAL} 問正解、{'%.1f' % (elapsed_ms / 1000)} 秒でした。新しい問題が始まっています。"
        for key in ("st_questions", "st_idx", "st_correct", "st_start"):
            session.pop(key, None)
        return render_stroop(message=f"{feedback} {result}")
    session["st_idx"] = idx + 1
    return render_stroop(message=feedback)


@app.route("/games/stroop/reset", methods=["POST"])
def stroop_reset():
    for key in ("st_questions", "st_idx", "st_correct", "st_start"):
        session.pop(key, None)
    flash("最初からやり直します。", "ok")
    return redirect(url_for("stroop"))


# ============================
# 神経衰弱
# ============================
CONCENTRATION_EMOJIS = ["🍎", "🍌", "🍇", "🍓", "🍊", "🍑"]


def concentration_new_game() -> None:
    cards = CONCENTRATION_EMOJIS * 2
    random.shuffle(cards)
    session["cc_cards"] = cards
    session["cc_matched"] = []
    session["cc_pending"] = None
    session["cc_mismatch"] = []
    session["cc_moves"] = 0


def render_concentration(message=None):
    if "cc_cards" not in session:
        concentration_new_game()
    cards = list(session["cc_cards"])
    matched = list(session.get("cc_matched", []))
    pending = session.get("cc_pending")
    mismatch = list(session.get("cc_mismatch", []))
    open_idx = set(matched) | set(mismatch)
    if pending is not None:
        open_idx.add(int(pending))
    body = render_template_string(
        CONCENTRATION_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        cards=cards,
        open_idx=open_idx,
        matched=set(matched),
        moves=int(session.get("cc_moves", 0)),
        pairs=len(matched) // 2,
        total_pairs=len(CONCENTRATION_EMOJIS),
        best=best_score("concentration", "min"),
        history=recent_scores("concentration", 10),
        message=message,
    )
    return game_page("神経衰弱", body)


CONCENTRATION_TEMPLATE = r"""
  <h1>🂡 神経衰弱</h1>
  <p class="howto">伏せられた12枚のカードから、同じ絵文字のペアを {{ total_pairs }} 組揃えるゲーム。2枚めくるごとに1手数です。間違えたペアは次の手を打つときに伏せられます。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">手数: {{ moves }} ／ 揃ったペア: {{ pairs }} ／ {{ total_pairs }} ／ ベスト（最小手数）: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('concentration_flip') }}">
      <div class="cards">
        {% for i in range(cards|length) %}
          {% if i in matched %}
            <button type="button" class="matched" disabled>{{ cards[i] }}</button>
          {% elif i in open_idx %}
            <button type="button" disabled>{{ cards[i] }}</button>
          {% else %}
            <button type="submit" name="index" value="{{ i }}">🂠</button>
          {% endif %}
        {% endfor %}
      </div>
    </form>
    <form method="post" action="{{ url_for('concentration_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">配り直す</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（手数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 手</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


@app.route("/games/concentration", methods=["GET"])
def concentration():
    return render_concentration()


@app.route("/games/concentration/flip", methods=["POST"])
def concentration_flip():
    if "cc_cards" not in session:
        concentration_new_game()
    cards = list(session["cc_cards"])
    matched = list(session.get("cc_matched", []))
    raw = request.form.get("index", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < len(cards)):
        return render_concentration()
    idx = int(raw)
    if idx in matched:
        return render_concentration()
    # 前回ミスマッチで開いたままの2枚は、この手で伏せてから処理する
    session["cc_mismatch"] = []
    pending = session.get("cc_pending")
    if pending is None:
        if idx in session.get("cc_mismatch", []):
            return render_concentration()
        session["cc_pending"] = idx
        return render_concentration()
    if int(pending) == idx:
        return render_concentration()
    moves = int(session.get("cc_moves", 0)) + 1
    session["cc_moves"] = moves
    first = int(pending)
    session["cc_pending"] = None
    if cards[first] == cards[idx]:
        matched.extend([first, idx])
        session["cc_matched"] = matched
        if len(matched) == len(cards):
            record_score("concentration", moves)
            concentration_new_game()
            return render_concentration(
                message=f"🎉 全部揃いました！ {moves} 手で記録しました。新しいゲームが配られています。"
            )
        return render_concentration(message=f"⭕ ペア成立！ {cards[idx]} が揃いました。")
    session["cc_mismatch"] = [first, idx]
    return render_concentration(message="❌ 違う絵文字でした。覚えて、次の手をどうぞ。")


@app.route("/games/concentration/reset", methods=["POST"])
def concentration_reset():
    concentration_new_game()
    flash("配り直しました。", "ok")
    return redirect(url_for("concentration"))


# ============================
# モンティホール
# ============================
MONTY_DOORS = 3


def monty_stats() -> dict:
    def get(key: str) -> int:
        raw = get_kv(key)
        return int(raw) if raw and raw.lstrip("-").isdigit() else 0

    stats = {}
    for label in ("switch", "stay"):
        games = get(f"monty_{label}_games")
        wins = get(f"monty_{label}_wins")
        stats[label] = {
            "games": games,
            "wins": wins,
            "rate": ("%.0f%%" % (wins * 100 / games)) if games else "—",
        }
    return stats


def render_monty(last=None):
    stage = "decide" if "mt_pick" in session else "pick"
    opened = session.get("mt_opened")
    pick = session.get("mt_pick")
    body = render_template_string(
        MONTY_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        stage=stage,
        pick=pick,
        opened=opened,
        stats=monty_stats(),
        last=last,
    )
    return game_page("モンティホール", body)


MONTY_TEMPLATE = r"""
  <h1>🚪 モンティホール</h1>
  <p class="howto">3つのドアのうち1つだけが当たりです。1つ選ぶと、司会がハズレのドアを1つ開けて見せます。そのあと「変える」か「変えない」か選んでください。変えた時と変えなかった時の勝率が下に集計されます。</p>
  __FLASH__
  <div class="card">
    {% if last %}
      <p class="result">{{ last.message }}</p>
    {% endif %}
    {% if stage == 'pick' %}
      <p class="mid">当たりだと思うドアを1つ選んでください</p>
      <form method="post" action="{{ url_for('monty_pick') }}" class="doors">
        {% for i in range(3) %}
          <button type="submit" name="door" value="{{ i }}">🚪</button>
        {% endfor %}
      </form>
    {% else %}
      <p class="mid">あなたが選んだのは {{ pick + 1 }} 番のドア。司会が {{ opened + 1 }} 番のドアを開けたら 🐐（ハズレ）でした。</p>
      <div class="doors">
        {% for i in range(3) %}
          <button type="button" disabled>{% if i == opened %}🐐{% elif i == pick %}👉🚪{% else %}🚪{% endif %}</button>
        {% endfor %}
      </div>
      <form method="post" action="{{ url_for('monty_decide') }}" class="row" style="margin-top:12px;">
        <button type="submit" name="choice" value="switch">もう一方に変える</button>
        <button type="submit" name="choice" value="stay">このまま変えない</button>
      </form>
    {% endif %}
    <h3 style="font-size:14px; margin:16px 0 8px;">これまでの集計（全プレイヤー共有）</h3>
    <table>
      <tr><th>戦略</th><th>回数</th><th>勝ち</th><th>勝率</th></tr>
      <tr><td>変えた</td><td>{{ stats.switch.games }}</td><td>{{ stats.switch.wins }}</td><td>{{ stats.switch.rate }}</td></tr>
      <tr><td>変えなかった</td><td>{{ stats.stay.games }}</td><td>{{ stats.stay.wins }}</td><td>{{ stats.stay.rate }}</td></tr>
    </table>
  </div>
"""


@app.route("/games/monty", methods=["GET"])
def monty():
    return render_monty()


@app.route("/games/monty/pick", methods=["POST"])
def monty_pick():
    raw = request.form.get("door", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < MONTY_DOORS):
        flash("ドアを選んでください。", "ng")
        return render_monty()
    pick = int(raw)
    prize = random.randrange(MONTY_DOORS)
    goats = [d for d in range(MONTY_DOORS) if d != pick and d != prize]
    session["mt_prize"] = prize
    session["mt_pick"] = pick
    session["mt_opened"] = random.choice(goats)
    return render_monty()


@app.route("/games/monty/decide", methods=["POST"])
def monty_decide():
    if "mt_pick" not in session or "mt_prize" not in session:
        return render_monty()
    choice = request.form.get("choice", "")
    if choice not in ("switch", "stay"):
        flash("「変える」か「変えない」かを選んでください。", "ng")
        return render_monty()
    pick = int(session["mt_pick"])
    opened = int(session["mt_opened"])
    prize = int(session["mt_prize"])
    final = next(d for d in range(MONTY_DOORS) if d != pick and d != opened) if choice == "switch" else pick
    win = final == prize
    games_key = f"monty_{choice}_games"
    wins_key = f"monty_{choice}_wins"
    raw_games = get_kv(games_key)
    set_kv(games_key, str((int(raw_games) if raw_games and raw_games.isdigit() else 0) + 1))
    if win:
        raw_wins = get_kv(wins_key)
        set_kv(wins_key, str((int(raw_wins) if raw_wins and raw_wins.isdigit() else 0) + 1))
    for key in ("mt_prize", "mt_pick", "mt_opened"):
        session.pop(key, None)
    if win:
        message = f"🎉 当たり！ 正解は {prize + 1} 番のドアでした（あなたは {final + 1} 番）。"
    else:
        message = f"ハズレ… 正解は {prize + 1} 番のドアでした（あなたは {final + 1} 番）。"
    return render_monty(last={"message": message})


# ============================
# クイズ
# ============================
QUIZ_BANK = [
    {"q": "日本の首都はどこ？", "choices": ["東京", "大阪", "京都", "名古屋"], "answer": 0},
    {"q": "水の化学式は？", "choices": ["CO2", "H2O", "O2", "NaCl"], "answer": 1},
    {"q": "地球に最も近い恒星は？", "choices": ["月", "火星", "太陽", "金星"], "answer": 2},
    {"q": "富士山の標高はおよそ何メートル？", "choices": ["2,776m", "3,776m", "4,776m", "5,776m"], "answer": 1},
    {"q": "平年の1年は何日？", "choices": ["360日", "364日", "365日", "366日"], "answer": 2},
    {"q": "日本で面積が一番大きい都道府県は？", "choices": ["青森県", "岩手県", "長野県", "北海道"], "answer": 3},
    {"q": "サッカーで1チームは何人でプレーする？", "choices": ["9人", "10人", "11人", "12人"], "answer": 2},
    {"q": "ピアノの鍵盤は全部でいくつ？", "choices": ["76", "84", "88", "96"], "answer": 2},
    {"q": "虹の色は一般に何色とされる？", "choices": ["5色", "6色", "7色", "8色"], "answer": 2},
    {"q": "日本の初代内閣総理大臣は？", "choices": ["伊藤博文", "大隈重信", "板垣退助", "西郷隆盛"], "answer": 0},
    {"q": "『走れメロス』の作者は？", "choices": ["夏目漱石", "太宰治", "芥川龍之介", "川端康成"], "answer": 1},
    {"q": "大人の歯は親知らずを含めて何本？", "choices": ["28本", "30本", "32本", "36本"], "answer": 2},
    {"q": "元素記号 Au が表す元素は？", "choices": ["銀", "金", "銅", "鉄"], "answer": 1},
    {"q": "日本で一番長い川は？", "choices": ["利根川", "石狩川", "信濃川", "吉野川"], "answer": 2},
    {"q": "光の速さはおよそ秒速何km？", "choices": ["3万km", "30万km", "300万km", "3,000万km"], "answer": 1},
    {"q": "オリンピック（夏季大会）は何年ごとに開かれる？", "choices": ["2年", "3年", "4年", "5年"], "answer": 2},
    {"q": "『モナ・リザ』を描いた画家は？", "choices": ["ゴッホ", "ピカソ", "モネ", "レオナルド・ダ・ヴィンチ"], "answer": 3},
    {"q": "1ダースは何個？", "choices": ["10個", "12個", "14個", "20個"], "answer": 1},
    {"q": "日本の国鳥は？", "choices": ["ツル", "キジ", "トキ", "ウグイス"], "answer": 1},
    {"q": "世界で一番長い川は？", "choices": ["アマゾン川", "ナイル川", "長江", "ミシシッピ川"], "answer": 1},
    {"q": "ゴッホの代表作として有名な花の絵は？", "choices": ["バラ", "ひまわり", "チューリップ", "睡蓮"], "answer": 1},
    {"q": "日本で一番人口の多い都道府県は？", "choices": ["大阪府", "神奈川県", "愛知県", "東京都"], "answer": 3},
]
QUIZ_TOTAL = 10


def quiz_prepare_current() -> None:
    items = session["qz_items"]
    idx = int(session.get("qz_idx", 0))
    question = QUIZ_BANK[int(items[idx])]
    order = list(range(len(question["choices"])))
    random.shuffle(order)
    session["qz_choices"] = [question["choices"][i] for i in order]
    session["qz_answer"] = order.index(int(question["answer"]))


def quiz_new_game() -> None:
    session["qz_items"] = random.sample(range(len(QUIZ_BANK)), QUIZ_TOTAL)
    session["qz_idx"] = 0
    session["qz_correct"] = 0
    quiz_prepare_current()


def render_quiz(message=None):
    if "qz_items" not in session:
        quiz_new_game()
    idx = int(session.get("qz_idx", 0))
    question = QUIZ_BANK[int(session["qz_items"][idx])]
    body = render_template_string(
        QUIZ_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        question=question["q"],
        choices=list(session.get("qz_choices", [])),
        num=idx + 1,
        total=QUIZ_TOTAL,
        correct=int(session.get("qz_correct", 0)),
        best=best_score("quiz", "max"),
        history=recent_scores("quiz", 10),
        message=message,
    )
    return game_page("クイズ", body)


QUIZ_TEMPLATE = r"""
  <h1>❓ クイズ</h1>
  <p class="howto">一般常識・雑学の4択クイズを {{ total }} 問出題します。正解数がスコアです。問題は {{ bank_size }} 問の中からランダムに選ばれます。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="mid">{{ num }} 問目 ／ {{ total }} 問（正解 {{ correct }}）</p>
    <p class="result">{{ question }}</p>
    <form method="post" action="{{ url_for('quiz_answer') }}" class="row" style="flex-direction:column; align-items:stretch;">
      {% for c in choices %}
        <button type="submit" name="choice" value="{{ loop.index0 }}">{{ c }}</button>
      {% endfor %}
    </form>
    <form method="post" action="{{ url_for('quiz_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    <p class="result">ベスト（最大正解数）: {{ best if best is not none else '—' }}{% if best is not none %} 問{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（正解数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 問</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
""".replace("{{ bank_size }}", str(len(QUIZ_BANK)))


@app.route("/games/quiz", methods=["GET"])
def quiz():
    return render_quiz()


@app.route("/games/quiz/answer", methods=["POST"])
def quiz_answer():
    if "qz_items" not in session:
        return render_quiz()
    raw = request.form.get("choice", "").strip()
    answer = int(session.get("qz_answer", -1))
    idx = int(session.get("qz_idx", 0))
    question = QUIZ_BANK[int(session["qz_items"][idx])]
    correct_text = str(session["qz_choices"][answer]) if 0 <= answer < len(session.get("qz_choices", [])) else ""
    correct = int(session.get("qz_correct", 0))
    if raw.isdigit() and int(raw) == answer:
        correct += 1
        feedback = "⭕ 正解！"
    else:
        feedback = f"❌ 不正解（正解は「{correct_text}」）"
    session["qz_correct"] = correct
    if idx + 1 >= QUIZ_TOTAL:
        record_score("quiz", correct)
        result = f"終了：{correct} / {QUIZ_TOTAL} 問正解でした。新しいクイズが始まっています。"
        for key in ("qz_items", "qz_idx", "qz_correct", "qz_choices", "qz_answer"):
            session.pop(key, None)
        return render_quiz(message=f"{feedback} {result}")
    session["qz_idx"] = idx + 1
    quiz_prepare_current()
    return render_quiz(message=feedback)


@app.route("/games/quiz/reset", methods=["POST"])
def quiz_reset():
    for key in ("qz_items", "qz_idx", "qz_correct", "qz_choices", "qz_answer"):
        session.pop(key, None)
    flash("最初からやり直します。", "ok")
    return redirect(url_for("quiz"))


# ============================
# どっちが多い？
# ============================
COUNT_EMOJIS = ["🍎", "🍌", "🍇", "🍓", "🍊", "🍑", "⭐", "❤️", "🍀"]


def count_new_round() -> None:
    left_emoji, right_emoji = random.sample(COUNT_EMOJIS, 2)
    left = random.randint(5, 25)
    right = random.randint(5, 25)
    while right == left:
        right = random.randint(5, 25)
    session["ct_left_emoji"] = left_emoji
    session["ct_right_emoji"] = right_emoji
    session["ct_left"] = left
    session["ct_right"] = right


def render_count(message=None):
    if "ct_left" not in session:
        count_new_round()
    body = render_template_string(
        COUNT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        left_emoji=session["ct_left_emoji"],
        right_emoji=session["ct_right_emoji"],
        left=int(session["ct_left"]),
        right=int(session["ct_right"]),
        streak=int(session.get("ct_streak", 0)),
        best=best_score("count", "max"),
        message=message,
    )
    return game_page("どっちが多い？", body)


COUNT_TEMPLATE = r"""
  <h1>🔍 どっちが多い？</h1>
  <p class="howto">左右に並んだ2種類の絵文字、数が多い方を当ててください。連続正解がスコアです。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <div class="split">
      <div class="emojis">{{ left_emoji * left }}</div>
      <div class="emojis">{{ right_emoji * right }}</div>
    </div>
    <form method="post" action="{{ url_for('count_answer') }}" class="row" style="margin-top:12px;">
      <button type="submit" name="side" value="left">左（{{ left_emoji }}）が多い</button>
      <button type="submit" name="side" value="right">右（{{ right_emoji }}）が多い</button>
    </form>
    <p class="result">現在の連勝: {{ streak }} ／ ベスト: {{ best if best is not none else '—' }}</p>
  </div>
"""


@app.route("/games/count", methods=["GET"])
def count():
    return render_count()


@app.route("/games/count/answer", methods=["POST"])
def count_answer():
    if "ct_left" not in session:
        count_new_round()
    left = int(session["ct_left"])
    right = int(session["ct_right"])
    side = request.form.get("side", "")
    answer = "left" if left > right else "right"
    streak = int(session.get("ct_streak", 0))
    detail = f"左は {left} 個、右は {right} 個でした。"
    if side == answer:
        streak += 1
        record_score("count", streak)
        message = f"⭕ 正解！ {detail} {streak} 連勝中"
    else:
        streak = 0
        message = f"❌ はずれ… {detail} 連勝はリセットされました"
    session["ct_streak"] = streak
    count_new_round()
    return render_count(message=message)


# ============================
# 数字並べ替え
# ============================
SORT_TEMPLATE = r"""
  <h1>🔟 数字並べ替え</h1>
  <p class="howto">シャッフルされた 1〜9 の数字ボタンを、小さい順にクリックしてください。間違えるとその場で教えてくれます。最初のクリックから全部押し終えるまでの時間を記録します（ベスト＝最速）。</p>
  __FLASH__
  <div class="card">
    <div class="numgrid" id="grid">
      {% for n in numbers %}
        <button type="button" data-value="{{ n }}">{{ n }}</button>
      {% endfor %}
    </div>
    <p class="result" id="message">次は 1 を押してね ／ ベスト（最速）: {{ best if best is not none else '—' }}{% if best is not none %} 秒{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ '%.1f' % (s.score / 1000) }} 秒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var message = document.getElementById("message");
  var expected = 1, startedAt = 0;
  var buttons = document.querySelectorAll("#grid button");
  buttons.forEach(function(btn){
    btn.addEventListener("click", function(){
      if (!startedAt) { startedAt = performance.now(); }
      var value = parseInt(btn.getAttribute("data-value"), 10);
      if (value !== expected) {
        message.textContent = "それは " + value + "。次は " + expected + " を押してね";
        return;
      }
      btn.disabled = true;
      btn.classList.add("done");
      expected += 1;
      if (expected > 9) {
        var ms = Math.round(performance.now() - startedAt);
        var form = new FormData();
        form.append("ms", String(ms));
        fetch("{{ url_for('sort_score') }}", {method: "POST", body: form})
          .then(function(r){ return r.json(); })
          .then(function(d){
            if (d && d.ok) {
              message.textContent = "🎉 完了！ " + (ms / 1000).toFixed(1) + " 秒 ／ ベスト（最速）: " + (d.best / 1000).toFixed(1) + " 秒（読み込むともう一度遊べます）";
            }
          })
          .catch(function(){});
      } else {
        message.textContent = "次は " + expected + " を押してね";
      }
    });
  });
})();
</script>
"""


@app.route("/games/sort", methods=["GET"])
def sort():
    numbers = list(range(1, 10))
    random.shuffle(numbers)
    best_ms = best_score("sort", "min")
    body = render_template_string(
        SORT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        numbers=numbers,
        best=("%.1f" % (best_ms / 1000)) if best_ms is not None else None,
        history=recent_scores("sort", 10),
    )
    return game_page("数字並べ替え", body)


@app.route("/games/sort/score", methods=["POST"])
def sort_score():
    raw = request.form.get("ms", "").strip()
    if not raw.isdigit() or not (300 <= int(raw) <= 600000):
        return {"ok": False, "error": "invalid ms"}, 400
    record_score("sort", int(raw))
    return {"ok": True, "best": best_score("sort", "min")}


# gunicorn 等で起動した場合にも DB を用意する（作成済みなら何もしない）
init_db()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
