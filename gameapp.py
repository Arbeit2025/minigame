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
from zoneinfo import ZoneInfo
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
    {
        "slug": "geoquiz",
        "title": "世界地理クイズ",
        "category": "クイズ・知識",
        "icon": "🌍",
        "description": "世界の国名・首都・国旗の3択クイズ10問。約45か国のデータからランダム出題。正解数を競います。",
        "endpoint": "geoquiz",
    },
    {
        "slug": "escape-cocoa",
        "title": "ココアの部屋からの脱出",
        "category": "脱出・謎解き",
        "icon": "🚪",
        "description": "ココアの部屋に閉じ込められた！ 机や本棚を調べて、ドアの鍵を見つける小さな脱出ゲーム。",
        "endpoint": "escape_cocoa",
    },
    {
        "slug": "escape-science",
        "title": "理科室からの脱出",
        "category": "脱出・謎解き",
        "icon": "🧪",
        "description": "理科室に閉じ込められた！ 黒板のヒントと実験道具をうまく使って脱出する小さな脱出ゲーム。",
        "endpoint": "escape_science",
    },
    {
        "slug": "escape-cafe",
        "title": "喫茶店の倉庫からの脱出",
        "category": "脱出・謎解き",
        "icon": "☕",
        "description": "喫茶店の倉庫に閉じ込められた！ 棚や缶を調べて、倉庫の鍵を探す小さな脱出ゲーム。",
        "endpoint": "escape_cafe",
    },
    {
        "slug": "hitblow",
        "title": "あいことば推理",
        "category": "脳トレ",
        "icon": "🕵️",
        "description": "重複のない4桁の数字を当てる推理ゲーム。ヒット（数字も場所も一致）とブロー（数字だけ一致）を手がかりに絞り込みます。",
        "endpoint": "hitblow",
    },
    {
        "slug": "shoefly",
        "title": "くつ飛ばし",
        "category": "アクション",
        "icon": "👟",
        "description": "往復するパワーゲージをタイミングよく止めて、くつを遠くへ飛ばすゲーム。飛距離（m）を競います。",
        "endpoint": "shoefly",
    },
    {
        "slug": "fishing",
        "title": "つりぼり図鑑",
        "category": "アクション",
        "icon": "🎣",
        "description": "ウキが沈む合図に素早く反応して魚を釣るゲーム。全12種の図鑑コンプリートを目指そう。反応が速いほどレアな魚に出会いやすい。",
        "endpoint": "fishing",
    },
    {
        "slug": "dodge",
        "title": "かわしサバイバー",
        "category": "アクション",
        "icon": "🏃",
        "description": "四方から迫る敵を避け続けるゲーム。時間が経つほど敵は増えて速くなります。生き残った秒数がスコアです。",
        "endpoint": "dodge",
    },
    {
        "slug": "snowball",
        "title": "ゆき玉転がし",
        "category": "アクション",
        "icon": "⛄",
        "description": "雪玉を左右に動かして岩を避けながら転がすゲーム。転がるほど玉は大きくなり、岩に当たると小さくなります。進んだ距離がスコアです。",
        "endpoint": "snowball",
    },
    {
        "slug": "zhgacha",
        "title": "中国語単語ガチャ",
        "category": "クイズ・知識",
        "icon": "🇨🇳",
        "description": "「ガチャを引く」と中国語の単語が1つランダムで出ます。簡体字・ピンイン・日本語訳・例文つき。全110語のコレクション完成を目指そう。",
        "endpoint": "zhgacha",
    },
    {
        "slug": "engacha",
        "title": "英単語ガチャ",
        "category": "クイズ・知識",
        "icon": "🇬🇧",
        "description": "中国語単語ガチャの英語版。「ガチャを引く」と英単語が1つランダムで出ます。カタカナ読み・日本語訳・例文つき。全110語のコレクション完成を目指そう。",
        "endpoint": "engacha",
    },
    {
        "slug": "eogacha",
        "title": "エスペラント単語ガチャ",
        "category": "クイズ・知識",
        "icon": "🌟",
        "description": "中国語単語ガチャのエスペラント版。「ガチャを引く」とエスペラントの単語が1つランダムで出ます。日本語訳・例文つき。全110語のコレクション完成を目指そう。",
        "endpoint": "eogacha",
    },
    {
        "slug": "shindan-trio",
        "title": "三人娘タイプ診断",
        "category": "抽選・占い",
        "icon": "☕",
        "description": "8つの質問に答えると、ココア・モカ・チャイの3人のうち、どのタイプに近いかを診断します。あなたの性格はどの娘タイプ？",
        "endpoint": "shindan_trio",
    },
    {
        "slug": "shindan-snack",
        "title": "今日のおやつ診断",
        "category": "抽選・占い",
        "icon": "🍮",
        "description": "気分や空腹度などを聞く6つの質問で、今日のおすすめおやつを診断します。ケーキ？ 和菓子？ それとも塩気？",
        "endpoint": "shindan_snack",
    },
    {
        "slug": "shindan-study",
        "title": "べんきょうタイプ診断",
        "category": "抽選・占い",
        "icon": "📚",
        "description": "勉強の進め方を聞く8つの質問で、あなたの学習タイプを診断します。タイプに合った小さな勉強のコツつき。",
        "endpoint": "shindan_study",
    },
    {
        "slug": "dotboard",
        "title": "ドット絵ボード",
        "category": "創作",
        "icon": "👾",
        "description": "単体ツール「dotboard」のポータル版。16×16のキャンバスにドット絵を描けます。お題ボタンで題材を引いて、「描けた！」で完成を記録。PNG保存もできます。",
        "endpoint": "dotboard",
    },
    {
        "slug": "slidepuzzle",
        "title": "スライドパズル",
        "category": "脳トレ",
        "icon": "🧩",
        "description": "3×3の数字パネルを空きマスへスライドさせて、1〜8の順に揃える定番パズル。初期配置は必ず解ける作りで、完成までの手数（少ないほど良い）を記録します。",
        "endpoint": "slidepuzzle",
    },
    {
        "slug": "touch25",
        "title": "1→25タッチ",
        "category": "アクション",
        "icon": "👆",
        "description": "5×5に散らばった1〜25の数字を、順番にタッチしていくタイムアタック。間違えた数字はその場で分かるので続行できます。全部押し終えるまでの速さを競います。",
        "endpoint": "touch25",
    },
    {
        "slug": "marubatsu",
        "title": "まるばつ対戦",
        "category": "対戦",
        "icon": "⭕",
        "description": "三目並べでCPUと対戦。あなたは○、CPUは×です。先手・後手が選べて、たまに本気を出さない程よい強さのCPU。勝利数を記録します。",
        "endpoint": "marubatsu",
    },
    {
        "slug": "shiritori",
        "title": "しりとり対戦",
        "category": "対戦",
        "icon": "🔤",
        "description": "内蔵の単語リスト（ひらがな）だけでCPUとしりとり対戦。「ん」で終わる単語を出した方が負け。続いた単語数を記録します。",
        "endpoint": "shiritori",
    },
    {
        "slug": "balloonpop",
        "title": "風船わり",
        "category": "アクション",
        "icon": "🎈",
        "description": "30秒間、画面に出てくる風船をタップ／クリックで割り続ける反射ゲーム。通常の風船は+1点、爆弾を割ると−3点。最終得点を記録します。",
        "endpoint": "balloonpop",
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
    .cats li button { background: none; border: 0; font: inherit; color: inherit; cursor: pointer; padding: 0; }
    .cats li.active { background: #222; border-color: #222; color: #fff; }
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
    <li class="active"><button type="button" data-filter="all">すべて（{{ games|length }}）</button></li>
    {% for name, count in categories %}
      <li><button type="button" data-filter="{{ name }}">{{ name }}（{{ count }}）</button></li>
    {% endfor %}
  </ul>
  <p class="muted">ジャンルを押すと、そのジャンルのゲームだけが下の一覧に表示されます。「すべて」を押すと全表示に戻ります。</p>

  <h2>ゲーム一覧</h2>
  <p class="muted" id="filterStatus">全 {{ games|length }} 本を表示中</p>
  <div class="grid">
    {% for game in games %}
      <div class="card" data-category="{{ game.category }}">
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
<script>
  (function () {
    var buttons = document.querySelectorAll('.cats button[data-filter]');
    var cards = document.querySelectorAll('.grid .card');
    var status = document.getElementById('filterStatus');
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var f = btn.getAttribute('data-filter');
        buttons.forEach(function (b) { b.parentElement.classList.toggle('active', b === btn); });
        var shown = 0;
        cards.forEach(function (card) {
          var ok = (f === 'all' || card.getAttribute('data-category') === f);
          card.style.display = ok ? '' : 'none';
          if (ok) shown++;
        });
        if (status) {
          status.textContent = (f === 'all')
            ? '全 ' + shown + ' 本を表示中'
            : '「' + f + '」のゲーム ' + shown + ' 本を表示中';
        }
      });
    });
  })();
</script>
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
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M:%S")


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
    .panel { border: 2px solid #bbb; border-radius: 12px; padding: 10px 8px 14px; background: #faf6ec; min-width: 0; }
    .panel.right { background: #eef5fa; border-color: #9db8cc; }
    .panel h3 { text-align: center; margin: 0 0 6px; font-size: 16px; }
    .numgrid { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
    .numgrid button { width: 64px; height: 64px; font-size: 24px; }
    .numgrid button.done { background: #bfe8bf; border-color: #7ab87a; }
    .doors { display: flex; gap: 12px; justify-content: center; }
    .doors button { font-size: 40px; padding: 18px 22px; }
    .doors button.labeled { font-size: 20px; }
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
      <p class="mid">あなたの予想は {{ last.choice }} でした</p>
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
    return render_coinflip(last={"result": result, "message": message, "choice": choice})


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
      <input type="text" id="answer-input" name="answer" inputmode="numeric" autocomplete="off" required placeholder="覚えた数字" disabled />
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
  var input = document.getElementById("answer-input");
  var text = digits.textContent;
  setTimeout(function(){
    digits.textContent = "●".repeat(text.length);
    hint.textContent = "隠れました。覚えた数字を入力してね";
    input.disabled = false;
    input.focus();
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
    <div class="row" id="again" style="display:none;">
      <button type="button" onclick="location.reload()">もう一度遊ぶ</button>
    </div>
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
              message.textContent = "記録: " + (ms / 1000).toFixed(1) + " 秒 ／ ベスト（最速）: " + (d.best / 1000).toFixed(1) + " 秒";
              document.getElementById("again").style.display = "flex";
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
          <button type="submit" name="door" value="{{ i }}" class="labeled">{{ i + 1 }}番のドア 🚪</button>
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
      <div class="panel left">
        <h3>左（{{ left_emoji }}）</h3>
        <div class="emojis">{{ left_emoji * left }}</div>
      </div>
      <div class="panel right">
        <h3>右（{{ right_emoji }}）</h3>
        <div class="emojis">{{ right_emoji * right }}</div>
      </div>
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
    <p class="result" id="bestline">ベスト（最速）: {{ best if best is not none else '—' }}{% if best is not none %} 秒{% endif %}</p>
    <p class="result" id="message">次は 1 を押してね</p>
    <div class="row" id="again" style="display:none;">
      <button type="button" onclick="location.reload()">もう一度遊ぶ</button>
    </div>
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
              message.textContent = "🎉 完了！ " + (ms / 1000).toFixed(1) + " 秒";
              document.getElementById("bestline").textContent = "ベスト（最速）: " + (d.best / 1000).toFixed(1) + " 秒";
              document.getElementById("again").style.display = "flex";
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


# ============================
# 世界地理クイズ
# ============================
GEO_BANK = [
    {"country": "日本", "capital": "東京", "flag": "🇯🇵"},
    {"country": "アメリカ", "capital": "ワシントン", "flag": "🇺🇸"},
    {"country": "イギリス", "capital": "ロンドン", "flag": "🇬🇧"},
    {"country": "フランス", "capital": "パリ", "flag": "🇫🇷"},
    {"country": "ドイツ", "capital": "ベルリン", "flag": "🇩🇪"},
    {"country": "イタリア", "capital": "ローマ", "flag": "🇮🇹"},
    {"country": "スペイン", "capital": "マドリード", "flag": "🇪🇸"},
    {"country": "ポルトガル", "capital": "リスボン", "flag": "🇵🇹"},
    {"country": "オランダ", "capital": "アムステルダム", "flag": "🇳🇱"},
    {"country": "ベルギー", "capital": "ブリュッセル", "flag": "🇧🇪"},
    {"country": "スイス", "capital": "ベルン", "flag": "🇨🇭"},
    {"country": "オーストリア", "capital": "ウィーン", "flag": "🇦🇹"},
    {"country": "スウェーデン", "capital": "ストックホルム", "flag": "🇸🇪"},
    {"country": "ノルウェー", "capital": "オスロ", "flag": "🇳🇴"},
    {"country": "デンマーク", "capital": "コペンハーゲン", "flag": "🇩🇰"},
    {"country": "フィンランド", "capital": "ヘルシンキ", "flag": "🇫🇮"},
    {"country": "ポーランド", "capital": "ワルシャワ", "flag": "🇵🇱"},
    {"country": "チェコ", "capital": "プラハ", "flag": "🇨🇿"},
    {"country": "ギリシャ", "capital": "アテネ", "flag": "🇬🇷"},
    {"country": "トルコ", "capital": "アンカラ", "flag": "🇹🇷"},
    {"country": "ロシア", "capital": "モスクワ", "flag": "🇷🇺"},
    {"country": "中国", "capital": "北京", "flag": "🇨🇳"},
    {"country": "韓国", "capital": "ソウル", "flag": "🇰🇷"},
    {"country": "インド", "capital": "ニューデリー", "flag": "🇮🇳"},
    {"country": "タイ", "capital": "バンコク", "flag": "🇹🇭"},
    {"country": "ベトナム", "capital": "ハノイ", "flag": "🇻🇳"},
    {"country": "インドネシア", "capital": "ジャカルタ", "flag": "🇮🇩"},
    {"country": "フィリピン", "capital": "マニラ", "flag": "🇵🇭"},
    {"country": "マレーシア", "capital": "クアラルンプール", "flag": "🇲🇾"},
    {"country": "シンガポール", "capital": "シンガポール", "flag": "🇸🇬"},
    {"country": "オーストラリア", "capital": "キャンベラ", "flag": "🇦🇺"},
    {"country": "ニュージーランド", "capital": "ウェリントン", "flag": "🇳🇿"},
    {"country": "カナダ", "capital": "オタワ", "flag": "🇨🇦"},
    {"country": "メキシコ", "capital": "メキシコシティ", "flag": "🇲🇽"},
    {"country": "ブラジル", "capital": "ブラジリア", "flag": "🇧🇷"},
    {"country": "アルゼンチン", "capital": "ブエノスアイレス", "flag": "🇦🇷"},
    {"country": "チリ", "capital": "サンティアゴ", "flag": "🇨🇱"},
    {"country": "ペルー", "capital": "リマ", "flag": "🇵🇪"},
    {"country": "エジプト", "capital": "カイロ", "flag": "🇪🇬"},
    {"country": "南アフリカ", "capital": "プレトリア", "flag": "🇿🇦"},
    {"country": "ケニア", "capital": "ナイロビ", "flag": "🇰🇪"},
    {"country": "モロッコ", "capital": "ラバト", "flag": "🇲🇦"},
    {"country": "アイスランド", "capital": "レイキャビク", "flag": "🇮🇸"},
    {"country": "アイルランド", "capital": "ダブリン", "flag": "🇮🇪"},
    {"country": "ハンガリー", "capital": "ブダペスト", "flag": "🇭🇺"},
    {"country": "ウクライナ", "capital": "キーウ", "flag": "🇺🇦"},
    {"country": "モンゴル", "capital": "ウランバートル", "flag": "🇲🇳"},
    {"country": "サウジアラビア", "capital": "リヤド", "flag": "🇸🇦"},
]
GEO_TOTAL = 10


def geoquiz_build_items() -> list:
    """出題10問を組み立てる（首都当て／国旗当て／首都から国当ての3形式、3択）。"""
    picks = random.sample(GEO_BANK, GEO_TOTAL)
    items = []
    for entry in picks:
        kind = random.choice(["capital", "flag", "country"])
        others = random.sample([c for c in GEO_BANK if c is not entry], 2)
        if kind == "capital":
            question = f"{entry['country']}の首都はどこ？"
            correct = entry["capital"]
            distract = [o["capital"] for o in others]
        elif kind == "flag":
            question = f"{entry['flag']} はどこの国の国旗？"
            correct = entry["country"]
            distract = [o["country"] for o in others]
        else:
            question = f"{entry['capital']}はどこの国の首都？"
            correct = entry["country"]
            distract = [o["country"] for o in others]
        choices = distract + [correct]
        random.shuffle(choices)
        items.append({"q": question, "choices": choices, "answer": choices.index(correct)})
    return items


def geoquiz_new_game() -> None:
    session["gq_items"] = geoquiz_build_items()
    session["gq_idx"] = 0
    session["gq_correct"] = 0


def render_geoquiz(message=None):
    if "gq_items" not in session:
        geoquiz_new_game()
    idx = int(session.get("gq_idx", 0))
    item = session["gq_items"][idx]
    body = render_template_string(
        GEOQUIZ_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        question=item["q"],
        choices=list(item["choices"]),
        num=idx + 1,
        total=GEO_TOTAL,
        correct=int(session.get("gq_correct", 0)),
        best=best_score("geoquiz", "max"),
        history=recent_scores("geoquiz", 10),
        message=message,
    )
    return game_page("世界地理クイズ", body)


GEOQUIZ_TEMPLATE = r"""
  <h1>🌍 世界地理クイズ</h1>
  <p class="howto">世界の国名・首都・国旗の3択クイズを {{ total }} 問出題します。正解数がスコアです。問題は {{ bank_size }} か国の中からランダムに選ばれます。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="mid">{{ num }} 問目 ／ {{ total }} 問（正解 {{ correct }}）</p>
    <p class="result">{{ question }}</p>
    <form method="post" action="{{ url_for('geoquiz_answer') }}" class="row" style="flex-direction:column; align-items:stretch;">
      {% for c in choices %}
        <button type="submit" name="choice" value="{{ loop.index0 }}">{{ c }}</button>
      {% endfor %}
    </form>
    <form method="post" action="{{ url_for('geoquiz_reset') }}" class="row" style="margin-top:10px;">
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
""".replace("{{ bank_size }}", str(len(GEO_BANK)))


@app.route("/games/geoquiz", methods=["GET"])
def geoquiz():
    return render_geoquiz()


@app.route("/games/geoquiz/answer", methods=["POST"])
def geoquiz_answer():
    if "gq_items" not in session:
        return render_geoquiz()
    raw = request.form.get("choice", "").strip()
    idx = int(session.get("gq_idx", 0))
    item = session["gq_items"][idx]
    answer = int(item["answer"])
    correct_text = str(item["choices"][answer]) if 0 <= answer < len(item["choices"]) else ""
    correct = int(session.get("gq_correct", 0))
    if raw.isdigit() and int(raw) == answer:
        correct += 1
        feedback = "⭕ 正解！"
    else:
        feedback = f"❌ 不正解（正解は「{correct_text}」）"
    session["gq_correct"] = correct
    if idx + 1 >= GEO_TOTAL:
        record_score("geoquiz", correct)
        result = f"終了：{correct} / {GEO_TOTAL} 問正解でした。新しいクイズが始まっています。"
        for key in ("gq_items", "gq_idx", "gq_correct"):
            session.pop(key, None)
        return render_geoquiz(message=f"{feedback} {result}")
    session["gq_idx"] = idx + 1
    return render_geoquiz(message=feedback)


@app.route("/games/geoquiz/reset", methods=["POST"])
def geoquiz_reset():
    for key in ("gq_items", "gq_idx", "gq_correct"):
        session.pop(key, None)
    flash("最初からやり直します。", "ok")
    return redirect(url_for("geoquiz"))


# ============================
# 脱出ゲーム（3部屋共通エンジン）
# 部屋はデータ定義だけで増やせる。spot の主なキー:
#   requires_item / requires_flag … 行動の前提（無い場合は text_fail）
#   gives_item / sets_flag        … 成功時の入手物・進行フラグ（完了判定にも使う）
#   text / text_again / text_fail … 初回成功時／完了後／前提不足時の文
# ドアは door_item を持っているときだけ開き、脱出成功で scores に 1 を記録する。
# ============================
ESCAPE_ROOMS = {
    "escape-cocoa": {
        "title": "ココアの部屋からの脱出",
        "icon": "🚪",
        "intro": "気づくとココアの部屋に閉じ込められていた！ 部屋の中を調べて、ドアの鍵を見つけよう。",
        "spots": [
            {
                "id": "desk", "label": "机の引き出しを調べる",
                "text": "紙きれが入っていた。『本棚の、緑色の本のうしろ』と書いてある。",
                "text_again": "机の引き出しはもう空っぽだ。",
                "sets_flag": "paper",
            },
            {
                "id": "shelf", "label": "本棚を調べる",
                "requires_flag": "paper",
                "text_fail": "本がぎっしり並んでいて、どこを見ればいいか分からない。",
                "text": "緑色の本のうしろに『小さな鍵』が隠してあった！",
                "text_again": "本棚にはもう何もない。",
                "gives_item": "小さな鍵",
            },
            {
                "id": "tin", "label": "紅茶缶を開ける",
                "requires_item": "小さな鍵",
                "text_fail": "紅茶缶には鍵がかかっていて開かない。",
                "text": "小さな鍵で紅茶缶を開けると、中に『ドアの鍵』が入っていた！",
                "text_again": "紅茶缶は空っぽだ。",
                "gives_item": "ドアの鍵",
            },
        ],
        "door_item": "ドアの鍵",
        "door_fail": "ドアは鍵がかかっている。",
        "clear_text": "ドアの鍵が開いた！ ココアの部屋から脱出成功！🎉",
    },
    "escape-science": {
        "title": "理科室からの脱出",
        "icon": "🧪",
        "intro": "理科室に閉じ込められてしまった。黒板のヒントと実験道具をうまく使って脱出しよう。",
        "spots": [
            {
                "id": "board", "label": "黒板を調べる",
                "text": "黒板に『鍵は水槽の底に沈んでいる。水を入れれば浮いてくる』とチョークで書いてある。",
                "text_again": "黒板には同じことが書いてある。",
                "sets_flag": "board",
            },
            {
                "id": "locker", "label": "ロッカーを調べる",
                "text": "ロッカーから『ビーカー』を見つけた！",
                "text_again": "ロッカーは空っぽだ。",
                "gives_item": "ビーカー",
            },
            {
                "id": "tap", "label": "水道で水を汲む",
                "requires_item": "ビーカー",
                "text_fail": "手では水を運べない。何か容器がいる。",
                "text": "ビーカーに水を汲んだ。",
                "text_again": "ビーカーにはもう水が入っている。",
                "gives_item": "水の入ったビーカー",
            },
            {
                "id": "tank", "label": "水槽を調べる",
                "requires_item": "水の入ったビーカー",
                "text_fail": "水槽は空っぽで、底に何かあるように見えるが手が届かない。",
                "text": "水槽に水を注ぐと、底に沈んでいた『理科室の鍵』が浮いてきた！",
                "text_again": "水槽にはもう何もない。",
                "gives_item": "理科室の鍵",
            },
        ],
        "door_item": "理科室の鍵",
        "door_fail": "ドアは鍵がかかっている。",
        "clear_text": "理科室の鍵が開いた！ 理科室から脱出成功！🎉",
    },
    "escape-cafe": {
        "title": "喫茶店の倉庫からの脱出",
        "icon": "☕",
        "intro": "喫茶店の倉庫に閉じ込められてしまった。棚や缶を調べて、倉庫の鍵を探そう。",
        "spots": [
            {
                "id": "shelf", "label": "棚を調べる",
                "text": "棚の奥から『脚立』を見つけた！",
                "text_again": "棚にはもう何もない。",
                "gives_item": "脚立",
            },
            {
                "id": "high", "label": "高い棚の缶を取る",
                "requires_item": "脚立",
                "text_fail": "高い棚の缶には手が届かない。",
                "text": "脚立に登って『クッキー缶』を取った！",
                "text_again": "高い棚にはもう何もない。",
                "gives_item": "クッキー缶",
            },
            {
                "id": "tin", "label": "クッキー缶を開ける",
                "requires_item": "クッキー缶",
                "text_fail": "クッキー缶を持っていない。",
                "text": "缶の中にメモが入っていた。『倉庫の鍵は冷蔵庫の横』と書いてある。",
                "text_again": "メモには『倉庫の鍵は冷蔵庫の横』と書いてある。",
                "sets_flag": "fridge_hint",
            },
            {
                "id": "fridge", "label": "冷蔵庫の横を調べる",
                "requires_flag": "fridge_hint",
                "text_fail": "冷蔵庫の横には何もなさそうだ。",
                "text": "冷蔵庫の横の隙間に『倉庫の鍵』が落ちていた！",
                "text_again": "冷蔵庫の横にはもう何もない。",
                "gives_item": "倉庫の鍵",
            },
        ],
        "door_item": "倉庫の鍵",
        "door_fail": "ドアは鍵がかかっている。",
        "clear_text": "倉庫の鍵が開いた！ 喫茶店の倉庫から脱出成功！🎉",
    },
}


def escape_load(key: str):
    return (
        list(session.get(f"esc_{key}_items", [])),
        list(session.get(f"esc_{key}_flags", [])),
        bool(session.get(f"esc_{key}_done", False)),
    )


def escape_save(key: str, items, flags, done) -> None:
    session[f"esc_{key}_items"] = items
    session[f"esc_{key}_flags"] = flags
    session[f"esc_{key}_done"] = done


def escape_do_action(key: str, action_id: str) -> str:
    """行動を1つ進め、結果メッセージを返す。"""
    room = ESCAPE_ROOMS[key]
    items, flags, done = escape_load(key)
    if done:
        return "もう脱出済みです。もう一度遊ぶときはリセットしてください。"
    if action_id == "door":
        if room["door_item"] in items:
            escape_save(key, items, flags, True)
            record_score(key, 1)
            return room["clear_text"]
        return room["door_fail"]
    spot = next((s for s in room["spots"] if s["id"] == action_id), None)
    if spot is None:
        return "そこには何もない。"
    completed = False
    if spot.get("sets_flag"):
        completed = spot["sets_flag"] in flags
    elif spot.get("gives_item"):
        completed = spot["gives_item"] in items
    if completed:
        return spot["text_again"]
    if spot.get("requires_item") and spot["requires_item"] not in items:
        return spot["text_fail"]
    if spot.get("requires_flag") and spot["requires_flag"] not in flags:
        return spot["text_fail"]
    if spot.get("gives_item") and spot["gives_item"] not in items:
        items.append(spot["gives_item"])
    if spot.get("sets_flag") and spot["sets_flag"] not in flags:
        flags.append(spot["sets_flag"])
    escape_save(key, items, flags, done)
    return spot["text"]


ESCAPE_TEMPLATE = r"""
  <h1>{{ icon }} {{ title }}</h1>
  <p class="howto">{{ intro }} 気になるところを調べてアイテムを集め、鍵を見つけてドアを開けよう。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    {% if done %}
      <p class="big">🎉 脱出成功！</p>
    {% endif %}
    <p class="mid">持ち物：{{ items|join('、') if items else 'なし' }}</p>
    <form method="post" action="{{ act_url }}" class="row" style="flex-direction:column; align-items:stretch;">
      {% for spot in spots %}
        <button type="submit" name="action" value="{{ spot.id }}">{{ spot.label }}</button>
      {% endfor %}
      <button type="submit" name="action" value="door">🚪 ドアを開ける</button>
    </form>
    <form method="post" action="{{ reset_url }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    <p class="result">脱出成功の記録: {{ clears }} 回</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の脱出記録</h3>
      <table>
        {% for s in history %}
          <tr><td>🎉 脱出成功</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_escape(key: str, endpoint: str, message=None):
    room = ESCAPE_ROOMS[key]
    items, flags, done = escape_load(key)
    history = recent_scores(key, 10)
    body = render_template_string(
        ESCAPE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        icon=room["icon"],
        title=room["title"],
        intro=room["intro"],
        spots=room["spots"],
        items=items,
        done=done,
        clears=len(recent_scores(key, 1000)),
        history=history,
        message=message,
        act_url=url_for(f"{endpoint}_act"),
        reset_url=url_for(f"{endpoint}_reset"),
    )
    return game_page(room["title"], body)


def escape_reset_session(key: str) -> None:
    for suffix in ("items", "flags", "done"):
        session.pop(f"esc_{key}_{suffix}", None)


@app.route("/games/escape-cocoa", methods=["GET"])
def escape_cocoa():
    return render_escape("escape-cocoa", "escape_cocoa")


@app.route("/games/escape-cocoa/act", methods=["POST"])
def escape_cocoa_act():
    message = escape_do_action("escape-cocoa", request.form.get("action", "").strip())
    return render_escape("escape-cocoa", "escape_cocoa", message=message)


@app.route("/games/escape-cocoa/reset", methods=["POST"])
def escape_cocoa_reset():
    escape_reset_session("escape-cocoa")
    flash("最初からやり直します。", "ok")
    return redirect(url_for("escape_cocoa"))


@app.route("/games/escape-science", methods=["GET"])
def escape_science():
    return render_escape("escape-science", "escape_science")


@app.route("/games/escape-science/act", methods=["POST"])
def escape_science_act():
    message = escape_do_action("escape-science", request.form.get("action", "").strip())
    return render_escape("escape-science", "escape_science", message=message)


@app.route("/games/escape-science/reset", methods=["POST"])
def escape_science_reset():
    escape_reset_session("escape-science")
    flash("最初からやり直します。", "ok")
    return redirect(url_for("escape_science"))


@app.route("/games/escape-cafe", methods=["GET"])
def escape_cafe():
    return render_escape("escape-cafe", "escape_cafe")


@app.route("/games/escape-cafe/act", methods=["POST"])
def escape_cafe_act():
    message = escape_do_action("escape-cafe", request.form.get("action", "").strip())
    return render_escape("escape-cafe", "escape_cafe", message=message)


@app.route("/games/escape-cafe/reset", methods=["POST"])
def escape_cafe_reset():
    escape_reset_session("escape-cafe")
    flash("最初からやり直します。", "ok")
    return redirect(url_for("escape_cafe"))



# ============================
# あいことば推理（ヒット＆ブロー）
# ============================
def hitblow_new_secret() -> str:
    """重複のない4桁の数字（先頭は0にしない）を返す。"""
    first = random.choice("123456789")
    rest = random.sample([d for d in "0123456789" if d != first], 3)
    return first + "".join(rest)


def hitblow_judge(secret: str, guess: str) -> tuple:
    """(ヒット数, ブロー数) を返す。秘密・予想とも重複なしが前提。"""
    hit = sum(1 for a, b in zip(secret, guess) if a == b)
    blow = sum(1 for d in guess if d in secret) - hit
    return hit, blow


HITBLOW_TEMPLATE = r"""
  <h1>🕵️ あいことば推理</h1>
  <p class="howto">重複のない4桁の数字を当てる推理ゲーム。予想するたびに「ヒット」（数字も場所も一致）と「ブロー」（数字だけ一致）の数が分かります。少ない回数で当てるほど良い記録です。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">予想回数: {{ tries }} ／ ベスト（最少回数）: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('hitblow_guess') }}" class="row">
      <input type="text" name="guess" inputmode="numeric" maxlength="4" required placeholder="4桁の数字" style="width:140px;" />
      <button type="submit">推理する</button>
    </form>
    <form method="post" action="{{ url_for('hitblow_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">答えを変えて最初から</button>
    </form>
    {% if guesses %}
      <h3 style="font-size:14px; margin:16px 0 8px;">これまでの推理</h3>
      <table>
        <tr><th>予想</th><th>ヒット</th><th>ブロー</th></tr>
        {% for g in guesses %}
          <tr><td>{{ g[0] }}</td><td>{{ g[1] }}</td><td>{{ g[2] }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（当てるまでの回数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 回</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_hitblow(message=None):
    if "hb_secret" not in session:
        session["hb_secret"] = hitblow_new_secret()
        session["hb_guesses"] = []
    guesses = session.get("hb_guesses", [])
    body = render_template_string(
        HITBLOW_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        tries=len(guesses),
        guesses=guesses,
        best=best_score("hitblow", "min"),
        history=recent_scores("hitblow", 10),
        message=message,
    )
    return game_page("あいことば推理", body)


@app.route("/games/hitblow", methods=["GET"])
def hitblow():
    return render_hitblow()


@app.route("/games/hitblow/guess", methods=["POST"])
def hitblow_guess():
    if "hb_secret" not in session:
        session["hb_secret"] = hitblow_new_secret()
        session["hb_guesses"] = []
    raw = request.form.get("guess", "").strip()
    if len(raw) != 4 or not raw.isdigit() or len(set(raw)) != 4:
        flash("重複のない4桁の数字を入力してください。", "ng")
        return render_hitblow()
    secret = str(session["hb_secret"])
    hit, blow = hitblow_judge(secret, raw)
    guesses = list(session.get("hb_guesses", []))
    guesses.append([raw, hit, blow])
    session["hb_guesses"] = guesses
    tries = len(guesses)
    if hit == 4:
        record_score("hitblow", tries)
        session.pop("hb_secret", None)
        session.pop("hb_guesses", None)
        return render_hitblow(message=f"🎉 正解！ 答えは {secret} でした（{tries} 回で的中）。新しいゲームが始まっています。")
    return render_hitblow(message=f"{raw} … {hit} ヒット / {blow} ブロー")


@app.route("/games/hitblow/reset", methods=["POST"])
def hitblow_reset():
    session.pop("hb_secret", None)
    session.pop("hb_guesses", None)
    flash("答えを変えました。", "ok")
    return redirect(url_for("hitblow"))


# ============================
# くつ飛ばし
# ============================
SHOEFLY_TEMPLATE = r"""
  <h1>👟 くつ飛ばし</h1>
  <p class="howto">パワーゲージが左右に往復します。「飛ばす！」を押した瞬間のパワーで飛距離が決まります。パワーが大きいほど遠くへ飛びます。</p>
  __FLASH__
  <div class="card">
    <div style="border:1px solid #ccc; border-radius:8px; height:26px; overflow:hidden; background:#fafafa;">
      <div id="gauge" style="height:100%; width:0%; background:#7ab87a;"></div>
    </div>
    <p class="mid">パワー: <span id="powerLabel">0</span></p>
    <div class="row">
      <button id="throwBtn" type="button">飛ばす！</button>
      <button id="againBtn" type="button" disabled>もう一度</button>
    </div>
    <p class="result" id="message">ベスト（最長飛距離）: {{ best_disp if best_disp is not none else '—' }}{% if best_disp is not none %} m{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（飛距離）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ (s.score / 10)|round(1) }} m</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var gauge = document.getElementById("gauge");
  var powerLabel = document.getElementById("powerLabel");
  var message = document.getElementById("message");
  var throwBtn = document.getElementById("throwBtn");
  var againBtn = document.getElementById("againBtn");
  var running = true, startedAt = performance.now();
  function currentPower(){
    var phase = ((performance.now() - startedAt) % 1400) / 1400;
    var p = phase < 0.5 ? phase * 200 : 200 - phase * 200;
    return Math.round(p);
  }
  function tick(){
    if (!running) { return; }
    var p = currentPower();
    gauge.style.width = p + "%";
    gauge.style.background = p >= 80 ? "#e8a13a" : "#7ab87a";
    powerLabel.textContent = String(p);
    requestAnimationFrame(tick);
  }
  tick();
  function throwShoe(){
    if (!running) { return; }
    running = false;
    var p = currentPower();
    gauge.style.width = p + "%";
    powerLabel.textContent = String(p);
    var dist = Math.round(((p * p) / 100 * 0.42 + p * 0.08) * 10) / 10;
    throwBtn.disabled = true;
    againBtn.disabled = false;
    message.textContent = "飛距離: " + dist.toFixed(1) + " m！";
    var form = new FormData();
    form.append("dist10", String(Math.round(dist * 10)));
    fetch("{{ url_for('shoefly_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "飛距離: " + dist.toFixed(1) + " m！／ベスト（最長飛距離）: " + (d.best / 10).toFixed(1) + " m";
        }
      })
      .catch(function(){});
  }
  throwBtn.addEventListener("click", throwShoe);
  againBtn.addEventListener("click", function(){
    running = true;
    startedAt = performance.now();
    throwBtn.disabled = false;
    againBtn.disabled = true;
    message.textContent = "ゲージが動いています。「飛ばす！」で止めてね";
    tick();
  });
})();
</script>
"""


@app.route("/games/shoefly", methods=["GET"])
def shoefly():
    best = best_score("shoefly", "max")
    body = render_template_string(
        SHOEFLY_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best_disp=(round(best / 10, 1) if best is not None else None),
        history=recent_scores("shoefly", 10),
    )
    return game_page("くつ飛ばし", body)


@app.route("/games/shoefly/score", methods=["POST"])
def shoefly_score():
    raw = request.form.get("dist10", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 600):
        return {"ok": False, "error": "invalid dist10"}, 400
    record_score("shoefly", int(raw))
    return {"ok": True, "best": best_score("shoefly", "max")}



# ============================
# つりぼり図鑑
# ============================
FISH_KINDS = [
    {"name": "フナ", "emoji": "🐟", "rarity": "ふつう", "points": 10, "weight": 30},
    {"name": "オイカワ", "emoji": "🐟", "rarity": "ふつう", "points": 10, "weight": 30},
    {"name": "ブルーギル", "emoji": "🐠", "rarity": "ふつう", "points": 10, "weight": 30},
    {"name": "タナゴ", "emoji": "🐠", "rarity": "ふつう", "points": 15, "weight": 26},
    {"name": "ブラックバス", "emoji": "🐟", "rarity": "めずらしい", "points": 30, "weight": 12},
    {"name": "ナマズ", "emoji": "🐟", "rarity": "めずらしい", "points": 30, "weight": 12},
    {"name": "ウナギ", "emoji": "🐟", "rarity": "めずらしい", "points": 40, "weight": 10},
    {"name": "ニジマス", "emoji": "🐟", "rarity": "レア", "points": 80, "weight": 4},
    {"name": "イトウ", "emoji": "🐟", "rarity": "レア", "points": 100, "weight": 3},
    {"name": "キンコイ", "emoji": "🎏", "rarity": "レア", "points": 120, "weight": 3},
    {"name": "リュウグウノツカイ", "emoji": "🐉", "rarity": "超レア", "points": 200, "weight": 1},
    {"name": "シーラカンス", "emoji": "🦕", "rarity": "超レア", "points": 300, "weight": 1},
]
FISH_ESCAPE_MS = 1200


def fishing_pick(ms: int) -> int:
    """反応が速いほどレアな魚の重みを上げる抽選。魚のインデックスを返す。"""
    if ms <= 300:
        bonus = 3.0
    elif ms <= 600:
        bonus = 1.8
    else:
        bonus = 1.0
    weights = []
    for fish in FISH_KINDS:
        w = float(fish["weight"])
        if fish["rarity"] in ("レア", "超レア"):
            w *= bonus
        weights.append(w)
    return random.choices(range(len(FISH_KINDS)), weights=weights)[0]


FISHING_TEMPLATE = r"""
  <h1>🎣 つりぼり図鑑</h1>
  <p class="howto">「つりをする」を押して待ち、ウキが沈んだら（画面の色が変わったら）すぐに「釣り上げる」を押そう。反応が速いほどレアな魚が釣れやすく、遅いと逃げられます。全 {{ total }} 種の図鑑コンプリートを目指そう。</p>
  __FLASH__
  <div class="card">
    <div id="stage" style="border-radius:12px; padding:40px 12px; text-align:center; font-size:22px; background:#eef5fa; user-select:none;">🎣 準備OK</div>
    <div class="row" style="margin-top:12px;">
      <button id="castBtn" type="button">つりをする</button>
      <button id="reelBtn" type="button" disabled>釣り上げる</button>
    </div>
    <p class="result" id="message">ベスト（最高ポイントの魚）: {{ best if best is not none else '—' }}{% if best is not none %} 点{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近釣った魚（ポイント）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
  <div class="card">
    <h3 style="margin:0 0 8px;">📖 図鑑（<span id="kindCount">{{ kinds }}</span> / {{ total }} 種）</h3>
    <table>
      {% for f in fish_list %}
        <tr>
          <td>{% if f.caught %}{{ f.emoji }} {{ f.name }}{% else %}❓ ？？？{% endif %}</td>
          <td class="muted">{{ f.rarity }}</td>
          <td class="muted">{% if f.caught %}{{ f.points }} 点{% endif %}</td>
        </tr>
      {% endfor %}
    </table>
    <form method="post" action="{{ url_for('fishing_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">図鑑をリセット</button>
    </form>
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var message = document.getElementById("message");
  var castBtn = document.getElementById("castBtn");
  var reelBtn = document.getElementById("reelBtn");
  var kindCount = document.getElementById("kindCount");
  var state = "idle"; // idle | waiting | signal
  var waitTimer = null, escapeTimer = null, signalAt = 0;
  function setStage(bg, text){ stage.style.background = bg; stage.textContent = text; }
  function sendCast(ms){
    var form = new FormData();
    form.append("ms", String(ms));
    fetch("{{ url_for('fishing_cast') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        state = "idle";
        castBtn.disabled = false;
        reelBtn.disabled = true;
        if (d && d.ok && d.caught) {
          setStage("#f3fff3", d.emoji + " " + d.name + " が釣れた！");
          message.textContent = d.name + "（" + d.rarity + "／" + d.points + " 点）" + (d.is_new ? " 図鑑に新登録！" : "") + " ／ ベスト: " + d.best + " 点";
          kindCount.textContent = String(d.kinds);
        } else if (d && d.ok) {
          setStage("#eef5fa", "💨 逃げられた…");
          message.textContent = "逃げられてしまった。もう一度挑戦しよう";
        } else {
          setStage("#eef5fa", "🎣 準備OK");
        }
      })
      .catch(function(){
        state = "idle";
        castBtn.disabled = false;
        reelBtn.disabled = true;
      });
  }
  castBtn.addEventListener("click", function(){
    if (state !== "idle") { return; }
    state = "waiting";
    castBtn.disabled = true;
    reelBtn.disabled = false;
    setStage("#eef5fa", "🎣 ウキを見ていて…");
    waitTimer = setTimeout(function(){
      state = "signal";
      signalAt = performance.now();
      setStage("#ffe9a8", "‼️ ウキが沈んだ！今だ！");
      escapeTimer = setTimeout(function(){
        if (state === "signal") { sendCast(9999); }
      }, {{ escape_ms }});
    }, 1500 + Math.random() * 3000);
  });
  reelBtn.addEventListener("click", function(){
    if (state === "waiting") {
      clearTimeout(waitTimer);
      state = "idle";
      castBtn.disabled = false;
      reelBtn.disabled = true;
      setStage("#fff3f3", "まだだよ！ウキが沈んでから押してね");
    } else if (state === "signal") {
      clearTimeout(escapeTimer);
      var ms = Math.round(performance.now() - signalAt);
      sendCast(ms);
    }
  });
})();
</script>
""".replace("{{ escape_ms }}", str(FISH_ESCAPE_MS))


def render_fishing():
    caught = session.get("fish_caught", [])
    fish_list = [
        {**fish, "caught": i in caught} for i, fish in enumerate(FISH_KINDS)
    ]
    body = render_template_string(
        FISHING_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        total=len(FISH_KINDS),
        kinds=len(caught),
        fish_list=fish_list,
        best=best_score("fishing", "max"),
        history=recent_scores("fishing", 10),
    )
    return game_page("つりぼり図鑑", body)


@app.route("/games/fishing", methods=["GET"])
def fishing():
    return render_fishing()


@app.route("/games/fishing/cast", methods=["POST"])
def fishing_cast():
    raw = request.form.get("ms", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 10000):
        return {"ok": False, "error": "invalid ms"}, 400
    ms = int(raw)
    if ms > FISH_ESCAPE_MS:
        return {"ok": True, "caught": False}
    idx = fishing_pick(ms)
    fish = FISH_KINDS[idx]
    caught = list(session.get("fish_caught", []))
    is_new = idx not in caught
    if is_new:
        caught.append(idx)
        session["fish_caught"] = caught
    record_score("fishing", int(fish["points"]))
    return {
        "ok": True,
        "caught": True,
        "name": fish["name"],
        "emoji": fish["emoji"],
        "rarity": fish["rarity"],
        "points": int(fish["points"]),
        "is_new": is_new,
        "kinds": len(caught),
        "total": len(FISH_KINDS),
        "best": best_score("fishing", "max"),
    }


@app.route("/games/fishing/reset", methods=["POST"])
def fishing_reset():
    session.pop("fish_caught", None)
    flash("図鑑をリセットしました。", "ok")
    return redirect(url_for("fishing"))



# ============================
# かわしサバイバー
# ============================
DODGE_TEMPLATE = r"""
  <h1>🏃 かわしサバイバー</h1>
  <p class="howto">青い丸（自分）をマウス／タッチ／矢印キーで動かし、四方から迫る赤い四角を避け続けよう。時間が経つほど敵は増えて速くなります。ぶつかるまでの秒数がスコアです。</p>
  __FLASH__
  <div class="card">
    <canvas id="cv" width="480" height="360" style="width:100%; max-width:480px; display:block; margin:0 auto; background:#222; border-radius:12px; touch-action:none;"></canvas>
    <p class="mid">経過: <span id="clock">0.0</span> 秒</p>
    <div class="row">
      <button id="startBtn" type="button">スタート</button>
    </div>
    <p class="result" id="message">ベスト（最長生存）: {{ best_disp if best_disp is not none else '—' }}{% if best_disp is not none %} 秒{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（生存秒数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ (s.score / 10)|round(1) }} 秒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var cv = document.getElementById("cv");
  var ctx = cv.getContext("2d");
  var clock = document.getElementById("clock");
  var message = document.getElementById("message");
  var startBtn = document.getElementById("startBtn");
  var W = cv.width, H = cv.height;
  var playing = false, raf = null, startedAt = 0, lastSpawn = 0;
  var player = {x: W / 2, y: H / 2, r: 12};
  var target = null, keys = {}, enemies = [];
  function spawnEnemy(t){
    var side = Math.floor(Math.random() * 4);
    var x = 0, y = 0;
    if (side === 0) { x = Math.random() * W; y = -16; }
    else if (side === 1) { x = Math.random() * W; y = H + 16; }
    else if (side === 2) { x = -16; y = Math.random() * H; }
    else { x = W + 16; y = Math.random() * H; }
    var elapsed = t / 1000;
    var speed = 1.1 + Math.random() * 0.9 + elapsed * 0.012;
    var dx = player.x - x, dy = player.y - y;
    var len = Math.sqrt(dx * dx + dy * dy) || 1;
    var jitter = 0.35;
    var ang = Math.atan2(dy, dx) + (Math.random() - 0.5) * jitter;
    enemies.push({x: x, y: y, vx: Math.cos(ang) * speed, vy: Math.sin(ang) * speed, s: 13 + Math.random() * 7});
  }
  function draw(){
    ctx.fillStyle = "#222";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#e85d5d";
    for (var i = 0; i < enemies.length; i++) {
      var e = enemies[i];
      ctx.fillRect(e.x - e.s / 2, e.y - e.s / 2, e.s, e.s);
    }
    ctx.fillStyle = "#5da8e8";
    ctx.beginPath();
    ctx.arc(player.x, player.y, player.r, 0, Math.PI * 2);
    ctx.fill();
  }
  function gameOver(elapsed){
    playing = false;
    cancelAnimationFrame(raf);
    var sec = elapsed / 1000;
    clock.textContent = sec.toFixed(1);
    draw();
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#fff";
    ctx.font = "24px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("ぶつかった！ " + sec.toFixed(1) + " 秒", W / 2, H / 2);
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("sec10", String(Math.floor(elapsed / 100)));
    fetch("{{ url_for('dodge_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "記録: " + sec.toFixed(1) + " 秒／ベスト（最長生存）: " + (d.best / 10).toFixed(1) + " 秒";
        }
      })
      .catch(function(){});
  }
  function loop(now){
    if (!playing) { return; }
    var elapsed = now - startedAt;
    if (target) { player.x = target.x; player.y = target.y; }
    var kv = 4;
    if (keys["ArrowLeft"]) { player.x -= kv; }
    if (keys["ArrowRight"]) { player.x += kv; }
    if (keys["ArrowUp"]) { player.y -= kv; }
    if (keys["ArrowDown"]) { player.y += kv; }
    player.x = Math.max(player.r, Math.min(W - player.r, player.x));
    player.y = Math.max(player.r, Math.min(H - player.r, player.y));
    var interval = Math.max(260, 750 - elapsed / 100);
    if (now - lastSpawn > interval) {
      spawnEnemy(elapsed);
      lastSpawn = now;
    }
    for (var i = enemies.length - 1; i >= 0; i--) {
      var e = enemies[i];
      e.x += e.vx;
      e.y += e.vy;
      if (e.x < -40 || e.x > W + 40 || e.y < -40 || e.y > H + 40) {
        enemies.splice(i, 1);
        continue;
      }
      var dx = e.x - player.x, dy = e.y - player.y;
      if (Math.sqrt(dx * dx + dy * dy) < player.r + e.s / 2) {
        gameOver(elapsed);
        return;
      }
    }
    clock.textContent = (elapsed / 1000).toFixed(1);
    draw();
    raf = requestAnimationFrame(loop);
  }
  function toCanvas(ev){
    var rect = cv.getBoundingClientRect();
    var cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
    var cy = (ev.touches ? ev.touches[0].clientY : ev.clientY) - rect.top;
    return {x: cx * W / rect.width, y: cy * H / rect.height};
  }
  cv.addEventListener("mousemove", function(ev){ target = toCanvas(ev); });
  cv.addEventListener("touchmove", function(ev){ ev.preventDefault(); target = toCanvas(ev); }, {passive: false});
  document.addEventListener("keydown", function(ev){ keys[ev.key] = true; });
  document.addEventListener("keyup", function(ev){ keys[ev.key] = false; });
  draw();
  startBtn.addEventListener("click", function(){
    enemies = [];
    player.x = W / 2; player.y = H / 2; target = null;
    startedAt = performance.now();
    lastSpawn = 0;
    playing = true;
    startBtn.disabled = true;
    message.textContent = "避け続けよう！";
    raf = requestAnimationFrame(loop);
  });
})();
</script>
"""


@app.route("/games/dodge", methods=["GET"])
def dodge():
    best = best_score("dodge", "max")
    body = render_template_string(
        DODGE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best_disp=(round(best / 10, 1) if best is not None else None),
        history=recent_scores("dodge", 10),
    )
    return game_page("かわしサバイバー", body)


@app.route("/games/dodge/score", methods=["POST"])
def dodge_score():
    raw = request.form.get("sec10", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 36000):
        return {"ok": False, "error": "invalid sec10"}, 400
    record_score("dodge", int(raw))
    return {"ok": True, "best": best_score("dodge", "max")}


# ============================
# ゆき玉転がし
# ============================
SNOWBALL_TEMPLATE = r"""
  <h1>⛄ ゆき玉転がし</h1>
  <p class="howto">雪玉は自動で転がり続けます。←→キー／タッチで左右に動かして岩を避けよう。転がるほど玉は大きくなりますが、岩に当たると小さくなり、小さくなりすぎると終わりです。進んだ距離がスコアです。</p>
  __FLASH__
  <div class="card">
    <canvas id="cv" width="480" height="360" style="width:100%; max-width:480px; display:block; margin:0 auto; background:#eef5fa; border-radius:12px; touch-action:none;"></canvas>
    <p class="mid">距離: <span id="dist">0</span> m ／ 玉の大きさ: <span id="size">14</span></p>
    <div class="row">
      <button id="startBtn" type="button">スタート</button>
    </div>
    <p class="result" id="message">ベスト（最長距離）: {{ best if best is not none else '—' }}{% if best is not none %} m{% endif %}</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（距離）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} m</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var cv = document.getElementById("cv");
  var ctx = cv.getContext("2d");
  var distLabel = document.getElementById("dist");
  var sizeLabel = document.getElementById("size");
  var message = document.getElementById("message");
  var startBtn = document.getElementById("startBtn");
  var W = cv.width, H = cv.height;
  var playing = false, raf = null;
  var ball = {x: W / 2, y: H - 80, r: 14};
  var targetX = null, keys = {}, rocks = [], flakes = [];
  var distancePx = 0, frame = 0, invuln = 0;
  for (var i = 0; i < 40; i++) {
    flakes.push({x: Math.random() * W, y: Math.random() * H, r: 1 + Math.random() * 2});
  }
  function draw(){
    ctx.fillStyle = "#eef5fa";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#fff";
    for (var i = 0; i < flakes.length; i++) {
      var f = flakes[i];
      ctx.beginPath();
      ctx.arc(f.x, f.y, f.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.fillStyle = "#8a8a8a";
    for (var j = 0; j < rocks.length; j++) {
      var rk = rocks[j];
      ctx.beginPath();
      ctx.arc(rk.x, rk.y, rk.r, 0, Math.PI * 2);
      ctx.fill();
    }
    if (!(invuln > 0 && frame % 6 < 3)) {
      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = "#9db8cc";
      ctx.beginPath();
      ctx.arc(ball.x, ball.y, ball.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
  }
  function gameOver(meters){
    playing = false;
    cancelAnimationFrame(raf);
    ctx.fillStyle = "rgba(0,0,0,0.45)";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "#fff";
    ctx.font = "24px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("玉が小さくなりすぎた！ " + meters + " m", W / 2, H / 2);
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("meters", String(meters));
    fetch("{{ url_for('snowball_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "記録: " + meters + " m／ベスト（最長距離）: " + d.best + " m";
        }
      })
      .catch(function(){});
  }
  function loop(){
    if (!playing) { return; }
    frame++;
    var speed = 2.2 + distancePx / 4000;
    distancePx += speed;
    ball.r = Math.min(42, ball.r + speed * 0.006);
    if (invuln > 0) { invuln--; }
    if (targetX !== null) {
      var dx = targetX - ball.x;
      ball.x += Math.max(-7, Math.min(7, dx));
    }
    if (keys["ArrowLeft"]) { ball.x -= 5; }
    if (keys["ArrowRight"]) { ball.x += 5; }
    ball.x = Math.max(ball.r, Math.min(W - ball.r, ball.x));
    for (var i = 0; i < flakes.length; i++) {
      flakes[i].y += speed;
      if (flakes[i].y > H) { flakes[i].y = -2; flakes[i].x = Math.random() * W; }
    }
    if (frame % 48 === 0 && Math.random() < 0.85) {
      rocks.push({x: 20 + Math.random() * (W - 40), y: -20, r: 9 + Math.random() * 8});
    }
    for (var j = rocks.length - 1; j >= 0; j--) {
      var rk = rocks[j];
      rk.y += speed;
      if (rk.y > H + 24) { rocks.splice(j, 1); continue; }
      var ddx = rk.x - ball.x, ddy = rk.y - ball.y;
      if (invuln === 0 && Math.sqrt(ddx * ddx + ddy * ddy) < ball.r + rk.r * 0.7) {
        rocks.splice(j, 1);
        ball.r -= 7;
        invuln = 50;
        if (ball.r < 9) {
          draw();
          gameOver(Math.floor(distancePx / 40));
          return;
        }
      }
    }
    distLabel.textContent = String(Math.floor(distancePx / 40));
    sizeLabel.textContent = String(Math.round(ball.r));
    draw();
    raf = requestAnimationFrame(loop);
  }
  function toCanvasX(ev){
    var rect = cv.getBoundingClientRect();
    var cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
    return cx * W / rect.width;
  }
  cv.addEventListener("mousemove", function(ev){ targetX = toCanvasX(ev); });
  cv.addEventListener("touchmove", function(ev){ ev.preventDefault(); targetX = toCanvasX(ev); }, {passive: false});
  document.addEventListener("keydown", function(ev){ keys[ev.key] = true; });
  document.addEventListener("keyup", function(ev){ keys[ev.key] = false; });
  draw();
  startBtn.addEventListener("click", function(){
    rocks = [];
    ball.x = W / 2; ball.r = 14; targetX = null;
    distancePx = 0; frame = 0; invuln = 0;
    playing = true;
    startBtn.disabled = true;
    message.textContent = "岩を避けて転がそう！";
    raf = requestAnimationFrame(loop);
  });
})();
</script>
"""


@app.route("/games/snowball", methods=["GET"])
def snowball():
    body = render_template_string(
        SNOWBALL_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("snowball", "max"),
        history=recent_scores("snowball", 10),
    )
    return game_page("ゆき玉転がし", body)


@app.route("/games/snowball/score", methods=["POST"])
def snowball_score():
    raw = request.form.get("meters", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 100000):
        return {"ok": False, "error": "invalid meters"}, 400
    record_score("snowball", int(raw))
    return {"ok": True, "best": best_score("snowball", "max")}


# ============================
# 中国語単語ガチャ
# 単語データ（ZH_WORDS）は単体ツール「zhwordgacha」の内蔵データ（全110語）を
# そのまま取り込んだもの。単体版にあった SQLite の履歴保存は移植せず、
# コレクションはセッション保持のみ（スコアには集めた種類数を記録する）。
# ============================
ZH_WORDS = [
    {"hanzi": "你好", "pinyin": "nǐhǎo", "meaning": "こんにちは",
     "example_cn": "你好，很高兴见到你。", "example_jp": "こんにちは、お会いできてうれしいです。"},
    {"hanzi": "谢谢", "pinyin": "xièxie", "meaning": "ありがとう",
     "example_cn": "谢谢你的帮助。", "example_jp": "助けてくれてありがとう。"},
    {"hanzi": "学习", "pinyin": "xuéxí", "meaning": "勉強する",
     "example_cn": "我每天学习中文。", "example_jp": "私は毎日中国語を勉強します。"},
    {"hanzi": "朋友", "pinyin": "péngyou", "meaning": "友達",
     "example_cn": "他是我的好朋友。", "example_jp": "彼は私の良い友達です。"},
    {"hanzi": "学校", "pinyin": "xuéxiào", "meaning": "学校",
     "example_cn": "我去学校上课。", "example_jp": "私は学校へ授業を受けに行きます。"},
    {"hanzi": "老师", "pinyin": "lǎoshī", "meaning": "先生",
     "example_cn": "老师讲得很清楚。", "example_jp": "先生の説明はとても分かりやすいです。"},
    {"hanzi": "学生", "pinyin": "xuésheng", "meaning": "学生",
     "example_cn": "我是大学生。", "example_jp": "私は大学生です。"},
    {"hanzi": "中国", "pinyin": "Zhōngguó", "meaning": "中国",
     "example_cn": "我想去中国旅行。", "example_jp": "私は中国へ旅行に行きたいです。"},
    {"hanzi": "日本", "pinyin": "Rìběn", "meaning": "日本",
     "example_cn": "我来自日本。", "example_jp": "私は日本から来ました。"},
    {"hanzi": "语言", "pinyin": "yǔyán", "meaning": "言語",
     "example_cn": "语言是沟通的工具。", "example_jp": "言語はコミュニケーションの道具です。"},
    {"hanzi": "时间", "pinyin": "shíjiān", "meaning": "時間",
     "example_cn": "我没有时间。", "example_jp": "私には時間がありません。"},
    {"hanzi": "今天", "pinyin": "jīntiān", "meaning": "今日",
     "example_cn": "今天是星期六。", "example_jp": "今日は土曜日です。"},
    {"hanzi": "明天", "pinyin": "míngtiān", "meaning": "明日",
     "example_cn": "明天见！", "example_jp": "また明日！"},
    {"hanzi": "昨天", "pinyin": "zuótiān", "meaning": "昨日",
     "example_cn": "昨天我去了图书馆。", "example_jp": "昨日私は図書館へ行きました。"},
    {"hanzi": "现在", "pinyin": "xiànzài", "meaning": "今",
     "example_cn": "现在几点？", "example_jp": "今何時ですか。"},
    {"hanzi": "早上", "pinyin": "zǎoshang", "meaning": "朝",
     "example_cn": "我早上七点起床。", "example_jp": "私は朝7時に起きます。"},
    {"hanzi": "晚上", "pinyin": "wǎnshang", "meaning": "夜・晩",
     "example_cn": "晚上我要看书。", "example_jp": "夜は本を読みます。"},
    {"hanzi": "工作", "pinyin": "gōngzuò", "meaning": "仕事",
     "example_cn": "我的工作很忙。", "example_jp": "私の仕事はとても忙しいです。"},
    {"hanzi": "家", "pinyin": "jiā", "meaning": "家・家庭",
     "example_cn": "我家有四口人。", "example_jp": "私の家は4人家族です。"},
    {"hanzi": "人", "pinyin": "rén", "meaning": "人",
     "example_cn": "这里有很多人。", "example_jp": "ここにはたくさんの人がいます。"},
    {"hanzi": "大", "pinyin": "dà", "meaning": "大きい",
     "example_cn": "这个房间很大。", "example_jp": "この部屋は大きいです。"},
    {"hanzi": "小", "pinyin": "xiǎo", "meaning": "小さい",
     "example_cn": "这只猫很小。", "example_jp": "この猫は小さいです。"},
    {"hanzi": "多", "pinyin": "duō", "meaning": "多い",
     "example_cn": "今天人很多。", "example_jp": "今日は人が多いです。"},
    {"hanzi": "少", "pinyin": "shǎo", "meaning": "少ない",
     "example_cn": "糖少一点。", "example_jp": "砂糖は少なめでお願いします。"},
    {"hanzi": "好", "pinyin": "hǎo", "meaning": "良い",
     "example_cn": "这个办法很好。", "example_jp": "この方法はとても良いです。"},
    {"hanzi": "新", "pinyin": "xīn", "meaning": "新しい",
     "example_cn": "我买了新手机。", "example_jp": "私は新しいスマホを買いました。"},
    {"hanzi": "忙", "pinyin": "máng", "meaning": "忙しい",
     "example_cn": "最近我很忙。", "example_jp": "最近私は忙しいです。"},
    {"hanzi": "累", "pinyin": "lèi", "meaning": "疲れた",
     "example_cn": "今天我很累。", "example_jp": "今日は疲れました。"},
    {"hanzi": "高兴", "pinyin": "gāoxìng", "meaning": "うれしい",
     "example_cn": "见到你我很高兴。", "example_jp": "あなたに会えてうれしいです。"},
    {"hanzi": "喜欢", "pinyin": "xǐhuan", "meaning": "好き・気に入る",
     "example_cn": "我喜欢喝茶。", "example_jp": "私はお茶を飲むのが好きです。"},
    {"hanzi": "爱", "pinyin": "ài", "meaning": "愛する・大好き",
     "example_cn": "我爱我的家人。", "example_jp": "私は家族を愛しています。"},
    {"hanzi": "想", "pinyin": "xiǎng", "meaning": "〜したい・思う",
     "example_cn": "我想喝水。", "example_jp": "水が飲みたいです。"},
    {"hanzi": "知道", "pinyin": "zhīdào", "meaning": "知っている",
     "example_cn": "我知道他的名字。", "example_jp": "私は彼の名前を知っています。"},
    {"hanzi": "觉得", "pinyin": "juéde", "meaning": "〜と思う・感じる",
     "example_cn": "我觉得这本书很有意思。", "example_jp": "この本はとても面白いと思います。"},
    {"hanzi": "可以", "pinyin": "kěyǐ", "meaning": "〜できる・〜してもよい",
     "example_cn": "我可以进来吗？", "example_jp": "入ってもいいですか。"},
    {"hanzi": "会", "pinyin": "huì", "meaning": "〜できる（習得して）・〜だろう",
     "example_cn": "我会说一点中文。", "example_jp": "私は少し中国語が話せます。"},
    {"hanzi": "去", "pinyin": "qù", "meaning": "行く",
     "example_cn": "我去商店买东西。", "example_jp": "私は店へ買い物に行きます。"},
    {"hanzi": "来", "pinyin": "lái", "meaning": "来る",
     "example_cn": "他明天来我家。", "example_jp": "彼は明日私の家に来ます。"},
    {"hanzi": "回家", "pinyin": "huí jiā", "meaning": "帰宅する",
     "example_cn": "我六点回家。", "example_jp": "私は6時に帰宅します。"},
    {"hanzi": "吃", "pinyin": "chī", "meaning": "食べる",
     "example_cn": "我们一起吃饭吧。", "example_jp": "一緒にご飯を食べましょう。"},
    {"hanzi": "喝", "pinyin": "hē", "meaning": "飲む",
     "example_cn": "我每天喝咖啡。", "example_jp": "私は毎日コーヒーを飲みます。"},
    {"hanzi": "看", "pinyin": "kàn", "meaning": "見る・読む",
     "example_cn": "我喜欢看电影。", "example_jp": "私は映画を見るのが好きです。"},
    {"hanzi": "听", "pinyin": "tīng", "meaning": "聞く",
     "example_cn": "请听我说。", "example_jp": "私の話を聞いてください。"},
    {"hanzi": "说", "pinyin": "shuō", "meaning": "話す・言う",
     "example_cn": "他说中文说得很好。", "example_jp": "彼は中国語を話すのが上手です。"},
    {"hanzi": "读", "pinyin": "dú", "meaning": "読む・音読する",
     "example_cn": "我每天读报纸。", "example_jp": "私は毎日新聞を読みます。"},
    {"hanzi": "写", "pinyin": "xiě", "meaning": "書く",
     "example_cn": "请写你的名字。", "example_jp": "名前を書いてください。"},
    {"hanzi": "买", "pinyin": "mǎi", "meaning": "買う",
     "example_cn": "我想买这本书。", "example_jp": "私はこの本を買いたいです。"},
    {"hanzi": "卖", "pinyin": "mài", "meaning": "売る",
     "example_cn": "这家店卖水果。", "example_jp": "この店は果物を売っています。"},
    {"hanzi": "走", "pinyin": "zǒu", "meaning": "歩く・去る",
     "example_cn": "我们走吧。", "example_jp": "行きましょう。"},
    {"hanzi": "跑步", "pinyin": "pǎobù", "meaning": "ジョギングする",
     "example_cn": "我每天早上跑步。", "example_jp": "私は毎朝ジョギングします。"},
    {"hanzi": "坐", "pinyin": "zuò", "meaning": "座る・（乗り物に）乗る",
     "example_cn": "请坐。", "example_jp": "どうぞ座ってください。"},
    {"hanzi": "站", "pinyin": "zhàn", "meaning": "立つ",
     "example_cn": "他站在门口。", "example_jp": "彼はドアの前に立っています。"},
    {"hanzi": "开", "pinyin": "kāi", "meaning": "開ける・運転する",
     "example_cn": "请开门。", "example_jp": "ドアを開けてください。"},
    {"hanzi": "关", "pinyin": "guān", "meaning": "閉める",
     "example_cn": "请关窗户。", "example_jp": "窓を閉めてください。"},
    {"hanzi": "打电话", "pinyin": "dǎ diànhuà", "meaning": "電話をかける",
     "example_cn": "我晚上给他打电话。", "example_jp": "夜に彼へ電話をかけます。"},
    {"hanzi": "上班", "pinyin": "shàngbān", "meaning": "出勤する",
     "example_cn": "我九点上班。", "example_jp": "私は9時に出勤します。"},
    {"hanzi": "下班", "pinyin": "xiàbān", "meaning": "退勤する",
     "example_cn": "他五点下班。", "example_jp": "彼は5時に退勤します。"},
    {"hanzi": "睡觉", "pinyin": "shuìjiào", "meaning": "寝る",
     "example_cn": "我十一点睡觉。", "example_jp": "私は11時に寝ます。"},
    {"hanzi": "起床", "pinyin": "qǐchuáng", "meaning": "起きる・起床する",
     "example_cn": "我每天六点起床。", "example_jp": "私は毎日6時に起きます。"},
    {"hanzi": "洗澡", "pinyin": "xǐzǎo", "meaning": "入浴する・シャワーを浴びる",
     "example_cn": "我晚上洗澡。", "example_jp": "私は夜にお風呂に入ります。"},
    {"hanzi": "做饭", "pinyin": "zuò fàn", "meaning": "料理する",
     "example_cn": "妈妈在做饭。", "example_jp": "母が料理をしています。"},
    {"hanzi": "唱歌", "pinyin": "chànggē", "meaning": "歌を歌う",
     "example_cn": "她唱歌唱得很好听。", "example_jp": "彼女は歌が上手です。"},
    {"hanzi": "跳舞", "pinyin": "tiàowǔ", "meaning": "踊る",
     "example_cn": "他们在跳舞。", "example_jp": "彼らは踊っています。"},
    {"hanzi": "游泳", "pinyin": "yóuyǒng", "meaning": "泳ぐ",
     "example_cn": "夏天我喜欢游泳。", "example_jp": "夏は泳ぐのが好きです。"},
    {"hanzi": "旅行", "pinyin": "lǚxíng", "meaning": "旅行する",
     "example_cn": "我喜欢去国外旅行。", "example_jp": "海外旅行が好きです。"},
    {"hanzi": "运动", "pinyin": "yùndòng", "meaning": "運動する・スポーツ",
     "example_cn": "运动对身体好。", "example_jp": "運動は体に良いです。"},
    {"hanzi": "水", "pinyin": "shuǐ", "meaning": "水",
     "example_cn": "请给我一杯水。", "example_jp": "水を一杯ください。"},
    {"hanzi": "茶", "pinyin": "chá", "meaning": "お茶",
     "example_cn": "中国人喜欢喝茶。", "example_jp": "中国人はお茶を飲むのが好きです。"},
    {"hanzi": "咖啡", "pinyin": "kāfēi", "meaning": "コーヒー",
     "example_cn": "我想喝一杯咖啡。", "example_jp": "コーヒーを一杯飲みたいです。"},
    {"hanzi": "米饭", "pinyin": "mǐfàn", "meaning": "ご飯（炊いた米）",
     "example_cn": "我吃米饭和菜。", "example_jp": "私はご飯とおかずを食べます。"},
    {"hanzi": "面条", "pinyin": "miàntiáo", "meaning": "麺",
     "example_cn": "这家店的面条很好吃。", "example_jp": "この店の麺はとてもおいしいです。"},
    {"hanzi": "水果", "pinyin": "shuǐguǒ", "meaning": "果物",
     "example_cn": "我每天吃水果。", "example_jp": "私は毎日果物を食べます。"},
    {"hanzi": "苹果", "pinyin": "píngguǒ", "meaning": "りんご",
     "example_cn": "这个苹果很甜。", "example_jp": "このりんごは甘いです。"},
    {"hanzi": "天气", "pinyin": "tiānqì", "meaning": "天気",
     "example_cn": "今天天气很好。", "example_jp": "今日は天気がとても良いです。"},
    {"hanzi": "下雨", "pinyin": "xiàyǔ", "meaning": "雨が降る",
     "example_cn": "明天会下雨。", "example_jp": "明日は雨が降るでしょう。"},
    {"hanzi": "雪", "pinyin": "xuě", "meaning": "雪",
     "example_cn": "冬天下雪了。", "example_jp": "冬に雪が降りました。"},
    {"hanzi": "热", "pinyin": "rè", "meaning": "暑い・熱い",
     "example_cn": "今天很热。", "example_jp": "今日は暑いです。"},
    {"hanzi": "冷", "pinyin": "lěng", "meaning": "寒い",
     "example_cn": "冬天很冷。", "example_jp": "冬は寒いです。"},
    {"hanzi": "猫", "pinyin": "māo", "meaning": "猫",
     "example_cn": "我家有一只猫。", "example_jp": "私の家には猫が一匹います。"},
    {"hanzi": "狗", "pinyin": "gǒu", "meaning": "犬",
     "example_cn": "这只狗很可爱。", "example_jp": "この犬はとてもかわいいです。"},
    {"hanzi": "鸟", "pinyin": "niǎo", "meaning": "鳥",
     "example_cn": "树上有一只鸟。", "example_jp": "木の上に鳥が一羽います。"},
    {"hanzi": "鱼", "pinyin": "yú", "meaning": "魚",
     "example_cn": "我喜欢吃鱼。", "example_jp": "私は魚を食べるのが好きです。"},
    {"hanzi": "书", "pinyin": "shū", "meaning": "本",
     "example_cn": "这本书很有意思。", "example_jp": "この本はとても面白いです。"},
    {"hanzi": "电脑", "pinyin": "diànnǎo", "meaning": "パソコン",
     "example_cn": "我的电脑坏了。", "example_jp": "私のパソコンが壊れました。"},
    {"hanzi": "手机", "pinyin": "shǒujī", "meaning": "スマートフォン",
     "example_cn": "我忘了带手机。", "example_jp": "スマホを持ってくるのを忘れました。"},
    {"hanzi": "电影", "pinyin": "diànyǐng", "meaning": "映画",
     "example_cn": "我们周末去看电影吧。", "example_jp": "週末に映画を見に行きましょう。"},
    {"hanzi": "音乐", "pinyin": "yīnyuè", "meaning": "音楽",
     "example_cn": "我喜欢听音乐。", "example_jp": "私は音楽を聞くのが好きです。"},
    {"hanzi": "钱", "pinyin": "qián", "meaning": "お金",
     "example_cn": "我没有钱了。", "example_jp": "お金がなくなりました。"},
    {"hanzi": "商店", "pinyin": "shāngdiàn", "meaning": "店・商店",
     "example_cn": "商店几点开门？", "example_jp": "店は何時に開きますか。"},
    {"hanzi": "医院", "pinyin": "yīyuàn", "meaning": "病院",
     "example_cn": "他去医院看病了。", "example_jp": "彼は病院へ診察に行きました。"},
    {"hanzi": "图书馆", "pinyin": "túshūguǎn", "meaning": "図書館",
     "example_cn": "我在图书馆学习。", "example_jp": "私は図書館で勉強します。"},
    {"hanzi": "公园", "pinyin": "gōngyuán", "meaning": "公園",
     "example_cn": "公园里有很多人。", "example_jp": "公園にはたくさんの人がいます。"},
    {"hanzi": "车站", "pinyin": "chēzhàn", "meaning": "駅・停留所",
     "example_cn": "车站在前面。", "example_jp": "駅は前方にあります。"},
    {"hanzi": "飞机", "pinyin": "fēijī", "meaning": "飛行機",
     "example_cn": "我坐飞机去北京。", "example_jp": "私は飛行機で北京へ行きます。"},
    {"hanzi": "火车", "pinyin": "huǒchē", "meaning": "列車",
     "example_cn": "火车几点到？", "example_jp": "列車は何時に着きますか。"},
    {"hanzi": "自行车", "pinyin": "zìxíngchē", "meaning": "自転車",
     "example_cn": "我骑自行车上学。", "example_jp": "私は自転車で通学します。"},
    {"hanzi": "快", "pinyin": "kuài", "meaning": "速い・もうすぐ",
     "example_cn": "他跑得很快。", "example_jp": "彼は走るのが速いです。"},
    {"hanzi": "慢", "pinyin": "màn", "meaning": "遅い・ゆっくり",
     "example_cn": "请慢一点说。", "example_jp": "ゆっくり話してください。"},
    {"hanzi": "贵", "pinyin": "guì", "meaning": "高い（値段）",
     "example_cn": "这件衣服太贵了。", "example_jp": "この服は高すぎます。"},
    {"hanzi": "便宜", "pinyin": "piányi", "meaning": "安い（値段）",
     "example_cn": "这家店的东西很便宜。", "example_jp": "この店の物は安いです。"},
    {"hanzi": "近", "pinyin": "jìn", "meaning": "近い",
     "example_cn": "我家离学校很近。", "example_jp": "私の家は学校から近いです。"},
    {"hanzi": "远", "pinyin": "yuǎn", "meaning": "遠い",
     "example_cn": "机场离这里很远。", "example_jp": "空港はここから遠いです。"},
    {"hanzi": "问题", "pinyin": "wèntí", "meaning": "問題・質問",
     "example_cn": "我有一个问题。", "example_jp": "質問が一つあります。"},
    {"hanzi": "意思", "pinyin": "yìsi", "meaning": "意味",
     "example_cn": "这个词是什么意思？", "example_jp": "この単語はどういう意味ですか。"},
    {"hanzi": "名字", "pinyin": "míngzi", "meaning": "名前",
     "example_cn": "你叫什么名字？", "example_jp": "あなたの名前は何ですか。"},
    {"hanzi": "东西", "pinyin": "dōngxi", "meaning": "物・もの",
     "example_cn": "我去买东西。", "example_jp": "買い物に行きます。"},
    {"hanzi": "一起", "pinyin": "yìqǐ", "meaning": "一緒に",
     "example_cn": "我们一起学习吧。", "example_jp": "一緒に勉強しましょう。"},
    {"hanzi": "已经", "pinyin": "yǐjīng", "meaning": "すでに・もう",
     "example_cn": "我已经吃过饭了。", "example_jp": "私はすでにご飯を食べました。"},
    {"hanzi": "还", "pinyin": "hái", "meaning": "まだ・さらに",
     "example_cn": "我还没做完。", "example_jp": "私はまだ終わっていません。"},
    {"hanzi": "再", "pinyin": "zài", "meaning": "再び・改めて",
     "example_cn": "我们明天再见面。", "example_jp": "また明日会いましょう。"},
]


ZHGACHA_TEMPLATE = r"""
  <h1>🇨🇳 中国語単語ガチャ</h1>
  <p class="howto">「ガチャを引く」を押すと、中国語の単語（HSK初級〜中級程度）が1つランダムで出ます。簡体字・ピンイン・日本語訳・例文つき。全 {{ total }} 語のコレクション完成を目指そう。引いた単語はこのページを開いている間だけ記録されます（単体版のような履歴保存はありません）。</p>
  __FLASH__
  <div class="card">
    <form method="post" action="{{ url_for('zhgacha_draw') }}" class="row">
      <button type="submit">🎰 ガチャを引く</button>
    </form>
    {% if card %}
      <div style="text-align:center; margin-top:16px;">
        <div style="font-size:40px; font-weight:bold;">{{ card.hanzi }}</div>
        <div style="font-size:18px;">{{ card.pinyin }}</div>
        <div style="font-size:18px; margin-top:4px;">{{ card.meaning }}</div>
        {% if is_new %}<p class="result">🆕 新しい単語をゲット！</p>{% endif %}
        <p style="margin-top:12px;">{{ card.example_cn }}<br><span class="muted">{{ card.example_jp }}</span></p>
      </div>
    {% else %}
      <p class="muted" style="margin-top:12px;">まだ引いていません。ガチャを引いてみよう。</p>
    {% endif %}
    <p class="result">ベスト（集めた種類数）: {{ best if best is not none else '—' }}{% if best is not none %} / {{ total }} 種{% endif %}</p>
  </div>
  <div class="card">
    <h3 style="margin:0 0 8px;">📖 コレクション（<span id="kindCount">{{ kinds }}</span> / {{ total }} 種）</h3>
    {% if word_list %}
      <table>
        {% for w in word_list %}
          <tr><td>{{ w.hanzi }}</td><td class="muted">{{ w.pinyin }}</td><td class="muted">{{ w.meaning }}</td></tr>
        {% endfor %}
      </table>
    {% else %}
      <p class="muted">まだ単語を集めていません。</p>
    {% endif %}
    <form method="post" action="{{ url_for('zhgacha_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">コレクションをリセット</button>
    </form>
  </div>
"""


def render_zhgacha():
    collected = session.get("zh_collected", [])
    last = session.get("zh_last")
    card = ZH_WORDS[last] if isinstance(last, int) and 0 <= last < len(ZH_WORDS) else None
    body = render_template_string(
        ZHGACHA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        total=len(ZH_WORDS),
        kinds=len(collected),
        word_list=[ZH_WORDS[i] for i in collected],
        card=card,
        is_new=bool(session.get("zh_last_new")),
        best=best_score("zhgacha", "max"),
    )
    return game_page("中国語単語ガチャ", body)


@app.route("/games/zhgacha", methods=["GET"])
def zhgacha():
    return render_zhgacha()


@app.route("/games/zhgacha/draw", methods=["POST"])
def zhgacha_draw():
    idx = random.randrange(len(ZH_WORDS))
    collected = list(session.get("zh_collected", []))
    is_new = idx not in collected
    if is_new:
        collected.append(idx)
        session["zh_collected"] = collected
        record_score("zhgacha", len(collected))
    session["zh_last"] = idx
    session["zh_last_new"] = is_new
    return redirect(url_for("zhgacha"))


@app.route("/games/zhgacha/reset", methods=["POST"])
def zhgacha_reset():
    session.pop("zh_collected", None)
    session.pop("zh_last", None)
    session.pop("zh_last_new", None)
    flash("コレクションをリセットしました。", "ok")
    return redirect(url_for("zhgacha"))


# ============================
# 英単語ガチャ
# 中国語単語ガチャ（zhgacha）の英語版。単語データは日常的な基礎単語
# （CEFR A1〜A2 程度）110語を内蔵。遊び方は zhgacha と同じで、
# コレクションはセッション保持のみ（スコアには集めた種類数を記録する）。
# ============================
EN_WORDS = [
    {"word": "apple", "kana": "アップル", "meaning": "りんご", "example": "I eat an apple every day."},
    {"word": "book", "kana": "ブック", "meaning": "本", "example": "This book is interesting."},
    {"word": "cat", "kana": "キャット", "meaning": "猫", "example": "The cat is sleeping."},
    {"word": "dog", "kana": "ドッグ", "meaning": "犬", "example": "My dog likes to run."},
    {"word": "water", "kana": "ウォーター", "meaning": "水", "example": "Please give me some water."},
    {"word": "school", "kana": "スクール", "meaning": "学校", "example": "I go to school by bus."},
    {"word": "friend", "kana": "フレンド", "meaning": "友達", "example": "She is my best friend."},
    {"word": "family", "kana": "ファミリー", "meaning": "家族", "example": "My family lives in Tokyo."},
    {"word": "house", "kana": "ハウス", "meaning": "家", "example": "Their house is near the park."},
    {"word": "car", "kana": "カー", "meaning": "車", "example": "He drives a red car."},
    {"word": "train", "kana": "トレイン", "meaning": "電車・列車", "example": "The train is late today."},
    {"word": "music", "kana": "ミュージック", "meaning": "音楽", "example": "I listen to music every night."},
    {"word": "movie", "kana": "ムービー", "meaning": "映画", "example": "Let's watch a movie tonight."},
    {"word": "food", "kana": "フード", "meaning": "食べ物", "example": "Japanese food is delicious."},
    {"word": "coffee", "kana": "コーヒー", "meaning": "コーヒー", "example": "I drink coffee in the morning."},
    {"word": "tea", "kana": "ティー", "meaning": "お茶", "example": "Would you like some tea?"},
    {"word": "morning", "kana": "モーニング", "meaning": "朝", "example": "Good morning, everyone."},
    {"word": "night", "kana": "ナイト", "meaning": "夜", "example": "I can see the moon at night."},
    {"word": "day", "kana": "デイ", "meaning": "日・一日", "example": "Today is a sunny day."},
    {"word": "week", "kana": "ウィーク", "meaning": "週", "example": "See you next week."},
    {"word": "month", "kana": "マンス", "meaning": "月", "example": "June is my favorite month."},
    {"word": "year", "kana": "イヤー", "meaning": "年", "example": "Happy New Year!"},
    {"word": "time", "kana": "タイム", "meaning": "時間", "example": "What time is it now?"},
    {"word": "money", "kana": "マネー", "meaning": "お金", "example": "I need some money for lunch."},
    {"word": "city", "kana": "シティ", "meaning": "市・都市", "example": "This city is very big."},
    {"word": "country", "kana": "カントリー", "meaning": "国", "example": "Japan is a beautiful country."},
    {"word": "sea", "kana": "シー", "meaning": "海", "example": "We swim in the sea in summer."},
    {"word": "mountain", "kana": "マウンテン", "meaning": "山", "example": "The mountain is high."},
    {"word": "river", "kana": "リバー", "meaning": "川", "example": "The river runs through the city."},
    {"word": "flower", "kana": "フラワー", "meaning": "花", "example": "These flowers are pretty."},
    {"word": "tree", "kana": "ツリー", "meaning": "木", "example": "A bird is in the tree."},
    {"word": "sun", "kana": "サン", "meaning": "太陽", "example": "The sun is bright today."},
    {"word": "rain", "kana": "レイン", "meaning": "雨", "example": "It will rain tomorrow."},
    {"word": "snow", "kana": "スノー", "meaning": "雪", "example": "Children play in the snow."},
    {"word": "bird", "kana": "バード", "meaning": "鳥", "example": "I can hear a bird singing."},
    {"word": "fish", "kana": "フィッシュ", "meaning": "魚", "example": "We eat fish for dinner."},
    {"word": "hand", "kana": "ハンド", "meaning": "手", "example": "Wash your hands, please."},
    {"word": "eye", "kana": "アイ", "meaning": "目", "example": "She has blue eyes."},
    {"word": "door", "kana": "ドア", "meaning": "ドア・扉", "example": "Please close the door."},
    {"word": "window", "kana": "ウィンドウ", "meaning": "窓", "example": "Open the window, please."},
    {"word": "table", "kana": "テーブル", "meaning": "テーブル・机", "example": "The book is on the table."},
    {"word": "chair", "kana": "チェア", "meaning": "いす", "example": "Sit on this chair."},
    {"word": "room", "kana": "ルーム", "meaning": "部屋", "example": "My room is small but clean."},
    {"word": "key", "kana": "キー", "meaning": "鍵", "example": "I can't find my key."},
    {"word": "phone", "kana": "フォン", "meaning": "電話・スマホ", "example": "My phone is new."},
    {"word": "computer", "kana": "コンピューター", "meaning": "コンピューター", "example": "I use a computer at work."},
    {"word": "picture", "kana": "ピクチャー", "meaning": "写真・絵", "example": "This picture is beautiful."},
    {"word": "question", "kana": "クエスチョン", "meaning": "質問", "example": "I have a question."},
    {"word": "answer", "kana": "アンサー", "meaning": "答え", "example": "The answer is easy."},
    {"word": "name", "kana": "ネーム", "meaning": "名前", "example": "My name is Anna."},
    {"word": "teacher", "kana": "ティーチャー", "meaning": "先生", "example": "Our teacher is kind."},
    {"word": "student", "kana": "スチューデント", "meaning": "学生・生徒", "example": "He is a high school student."},
    {"word": "child", "kana": "チャイルド", "meaning": "子ども", "example": "The child is playing in the park."},
    {"word": "man", "kana": "マン", "meaning": "男の人", "example": "That man is my father."},
    {"word": "woman", "kana": "ウーマン", "meaning": "女の人", "example": "The woman is a doctor."},
    {"word": "shop", "kana": "ショップ", "meaning": "店", "example": "The shop opens at nine."},
    {"word": "station", "kana": "ステーション", "meaning": "駅", "example": "The station is near my house."},
    {"word": "park", "kana": "パーク", "meaning": "公園", "example": "Let's play in the park."},
    {"word": "hospital", "kana": "ホスピタル", "meaning": "病院", "example": "She works at a hospital."},
    {"word": "library", "kana": "ライブラリー", "meaning": "図書館", "example": "I study at the library."},
    {"word": "eat", "kana": "イート", "meaning": "食べる", "example": "We eat breakfast at seven."},
    {"word": "drink", "kana": "ドリンク", "meaning": "飲む", "example": "I drink water after running."},
    {"word": "go", "kana": "ゴー", "meaning": "行く", "example": "I go to school every day."},
    {"word": "come", "kana": "カム", "meaning": "来る", "example": "Come here, please."},
    {"word": "see", "kana": "シー", "meaning": "見る・会う", "example": "I see a bird in the sky."},
    {"word": "read", "kana": "リード", "meaning": "読む", "example": "I read a book before bed."},
    {"word": "write", "kana": "ライト", "meaning": "書く", "example": "Please write your name here."},
    {"word": "speak", "kana": "スピーク", "meaning": "話す", "example": "She can speak English."},
    {"word": "listen", "kana": "リッスン", "meaning": "聞く", "example": "Listen to the teacher."},
    {"word": "walk", "kana": "ウォーク", "meaning": "歩く", "example": "I walk to the station."},
    {"word": "run", "kana": "ラン", "meaning": "走る", "example": "They run in the park."},
    {"word": "swim", "kana": "スイム", "meaning": "泳ぐ", "example": "Fish swim in the river."},
    {"word": "sing", "kana": "シング", "meaning": "歌う", "example": "She sings very well."},
    {"word": "play", "kana": "プレイ", "meaning": "遊ぶ・弾く", "example": "Children play soccer."},
    {"word": "study", "kana": "スタディ", "meaning": "勉強する", "example": "I study English every day."},
    {"word": "work", "kana": "ワーク", "meaning": "働く・仕事する", "example": "My father works in an office."},
    {"word": "sleep", "kana": "スリープ", "meaning": "眠る", "example": "I sleep for eight hours."},
    {"word": "buy", "kana": "バイ", "meaning": "買う", "example": "I buy bread at that shop."},
    {"word": "make", "kana": "メイク", "meaning": "作る", "example": "Let's make a cake."},
    {"word": "like", "kana": "ライク", "meaning": "好き", "example": "I like music."},
    {"word": "want", "kana": "ウォント", "meaning": "欲しい・〜したい", "example": "I want a new bicycle."},
    {"word": "know", "kana": "ノウ", "meaning": "知っている", "example": "I know his name."},
    {"word": "think", "kana": "シンク", "meaning": "思う・考える", "example": "I think so too."},
    {"word": "help", "kana": "ヘルプ", "meaning": "助ける・手伝う", "example": "Please help me."},
    {"word": "open", "kana": "オープン", "meaning": "開ける", "example": "Open the book, please."},
    {"word": "close", "kana": "クローズ", "meaning": "閉める", "example": "Close your eyes."},
    {"word": "start", "kana": "スタート", "meaning": "始める・始まる", "example": "The movie starts at seven."},
    {"word": "finish", "kana": "フィニッシュ", "meaning": "終わる・終える", "example": "I finish my homework early."},
    {"word": "live", "kana": "リブ", "meaning": "住む・生きる", "example": "I live in Japan."},
    {"word": "love", "kana": "ラブ", "meaning": "大好き・愛する", "example": "I love my family."},
    {"word": "big", "kana": "ビッグ", "meaning": "大きい", "example": "This is a big house."},
    {"word": "small", "kana": "スモール", "meaning": "小さい", "example": "The cat is small."},
    {"word": "new", "kana": "ニュー", "meaning": "新しい", "example": "I have a new bike."},
    {"word": "old", "kana": "オールド", "meaning": "古い・年をとった", "example": "This is an old book."},
    {"word": "good", "kana": "グッド", "meaning": "良い", "example": "This is a good idea."},
    {"word": "happy", "kana": "ハッピー", "meaning": "うれしい・幸せな", "example": "I am happy today."},
    {"word": "hot", "kana": "ホット", "meaning": "暑い・熱い", "example": "Today is very hot."},
    {"word": "cold", "kana": "コールド", "meaning": "寒い・冷たい", "example": "The water is cold."},
    {"word": "easy", "kana": "イージー", "meaning": "簡単な", "example": "This question is easy."},
    {"word": "difficult", "kana": "ディフィカルト", "meaning": "難しい", "example": "This puzzle is difficult."},
    {"word": "busy", "kana": "ビジー", "meaning": "忙しい", "example": "I am busy today."},
    {"word": "fast", "kana": "ファスト", "meaning": "速い", "example": "He runs fast."},
    {"word": "slow", "kana": "スロー", "meaning": "遅い・ゆっくりした", "example": "The train is slow."},
    {"word": "beautiful", "kana": "ビューティフル", "meaning": "美しい", "example": "The sea is beautiful."},
    {"word": "delicious", "kana": "デリシャス", "meaning": "おいしい", "example": "The cake is delicious."},
    {"word": "interesting", "kana": "インタレスティング", "meaning": "面白い", "example": "The movie is interesting."},
    {"word": "kind", "kana": "カインド", "meaning": "親切な", "example": "She is kind to everyone."},
    {"word": "strong", "kana": "ストロング", "meaning": "強い", "example": "He is strong."},
    {"word": "young", "kana": "ヤング", "meaning": "若い", "example": "She is a young teacher."},
    {"word": "long", "kana": "ロング", "meaning": "長い", "example": "This is a long story."},
]

# ============================
# エスペラント単語ガチャ
# 中国語単語ガチャ（zhgacha）のエスペラント版。単語データは基礎語彙
# 110語を内蔵。綴り通り読める言語なので読み欄は設けず、文字は
# x-system ではなく字上符つき文字（ĉ ĝ ĥ ĵ ŝ ŭ）をそのまま使う。
# 遊び方は zhgacha と同じで、コレクションはセッション保持のみ
# （スコアには集めた種類数を記録する）。
# ============================
EO_WORDS = [
    {"word": "saluton", "meaning": "こんにちは", "example": "Saluton! Kiel vi fartas?"},
    {"word": "libro", "meaning": "本", "example": "Mi legas libron ĉiutage."},
    {"word": "hundo", "meaning": "犬", "example": "La hundo kuras en la parko."},
    {"word": "kato", "meaning": "猫", "example": "La kato dormas sur la seĝo."},
    {"word": "akvo", "meaning": "水", "example": "Mi trinkas akvon matene."},
    {"word": "pano", "meaning": "パン", "example": "Ŝi manĝas panon."},
    {"word": "pomo", "meaning": "りんご", "example": "La pomo estas ruĝa."},
    {"word": "domo", "meaning": "家", "example": "Mia domo estas malgranda."},
    {"word": "urbo", "meaning": "市・町", "example": "Tokio estas granda urbo."},
    {"word": "lernejo", "meaning": "学校", "example": "La infanoj iras al la lernejo."},
    {"word": "instruisto", "meaning": "先生", "example": "La instruisto estas afabla."},
    {"word": "studento", "meaning": "学生", "example": "Li estas studento."},
    {"word": "amiko", "meaning": "友達", "example": "Li estas mia bona amiko."},
    {"word": "familio", "meaning": "家族", "example": "Mia familio estas granda."},
    {"word": "patro", "meaning": "父", "example": "Mia patro laboras en oficejo."},
    {"word": "patrino", "meaning": "母", "example": "Mia patrino kuiras bone."},
    {"word": "frato", "meaning": "兄弟", "example": "Mi havas unu fraton."},
    {"word": "fratino", "meaning": "姉妹", "example": "Ŝia fratino estas juna."},
    {"word": "infano", "meaning": "子ども", "example": "La infano ludas en la parko."},
    {"word": "viro", "meaning": "男の人", "example": "La viro estas alta."},
    {"word": "virino", "meaning": "女の人", "example": "La virino estas kuracisto."},
    {"word": "homo", "meaning": "人", "example": "Multaj homoj loĝas ĉi tie."},
    {"word": "tago", "meaning": "日・一日", "example": "Hodiaŭ estas bela tago."},
    {"word": "nokto", "meaning": "夜", "example": "La nokto estas malluma."},
    {"word": "mateno", "meaning": "朝", "example": "Mi vekiĝas frue en la mateno."},
    {"word": "vespero", "meaning": "夕方・晩", "example": "Ni promenas vespere."},
    {"word": "semajno", "meaning": "週", "example": "Unu semajno havas sep tagojn."},
    {"word": "monato", "meaning": "月", "example": "Junio estas varma monato."},
    {"word": "jaro", "meaning": "年", "example": "Feliĉan Novan Jaron!"},
    {"word": "tempo", "meaning": "時間", "example": "Mi ne havas tempon."},
    {"word": "suno", "meaning": "太陽", "example": "La suno brilas hodiaŭ."},
    {"word": "luno", "meaning": "月（天体）", "example": "La luno estas plena."},
    {"word": "stelo", "meaning": "星", "example": "Multaj steloj brilas en la ĉielo."},
    {"word": "ĉielo", "meaning": "空", "example": "La ĉielo estas blua."},
    {"word": "maro", "meaning": "海", "example": "Ni naĝas en la maro."},
    {"word": "rivero", "meaning": "川", "example": "La rivero estas longa."},
    {"word": "monto", "meaning": "山", "example": "La monto estas alta."},
    {"word": "arbo", "meaning": "木", "example": "Birdo sidas sur la arbo."},
    {"word": "floro", "meaning": "花", "example": "La floroj estas belaj."},
    {"word": "pluvo", "meaning": "雨", "example": "La pluvo falas ekde la mateno."},
    {"word": "neĝo", "meaning": "雪", "example": "La infanoj ludas en la neĝo."},
    {"word": "vento", "meaning": "風", "example": "La vento blovas forte."},
    {"word": "birdo", "meaning": "鳥", "example": "La birdo kantas bele."},
    {"word": "fiŝo", "meaning": "魚", "example": "Mi ŝatas fiŝon."},
    {"word": "ĉevalo", "meaning": "馬", "example": "La ĉevalo kuras rapide."},
    {"word": "muso", "meaning": "ネズミ", "example": "Malgranda muso estas sub la tablo."},
    {"word": "tablo", "meaning": "テーブル・机", "example": "La libro estas sur la tablo."},
    {"word": "seĝo", "meaning": "いす", "example": "Sidu sur la seĝo, bonvolu."},
    {"word": "pordo", "meaning": "ドア・扉", "example": "Bonvolu fermi la pordon."},
    {"word": "fenestro", "meaning": "窓", "example": "Malfermu la fenestron, bonvolu."},
    {"word": "ĉambro", "meaning": "部屋", "example": "Mia ĉambro estas pura."},
    {"word": "ŝlosilo", "meaning": "鍵", "example": "Mi perdis mian ŝlosilon."},
    {"word": "telefono", "meaning": "電話", "example": "Mia telefono estas nova."},
    {"word": "komputilo", "meaning": "コンピューター", "example": "Mi uzas komputilon por labori."},
    {"word": "ĝardeno", "meaning": "庭", "example": "La ĝardeno estas plena de floroj."},
    {"word": "vorto", "meaning": "単語", "example": "Tiu vorto estas malfacila."},
    {"word": "lingvo", "meaning": "言語", "example": "Esperanto estas internacia lingvo."},
    {"word": "demando", "meaning": "質問", "example": "Mi havas demandon."},
    {"word": "respondo", "meaning": "答え", "example": "La respondo estas facila."},
    {"word": "nomo", "meaning": "名前", "example": "Mia nomo estas Ken."},
    {"word": "mono", "meaning": "お金", "example": "Mi bezonas iom da mono."},
    {"word": "vendejo", "meaning": "店", "example": "La vendejo malfermiĝas je la naŭa horo."},
    {"word": "stacio", "meaning": "駅", "example": "La stacio estas proksime de mia domo."},
    {"word": "parko", "meaning": "公園", "example": "La parko estas granda kaj verda."},
    {"word": "hospitalo", "meaning": "病院", "example": "Ŝi laboras en hospitalo."},
    {"word": "biblioteko", "meaning": "図書館", "example": "Mi studas en la biblioteko."},
    {"word": "aŭto", "meaning": "車", "example": "Li veturas per ruĝa aŭto."},
    {"word": "trajno", "meaning": "電車・列車", "example": "La trajno malfruas hodiaŭ."},
    {"word": "biciklo", "meaning": "自転車", "example": "Mi volas novan biciklon."},
    {"word": "ĵurnalo", "meaning": "新聞", "example": "Mi legas ĵurnalon matene."},
    {"word": "manĝi", "meaning": "食べる", "example": "Ni manĝas kune."},
    {"word": "trinki", "meaning": "飲む", "example": "Mi trinkas teon post la manĝo."},
    {"word": "iri", "meaning": "行く", "example": "Mi iras al la lernejo piede."},
    {"word": "veni", "meaning": "来る", "example": "Venu ĉi tien, bonvolu."},
    {"word": "vidi", "meaning": "見る", "example": "Mi vidas birdon en la arbo."},
    {"word": "aŭdi", "meaning": "聞く", "example": "Mi aŭdas belan muzikon."},
    {"word": "paroli", "meaning": "話す", "example": "Ŝi parolas Esperanton tre bone."},
    {"word": "legi", "meaning": "読む", "example": "Mi legas libron ĉiuvespere."},
    {"word": "skribi", "meaning": "書く", "example": "Bonvolu skribi vian nomon."},
    {"word": "lerni", "meaning": "学ぶ", "example": "Mi lernas Esperanton."},
    {"word": "labori", "meaning": "働く", "example": "Ŝi laboras tre multe."},
    {"word": "dormi", "meaning": "眠る", "example": "Mi dormas ok horojn."},
    {"word": "ludi", "meaning": "遊ぶ", "example": "La infanoj ludas ekstere."},
    {"word": "kanti", "meaning": "歌う", "example": "Ŝi kantas tre bele."},
    {"word": "danci", "meaning": "踊る", "example": "Ili dancas kune."},
    {"word": "naĝi", "meaning": "泳ぐ", "example": "Ni naĝas en la rivero somere."},
    {"word": "kuri", "meaning": "走る", "example": "Li kuras ĉiun matenon."},
    {"word": "marŝi", "meaning": "歩く", "example": "Mi marŝas al la stacio."},
    {"word": "ami", "meaning": "愛する・大好き", "example": "Mi amas mian familion."},
    {"word": "ŝati", "meaning": "好き・気に入る", "example": "Mi ŝatas muzikon."},
    {"word": "voli", "meaning": "欲しい・〜したい", "example": "Mi volas trinki akvon."},
    {"word": "povi", "meaning": "できる", "example": "Mi povas helpi vin."},
    {"word": "devi", "meaning": "〜しなければならない", "example": "Mi devas lerni hodiaŭ."},
    {"word": "scii", "meaning": "知っている", "example": "Mi scias lian nomon."},
    {"word": "pensi", "meaning": "思う・考える", "example": "Mi pensas same kiel vi."},
    {"word": "helpi", "meaning": "助ける", "example": "Bonvolu helpi min."},
    {"word": "aĉeti", "meaning": "買う", "example": "Mi aĉetas panon en la vendejo."},
    {"word": "fari", "meaning": "する・作る", "example": "Ni faras kukon kune."},
    {"word": "loĝi", "meaning": "住む", "example": "Mi loĝas en Japanio."},
    {"word": "vojaĝi", "meaning": "旅行する", "example": "Ili vojaĝas al Eŭropo."},
    {"word": "granda", "meaning": "大きい", "example": "La domo estas granda."},
    {"word": "malgranda", "meaning": "小さい", "example": "La kato estas malgranda."},
    {"word": "bona", "meaning": "良い", "example": "Tio estas bona ideo."},
    {"word": "nova", "meaning": "新しい", "example": "Ŝi havas novan telefonon."},
    {"word": "malnova", "meaning": "古い", "example": "Tio estas malnova domo."},
    {"word": "varma", "meaning": "暖かい・熱い", "example": "Hodiaŭ estas varma tago."},
    {"word": "malvarma", "meaning": "寒い・冷たい", "example": "La akvo estas malvarma."},
    {"word": "ĥoro", "meaning": "合唱団・コーラス", "example": "La ĥoro kantas bele."},
    {"word": "malfacila", "meaning": "難しい", "example": "La ekzameno estas malfacila."},
    {"word": "feliĉa", "meaning": "幸せな・うれしい", "example": "Mi estas feliĉa hodiaŭ."},
]


ENGACHA_TEMPLATE = r"""
  <h1>🇬🇧 英単語ガチャ</h1>
  <p class="howto">「ガチャを引く」を押すと、英単語（日常的な基礎単語）が1つランダムで出ます。カタカナ読み・日本語訳・例文つき。全 {{ total }} 語のコレクション完成を目指そう。引いた単語はこのページを開いている間だけ記録されます（履歴保存はありません）。</p>
  __FLASH__
  <div class="card">
    <form method="post" action="{{ url_for('engacha_draw') }}" class="row">
      <button type="submit">🎰 ガチャを引く</button>
    </form>
    {% if card %}
      <div style="text-align:center; margin-top:16px;">
        <div style="font-size:40px; font-weight:bold;">{{ card.word }}</div>
        <div style="font-size:18px;">{{ card.kana }}</div>
        <div style="font-size:18px; margin-top:4px;">{{ card.meaning }}</div>
        {% if is_new %}<p class="result">🆕 新しい単語をゲット！</p>{% endif %}
        <p style="margin-top:12px;">{{ card.example }}</p>
      </div>
    {% else %}
      <p class="muted" style="margin-top:12px;">まだ引いていません。ガチャを引いてみよう。</p>
    {% endif %}
    <p class="result">ベスト（集めた種類数）: {{ best if best is not none else '—' }}{% if best is not none %} / {{ total }} 種{% endif %}</p>
  </div>
  <div class="card">
    <h3 style="margin:0 0 8px;">📖 コレクション（<span id="kindCount">{{ kinds }}</span> / {{ total }} 種）</h3>
    {% if word_list %}
      <table>
        {% for w in word_list %}
          <tr><td>{{ w.word }}</td><td class="muted">{{ w.kana }}</td><td class="muted">{{ w.meaning }}</td></tr>
        {% endfor %}
      </table>
    {% else %}
      <p class="muted">まだ単語を集めていません。</p>
    {% endif %}
    <form method="post" action="{{ url_for('engacha_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">コレクションをリセット</button>
    </form>
  </div>
"""


def render_engacha():
    collected = session.get("en_collected", [])
    last = session.get("en_last")
    card = EN_WORDS[last] if isinstance(last, int) and 0 <= last < len(EN_WORDS) else None
    body = render_template_string(
        ENGACHA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        total=len(EN_WORDS),
        kinds=len(collected),
        word_list=[EN_WORDS[i] for i in collected],
        card=card,
        is_new=bool(session.get("en_last_new")),
        best=best_score("engacha", "max"),
    )
    return game_page("英単語ガチャ", body)


@app.route("/games/engacha", methods=["GET"])
def engacha():
    return render_engacha()


@app.route("/games/engacha/draw", methods=["POST"])
def engacha_draw():
    idx = random.randrange(len(EN_WORDS))
    collected = list(session.get("en_collected", []))
    is_new = idx not in collected
    if is_new:
        collected.append(idx)
        session["en_collected"] = collected
        record_score("engacha", len(collected))
    session["en_last"] = idx
    session["en_last_new"] = is_new
    return redirect(url_for("engacha"))


@app.route("/games/engacha/reset", methods=["POST"])
def engacha_reset():
    session.pop("en_collected", None)
    session.pop("en_last", None)
    session.pop("en_last_new", None)
    flash("コレクションをリセットしました。", "ok")
    return redirect(url_for("engacha"))


EOGACHA_TEMPLATE = r"""
  <h1>🌟 エスペラント単語ガチャ</h1>
  <p class="howto">「ガチャを引く」を押すと、エスペラントの単語（基礎単語）が1つランダムで出ます。日本語訳・例文つき。全 {{ total }} 語のコレクション完成を目指そう。エスペラントは綴りをそのまま読める言語なので、読みがなは付けていません（ĉ や ĝ のような字上符つき文字もそのまま使っています）。引いた単語はこのページを開いている間だけ記録されます（履歴保存はありません）。</p>
  __FLASH__
  <div class="card">
    <form method="post" action="{{ url_for('eogacha_draw') }}" class="row">
      <button type="submit">🎰 ガチャを引く</button>
    </form>
    {% if card %}
      <div style="text-align:center; margin-top:16px;">
        <div style="font-size:40px; font-weight:bold;">{{ card.word }}</div>
        <div style="font-size:18px; margin-top:4px;">{{ card.meaning }}</div>
        {% if is_new %}<p class="result">🆕 新しい単語をゲット！</p>{% endif %}
        <p style="margin-top:12px;">{{ card.example }}</p>
      </div>
    {% else %}
      <p class="muted" style="margin-top:12px;">まだ引いていません。ガチャを引いてみよう。</p>
    {% endif %}
    <p class="result">ベスト（集めた種類数）: {{ best if best is not none else '—' }}{% if best is not none %} / {{ total }} 種{% endif %}</p>
  </div>
  <div class="card">
    <h3 style="margin:0 0 8px;">📖 コレクション（<span id="kindCount">{{ kinds }}</span> / {{ total }} 種）</h3>
    {% if word_list %}
      <table>
        {% for w in word_list %}
          <tr><td>{{ w.word }}</td><td class="muted">{{ w.meaning }}</td></tr>
        {% endfor %}
      </table>
    {% else %}
      <p class="muted">まだ単語を集めていません。</p>
    {% endif %}
    <form method="post" action="{{ url_for('eogacha_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">コレクションをリセット</button>
    </form>
  </div>
"""


def render_eogacha():
    collected = session.get("eo_collected", [])
    last = session.get("eo_last")
    card = EO_WORDS[last] if isinstance(last, int) and 0 <= last < len(EO_WORDS) else None
    body = render_template_string(
        EOGACHA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        total=len(EO_WORDS),
        kinds=len(collected),
        word_list=[EO_WORDS[i] for i in collected],
        card=card,
        is_new=bool(session.get("eo_last_new")),
        best=best_score("eogacha", "max"),
    )
    return game_page("エスペラント単語ガチャ", body)


@app.route("/games/eogacha", methods=["GET"])
def eogacha():
    return render_eogacha()


@app.route("/games/eogacha/draw", methods=["POST"])
def eogacha_draw():
    idx = random.randrange(len(EO_WORDS))
    collected = list(session.get("eo_collected", []))
    is_new = idx not in collected
    if is_new:
        collected.append(idx)
        session["eo_collected"] = collected
        record_score("eogacha", len(collected))
    session["eo_last"] = idx
    session["eo_last_new"] = is_new
    return redirect(url_for("eogacha"))


@app.route("/games/eogacha/reset", methods=["POST"])
def eogacha_reset():
    session.pop("eo_collected", None)
    session.pop("eo_last", None)
    session.pop("eo_last_new", None)
    flash("コレクションをリセットしました。", "ok")
    return redirect(url_for("eogacha"))


# ============================
# 診断ゲーム共通
# ============================
# 1問ずつ表示して選択肢で答えるセッション型。回答ごとにタイプ別ポイントを
# 加算し、全問終わったら最も高いタイプを結果として表示する。
# 同点の場合は、タイプの定義順で先に来るものを優先する（shindan_judge）。
# 数値スコアの記録はしない（診断結果そのものが成果物）。

def shindan_judge(type_keys, scores):
    """最多ポイントのタイプを返す。同点なら定義順で先のタイプを優先。"""
    best_key = type_keys[0]
    best_val = -1
    for key in type_keys:
        val = int(scores.get(key, 0))
        if val > best_val:
            best_key, best_val = key, val
    return best_key


SHINDAN_TEMPLATE = r"""
  <h1>{{ icon }} {{ title }}</h1>
  <p class="howto">{{ howto }}</p>
  __FLASH__
  <div class="card">
    {% if result %}
      <p class="mid">🎉 診断結果</p>
      <div class="big">{{ result.name }}</div>
      <p class="result">{{ result.text }}</p>
      {% if result.tip %}
        <p class="result">💡 {{ result.tip }}</p>
      {% endif %}
      <form method="post" action="{{ reset_url }}" class="row">
        <button type="submit">もう一度診断する</button>
      </form>
    {% else %}
      <p class="mid">第 {{ num }} 問 ／ 全 {{ total }} 問</p>
      <p class="result">{{ question }}</p>
      <form method="post" action="{{ answer_url }}" class="row" style="flex-direction:column; align-items:stretch;">
        {% for label in choices %}
          <button type="submit" name="choice" value="{{ loop.index0 }}">{{ label }}</button>
        {% endfor %}
      </form>
      <form method="post" action="{{ reset_url }}" class="row" style="margin-top:10px;">
        <button type="submit">最初からやり直す</button>
      </form>
    {% endif %}
  </div>
"""


def render_shindan(cfg):
    prefix = cfg["prefix"]
    questions = cfg["questions"]
    if session.get(prefix + "_idx") is None:
        session[prefix + "_idx"] = 0
        session[prefix + "_scores"] = {}
    idx = int(session.get(prefix + "_idx", 0))
    scores = session.get(prefix + "_scores", {})
    if idx >= len(questions):
        info = cfg["types"][shindan_judge(cfg["type_keys"], scores)]
        result = {"name": info["name"], "text": info["text"], "tip": info.get("tip", "")}
        question, choices, num = "", [], len(questions)
    else:
        result = None
        question = questions[idx]["q"]
        choices = [c["label"] for c in questions[idx]["choices"]]
        num = idx + 1
    body = render_template_string(
        SHINDAN_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        icon=cfg["icon"],
        title=cfg["title"],
        howto=cfg["howto"],
        result=result,
        num=num,
        total=len(questions),
        question=question,
        choices=choices,
        answer_url=url_for(cfg["endpoint"] + "_answer"),
        reset_url=url_for(cfg["endpoint"] + "_reset"),
    )
    return game_page(cfg["title"], body)


def shindan_handle_answer(cfg):
    prefix = cfg["prefix"]
    questions = cfg["questions"]
    if session.get(prefix + "_idx") is None:
        session[prefix + "_idx"] = 0
        session[prefix + "_scores"] = {}
    idx = int(session.get(prefix + "_idx", 0))
    if idx >= len(questions):
        return redirect(url_for(cfg["endpoint"]))
    raw = request.form.get("choice", "").strip()
    if raw.isdigit():
        choice_idx = int(raw)
        choices = questions[idx]["choices"]
        if 0 <= choice_idx < len(choices):
            scores = dict(session.get(prefix + "_scores", {}))
            type_key = choices[choice_idx]["type"]
            scores[type_key] = int(scores.get(type_key, 0)) + 1
            session[prefix + "_scores"] = scores
            session[prefix + "_idx"] = idx + 1
    return redirect(url_for(cfg["endpoint"]))


def shindan_handle_reset(cfg):
    prefix = cfg["prefix"]
    session.pop(prefix + "_idx", None)
    session.pop(prefix + "_scores", None)
    flash("最初からやり直します。", "ok")
    return redirect(url_for(cfg["endpoint"]))


# ============================
# 三人娘タイプ診断
# ============================
TRIO_TYPES = {
    "cocoa": {
        "name": "ココア型",
        "text": "知的で感情豊かなタイプ。考えごとが好きで、ふとした日常の中にも意味や面白さを見つけます。自分の世界を大切にしながら、人の気持ちの変化にも敏感です。たまに哲学っぽいことを言い出すのも、このタイプのご愛敬。",
    },
    "mocha": {
        "name": "モカ型",
        "text": "論理的で冷静なタイプ。計画と整理が得意で、物事を順序立てて考えるのが上手です。面倒見がよく、周りの世話を焼く優しさがあります。困ったときに頼られる、縁の下の力持ちです。",
    },
    "chai": {
        "name": "チャイ型",
        "text": "活発で直感的なタイプ。思いつきと行動力で場を動かすムードメーカーです。素直で明るく、一緒にいる人を元気にします。その場のノリを楽しむ天才です。",
    },
}

TRIO_QUESTIONS = [
    {"q": "休みの日、気づいたら何をしていることが多い？", "choices": [
        {"label": "本や記事を読みながら、つい考えごとにふける", "type": "cocoa"},
        {"label": "部屋を片付けて、来週の予定を整理している", "type": "mocha"},
        {"label": "思いつきで出かけたり、誰かを誘ったりしている", "type": "chai"},
    ]},
    {"q": "困ったことが起きたとき、まずどうする？", "choices": [
        {"label": "状況を整理して、やることリストを作る", "type": "mocha"},
        {"label": "ひとりでじっくり原因を考える", "type": "cocoa"},
        {"label": "とりあえず動いてみる。誰かに相談もする", "type": "chai"},
    ]},
    {"q": "飲み物を選ぶなら、どれが近い？", "choices": [
        {"label": "チャイやジュース。その日の気分で決めたい", "type": "chai"},
        {"label": "ココア。ゆっくり味わいたい", "type": "cocoa"},
        {"label": "モカなどのコーヒー。きりっとしたい", "type": "mocha"},
    ]},
    {"q": "買い物に行くと、どうなりがち？", "choices": [
        {"label": "気になる本や小物をじっくり眺めてしまう", "type": "cocoa"},
        {"label": "目についた面白そうなものをつい買ってしまう", "type": "chai"},
        {"label": "必要なものをリストどおりに買って終わる", "type": "mocha"},
    ]},
    {"q": "グループで集まると、あなたの役回りは？", "choices": [
        {"label": "進行役。段取りを整えることが多い", "type": "mocha"},
        {"label": "盛り上げ役。場を明るくする", "type": "chai"},
        {"label": "話題を深掘りする役。意見を出す", "type": "cocoa"},
    ]},
    {"q": "あなたの部屋の様子に近いのは？", "choices": [
        {"label": "そのときの趣味のものが広がっている", "type": "chai"},
        {"label": "本や好きなものが積んである、味のある散らかり方", "type": "cocoa"},
        {"label": "物の定位置が決まっていて、整っている", "type": "mocha"},
    ]},
    {"q": "旅行に行くなら、楽しみなのは？", "choices": [
        {"label": "行き先の歴史や物語を調べること", "type": "cocoa"},
        {"label": "スケジュールと持ち物をきっちり決めること", "type": "mocha"},
        {"label": "細かいことは決めず、その場のノリで動くこと", "type": "chai"},
    ]},
    {"q": "夕食のあとの過ごし方は？", "choices": [
        {"label": "みんなでおしゃべりやゲームをして過ごす", "type": "chai"},
        {"label": "明日の準備をして、早めに休む", "type": "mocha"},
        {"label": "音楽や本と一緒に、自分の時間を味わう", "type": "cocoa"},
    ]},
]

TRIO_CFG = {
    "prefix": "strio",
    "endpoint": "shindan_trio",
    "icon": "☕",
    "title": "三人娘タイプ診断",
    "howto": "8つの質問に答えると、ココア・モカ・チャイの3人のうち、どのタイプに近いかを診断します。直感で選んでみてください。",
    "type_keys": ["cocoa", "mocha", "chai"],
    "types": TRIO_TYPES,
    "questions": TRIO_QUESTIONS,
}


@app.route("/games/shindan-trio", methods=["GET"])
def shindan_trio():
    return render_shindan(TRIO_CFG)


@app.route("/games/shindan-trio/answer", methods=["POST"])
def shindan_trio_answer():
    return shindan_handle_answer(TRIO_CFG)


@app.route("/games/shindan-trio/reset", methods=["POST"])
def shindan_trio_reset():
    return shindan_handle_reset(TRIO_CFG)


# ============================
# 今日のおやつ診断
# ============================
SNACK_TYPES = {
    "cake": {
        "name": "ケーキ",
        "text": "ご褒美気分の今日はケーキ。ふわっとした甘さと満足感で、気分までふんわり上向きになりそうです。",
    },
    "wagashi": {
        "name": "和菓子（団子・大福）",
        "text": "ほっと落ち着きたい今日は和菓子。控えめな甘さともちもちの食感で、ゆっくり一息つきましょう。",
    },
    "chocolate": {
        "name": "チョコレート",
        "text": "集中の合間の味方はチョコレート。ひとかけらで頭と気分を切り替えて、もうひとがんばり。",
    },
    "snack": {
        "name": "スナック菓子（しょっぱい系）",
        "text": "今日は塩気が正解。サクサクのスナック菓子で、小腹も気分もリフレッシュしましょう。",
    },
    "pudding": {
        "name": "プリン・ゼリー",
        "text": "なめらかで優しいプリン・ゼリー。疲れた日でもすっと入る、癒やしのおやつです。",
    },
    "drink": {
        "name": "温かいドリンクと焼き菓子",
        "text": "温かいドリンクと焼き菓子の組み合わせで、ゆっくり時間を味わうのが今日の正解。香ばしさと温かさでほっとできます。",
    },
}

SNACK_QUESTIONS = [
    {"q": "今の気分に一番近いのは？", "choices": [
        {"label": "ふんわり甘いもので癒やされたい", "type": "pudding"},
        {"label": "しっかり甘くて満足感がほしい", "type": "cake"},
        {"label": "ほっと落ち着きたい", "type": "wagashi"},
        {"label": "塩気でリフレッシュしたい", "type": "snack"},
    ]},
    {"q": "お腹の空き具合は？", "choices": [
        {"label": "かなり空いた。がっつりいきたい", "type": "cake"},
        {"label": "小腹が空いた程度", "type": "snack"},
        {"label": "ほぼ空いていない。気分転換に少しだけ", "type": "chocolate"},
        {"label": "飲みもので十分", "type": "drink"},
    ]},
    {"q": "好きな食感は？", "choices": [
        {"label": "とろける・なめらか", "type": "pudding"},
        {"label": "サクサク・パリパリ", "type": "snack"},
        {"label": "もちもち", "type": "wagashi"},
        {"label": "ふわふわ・しっとり", "type": "cake"},
    ]},
    {"q": "甘さの好みは？", "choices": [
        {"label": "控えめで上品な甘さ", "type": "wagashi"},
        {"label": "濃厚な甘さ", "type": "chocolate"},
        {"label": "ほどよい甘さ", "type": "pudding"},
        {"label": "甘さより香ばしさ", "type": "drink"},
    ]},
    {"q": "今のシーンは？", "choices": [
        {"label": "家でゆっくり過ごしている", "type": "drink"},
        {"label": "仕事や勉強の合間", "type": "chocolate"},
        {"label": "外出先でさくっと済ませたい", "type": "snack"},
        {"label": "誰かと一緒にいる", "type": "cake"},
    ]},
    {"q": "今日はどんな日？", "choices": [
        {"label": "晴れて活動的な日", "type": "snack"},
        {"label": "雨でのんびりな日", "type": "drink"},
        {"label": "肌寒くて温まりたい日", "type": "wagashi"},
        {"label": "自分へのご褒美の日", "type": "cake"},
    ]},
]

SNACK_CFG = {
    "prefix": "ssnack",
    "endpoint": "shindan_snack",
    "icon": "🍮",
    "title": "今日のおやつ診断",
    "howto": "気分や空腹度などを聞く6つの質問で、今日のおすすめおやつを診断します。迷ったときのおやつ決めにどうぞ。",
    "type_keys": ["cake", "wagashi", "chocolate", "snack", "pudding", "drink"],
    "types": SNACK_TYPES,
    "questions": SNACK_QUESTIONS,
}


@app.route("/games/shindan-snack", methods=["GET"])
def shindan_snack():
    return render_shindan(SNACK_CFG)


@app.route("/games/shindan-snack/answer", methods=["POST"])
def shindan_snack_answer():
    return shindan_handle_answer(SNACK_CFG)


@app.route("/games/shindan-snack/reset", methods=["POST"])
def shindan_snack_reset():
    return shindan_handle_reset(SNACK_CFG)


# ============================
# べんきょうタイプ診断
# ============================
STUDY_TYPES = {
    "plan": {
        "name": "計画コツコツ型",
        "text": "決めたことを少しずつ積み上げるのが得意なタイプ。計画と記録が、そのまま力になります。",
        "tip": "計画は「今日の分」まで小さく区切っておくと、ズレた日も立て直しやすくなります。",
    },
    "burst": {
        "name": "短期集中型",
        "text": "追い込みの瞬発力が持ち味のタイプ。締切が近づいたときの集中力は随一です。",
        "tip": "詰め込みの前に「やる範囲のリスト」だけ先に作っておくと、集中の質が上がります。",
    },
    "mypace": {
        "name": "気分マイペース型",
        "text": "気持ちが乗ったときの伸びが大きいタイプ。楽しさが、続ける力になります。",
        "tip": "やる気待ちの日にも始められるよう、5分だけ触る「入口タスク」を用意しておくのがおすすめです。",
    },
    "env": {
        "name": "環境こだわり型",
        "text": "場所や道具が整うと力が出るタイプ。環境づくりも、勉強の一部として楽しめます。",
        "tip": "お気に入りの場所と道具のセットを決めておくと、始めるまでの迷いが減ります。",
    },
}

STUDY_QUESTIONS = [
    {"q": "勉強を始めるタイミングは？", "choices": [
        {"label": "決めた時間に机に向かう", "type": "plan"},
        {"label": "締切が見えてきてから一気に", "type": "burst"},
        {"label": "やる気が出たときに", "type": "mypace"},
        {"label": "お気に入りの場所に行けたときに", "type": "env"},
    ]},
    {"q": "計画の立て方は？", "choices": [
        {"label": "直前の数日で詰め込む前提で組む", "type": "burst"},
        {"label": "1週間から1か月の計画を細かく立てる", "type": "plan"},
        {"label": "まず勉強する場所と道具を整える", "type": "env"},
        {"label": "計画はざっくり、あとは気分で", "type": "mypace"},
    ]},
    {"q": "休憩の取り方は？", "choices": [
        {"label": "時間を決めてきっちり区切る", "type": "plan"},
        {"label": "疲れたらすぐ休む", "type": "mypace"},
        {"label": "区切りがつくまでぶっ続け", "type": "burst"},
        {"label": "場所を変えてリフレッシュする", "type": "env"},
    ]},
    {"q": "苦手な科目にはどう向き合う？", "choices": [
        {"label": "少しずつ毎日触れる", "type": "plan"},
        {"label": "好きな科目の合間に混ぜる", "type": "mypace"},
        {"label": "短期間で集中的に潰す", "type": "burst"},
        {"label": "参考書やツールを新しくして気分一新", "type": "env"},
    ]},
    {"q": "勉強の記録については？", "choices": [
        {"label": "学習ログを毎日つける", "type": "plan"},
        {"label": "記録は気が向いたときだけ", "type": "mypace"},
        {"label": "テスト前にまとめて振り返る", "type": "burst"},
        {"label": "ノートの見た目や道具にこだわる", "type": "env"},
    ]},
    {"q": "集中が切れたらどうする？", "choices": [
        {"label": "場所を変えたり散歩したりする", "type": "env"},
        {"label": "今日の分は最低限やって終える", "type": "plan"},
        {"label": "いったん寝て、起きてから再集中", "type": "burst"},
        {"label": "別の科目や作業に切り替える", "type": "mypace"},
    ]},
    {"q": "目標の決め方は？", "choices": [
        {"label": "「この試験に受かる」と大きく決める", "type": "burst"},
        {"label": "数値や範囲で具体的に決める", "type": "plan"},
        {"label": "楽しみながら続けられる量で決める", "type": "mypace"},
        {"label": "行きたい場所や使いたい道具とセットで決める", "type": "env"},
    ]},
    {"q": "振り返りはどうする？", "choices": [
        {"label": "計画とのズレを確認して直す", "type": "plan"},
        {"label": "あまり振り返らない。そのとき学べれば十分", "type": "mypace"},
        {"label": "結果だけ見て次に活かす", "type": "burst"},
        {"label": "環境や道具の改善点をメモする", "type": "env"},
    ]},
]

STUDY_CFG = {
    "prefix": "sstudy",
    "endpoint": "shindan_study",
    "icon": "📚",
    "title": "べんきょうタイプ診断",
    "howto": "勉強の進め方を聞く8つの質問で、あなたの学習タイプを診断します。タイプに合った小さな勉強のコツつき。",
    "type_keys": ["plan", "burst", "mypace", "env"],
    "types": STUDY_TYPES,
    "questions": STUDY_QUESTIONS,
}


@app.route("/games/shindan-study", methods=["GET"])
def shindan_study():
    return render_shindan(STUDY_CFG)


@app.route("/games/shindan-study/answer", methods=["POST"])
def shindan_study_answer():
    return shindan_handle_answer(STUDY_CFG)


@app.route("/games/shindan-study/reset", methods=["POST"])
def shindan_study_reset():
    return shindan_handle_reset(STUDY_CFG)


# ============================
# ドット絵ボード
# 単体ツール「dotboard」のポータル版。描画はブラウザ側で行い、
# サーバーは「描けた！」の完成記録（セッション内の完成数）だけを持つ。
# ============================
DOTBOARD_COLORS = [
    "#000000", "#ffffff", "#e03131", "#f08c00",
    "#ffd43b", "#2f9e44", "#1971c2", "#74c0fc",
    "#9775fa", "#f783ac", "#a0522d", "#868e96",
]

DOTBOARD_THEMES = [
    "りんご", "ねこ", "さかな", "くるま",
    "はな", "ほし", "つき", "ケーキ",
    "ロボット", "きのこ", "とり", "いえ",
    "でんしゃ", "かさ", "ゆきだるま", "かめ",
]

DOTBOARD_TEMPLATE = r"""
  <h1>👾 ドット絵ボード</h1>
  <p class="howto">16×16 のキャンバスにドット絵を描くボードです。色を選んで、クリックやドラッグで描いてください。「お題を引く」で題材を決めて描くのもおすすめ。描けたら「描けた！」で完成を記録できます（お題がなくても自由作品でOK）。</p>
  __FLASH__
  <div class="card">
    <p class="mid">🎲 お題: <span id="themeLabel">まだ引いていません</span></p>
    <div class="row" style="margin-bottom:12px;">
      <button id="themeBtn" type="button">お題を引く</button>
    </div>
    <div id="palette" style="text-align:center; margin-bottom:10px;">
      {% for c in colors %}<button type="button" class="dotswatch" data-color="{{ c }}" title="{{ c }}" style="background:{{ c }}; width:30px; height:30px; padding:0; border-radius:6px; margin:2px;"></button>{% endfor %}
      <button type="button" id="eraser" style="margin:2px;">🧽 消しゴム</button>
    </div>
    <div style="text-align:center;">
      <canvas id="board" width="16" height="16" style="width:min(384px, 90vw); height:min(384px, 90vw); border:1px solid #999; image-rendering:pixelated; touch-action:none; background:#fff;"></canvas>
    </div>
    <div class="row" style="margin-top:12px;">
      <button id="clearBtn" type="button">ぜんぶ消す</button>
      <button id="saveBtn" type="button">PNGで保存</button>
      <button id="doneBtn" type="button">🎉 描けた！</button>
    </div>
    <p class="result" id="doneMessage">完成した作品数: <span id="doneCount">{{ session_count }}</span> ／ ベスト（完成作品数）: <span id="bestCount">{{ best if best is not none else '—' }}</span></p>
    <p class="muted" style="text-align:center;">完成数はこのブラウザのセッションで数えます。ベストはサーバーに残りますが、再デプロイ等で消えることがあります。</p>
  </div>
<script>
(function(){
  var themes = {{ themes|tojson }};
  var canvas = document.getElementById("board");
  var ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, 16, 16);
  var color = "{{ colors[0] }}";
  var drawing = false;
  var swatches = Array.prototype.slice.call(document.querySelectorAll(".dotswatch"));
  function markSelected(target){
    swatches.forEach(function(s){ s.style.outline = (s === target) ? "3px solid #333" : ""; });
    document.getElementById("eraser").style.outline = (target === "eraser") ? "3px solid #333" : "";
  }
  markSelected(swatches[0]);
  document.getElementById("palette").addEventListener("click", function(e){
    var btn = e.target.closest(".dotswatch");
    if (btn) {
      color = btn.dataset.color;
      markSelected(btn);
    }
  });
  document.getElementById("eraser").addEventListener("click", function(){
    color = "#ffffff";
    markSelected("eraser");
  });
  function pos(clientX, clientY){
    var r = canvas.getBoundingClientRect();
    var x = Math.floor((clientX - r.left) / r.width * 16);
    var y = Math.floor((clientY - r.top) / r.height * 16);
    return [x, y];
  }
  function paint(clientX, clientY){
    var p = pos(clientX, clientY);
    if (p[0] < 0 || p[0] > 15 || p[1] < 0 || p[1] > 15) { return; }
    ctx.fillStyle = color;
    ctx.fillRect(p[0], p[1], 1, 1);
  }
  canvas.addEventListener("mousedown", function(e){ drawing = true; paint(e.clientX, e.clientY); });
  canvas.addEventListener("mousemove", function(e){ if (drawing) { paint(e.clientX, e.clientY); } });
  window.addEventListener("mouseup", function(){ drawing = false; });
  canvas.addEventListener("touchstart", function(e){ e.preventDefault(); paint(e.touches[0].clientX, e.touches[0].clientY); }, {passive: false});
  canvas.addEventListener("touchmove", function(e){ e.preventDefault(); paint(e.touches[0].clientX, e.touches[0].clientY); }, {passive: false});
  document.getElementById("themeBtn").addEventListener("click", function(){
    var t = themes[Math.floor(Math.random() * themes.length)];
    document.getElementById("themeLabel").textContent = t;
  });
  document.getElementById("clearBtn").addEventListener("click", function(){
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, 16, 16);
  });
  document.getElementById("saveBtn").addEventListener("click", function(){
    var out = document.createElement("canvas");
    out.width = 384; out.height = 384;
    var octx = out.getContext("2d");
    octx.imageSmoothingEnabled = false;
    octx.drawImage(canvas, 0, 0, 384, 384);
    var a = document.createElement("a");
    a.href = out.toDataURL("image/png");
    a.download = "dotboard.png";
    a.click();
  });
  document.getElementById("doneBtn").addEventListener("click", function(){
    fetch("{{ url_for('dotboard_complete') }}", {method: "POST"})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          document.getElementById("doneCount").textContent = String(d.count);
          document.getElementById("bestCount").textContent = String(d.best);
          document.getElementById("doneMessage").firstChild.textContent = "🎉 完成！ 完成した作品数: ";
        }
      })
      .catch(function(){});
  });
})();
</script>
"""


def render_dotboard() -> str:
    body = render_template_string(
        DOTBOARD_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        colors=DOTBOARD_COLORS,
        themes=DOTBOARD_THEMES,
        best=best_score("dotboard", "max"),
        session_count=int(session.get("dotboard_done", 0)),
    )
    return game_page("ドット絵ボード", body)


@app.route("/games/dotboard", methods=["GET"])
def dotboard():
    return render_dotboard()


@app.route("/games/dotboard/complete", methods=["POST"])
def dotboard_complete():
    count = int(session.get("dotboard_done", 0)) + 1
    session["dotboard_done"] = count
    record_score("dotboard", count)
    return {"ok": True, "best": best_score("dotboard", "max"), "count": count}


# ============================
# スライドパズル
# 盤面はサーバー側セッションで管理する（空きマスは 0）。
# 初期配置は完成状態からランダムにスライドさせて作るので、必ず解ける。
# ============================
SLIDEPUZZLE_GOAL = [1, 2, 3, 4, 5, 6, 7, 8, 0]


def slidepuzzle_neighbors(index: int) -> list:
    """3×3盤面で index の上下左右にあるマスの index 一覧。"""
    row, col = divmod(index, 3)
    result = []
    if row > 0:
        result.append(index - 3)
    if row < 2:
        result.append(index + 3)
    if col > 0:
        result.append(index - 1)
    if col < 2:
        result.append(index + 1)
    return result


def slidepuzzle_is_solved(board) -> bool:
    return list(board) == SLIDEPUZZLE_GOAL


def slidepuzzle_try_move(board, index: int):
    """index のパネルが空きマスに隣接していれば動かした新しい盤面を返し、
    動かせなければ None を返す。"""
    board = list(board)
    if not (0 <= index < 9) or board[index] == 0:
        return None
    blank = board.index(0)
    if blank not in slidepuzzle_neighbors(index):
        return None
    board[blank], board[index] = board[index], board[blank]
    return board


def slidepuzzle_new_board(moves: int = 60):
    """完成状態からランダムにスライドさせて作る、必ず解ける初期配置。
    直前に動かしたパネルをすぐ戻す手は選ばない（無駄な往復を減らす）。"""
    while True:
        board = list(SLIDEPUZZLE_GOAL)
        blank = 8
        prev_blank = -1
        for _ in range(moves):
            options = [i for i in slidepuzzle_neighbors(blank) if i != prev_blank]
            nxt = random.choice(options)
            board[blank], board[nxt] = board[nxt], board[blank]
            prev_blank, blank = blank, nxt
        if not slidepuzzle_is_solved(board):
            return board


def slidepuzzle_new_game() -> None:
    session["sp_board"] = slidepuzzle_new_board()
    session["sp_moves"] = 0
    session["sp_done"] = False


SLIDEPUZZLE_TEMPLATE = r"""
  <h1>🧩 スライドパズル</h1>
  <p class="howto">1〜8のパネルを、空きマスの上下左右からスライドさせて、左上から 1→8 の順に揃えるパズルです。初期配置は必ず解けるようになっています。完成までの手数を記録します（ベスト＝最小手数）。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">手数: {{ moves }} ／ ベスト（最小手数）: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('slidepuzzle_move') }}">
      <div style="display:grid; grid-template-columns: repeat(3, 76px); gap:8px; justify-content:center;">
        {% for i in range(9) %}
          {% if board[i] == 0 %}
            <button type="button" disabled style="height:76px; font-size:26px; background:#eee; border-style:dashed;">&nbsp;</button>
          {% elif done %}
            <button type="button" disabled style="height:76px; font-size:26px;">{{ board[i] }}</button>
          {% else %}
            <button type="submit" name="index" value="{{ i }}" style="height:76px; font-size:26px;">{{ board[i] }}</button>
          {% endif %}
        {% endfor %}
      </div>
    </form>
    <form method="post" action="{{ url_for('slidepuzzle_reset') }}" class="row" style="margin-top:12px;">
      <button type="submit">シャッフルし直す</button>
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


def render_slidepuzzle(message=None):
    if "sp_board" not in session:
        slidepuzzle_new_game()
    body = render_template_string(
        SLIDEPUZZLE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        board=list(session["sp_board"]),
        moves=int(session.get("sp_moves", 0)),
        done=bool(session.get("sp_done", False)),
        best=best_score("slidepuzzle", "min"),
        history=recent_scores("slidepuzzle", 10),
        message=message,
    )
    return game_page("スライドパズル", body)


@app.route("/games/slidepuzzle", methods=["GET"])
def slidepuzzle():
    return render_slidepuzzle()


@app.route("/games/slidepuzzle/move", methods=["POST"])
def slidepuzzle_move():
    if "sp_board" not in session:
        slidepuzzle_new_game()
    if session.get("sp_done"):
        return render_slidepuzzle()
    raw = request.form.get("index", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < 9):
        return render_slidepuzzle()
    board = slidepuzzle_try_move(session["sp_board"], int(raw))
    if board is None:
        return render_slidepuzzle(
            message="そのパネルは動かせません。空きマスの上下左右のパネルを選んでね。"
        )
    moves = int(session.get("sp_moves", 0)) + 1
    session["sp_board"] = board
    session["sp_moves"] = moves
    if slidepuzzle_is_solved(board):
        session["sp_done"] = True
        record_score("slidepuzzle", moves)
        return render_slidepuzzle(message=f"🎉 完成！ {moves} 手で揃えました。")
    return render_slidepuzzle()


@app.route("/games/slidepuzzle/reset", methods=["POST"])
def slidepuzzle_reset():
    slidepuzzle_new_game()
    flash("シャッフルし直しました。", "ok")
    return redirect(url_for("slidepuzzle"))


# ============================
# 1→25タッチ
# 計測はクライアント JS、配置はサーバーでシャッフルして渡す。
# スコアは秒×10（0.1秒単位）の整数で記録する（ベスト＝最小）。
# ============================
TOUCH25_TEMPLATE = r"""
  <h1>👆 1→25タッチ</h1>
  <p class="howto">5×5に散らばった 1〜25 の数字を、1から順番にタッチしていくタイムアタックです。「スタート」を押すと計測開始。間違えた数字を押しても光って知らせるだけで、そのまま続けられます。</p>
  __FLASH__
  <div class="card">
    <div id="grid" style="display:grid; grid-template-columns: repeat(5, 1fr); gap:8px; max-width:360px; margin:0 auto;">
      {% for n in numbers %}
        <button type="button" data-value="{{ n }}" disabled style="font-size:20px; padding:12px 0;">{{ n }}</button>
      {% endfor %}
    </div>
    <p class="result" id="bestline">ベスト（最速）: {{ best_disp if best_disp is not none else '—' }}{% if best_disp is not none %} 秒{% endif %}</p>
    <p class="result" id="message">「スタート」を押してね</p>
    <p class="mid">経過: <span id="timer">0.0</span> 秒 ／ 次は <span id="next">1</span></p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
      <button type="button" onclick="location.reload()">並べ直す</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ '%.1f' % (s.score / 10) }} 秒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var message = document.getElementById("message");
  var timerEl = document.getElementById("timer");
  var nextEl = document.getElementById("next");
  var startBtn = document.getElementById("startBtn");
  var buttons = document.querySelectorAll("#grid button");
  var expected = 1, startedAt = 0, timerId = null, playing = false;
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    startedAt = performance.now();
    startBtn.disabled = true;
    buttons.forEach(function(btn){ btn.disabled = false; });
    message.textContent = "次は 1 を押してね";
    timerId = setInterval(function(){
      timerEl.textContent = ((performance.now() - startedAt) / 1000).toFixed(1);
    }, 100);
  });
  buttons.forEach(function(btn){
    btn.addEventListener("click", function(){
      if (!playing || btn.disabled) { return; }
      var value = parseInt(btn.getAttribute("data-value"), 10);
      if (value !== expected) {
        var old = btn.style.background;
        btn.style.background = "#f8c9c9";
        message.textContent = "それは " + value + "。次は " + expected + " を押してね";
        setTimeout(function(){ btn.style.background = old; }, 350);
        return;
      }
      btn.disabled = true;
      btn.style.background = "#bfe8bf";
      btn.style.borderColor = "#7ab87a";
      expected += 1;
      if (expected > 25) {
        playing = false;
        clearInterval(timerId);
        var ds = Math.round((performance.now() - startedAt) / 100);
        timerEl.textContent = (ds / 10).toFixed(1);
        var form = new FormData();
        form.append("ds", String(ds));
        fetch("{{ url_for('touch25_score') }}", {method: "POST", body: form})
          .then(function(r){ return r.json(); })
          .then(function(d){
            if (d && d.ok) {
              message.textContent = "🎉 完了！ " + (ds / 10).toFixed(1) + " 秒";
              document.getElementById("bestline").textContent = "ベスト（最速）: " + (d.best / 10).toFixed(1) + " 秒";
            }
          })
          .catch(function(){});
      } else {
        nextEl.textContent = String(expected);
        message.textContent = "次は " + expected + " を押してね";
      }
    });
  });
})();
</script>
"""


@app.route("/games/touch25", methods=["GET"])
def touch25():
    numbers = list(range(1, 26))
    random.shuffle(numbers)
    best = best_score("touch25", "min")
    body = render_template_string(
        TOUCH25_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        numbers=numbers,
        best_disp=(round(best / 10, 1) if best is not None else None),
        history=recent_scores("touch25", 10),
    )
    return game_page("1→25タッチ", body)


@app.route("/games/touch25/score", methods=["POST"])
def touch25_score():
    raw = request.form.get("ds", "").strip()
    if not raw.isdigit() or not (20 <= int(raw) <= 36000):
        return {"ok": False, "error": "invalid ds"}, 400
    record_score("touch25", int(raw))
    return {"ok": True, "best": best_score("touch25", "min")}


# ============================
# まるばつ対戦
# 盤面・勝敗判定・CPU はサーバー側。プレイヤーは ○、CPU は ×。
# 勝利数は dotboard と同じ流儀で、セッション累計を record_score する。
# ============================
MARUBATSU_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


def marubatsu_winner(board):
    """勝者がいれば '○' か '×'、引き分けなら 'draw'、継続中なら None。"""
    for a, b, c in MARUBATSU_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None


def marubatsu_winning_cell(board, mark: str):
    """mark が次に置けば勝てるマスがあれば、その index（なければ None）。"""
    for i in range(9):
        if board[i] == "":
            trial = list(board)
            trial[i] = mark
            if marubatsu_winner(trial) == mark:
                return i
    return None


def marubatsu_best_move(board, mark: str):
    """CPU の最善手：勝ち手＞相手の勝ち手の阻止＞中央＞角＞辺。空きがなければ None。"""
    opponent = "×" if mark == "○" else "○"
    win = marubatsu_winning_cell(board, mark)
    if win is not None:
        return win
    block = marubatsu_winning_cell(board, opponent)
    if block is not None:
        return block
    for i in (4, 0, 2, 6, 8, 1, 3, 5, 7):
        if board[i] == "":
            return i
    return None


def marubatsu_cpu_move(board, mark: str = "×"):
    """ほどほどの強さの CPU。4回に1回くらいはわざとランダムな手を打つので、
    毎回完璧にはならない。空きがなければ None。"""
    empty = [i for i, v in enumerate(board) if v == ""]
    if not empty:
        return None
    if random.random() < 0.25:
        return random.choice(empty)
    return marubatsu_best_move(board, mark)


def marubatsu_start_board(player_first: bool):
    """新しい対局の盤面を作る。後手のときは CPU が先に1手打つ。"""
    board = [""] * 9
    if not player_first:
        cpu = marubatsu_cpu_move(board, "×")
        if cpu is not None:
            board[cpu] = "×"
    return board


MARUBATSU_TEMPLATE = r"""
  <h1>⭕ まるばつ対戦</h1>
  <p class="howto">三目並べで CPU と対戦。あなたは ○、CPU は × です。縦・横・斜めのどれか1列を先に揃えた方が勝ち。CPU は程よい強さで、たまに本気を出しません。勝利数はこのセッションの累計で記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">このセッションの勝利数: {{ wins }} ／ ベスト（勝利数）: {{ best if best is not none else '—' }}</p>
    {% if board is none %}
      <p class="mid">先手・後手を選んでスタート</p>
      <div class="row">
        <form method="post" action="{{ url_for('marubatsu_start') }}">
          <input type="hidden" name="first" value="1">
          <button type="submit">先手（○が先）で始める</button>
        </form>
        <form method="post" action="{{ url_for('marubatsu_start') }}">
          <input type="hidden" name="first" value="0">
          <button type="submit">後手（CPUが先）で始める</button>
        </form>
      </div>
    {% else %}
      <form method="post" action="{{ url_for('marubatsu_move') }}">
        <div style="display:grid; grid-template-columns: repeat(3, 76px); gap:8px; justify-content:center;">
          {% for i in range(9) %}
            {% if board[i] %}
              <button type="button" disabled style="height:76px; font-size:34px;">{{ board[i] }}</button>
            {% elif over %}
              <button type="button" disabled style="height:76px; font-size:34px;">&nbsp;</button>
            {% else %}
              <button type="submit" name="index" value="{{ i }}" style="height:76px; font-size:34px;">&nbsp;</button>
            {% endif %}
          {% endfor %}
        </div>
      </form>
      <div class="row" style="margin-top:12px;">
        {% if over %}
          <form method="post" action="{{ url_for('marubatsu_next') }}">
            <button type="submit">連戦する</button>
          </form>
        {% endif %}
        <form method="post" action="{{ url_for('marubatsu_reset') }}">
          <button type="submit">先手・後手を選び直す</button>
        </form>
      </div>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（勝利数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 勝</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_marubatsu(message=None):
    board = list(session["mb_board"]) if "mb_board" in session else None
    body = render_template_string(
        MARUBATSU_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        board=board,
        over=bool(session.get("mb_over", False)),
        wins=int(session.get("mb_wins", 0)),
        best=best_score("marubatsu", "max"),
        history=recent_scores("marubatsu", 10),
        message=message,
    )
    return game_page("まるばつ対戦", body)


@app.route("/games/marubatsu", methods=["GET"])
def marubatsu():
    return render_marubatsu()


@app.route("/games/marubatsu/start", methods=["POST"])
def marubatsu_start():
    first = request.form.get("first", "1") == "1"
    session["mb_first"] = first
    session["mb_over"] = False
    session["mb_board"] = marubatsu_start_board(first)
    if first:
        return render_marubatsu(message="あなたは ○ です。先手なので、好きなマスからどうぞ。")
    return render_marubatsu(message="あなたは ○ です。後手なので、CPU が先に打ちました。")


@app.route("/games/marubatsu/move", methods=["POST"])
def marubatsu_move():
    if "mb_board" not in session or session.get("mb_over"):
        return render_marubatsu()
    board = list(session["mb_board"])
    raw = request.form.get("index", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < 9):
        return render_marubatsu()
    idx = int(raw)
    if board[idx] != "":
        return render_marubatsu(message="そこはもう埋まっています。")
    board[idx] = "○"
    result = marubatsu_winner(board)
    if result is None:
        cpu = marubatsu_cpu_move(board, "×")
        if cpu is not None:
            board[cpu] = "×"
        result = marubatsu_winner(board)
    session["mb_board"] = board
    if result == "○":
        session["mb_over"] = True
        wins = int(session.get("mb_wins", 0)) + 1
        session["mb_wins"] = wins
        record_score("marubatsu", wins)
        return render_marubatsu(message=f"🎉 あなたの勝ち！ このセッション {wins} 勝目です。")
    if result == "×":
        session["mb_over"] = True
        return render_marubatsu(message="CPU の勝ち…。連戦ボタンでもう一局どうぞ。")
    if result == "draw":
        session["mb_over"] = True
        return render_marubatsu(message="引き分けです。連戦ボタンでもう一局どうぞ。")
    return render_marubatsu()


@app.route("/games/marubatsu/next", methods=["POST"])
def marubatsu_next():
    first = bool(session.get("mb_first", True))
    session["mb_over"] = False
    session["mb_board"] = marubatsu_start_board(first)
    return render_marubatsu(message="新しい対局です。")


@app.route("/games/marubatsu/reset", methods=["POST"])
def marubatsu_reset():
    session.pop("mb_board", None)
    session.pop("mb_over", None)
    session.pop("mb_first", None)
    flash("先手・後手を選び直せます。", "ok")
    return redirect(url_for("marubatsu"))


# ============================
# しりとり対戦
# 内蔵の単語リスト（ひらがな名詞）だけで CPU と交互にしりとりする。
# 末尾の「ー」はその前のかなの母音に読み替える（例：かれー → え）。
# 拗音・促音が末尾に来たらその文字自体を使う（リスト内には末尾が
# 小さいかなの単語を入れていない）。
# ============================
SHIRITORI_WORDS = [
    # あ行
    "あめ", "あひる", "あいす",
    "いぬ", "いちご", "いす", "いか", "いえ",
    "うみ", "うさぎ", "うた", "うし",
    "えんぴつ", "えき", "えび", "えいが",
    "おに", "おかし",
    # か行
    "かめ", "かさ", "かぜ", "かばん", "かれー", "かべ",
    "きつね", "きのこ", "きりん", "きって", "きゅうり",
    "くま", "くも", "くらげ", "くじら", "くつ",
    "けーき", "けむり",
    "こめ", "こおり", "こあら", "ことり", "こんぶ",
    # さ行
    "さかな", "さくら", "さる", "さとう",
    "しか", "しお", "しろ", "しっぽ", "しんぶん",
    "すいか", "すし", "すずめ",
    "せみ", "せんせい", "せっけん",
    "そら", "そば",
    # た行
    "たまご", "たぬき", "たいよう", "たけ", "たこ",
    "ちず", "ちきゅう", "ちーず",
    "つき", "つな", "つる", "つばめ",
    "てがみ", "てら", "てんき", "てぶくろ",
    "とり", "とけい", "とまと", "とら",
    # な行
    "なつ", "なみ", "なし", "なっとう",
    "にじ", "にんじん", "にわとり", "にく",
    "ぬの",
    "ねこ", "ねずみ", "ねぎ",
    "のり", "のこぎり",
    # は行
    "はな", "はし", "はと", "はちみつ", "はる",
    "ひまわり", "ひこうき", "ひよこ",
    "ふね", "ふくろ", "ふで", "ふうせん",
    "へび", "へや",
    "ほし", "ほん", "ほたる",
    # ま行
    "まめ", "まど", "まくら", "まつり",
    "みかん", "みず", "みち", "みそ",
    "むし", "むぎ", "むら",
    "めがね", "めろん", "めだか",
    "もも", "もち", "もみじ",
    # や・ら・わ行
    "やま", "やさい", "やね", "やかん",
    "ゆき", "ゆめ", "ゆび",
    "よる", "ようふく", "よっと",
    "らいおん", "らくだ", "らっぱ",
    "りんご", "りす", "りぼん",
    "るす",
    "れもん", "れんげ",
    "ろうそく", "ろぼっと", "ろけっと",
    "わに", "わた", "わかめ",
    # 濁点・半濁点
    "がっこう", "がらす",
    "ぎんこう",
    "げた",
    "ごりら", "ごま", "ごはん",
    "ざっし",
    "じゃがいも", "じかん",
    "ずぼん",
    "だるま", "だいこん",
    "でんわ",
    "どんぐり",
    "ばなな", "ばら",
    "びわ",
    "ぶどう", "ぶた",
    "べんきょう",
    "ぼうし",
    "ぱん",
    "ぴざ",
    "ぽすと",
]

_VOWEL_OF = {}
for _row, _vowel in (
    ("あかさたなはまやらわがざだばぱ", "あ"),
    ("いきしちにひみりゐぎじぢびぴ", "い"),
    ("うくすつぬふむゆるぐずづぶぷ", "う"),
    ("えけせてねへめれゑげぜでべぺ", "え"),
    ("おこそとのほもよろをごぞどぼぽ", "お"),
):
    for _ch in _row:
        _VOWEL_OF[_ch] = _vowel
_VOWEL_OF.update(
    {"ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お",
     "ゃ": "あ", "ゅ": "う", "ょ": "お", "っ": "う", "ゎ": "あ"}
)


def shiritori_last_kana(word: str) -> str:
    """次の単語が始まるべきかなを返す。末尾の「ー」は、その前のかなの
    母音に読み替える。それ以外（拗音・促音を含む）は末尾の文字そのまま。"""
    if not word:
        return ""
    if word[-1] == "ー":
        for ch in reversed(word[:-1]):
            if ch != "ー":
                return _VOWEL_OF.get(ch, ch)
        return ""
    return word[-1]


def shiritori_normalize(text: str) -> str:
    """入力を正規化する：空白を取り除き、カタカナをひらがなにそろえる。"""
    text = (text or "").strip().replace(" ", "").replace("　", "")
    out = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:  # カタカナ → ひらがな
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def shiritori_check(word: str, required: str, used) -> str:
    """入力チェック。'ok' / 'not_in_list' / 'used' / 'wrong_start' のいずれか。"""
    if word not in SHIRITORI_WORDS:
        return "not_in_list"
    if word in used:
        return "used"
    if required and word[0] != required:
        return "wrong_start"
    return "ok"


def shiritori_candidates(required: str, used) -> list:
    used_set = set(used)
    return [w for w in SHIRITORI_WORDS if w[0] == required and w not in used_set]


def shiritori_cpu_word(required: str, used):
    """CPU の手。「ん」で終わらない単語を優先してランダムに選ぶ。
    続けられる単語がなければ None。"""
    cands = shiritori_candidates(required, used)
    if not cands:
        return None
    safe = [w for w in cands if not w.endswith("ん")]
    return random.choice(safe if safe else cands)


def shiritori_new_game() -> None:
    session["st_chain"] = []
    session["st_over"] = False


SHIRITORI_TEMPLATE = r"""
  <h1>🔤 しりとり対戦</h1>
  <p class="howto">CPU と交互にしりとりする対戦ゲーム。使えるのは内蔵リスト（全 {{ word_total }} 語、ひらがな名詞）にある単語だけです。カタカナで入力してもひらがなに直して判定します。「ん」で終わる単語を出した方が負け。同じ単語は2回使えません。言葉が続かなくなった側の負けで、続いた単語数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">つながった単語数: {{ chain|length }} ／ ベスト（最長）: {{ best if best is not none else '—' }}</p>
    {% if chain %}
      <p style="font-size:18px; line-height:1.9; text-align:center;">
        {% for word, who in chain %}
          <span class="pill">{{ who }}</span> {{ word }}{% if not loop.last %} → {% endif %}
        {% endfor %}
      </p>
    {% else %}
      <p class="mid">まだ単語がありません。最初の単語はリスト内のどれでもOKです。</p>
    {% endif %}
    {% if not over %}
      <form method="post" action="{{ url_for('shiritori_play') }}" class="row">
        <input type="text" name="word" placeholder="{% if required %}「{{ required }}」から始まる単語{% else %}ひらがなで単語を入力{% endif %}" autocomplete="off">
        <button type="submit">出す</button>
      </form>
      {% if required %}
        <p class="muted" style="text-align:center;">次は「{{ required }}」から始まる単語です。</p>
      {% endif %}
    {% endif %}
    <form method="post" action="{{ url_for('shiritori_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">はじめから</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（単語数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 語</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_shiritori(message=None):
    if "st_chain" not in session:
        shiritori_new_game()
    chain = [list(pair) for pair in session["st_chain"]]
    used = [w for w, _who in chain]
    required = shiritori_last_kana(used[-1]) if used and not session.get("st_over") else ""
    body = render_template_string(
        SHIRITORI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        chain=chain,
        over=bool(session.get("st_over", False)),
        required=required,
        word_total=len(SHIRITORI_WORDS),
        best=best_score("shiritori", "max"),
        history=recent_scores("shiritori", 10),
        message=message,
    )
    return game_page("しりとり対戦", body)


def shiritori_finish(chain, message: str):
    session["st_chain"] = chain
    session["st_over"] = True
    record_score("shiritori", len(chain))
    return render_shiritori(message=f"{message}（{len(chain)} 語つながりました）")


@app.route("/games/shiritori", methods=["GET"])
def shiritori():
    return render_shiritori()


@app.route("/games/shiritori/play", methods=["POST"])
def shiritori_play():
    if "st_chain" not in session:
        shiritori_new_game()
    if session.get("st_over"):
        return render_shiritori()
    chain = [list(pair) for pair in session["st_chain"]]
    used = [w for w, _who in chain]
    required = shiritori_last_kana(used[-1]) if used else ""
    word = shiritori_normalize(request.form.get("word", ""))
    status = shiritori_check(word, required, used) if word else "not_in_list"
    if status == "not_in_list":
        return render_shiritori(
            message="その単語はリストにありません。リストにある単語（ひらがな）でお願いします。"
        )
    if status == "used":
        return render_shiritori(message=f"「{word}」はもう使われています。")
    if status == "wrong_start":
        return render_shiritori(message=f"「{required}」から始まる単語をどうぞ。")
    chain.append([word, "あなた"])
    session["st_chain"] = chain
    if word.endswith("ん"):
        return shiritori_finish(chain, f"「{word}」は「ん」で終わるので、あなたの負け…。")
    nxt = shiritori_last_kana(word)
    cpu = shiritori_cpu_word(nxt, [w for w, _who in chain])
    if cpu is None:
        return shiritori_finish(
            chain, f"CPU は「{nxt}」から始まる単語を続けられませんでした。あなたの勝ち！"
        )
    chain.append([cpu, "CPU"])
    session["st_chain"] = chain
    if cpu.endswith("ん"):
        return shiritori_finish(
            chain, f"CPU の「{cpu}」は「ん」で終わるので、あなたの勝ち！"
        )
    return render_shiritori(
        message=f"CPU： {cpu}。次は「{shiritori_last_kana(cpu)}」から始まる単語をどうぞ。"
    )


@app.route("/games/shiritori/reset", methods=["POST"])
def shiritori_reset():
    shiritori_new_game()
    flash("はじめからやり直します。", "ok")
    return redirect(url_for("shiritori"))


# ============================
# 風船わり
# 30秒間の反射ゲーム。進行はクライアント JS、終了時に得点を POST する。
# 通常の風船 +1点、爆弾 −3点（合計は0未満にしない）。
# ============================
BALLOONPOP_TEMPLATE = r"""
  <h1>🎈 風船わり</h1>
  <p class="howto">「スタート」を押すと30秒のカウントダウンが始まります。出てくる風船をタップ／クリックで割ってください。通常の風船は +1点、爆弾（💣）を割ると −3点（0点未満にはなりません）。風船は少し放っておくと消えてしまいます。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（最高得点）: {{ best if best is not none else '—' }}</p>
    <p class="mid">残り時間: <span id="timeLeft">30.0</span> 秒 ／ 得点: <span id="score">0</span></p>
    <div id="area" style="position:relative; height:360px; border:1px solid #ddd; border-radius:12px; background:#f4f9ff; overflow:hidden; margin:10px 0;"></div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（得点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var area = document.getElementById("area");
  var message = document.getElementById("message");
  var scoreEl = document.getElementById("score");
  var timeEl = document.getElementById("timeLeft");
  var startBtn = document.getElementById("startBtn");
  var COLORS = ["#ef6461", "#f2b134", "#6bcb77", "#4d96ff", "#b983ff", "#ff8fb1"];
  var playing = false, score = 0, endsAt = 0, spawnId = null, tickId = null;
  function spawn(){
    if (!playing) { return; }
    var bomb = Math.random() < 0.18;
    var size = 46 + Math.floor(Math.random() * 18);
    var el = document.createElement("button");
    el.type = "button";
    el.textContent = bomb ? "💣" : "🎈";
    el.style.cssText = "position:absolute; border-radius:50%; border:2px solid rgba(0,0,0,.15);"
      + " width:" + size + "px; height:" + size + "px; padding:0; cursor:pointer;"
      + " font-size:" + Math.floor(size * 0.55) + "px; line-height:1;"
      + " background:" + (bomb ? "#666" : COLORS[Math.floor(Math.random() * COLORS.length)])
      + "; left:" + (Math.random() * 86) + "%; top:" + (Math.random() * 80) + "%;";
    el.addEventListener("click", function(){
      if (!playing) { return; }
      if (bomb) { score = Math.max(0, score - 3); } else { score += 1; }
      scoreEl.textContent = String(score);
      el.remove();
    });
    area.appendChild(el);
    setTimeout(function(){ el.remove(); }, 1500);
  }
  function finish(){
    playing = false;
    clearInterval(spawnId);
    clearInterval(tickId);
    timeEl.textContent = "0.0";
    area.innerHTML = "";
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(score));
    fetch("{{ url_for('balloonpop_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ 得点は " + score + " 点でした";
          document.getElementById("bestline").textContent = "ベスト（最高得点）: " + d.best;
        }
      })
      .catch(function(){});
  }
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    score = 0;
    scoreEl.textContent = "0";
    area.innerHTML = "";
    message.textContent = "風船を割ろう！ 爆弾は避けてね";
    startBtn.disabled = true;
    endsAt = Date.now() + 30000;
    spawnId = setInterval(spawn, 650);
    spawn();
    tickId = setInterval(function(){
      var left = Math.max(0, endsAt - Date.now());
      timeEl.textContent = (left / 1000).toFixed(1);
      if (left <= 0) { finish(); }
    }, 100);
  });
})();
</script>
"""


@app.route("/games/balloonpop", methods=["GET"])
def balloonpop():
    body = render_template_string(
        BALLOONPOP_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("balloonpop", "max"),
        history=recent_scores("balloonpop", 10),
    )
    return game_page("風船わり", body)


@app.route("/games/balloonpop/score", methods=["POST"])
def balloonpop_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 300):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("balloonpop", int(raw))
    return {"ok": True, "best": best_score("balloonpop", "max")}


# gunicorn 等で起動した場合にも DB を用意する（作成済みなら何もしない）
init_db()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
