# gameapp.py
# Flask + SQLite 自作ミニゲーム集ポータル（完全1ファイル）
# トップページがゲーム一覧ポータル、各ゲームは /games/<slug> で遊べる。
# 収録ゲームはすべて作者の自作。新しいゲームは GAMES リストへ1件足して追加する。
# 起動:  python gameapp.py
# URL:  http://127.0.0.1:5000

from __future__ import annotations

import os
import sqlite3
import math
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
    {
        "slug": "flasksort",
        "title": "いろわけフラスコ",
        "category": "脳トレ",
        "icon": "🧪",
        "description": "色の付いた液体をフラスコの間で移し替え、1本に1色だけが入るように分ける並べ替えパズル。空きフラスコをうまく使って、少ない手数で完成させるほど高記録です。",
        "endpoint": "flasksort",
    },
    {
        "slug": "cupshuffle",
        "title": "カップシャッフル当て",
        "category": "抽選・占い",
        "icon": "🥤",
        "description": "ボールの入ったカップがシャッフルされる様子を目で追って、最後にボールが入っているカップを当てる観察ゲーム。当てた回数を記録します。",
        "endpoint": "cupshuffle",
    },
    {
        "slug": "colorwall",
        "title": "カラー壁ぬけ",
        "category": "アクション",
        "icon": "🌈",
        "description": "流れてくる壁の色に合わせて、自分のボールの色をタイミングよく切り替えてすり抜ける反射ゲーム。抜けた壁の数を記録します。",
        "endpoint": "colorwall",
    },
    {
        "slug": "trio-card",
        "title": "三すくみカード",
        "category": "カード・数字",
        "icon": "🃏",
        "description": "炎・草・水の三すくみ（炎＞草＞水＞炎）で CPU とカード対戦。同じ属性なら数字の大きい方が勝ち。5回戦の勝ち数を記録します。",
        "endpoint": "trio_card",
    },
    {
        "slug": "flat3d",
        "title": "平面⇔立体パズル",
        "category": "脳トレ",
        "icon": "🧊",
        "description": "上面図（平面）と正面図（立体）の表示を切り替えながら進む迷路パズル。立体表示でだけ見える足場を使ってゴールを目指します。ゴールまでの歩数を記録します。",
        "endpoint": "flat3d",
    },
    {
        "slug": "gomoku-tsume",
        "title": "ゴモク一手詰め",
        "category": "脳トレ",
        "icon": "⚫",
        "description": "五目並べで「あと1手で五つ揃う」詰め問題に挑戦。正しいマスに打てば勝ち。連続正解数を記録します。",
        "endpoint": "gomoku_tsume",
    },
    {
        "slug": "iceweak",
        "title": "氷の弱点タップ",
        "category": "アクション",
        "icon": "🧊",
        "description": "氷の盤面にうっすら光る弱点が一瞬だけ現れます。その場所を覚えてタップで割っていく、観察と反応のゲーム。割った氷の数を記録します。",
        "endpoint": "iceweak",
    },
    {
        "slug": "saisen",
        "title": "賽銭チャレンジ",
        "category": "アクション",
        "icon": "🪙",
        "description": "角度だけを決めてコインを投げ入れ、賽銭箱の口に入れるタイミング＆角度ゲーム。10投のうち入った数を記録します。",
        "endpoint": "saisen",
    },
    {
        "slug": "suzuatume",
        "title": "すずあつめ落ちもの",
        "category": "アクション",
        "icon": "🔔",
        "description": "落ちてくる鈴を左右に動くかごでキャッチする落ちものゲーム。金色の鈴は高得点、石を取ると減点。30秒の最終得点を記録します。",
        "endpoint": "suzuatume",
    },
    {
        "slug": "tunnelface",
        "title": "トンネル顔出し当て",
        "category": "脳トレ",
        "icon": "🚇",
        "description": "3つのトンネルから一瞬だけ顔を出すキャラの場所と順番を覚えて当てる記憶ゲーム。当てた問題数を記録します。",
        "endpoint": "tunnelface",
    },
    {
        "slug": "bagpack",
        "title": "バッグ詰めパズルバトル",
        "category": "創作",
        "icon": "🎒",
        "description": "形の違う道具を6×6のバッグにぎっしり詰めるパッキングパズル。回転もできます。埋めたマスの割合で CPU と勝負し、勝ったラウンド数を記録します。",
        "endpoint": "bagpack",
    },
    {
        "slug": "wordmonster",
        "title": "3ワードモンスター",
        "category": "対戦",
        "icon": "👹",
        "description": "3つの言葉を組み合わせてモンスターを生成。言葉の相性でステータスが決まり、CPU のモンスターと対戦します。勝利数を記録します。",
        "endpoint": "wordmonster",
    },
    {
        "slug": "mojiotoshi",
        "title": "もじおとし",
        "category": "脳トレ",
        "icon": "🗑️",
        "description": "落ちてくるひらがなを横に並べて、言葉ができたら消えるパズル。消した言葉の数を記録します。",
        "endpoint": "mojiotoshi",
    },
    {
        "slug": "mensetsu",
        "title": "面接吹き出しジャッジ",
        "category": "クイズ・知識",
        "icon": "💼",
        "description": "面接官の質問に、吹き出しの回答候補から一番ふさわしいものを選んで進める選択ゲーム。最後の評価（S〜D）を記録します。",
        "endpoint": "mensetsu",
    },
    {
        "slug": "suishitsu",
        "title": "水質バランス処理",
        "category": "クイズ・知識",
        "icon": "💧",
        "description": "水質パラメータ（濁度・pH・細菌）を読んで、設備と薬剤を使い分ける判断ゲーム。基準内に収めつつコストを抑えた分だけ高得点。合計得点を記録します。",
        "endpoint": "suishitsu",
    },
    {
        "slug": "boomerang",
        "title": "ブーメラン軌道アタック",
        "category": "アクション",
        "icon": "🪃",
        "description": "投げたブーメランが自分の今いる場所へ戻ってくる軌道で敵を倒すエンドレス・スコアアタック。投げた後に動くと軌道が曲がります。倒した数を記録します。",
        "endpoint": "boomerang",
    },
    {
        "slug": "timing-tennis",
        "title": "タイミング返球テニス",
        "category": "アクション",
        "icon": "🎾",
        "description": "ボールがラケットに来るタイミングで打つテニス風の返球ゲーム。ぴったりだとパーフェクト返球で+2点。3回ミスで終了、合計点を記録します。",
        "endpoint": "timing_tennis",
    },
    {
        "slug": "secret-name",
        "title": "ひみつネーム即死当て",
        "category": "クイズ・知識",
        "icon": "🤫",
        "description": "秘密の動物の名前を、文字の一致ヒント（◎△×）で当てる推理ゲーム。ただし「即死ネーム」を言ってしまうと即ゲームオーバー。6回以内に当てて得点を記録します。",
        "endpoint": "secret_name",
    },
    {
        "slug": "current-shot",
        "title": "海流ながれ弾シューティング",
        "category": "アクション",
        "icon": "🌊",
        "description": "海流の帯を通る弾が横に流される、インベーダー風シューティング。流れを読んで敵を撃ち落とそう。倒した数を記録します。",
        "endpoint": "current_shot",
    },
    {
        "slug": "tier-party",
        "title": "ティアならべパーティ",
        "category": "創作",
        "icon": "🎚️",
        "description": "お題の8項目を S/A/B/C のティア表に並べるゲーム。隠れた「みんなの感覚」と一致するほど高得点。全ティア使用ボーナスもあります。",
        "endpoint": "tier_party",
    },
    {
        "slug": "shodo",
        "title": "おてほん書道採点",
        "category": "創作",
        "icon": "🖌️",
        "description": "薄く表示されたお手本の漢字をマウスや指でなぞると、なぞり具合を100点満点で採点します。被覆率とはみ出しの少なさが鍵。",
        "endpoint": "shodo",
    },
    {
        "slug": "rousoku",
        "title": "一息ろうそく消し",
        "category": "アクション",
        "icon": "🕯️",
        "description": "ろうそくを長押しして息を吹きかけ、火を消すゲーム。息ゲージが空になると息継ぎが必要。60秒で消した本数を記録します。",
        "endpoint": "rousoku",
    },
    {
        "slug": "shield-moji",
        "title": "胸ポケットの盾文字",
        "category": "アクション",
        "icon": "🛡️",
        "description": "選んだ漢字の輪郭を盾にして、落ちてくる玉を防ぐゲーム。字のインク部分でしか防げず、空白はすり抜けます。防いだ数を記録します。",
        "endpoint": "shield_moji",
    },
    {
        "slug": "ramen-oil",
        "title": "ラーメン油あつめ",
        "category": "アクション",
        "icon": "🍜",
        "description": "丼に浮いた油の粒をドラッグ（箸）で寄せ集め、中央のまとめゾーンへ集めるゲーム。45秒で集めた粒の数を記録します。",
        "endpoint": "ramen_oil",
    },
    {
        "slug": "ikasama",
        "title": "イカサマ割合ハイボール",
        "category": "カード・数字",
        "icon": "🥃",
        "description": "ハイボールのウイスキー割合を決めて客に出す読み合いゲーム。薄いほど儲かるが、客の許容ラインを下回るとバレてストライク。合計利益を記録します。",
        "endpoint": "ikasama",
    },
    {
        "slug": "machigai-card",
        "title": "まちがいカード見抜き",
        "category": "カード・数字",
        "icon": "🃏",
        "description": "表示されたトランプと説明文を見比べて、間違いが「ある」か「ない」かを見抜くゲーム。全10問の正解数を記録します。",
        "endpoint": "machigai_card",
    },
    {
        "slug": "poyon-rhythm",
        "title": "2ボタンぽよんリズム",
        "category": "アクション",
        "icon": "🎵",
        "description": "左と右の2ボタンだけのリズムゲーム。落ちてくるノートが判定ラインに重なった瞬間にボタンを押そう。40秒の合計点を記録します。",
        "endpoint": "poyon_rhythm",
    },
    {
        "slug": "bubble-shot",
        "title": "カラフルバブルシュート",
        "category": "アクション",
        "icon": "🫧",
        "description": "狙ってバブルを発射し、同じ色を3つ以上つなげて消すバブルシューティング。全3ステージ。得点を記録します。",
        "endpoint": "bubble_shot",
    },
    {
        "slug": "draw-poker",
        "title": "1回交換ドローポーカー",
        "category": "カード・数字",
        "icon": "🂡",
        "description": "5枚の手札から1回だけ交換して、役で CPU と勝負するポーカー。全5ラウンド、勝ち3点・引き分け1点の合計を記録します。",
        "endpoint": "draw_poker",
    },
    {
        "slug": "ronpa",
        "title": "手がかり論破レスバ",
        "category": "脱出・謎解き",
        "icon": "💬",
        "description": "書きこみの時刻や名前などの手がかりを集め、相手の言い分につきつけてうそを言い負かす推理ゲーム。短いシナリオ全3問、合計点を記録します。",
        "endpoint": "ronpa",
    },
    {
        "slug": "curling-tsume",
        "title": "カーリング一投詰め",
        "category": "脳トレ",
        "icon": "🥌",
        "description": "角度・強さ・曲げを決めて1投だけ投げ、相手より中心に近い位置に石を残す詰めパズル。全3問の合計点を記録します。",
        "endpoint": "curling_tsume",
    },
    {
        "slug": "prism-mirror",
        "title": "プリズム鏡あわせ",
        "category": "脳トレ",
        "icon": "🪞",
        "description": "鏡を45度ずつ回して光を全部のクリスタルへ届けるパズル。全3ステージで、手数が少ないほど高得点です。",
        "endpoint": "prism_mirror",
    },
    {
        "slug": "eyeball-sokoban",
        "title": "目玉みはり倉庫番",
        "category": "脳トレ",
        "icon": "👁️",
        "description": "目玉の視線に入ると後ろへ下がれなくなる倉庫番。全部の箱をゴールへ運ぶ全3ステージ、移動回数が少ないほど高得点です。",
        "endpoint": "eyeball_sokoban",
    },
    {
        "slug": "ushi-tomato",
        "title": "ウシおどかしトマト",
        "category": "アクション",
        "icon": "🐄",
        "description": "猫でウシを驚かせて逃がし、通り道のトマトを食べさせる60秒アクション。追いかけてくる人から逃げ切ろう。",
        "endpoint": "ushi_tomato",
    },
    {
        "slug": "oyatsu-kaba",
        "title": "おやつカバ60秒",
        "category": "アクション",
        "icon": "🦛",
        "description": "流れてくるおやつを集め、あふれる前に保存して得点化する60秒収集ゲーム。満腹で鈍くなったらお茶でリフレッシュ。",
        "endpoint": "oyatsu_kaba",
    },
    {
        "slug": "swipe-ushi",
        "title": "スワイプ加速ウシ",
        "category": "アクション",
        "icon": "🐮",
        "description": "連打で牛がどんどん加速していくジョーク系ゲーム。牧場から宇宙まで、30秒で進んだ距離を記録します。",
        "endpoint": "swipe_ushi",
    },
    {
        "slug": "kyushin-judge",
        "title": "球審ジャッジ",
        "category": "クイズ・知識",
        "icon": "⚾",
        "description": "投げられた球がストライクかボールかを判定する球審ゲーム。際どい球ほど迷います。誤審3回で終了、正解数が得点です。",
        "endpoint": "kyushin_judge",
    },
    {
        "slug": "kagiban",
        "title": "カギバンさばき",
        "category": "脳トレ",
        "icon": "🔑",
        "description": "フォローリクエストを掟（ルール）に沿って承認／拒否にさばくゲーム。掟は5件ごとに増え、3回ミスで終了です。",
        "endpoint": "kagiban",
    },
    {
        "slug": "block-survive",
        "title": "ブロック側サバイバル",
        "category": "アクション",
        "icon": "🧱",
        "description": "ブロック崩しの「ブロック側」を操作して、ボールとCPUパドルから生き残る逆転アクション。生き残り時間と他ブロック破壊で得点。",
        "endpoint": "block_survive",
    },
    {
        "slug": "meiga-naoshi",
        "title": "名画おなおしミニ",
        "category": "創作",
        "icon": "🖼️",
        "description": "破れた名画風の絵の欠けた部分を、お手本を見ながら描き足すお絵かきゲーム。元の絵との一致度で採点します。",
        "endpoint": "meiga_naoshi",
    },
    {
        "slug": "fukuwarai",
        "title": "証言ふくわらい捜査",
        "category": "クイズ・知識",
        "icon": "🔍",
        "description": "目撃証言（位置の範囲）を頼りに福笑いで顔を再現する捜査ゲーム。本物との近さで100点満点、証言に反すると減点です。",
        "endpoint": "fukuwarai",
    },
    {
        "slug": "majyo-suiri",
        "title": "憑依まじょ推理",
        "category": "脱出・謎解き",
        "icon": "🧙",
        "description": "村人の発言の矛盾から「憑依」の持ち主を当てる一人用人狼風推理。憑依した村人はうそをつく。短いシナリオ全3問。",
        "endpoint": "majyo_suiri",
    },
    {
        "slug": "hikigiwa-dungeon",
        "title": "引き際ダンジョンすごろく",
        "category": "カード・数字",
        "icon": "🎲",
        "description": "サイコロすごろく×カードバトル。12回進む前に帰還すれば金を持ち帰れるが、全滅すると全ロスト。引き際の判断が核です。",
        "endpoint": "hikigiwa_dungeon",
    },
    {
        "slug": "draft-meate",
        "title": "ドラフト目利き",
        "category": "クイズ・知識",
        "icon": "📋",
        "description": "スカウトの報告（誤差あり）をもとに架空選手の候補を比較して指名し、本当の実力で答え合わせする目利きゲーム。全5ラウンド。",
        "endpoint": "draft_meate",
    },
    {
        "slug": "color-hamekomi",
        "title": "回してはめこみカラー探し",
        "category": "脳トレ",
        "icon": "🧩",
        "description": "色と形がぴったり合う場所を探し、ピースを回転させてはめ込むパズル。全2ステージ、解けることを検証済みの構成です。",
        "endpoint": "color_hamekomi",
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




# ============================
# いろわけフラスコ
# 色の液体をフラスコ間で移し替え、1本に1色だけにする並べ替えパズル。
# 盤面はサーバー側セッションで管理する（各フラスコは色IDのリスト、下が底）。
# 初期配置はランダム配分したものを幅優先探索で検証し、必ず解ける配置だけ出す。
# ============================
FLASKSORT_COLORS = ["#e2543e", "#3e7de2", "#e8b93c"]
FLASKSORT_NAMES = ["あか", "あお", "きいろ"]
FLASKSORT_CAPACITY = 4


def flasksort_top_run(flask) -> int:
    """フラスコの一番上にある同色のかたまりの個数。空なら 0。"""
    if not flask:
        return 0
    run = 1
    for i in range(len(flask) - 2, -1, -1):
        if flask[i] == flask[-1]:
            run += 1
        else:
            break
    return run


def flasksort_pour(state, src: int, dst: int):
    """src の一番上の同色かたまりを dst へ注ぐ。注げなければ None、
    注げれば新しい状態（リストのリスト）を返す。元の状態は壊さない。"""
    if src == dst or not (0 <= src < len(state)) or not (0 <= dst < len(state)):
        return None
    state = [list(f) for f in state]
    source, target = state[src], state[dst]
    if not source or len(target) >= FLASKSORT_CAPACITY:
        return None
    if target and target[-1] != source[-1]:
        return None
    amount = min(flasksort_top_run(source), FLASKSORT_CAPACITY - len(target))
    if amount <= 0:
        return None
    color = source[-1]
    for _ in range(amount):
        source.pop()
        target.append(color)
    return state


def flasksort_is_solved(state) -> bool:
    """空か、容量いっぱいで単色のフラスコだけなら完成。"""
    for flask in state:
        if not flask:
            continue
        if len(flask) != FLASKSORT_CAPACITY or len(set(flask)) != 1:
            return False
    return True


def flasksort_is_solvable(state, node_cap: int = 300000) -> bool:
    """幅優先探索で完成状態へたどり着けるかを判定する。"""
    from collections import deque

    start = tuple(tuple(f) for f in state)
    seen = {start}
    queue = deque([start])
    nodes = 0
    while queue:
        cur = queue.popleft()
        nodes += 1
        if nodes > node_cap:
            return False
        if flasksort_is_solved([list(f) for f in cur]):
            return True
        for s in range(len(cur)):
            for d in range(len(cur)):
                nxt = flasksort_pour([list(f) for f in cur], s, d)
                if nxt is None:
                    continue
                key = tuple(tuple(f) for f in nxt)
                if key not in seen:
                    seen.add(key)
                    queue.append(key)
    return False


def flasksort_new_state():
    """色をランダムに配分し、解けることが確認できた配置を返す。
    （完成状態から注ぐ方式では単色フラスコが丸ごと移動するだけで
    永遠に混ざらないため、配分＋検証の方式にしている。）"""
    n_colors = len(FLASKSORT_COLORS)
    units = [c for c in range(n_colors) for _ in range(FLASKSORT_CAPACITY)]
    while True:
        random.shuffle(units)
        state = [
            units[i * FLASKSORT_CAPACITY:(i + 1) * FLASKSORT_CAPACITY]
            for i in range(n_colors)
        ]
        state.append([])
        if flasksort_is_solved(state):
            continue
        if flasksort_is_solvable(state):
            return state


def flasksort_new_game() -> None:
    session["fs_flasks"] = flasksort_new_state()
    session["fs_moves"] = 0
    session["fs_sel"] = -1
    session["fs_done"] = False


FLASKSORT_TEMPLATE = r"""
  <h1>🧪 いろわけフラスコ</h1>
  <p class="howto">フラスコをタップして選び、移したいフラスコをタップすると、一番上の色のかたまりが注がれます。注げるのは「空のフラスコ」か「一番上が同じ色で、空きがあるフラスコ」だけ。全部の色が1本にそろえば完成です。完成までの手数を記録します（ベスト＝最小手数）。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">手数: {{ moves }} ／ ベスト（最小手数）: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('flasksort_tap') }}">
      <div style="display:flex; gap:14px; justify-content:center; align-items:flex-end; flex-wrap:wrap;">
        {% for fi in range(flasks|length) %}
          <div style="text-align:center;">
            <button type="submit" name="index" value="{{ fi }}" {% if done %}disabled{% endif %}
              style="display:flex; flex-direction:column-reverse; gap:3px; width:64px; height:190px; padding:6px; border-radius:10px 10px 18px 18px; background:{% if sel == fi %}#fff3cd{% else %}#fdfdfd{% endif %}; border:2px solid {% if sel == fi %}#e8b93c{% else %}#bbb{% endif %};">
              {% for slot in range(4) %}
                {% if slot < flasks[fi]|length %}
                  <span style="display:block; height:38px; border-radius:6px; background:{{ colors[flasks[fi][slot]] }};"></span>
                {% else %}
                  <span style="display:block; height:38px; border-radius:6px; background:#f1f1f1;"></span>
                {% endif %}
              {% endfor %}
            </button>
            <div class="muted">{{ fi + 1 }}番</div>
          </div>
        {% endfor %}
      </div>
    </form>
    <p class="muted" style="text-align:center;">{% if sel >= 0 %}{{ sel + 1 }}番のフラスコを選択中。移し先をタップしてください（もう一度タップで選択解除）。{% else %}まず、移したいフラスコをタップしてください。{% endif %}</p>
    <form method="post" action="{{ url_for('flasksort_reset') }}" class="row">
      <button type="submit">最初からやり直す</button>
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


def render_flasksort(message=None):
    if "fs_flasks" not in session:
        flasksort_new_game()
    body = render_template_string(
        FLASKSORT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        flasks=[list(f) for f in session["fs_flasks"]],
        moves=int(session.get("fs_moves", 0)),
        sel=int(session.get("fs_sel", -1)),
        done=bool(session.get("fs_done", False)),
        colors=FLASKSORT_COLORS,
        best=best_score("flasksort", "min"),
        history=recent_scores("flasksort", 10),
        message=message,
    )
    return game_page("いろわけフラスコ", body)


@app.route("/games/flasksort", methods=["GET"])
def flasksort():
    return render_flasksort()


@app.route("/games/flasksort/tap", methods=["POST"])
def flasksort_tap():
    if "fs_flasks" not in session:
        flasksort_new_game()
    if session.get("fs_done"):
        return render_flasksort()
    raw = request.form.get("index", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < len(session["fs_flasks"])):
        return render_flasksort()
    idx = int(raw)
    state = [list(f) for f in session["fs_flasks"]]
    sel = int(session.get("fs_sel", -1))
    if sel < 0:
        if not state[idx]:
            return render_flasksort(message="そのフラスコは空です。色の入ったフラスコを選んでね。")
        session["fs_sel"] = idx
        return render_flasksort()
    if idx == sel:
        session["fs_sel"] = -1
        return render_flasksort()
    new_state = flasksort_pour(state, sel, idx)
    session["fs_sel"] = -1
    if new_state is None:
        return render_flasksort(message="そこへは注げません。空のフラスコか、一番上が同じ色のフラスコを選んでね。")
    moves = int(session.get("fs_moves", 0)) + 1
    session["fs_flasks"] = new_state
    session["fs_moves"] = moves
    if flasksort_is_solved(new_state):
        session["fs_done"] = True
        record_score("flasksort", moves)
        return render_flasksort(message=f"🎉 完成！ {moves} 手で色分けできました。")
    return render_flasksort()


@app.route("/games/flasksort/reset", methods=["POST"])
def flasksort_reset():
    flasksort_new_game()
    flash("新しい配置にしました。", "ok")
    return redirect(url_for("flasksort"))


# ============================
# カップシャッフル当て
# 3つのカップのうち1つにボールが入っている。シャッフルを目で追って当てる。
# 進行はクライアント JS、結果（当てた回数）は終了時に POST する。
# ============================
CUPSHUFFLE_TEMPLATE = r"""
  <h1>🥤 カップシャッフル当て</h1>
  <p class="howto">ボール（🔴）が入っているカップを覚えてください。「シャッフル開始」でカップが入れ替わります。止まったら、ボールが入っていると思うカップをクリック。当てるたびに次のラウンドは少し速くなります。3回ミスで終了、当てた回数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（当てた回数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">ラウンド: <span id="round">1</span> ／ 当てた数: <span id="hits">0</span> ／ ミス: <span id="miss">0</span> / 3</p>
    <div style="position:relative; height:150px; margin:10px 0;">
      <div id="cup0" class="cup" style="left:8%;">🥤</div>
      <div id="cup1" class="cup" style="left:41%;">🥤</div>
      <div id="cup2" class="cup" style="left:74%;">🥤</div>
    </div>
    <style>
      .cup { position:absolute; top:20px; width:18%; font-size:64px; text-align:center; cursor:pointer; transition:left .45s ease; user-select:none; }
      .cup .ball { display:block; font-size:26px; height:28px; }
    </style>
    <p class="result" id="message">まず「ボールを見せる」を押してね</p>
    <div class="row">
      <button type="button" id="showBtn">ボールを見せる</button>
      <button type="button" id="shuffleBtn" disabled>シャッフル開始</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（当てた回数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 回</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var cups = [document.getElementById("cup0"), document.getElementById("cup1"), document.getElementById("cup2")];
  var message = document.getElementById("message");
  var roundEl = document.getElementById("round");
  var hitsEl = document.getElementById("hits");
  var missEl = document.getElementById("miss");
  var showBtn = document.getElementById("showBtn");
  var shuffleBtn = document.getElementById("shuffleBtn");
  var LEFTS = ["8%", "41%", "74%"];
  var pos = [0, 1, 2];        // pos[slot] = そのスロットにいるカップ番号
  var ballCup = 0;            // ボールが入っているカップ番号
  var phase = "idle";         // idle -> shown -> shuffled -> guessing
  var round = 1, hits = 0, miss = 0, busy = false;
  function drawBall(show){
    cups.forEach(function(cup, i){
      var old = cup.querySelector(".ball");
      if (old) { old.remove(); }
      if (show && i === ballCup) {
        var b = document.createElement("span");
        b.className = "ball"; b.textContent = "🔴";
        cup.appendChild(b);
      }
    });
  }
  function place(animate){
    cups.forEach(function(cup, i){
      var slot = pos.indexOf(i);
      cup.style.left = LEFTS[slot];
    });
  }
  function swapSlots(a, b){
    var t = pos[a]; pos[a] = pos[b]; pos[b] = t;
    place(true);
  }
  function finish(){
    phase = "over";
    showBtn.disabled = true; shuffleBtn.disabled = true;
    var form = new FormData();
    form.append("score", String(hits));
    fetch("{{ url_for('cupshuffle_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + hits + " 回当てました";
          document.getElementById("bestline").textContent = "ベスト（当てた回数）: " + d.best;
          showBtn.textContent = "ページを再読み込みでもう一度";
          showBtn.disabled = false;
          showBtn.onclick = function(){ location.reload(); };
        }
      })
      .catch(function(){});
  }
  showBtn.addEventListener("click", function(){
    if (busy || phase === "over") { return; }
    ballCup = Math.floor(Math.random() * 3);
    drawBall(true);
    phase = "shown";
    message.textContent = "ボールの場所を覚えて！";
    showBtn.disabled = true;
    shuffleBtn.disabled = false;
  });
  shuffleBtn.addEventListener("click", function(){
    if (busy || phase !== "shown") { return; }
    busy = true;
    shuffleBtn.disabled = true;
    drawBall(false);
    var swaps = 4 + round;
    var speed = Math.max(180, 480 - round * 30);
    var i = 0;
    function step(){
      if (i >= swaps) {
        busy = false;
        phase = "guessing";
        message.textContent = "ボールはどのカップ？ クリックしてね";
        return;
      }
      var a = Math.floor(Math.random() * 3);
      var b = (a + 1 + Math.floor(Math.random() * 2)) % 3;
      swapSlots(a, b);
      i++;
      setTimeout(step, speed);
    }
    step();
  });
  cups.forEach(function(cup, i){
    cup.addEventListener("click", function(){
      if (busy || phase !== "guessing") { return; }
      drawBall(true);
      if (i === ballCup) {
        hits++;
        hitsEl.textContent = String(hits);
        message.textContent = "⭕ 正解！ 次のラウンドへ";
        round++;
        roundEl.textContent = String(round);
      } else {
        miss++;
        missEl.textContent = String(miss);
        message.textContent = "❌ ハズレ… ボールは別のカップでした";
        if (miss >= 3) { setTimeout(finish, 700); phase = "over"; return; }
      }
      phase = "idle";
      setTimeout(function(){ drawBall(false); showBtn.disabled = false; showBtn.textContent = "次のボールを見せる"; }, 800);
    });
  });
})();
</script>
"""


@app.route("/games/cupshuffle", methods=["GET"])
def cupshuffle():
    body = render_template_string(
        CUPSHUFFLE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("cupshuffle", "max"),
        history=recent_scores("cupshuffle", 10),
    )
    return game_page("カップシャッフル当て", body)


@app.route("/games/cupshuffle/score", methods=["POST"])
def cupshuffle_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("cupshuffle", int(raw))
    return {"ok": True, "best": best_score("cupshuffle", "max")}


# ============================
# カラー壁ぬけ
# 流れてくる壁と同じ色にボールを切り替えてすり抜ける反射ゲーム。
# 進行はクライアント JS、終了時に抜けた壁の数を POST する。
# ============================
COLORWALL_TEMPLATE = r"""
  <h1>🌈 カラー壁ぬけ</h1>
  <p class="howto">右から壁が流れてきます。下の色ボタンでボールの色を壁と同じ色に切り替えて、ぶつからずにすり抜けてください。色が違うとゲームオーバー。だんだん速くなります。抜けた壁の数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（抜けた壁）: {{ best if best is not none else '—' }}</p>
    <p class="mid">抜けた壁: <span id="passed">0</span> 枚</p>
    <div id="stage" style="position:relative; height:170px; border:1px solid #ddd; border-radius:12px; background:#f7fbff; overflow:hidden; margin:10px 0;">
      <div id="ball" style="position:absolute; left:60px; top:64px; width:42px; height:42px; border-radius:50%; background:#e2543e; border:2px solid rgba(0,0,0,.2);"></div>
      <div id="wall" style="position:absolute; top:0; height:100%; width:26px; background:#e2543e; display:none;"></div>
    </div>
    <div class="row">
      <button type="button" class="colorBtn" data-color="0" style="background:#e2543e; color:#fff;">あか</button>
      <button type="button" class="colorBtn" data-color="1" style="background:#3e7de2; color:#fff;">あお</button>
      <button type="button" class="colorBtn" data-color="2" style="background:#e8b93c;">きいろ</button>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（抜けた壁）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 枚</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var ball = document.getElementById("ball");
  var wall = document.getElementById("wall");
  var message = document.getElementById("message");
  var passedEl = document.getElementById("passed");
  var startBtn = document.getElementById("startBtn");
  var COLORS = ["#e2543e", "#3e7de2", "#e8b93c"];
  var playing = false, raf = null, last = 0;
  var ballColor = 0, wallColor = 0, wallX = 0, speed = 0, passed = 0, judged = false;
  function newWall(){
    wallColor = Math.floor(Math.random() * 3);
    wall.style.background = COLORS[wallColor];
    wallX = stage.clientWidth + 10;
    wall.style.left = wallX + "px";
    wall.style.display = "block";
    judged = false;
  }
  function finish(){
    playing = false;
    if (raf) { cancelAnimationFrame(raf); }
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(passed));
    fetch("{{ url_for('colorwall_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "💥 壁にぶつかった！ " + passed + " 枚抜けました";
          document.getElementById("bestline").textContent = "ベスト（抜けた壁）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function frame(ts){
    if (!playing) { return; }
    if (!last) { last = ts; }
    var dt = Math.min(50, ts - last);
    last = ts;
    wallX -= speed * dt / 1000;
    wall.style.left = wallX + "px";
    var ballX = 60;
    if (!judged && wallX <= ballX + 42 && wallX + 26 >= ballX) {
      judged = true;
      if (wallColor !== ballColor) { finish(); return; }
    }
    if (wallX + 26 < ballX) {
      passed++;
      passedEl.textContent = String(passed);
      speed += 14;
      newWall();
    }
    raf = requestAnimationFrame(frame);
  }
  document.querySelectorAll(".colorBtn").forEach(function(btn){
    btn.addEventListener("click", function(){
      ballColor = parseInt(btn.getAttribute("data-color"), 10);
      ball.style.background = COLORS[ballColor];
    });
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    passed = 0;
    passedEl.textContent = "0";
    ballColor = 0;
    ball.style.background = COLORS[0];
    speed = 150;
    last = 0;
    message.textContent = "壁と同じ色に切り替えて！";
    startBtn.disabled = true;
    newWall();
    raf = requestAnimationFrame(frame);
  });
})();
</script>
"""


@app.route("/games/colorwall", methods=["GET"])
def colorwall():
    body = render_template_string(
        COLORWALL_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("colorwall", "max"),
        history=recent_scores("colorwall", 10),
    )
    return game_page("カラー壁ぬけ", body)


@app.route("/games/colorwall/score", methods=["POST"])
def colorwall_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("colorwall", int(raw))
    return {"ok": True, "best": best_score("colorwall", "max")}


# ============================
# 三すくみカード
# 炎＞草＞水＞炎 の三すくみで CPU とカード対戦（サーバー側）。
# 同じ属性同士は数字（1〜9）の大きい方が勝ち。5回戦して勝ち数を記録する。
# ============================
TRIOCARD_ATTRS = ["炎", "草", "水"]
TRIOCARD_BEATS = {"炎": "草", "草": "水", "水": "炎"}


def triocard_judge(player_attr: str, player_num: int, cpu_attr: str, cpu_num: int) -> str:
    """勝敗判定。'win' / 'lose' / 'draw' を返す。"""
    if player_attr == cpu_attr:
        if player_num > cpu_num:
            return "win"
        if player_num < cpu_num:
            return "lose"
        return "draw"
    return "win" if TRIOCARD_BEATS[player_attr] == cpu_attr else "lose"


def triocard_new_hand():
    """プレイヤーの手札（属性×数字の組み合わせ3枚）を配る。"""
    combos = [(a, n) for a in TRIOCARD_ATTRS for n in range(1, 10)]
    return random.sample(combos, 3)


def triocard_cpu_card():
    return (random.choice(TRIOCARD_ATTRS), random.randint(1, 9))


def triocard_new_game() -> None:
    session["tc_round"] = 1
    session["tc_wins"] = 0
    session["tc_hand"] = [list(c) for c in triocard_new_hand()]
    session["tc_over"] = False


TRIOCARD_TEMPLATE = r"""
  <h1>🃏 三すくみカード</h1>
  <p class="howto">炎＞草＞水＞炎 の三すくみで CPU と対戦。手札3枚から1枚を選ぶと、CPU もカードを出します。同じ属性なら数字（1〜9）の大きい方が勝ち。全5回戦の勝ち数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">第 {{ round_no }} 戦 ／ あなたの勝ち数: {{ wins }} ／ ベスト（勝ち数）: {{ best if best is not none else '—' }}</p>
    {% if last %}
      <p class="mid">前の対戦： あなた {{ last[0] }} {{ last[1] }} vs CPU {{ last[2] }} {{ last[3] }} → {{ last[4] }}</p>
    {% endif %}
    {% if over %}
      <p class="result">対戦終了！ 5戦で {{ wins }} 勝でした。</p>
      <form method="post" action="{{ url_for('trio_card_reset') }}" class="row">
        <button type="submit">もう一度対戦する</button>
      </form>
    {% else %}
      <p class="mid">出すカードを選んでください</p>
      <div class="row">
        {% for card in hand %}
          <form method="post" action="{{ url_for('trio_card_play') }}">
            <input type="hidden" name="card" value="{{ loop.index0 }}">
            <button type="submit" style="font-size:20px; padding:16px 20px;">{% if card[0] == '炎' %}🔥{% elif card[0] == '草' %}🌿{% else %}💧{% endif %} {{ card[0] }} {{ card[1] }}</button>
          </form>
        {% endfor %}
      </div>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（勝ち数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 勝</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_trio_card(message=None):
    if "tc_hand" not in session:
        triocard_new_game()
    body = render_template_string(
        TRIOCARD_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        hand=[list(c) for c in session["tc_hand"]],
        round_no=int(session.get("tc_round", 1)),
        wins=int(session.get("tc_wins", 0)),
        over=bool(session.get("tc_over", False)),
        last=session.get("tc_last"),
        best=best_score("trio-card", "max"),
        history=recent_scores("trio-card", 10),
        message=message,
    )
    return game_page("三すくみカード", body)


@app.route("/games/trio-card", methods=["GET"])
def trio_card():
    return render_trio_card()


@app.route("/games/trio-card/play", methods=["POST"])
def trio_card_play():
    if "tc_hand" not in session:
        triocard_new_game()
    if session.get("tc_over"):
        return render_trio_card()
    hand = [list(c) for c in session["tc_hand"]]
    raw = request.form.get("card", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < len(hand)):
        return render_trio_card()
    player = hand.pop(int(raw))
    cpu = triocard_cpu_card()
    verdict = triocard_judge(player[0], int(player[1]), cpu[0], cpu[1])
    wins = int(session.get("tc_wins", 0)) + (1 if verdict == "win" else 0)
    session["tc_wins"] = wins
    verdict_text = {"win": "あなたの勝ち！", "lose": "CPU の勝ち", "draw": "引き分け"}[verdict]
    session["tc_last"] = [player[0], int(player[1]), cpu[0], cpu[1], verdict_text]
    round_no = int(session.get("tc_round", 1))
    if round_no >= 5:
        session["tc_over"] = True
        session["tc_hand"] = hand
        record_score("trio-card", wins)
        return render_trio_card(message=f"最終戦は{verdict_text}。")
    session["tc_round"] = round_no + 1
    hand.append(list(triocard_new_hand()[0]))
    session["tc_hand"] = hand
    return render_trio_card(message=f"第{round_no}戦は{verdict_text}")


@app.route("/games/trio-card/reset", methods=["POST"])
def trio_card_reset():
    triocard_new_game()
    flash("新しい対戦を始めました。", "ok")
    return redirect(url_for("trio_card"))


# ============================
# 平面⇔立体パズル
# 上面図（平面）と正面図（立体）の表示を切り替えて進む迷路（サーバー側）。
# 立体表示のときだけ渡れる足場マスがある。歩数を記録する（ベスト＝最小）。
# ============================
FLAT3D_MAP = [
    "##########",
    "#S...#...#",
    "#.##.###.#",
    "#..b...#.#",
    "###.####.#",
    "#...#....#",
    "#.#.#.##.#",
    "#.#..b..G#",
    "#...######",
    "##########",
]
FLAT3D_DIRS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}


def flat3d_cell(board, row: int, col: int) -> str:
    if 0 <= row < len(board) and 0 <= col < len(board[row]):
        return board[row][col]
    return "#"


def flat3d_can_step(board, row: int, col: int, mode: str) -> bool:
    """そのマスへ進めるか。'b'（足場）は立体表示のときだけ進める。"""
    cell = flat3d_cell(board, row, col)
    if cell == "#":
        return False
    if cell == "b" and mode != "solid":
        return False
    return True


def flat3d_find(board, mark: str):
    for r, line in enumerate(board):
        for c, ch in enumerate(line):
            if ch == mark:
                return (r, c)
    return None


def flat3d_new_game() -> None:
    start = flat3d_find(FLAT3D_MAP, "S")
    session["f3_pos"] = list(start)
    session["f3_mode"] = "flat"
    session["f3_steps"] = 0
    session["f3_done"] = False


FLAT3D_TEMPLATE = r"""
  <h1>🧊 平面⇔立体パズル</h1>
  <p class="howto">上面図（平面）と正面図（立体）を切り替えながら、S から G へ進む迷路です。「🧱 足場」のマスは立体表示のときだけ渡れます（平面では谷に見えて進めません）。表示の切り替えは歩数に数えません。ゴールまでの歩数を記録します（ベスト＝最小歩数）。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">歩数: {{ steps }} ／ 表示: {% if mode == 'solid' %}立体{% else %}平面{% endif %} ／ ベスト（最小歩数）: {{ best if best is not none else '—' }}</p>
    <div style="display:grid; grid-template-columns: repeat(10, 34px); gap:3px; justify-content:center; margin:10px 0;">
      {% for r in range(board|length) %}
        {% for c in range(board[r]|length) %}
          {% set cell = board[r][c] %}
          {% if pos[0] == r and pos[1] == c %}
            <span style="display:block; height:34px; line-height:34px; text-align:center; border-radius:6px; background:#ffd94d; font-size:18px;">🙂</span>
          {% elif cell == '#' %}
            <span style="display:block; height:34px; border-radius:6px; background:#555;"></span>
          {% elif cell == 'G' %}
            <span style="display:block; height:34px; line-height:34px; text-align:center; border-radius:6px; background:#bfe8bf; font-size:18px;">🏁</span>
          {% elif cell == 'b' %}
            <span style="display:block; height:34px; line-height:34px; text-align:center; border-radius:6px; background:{% if mode == 'solid' %}#a8d8ea{% else %}#f3d9d9{% endif %}; font-size:15px;">🧱</span>
          {% else %}
            <span style="display:block; height:34px; border-radius:6px; background:#fff; border:1px solid #eee;"></span>
          {% endif %}
        {% endfor %}
      {% endfor %}
    </div>
    {% if not done %}
      <div style="display:grid; grid-template-columns: repeat(3, 64px); gap:6px; justify-content:center; margin-bottom:10px;">
        <span></span>
        <form method="post" action="{{ url_for('flat3d_move') }}"><input type="hidden" name="dir" value="up"><button type="submit" style="width:64px;">↑</button></form>
        <span></span>
        <form method="post" action="{{ url_for('flat3d_move') }}"><input type="hidden" name="dir" value="left"><button type="submit" style="width:64px;">←</button></form>
        <form method="post" action="{{ url_for('flat3d_move') }}"><input type="hidden" name="dir" value="down"><button type="submit" style="width:64px;">↓</button></form>
        <form method="post" action="{{ url_for('flat3d_move') }}"><input type="hidden" name="dir" value="right"><button type="submit" style="width:64px;">→</button></form>
      </div>
      <form method="post" action="{{ url_for('flat3d_toggle') }}" class="row">
        <button type="submit">表示を切り替える（現在：{% if mode == 'solid' %}立体{% else %}平面{% endif %}）</button>
      </form>
    {% endif %}
    <form method="post" action="{{ url_for('flat3d_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（歩数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 歩</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_flat3d(message=None):
    if "f3_pos" not in session:
        flat3d_new_game()
    body = render_template_string(
        FLAT3D_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        board=FLAT3D_MAP,
        pos=list(session["f3_pos"]),
        mode=session.get("f3_mode", "flat"),
        steps=int(session.get("f3_steps", 0)),
        done=bool(session.get("f3_done", False)),
        best=best_score("flat3d", "min"),
        history=recent_scores("flat3d", 10),
        message=message,
    )
    return game_page("平面⇔立体パズル", body)


@app.route("/games/flat3d", methods=["GET"])
def flat3d():
    return render_flat3d()


@app.route("/games/flat3d/move", methods=["POST"])
def flat3d_move():
    if "f3_pos" not in session:
        flat3d_new_game()
    if session.get("f3_done"):
        return render_flat3d()
    direction = request.form.get("dir", "")
    if direction not in FLAT3D_DIRS:
        return render_flat3d()
    dr, dc = FLAT3D_DIRS[direction]
    row, col = [int(v) for v in session["f3_pos"]]
    nr, nc = row + dr, col + dc
    mode = session.get("f3_mode", "flat")
    if not flat3d_can_step(FLAT3D_MAP, nr, nc, mode):
        cell = flat3d_cell(FLAT3D_MAP, nr, nc)
        if cell == "b":
            return render_flat3d(message="その足場は平面表示では渡れません。立体表示に切り替えてみて。")
        return render_flat3d(message="壁があって進めません。")
    steps = int(session.get("f3_steps", 0)) + 1
    session["f3_pos"] = [nr, nc]
    session["f3_steps"] = steps
    if flat3d_cell(FLAT3D_MAP, nr, nc) == "G":
        session["f3_done"] = True
        record_score("flat3d", steps)
        return render_flat3d(message=f"🎉 ゴール！ {steps} 歩でたどり着きました。")
    return render_flat3d()


@app.route("/games/flat3d/toggle", methods=["POST"])
def flat3d_toggle():
    if "f3_pos" not in session:
        flat3d_new_game()
    session["f3_mode"] = "solid" if session.get("f3_mode") == "flat" else "flat"
    return render_flat3d()


@app.route("/games/flat3d/reset", methods=["POST"])
def flat3d_reset():
    flat3d_new_game()
    flash("スタート地点に戻りました。", "ok")
    return redirect(url_for("flat3d"))


# ============================
# ゴモク一手詰め
# 五目並べで「あと1手で五つ揃う」詰め問題（サーバー側）。9×9 盤面。
# 連続正解数を記録する。
# ============================
GOMOKU_SIZE = 9
GOMOKU_DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]


def gomoku_count_dir(board, row: int, col: int, dr: int, dc: int, mark: str) -> int:
    """(row, col) から (dr, dc) 方向へ mark が続く数（起点は数えない）。"""
    n = 0
    r, c = row + dr, col + dc
    while 0 <= r < GOMOKU_SIZE and 0 <= c < GOMOKU_SIZE and board[r][c] == mark:
        n += 1
        r += dr
        c += dc
    return n


def gomoku_winning_moves(board, mark: str = "B") -> list:
    """board（文字列のリスト）で mark が打てば5つ揃う空きマスの一覧。"""
    result = []
    for r in range(GOMOKU_SIZE):
        for c in range(GOMOKU_SIZE):
            if board[r][c] != ".":
                continue
            for dr, dc in GOMOKU_DIRS:
                total = 1
                total += gomoku_count_dir(board, r, c, dr, dc, mark)
                total += gomoku_count_dir(board, r, c, -dr, -dc, mark)
                if total >= 5:
                    result.append((r, c))
                    break
    return result


def gomoku_five(board, mark: str) -> bool:
    """mark の石が5つ以上並んでいるか。"""
    for r in range(GOMOKU_SIZE):
        for c in range(GOMOKU_SIZE):
            if board[r][c] != mark:
                continue
            for dr, dc in GOMOKU_DIRS:
                if gomoku_count_dir(board, r, c, dr, dc, mark) >= 4:
                    return True
    return False


def gomoku_new_puzzle():
    """必ず「ちょうど1マスだけ打てば勝ち」の詰め問題を作る。
    黒（あなた）・白（CPU）の石を置き、黒に勝ち手が1つだけある配置を返す。"""
    while True:
        cells = [(r, c) for r in range(GOMOKU_SIZE) for c in range(GOMOKU_SIZE)]
        random.shuffle(cells)
        board = [["."] * GOMOKU_SIZE for _ in range(GOMOKU_SIZE)]
        # 黒の「四つ並び＋開いた端」を骨格として置く
        r0 = random.randint(2, GOMOKU_SIZE - 3)
        c0 = random.randint(2, GOMOKU_SIZE - 3)
        dr, dc = random.choice(GOMOKU_DIRS)
        line = [(r0 + dr * i, c0 + dc * i) for i in range(-2, 3)]
        if not all(0 <= r < GOMOKU_SIZE and 0 <= c < GOMOKU_SIZE for r, c in line):
            continue
        for r, c in line[:4]:
            board[r][c] = "B"
        answer = line[4]
        # 残りの黒石と白石を散らす（勝ち手が増えたり五つ揃ったりしない範囲で）
        used = {tuple(p) for p in line}
        placed = 0
        for r, c in cells:
            if placed >= 7:
                break
            if (r, c) in used:
                continue
            mark = "B" if placed % 2 == 0 else "W"
            board[r][c] = mark
            trial = ["".join(row) for row in board]
            wins = gomoku_winning_moves(trial, "B")
            if len(wins) != 1 or wins[0] != answer or gomoku_five(trial, "B") or gomoku_five(trial, "W"):
                board[r][c] = "."
                continue
            used.add((r, c))
            placed += 1
        rows = ["".join(row) for row in board]
        wins = gomoku_winning_moves(rows, "B")
        if len(wins) == 1 and wins[0] == answer and placed >= 4:
            return rows, answer


def gomoku_new_game() -> None:
    board, answer = gomoku_new_puzzle()
    session["gm_board"] = board
    session["gm_answer"] = list(answer)
    session["gm_streak"] = int(session.get("gm_streak", 0))
    session["gm_message"] = None


GOMOKU_TEMPLATE = r"""
  <h1>⚫ ゴモク一手詰め</h1>
  <p class="howto">五目並べの詰め問題です。あなたは黒（●）。あと1手打てば五つ揃って勝てるマスが、ちょうど1つだけあります。そのマスをクリックしてください。外すと連続正解はリセットされます。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">連続正解: {{ streak }} ／ ベスト（連続正解）: {{ best if best is not none else '—' }}</p>
    <form method="post" action="{{ url_for('gomoku_tsume_move') }}">
      <div style="display:grid; grid-template-columns: repeat(9, 34px); gap:3px; justify-content:center;">
        {% for r in range(9) %}
          {% for c in range(9) %}
            {% set cell = board[r][c] %}
            {% if cell == 'B' %}
              <button type="button" disabled style="height:34px; border-radius:50%; background:#222; color:#fff; padding:0;">●</button>
            {% elif cell == 'W' %}
              <button type="button" disabled style="height:34px; border-radius:50%; background:#fff; color:#222; padding:0;">○</button>
            {% else %}
              <button type="submit" name="cell" value="{{ r }}-{{ c }}" style="height:34px; border-radius:50%; background:#f3e2b3; padding:0;">&nbsp;</button>
            {% endif %}
          {% endfor %}
        {% endfor %}
      </div>
    </form>
    <form method="post" action="{{ url_for('gomoku_tsume_skip') }}" class="row" style="margin-top:12px;">
      <button type="submit">分からないので次の問題へ（連続正解はリセット）</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（連続正解）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 問連続</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_gomoku(message=None):
    if "gm_board" not in session:
        gomoku_new_game()
    body = render_template_string(
        GOMOKU_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        board=list(session["gm_board"]),
        streak=int(session.get("gm_streak", 0)),
        best=best_score("gomoku-tsume", "max"),
        history=recent_scores("gomoku-tsume", 10),
        message=message,
    )
    return game_page("ゴモク一手詰め", body)


@app.route("/games/gomoku-tsume", methods=["GET"])
def gomoku_tsume():
    return render_gomoku()


@app.route("/games/gomoku-tsume/move", methods=["POST"])
def gomoku_tsume_move():
    if "gm_board" not in session:
        gomoku_new_game()
    raw = request.form.get("cell", "").strip()
    parts = raw.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return render_gomoku()
    r, c = int(parts[0]), int(parts[1])
    answer = [int(v) for v in session["gm_answer"]]
    if [r, c] == answer:
        streak = int(session.get("gm_streak", 0)) + 1
        session["gm_streak"] = streak
        record_score("gomoku-tsume", streak)
        board, ans = gomoku_new_puzzle()
        session["gm_board"] = board
        session["gm_answer"] = list(ans)
        return render_gomoku(message=f"🎉 正解！ 五つ揃いました。{streak} 問連続正解です。次の問題へ。")
    session["gm_streak"] = 0
    board, ans = gomoku_new_puzzle()
    session["gm_board"] = board
    session["gm_answer"] = list(ans)
    return render_gomoku(message="❌ 残念、そこでは揃いません。連続正解はリセット。新しい問題です。")


@app.route("/games/gomoku-tsume/skip", methods=["POST"])
def gomoku_tsume_skip():
    session["gm_streak"] = 0
    board, ans = gomoku_new_puzzle()
    session["gm_board"] = board
    session["gm_answer"] = list(ans)
    return render_gomoku(message="次の問題にしました。連続正解はリセットされています。")


# ============================
# 氷の弱点タップ
# 氷の盤面に一瞬だけ光る弱点を覚えてタップで割る（クライアント JS）。
# 60秒で何枚割れるかを競う。終了時に割った数を POST する。
# ============================
ICEWEAK_TEMPLATE = r"""
  <h1>🧊 氷の弱点タップ</h1>
  <p class="howto">「スタート」を押すと、3×3の氷のどこか1マスに弱点（✨）が一瞬だけ光ります。消えたあと、そのマスをタップして割ってください。当たると次の氷へ、外すと少し時間をロスします。60秒で割った氷の数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（割った数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">残り時間: <span id="timeLeft">60.0</span> 秒 ／ 割った数: <span id="cracked">0</span> 枚</p>
    <div style="display:grid; grid-template-columns: repeat(3, 92px); gap:8px; justify-content:center; margin:10px 0;" id="grid"></div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（割った数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 枚</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var grid = document.getElementById("grid");
  var message = document.getElementById("message");
  var timeEl = document.getElementById("timeLeft");
  var crackedEl = document.getElementById("cracked");
  var startBtn = document.getElementById("startBtn");
  var playing = false, waiting = false, target = -1, cracked = 0, endsAt = 0, tickId = null, penaltyUntil = 0;
  var cells = [];
  for (var i = 0; i < 9; i++) {
    (function(idx){
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = "🧊";
      b.style.cssText = "height:92px; font-size:40px; background:#eaf6ff;";
      b.addEventListener("click", function(){
        if (!playing || !waiting || Date.now() < penaltyUntil) { return; }
        if (idx === target) {
          cracked++;
          crackedEl.textContent = String(cracked);
          b.textContent = "💥";
          waiting = false;
          message.textContent = "割れた！ 次の弱点は…";
          setTimeout(nextRound, 450);
        } else {
          penaltyUntil = Date.now() + 600;
          message.textContent = "❌ そこじゃない！ 一瞬ストップ";
        }
      });
      grid.appendChild(b);
      cells.push(b);
    })(i);
  }
  function nextRound(){
    if (!playing) { return; }
    cells.forEach(function(b){ b.textContent = "🧊"; });
    target = Math.floor(Math.random() * 9);
    cells[target].textContent = "✨";
    message.textContent = "弱点が光った！ 場所を覚えて";
    setTimeout(function(){
      if (!playing) { return; }
      cells[target].textContent = "🧊";
      waiting = true;
      message.textContent = "弱点はどこだった？ タップして割ろう";
    }, 550);
  }
  function finish(){
    playing = false;
    waiting = false;
    clearInterval(tickId);
    timeEl.textContent = "0.0";
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(cracked));
    fetch("{{ url_for('iceweak_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + cracked + " 枚割りました";
          document.getElementById("bestline").textContent = "ベスト（割った数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    cracked = 0;
    crackedEl.textContent = "0";
    message.textContent = "弱点の光を見逃すな！";
    startBtn.disabled = true;
    endsAt = Date.now() + 60000;
    tickId = setInterval(function(){
      var left = Math.max(0, endsAt - Date.now());
      timeEl.textContent = (left / 1000).toFixed(1);
      if (left <= 0) { finish(); }
    }, 100);
    nextRound();
  });
})();
</script>
"""


@app.route("/games/iceweak", methods=["GET"])
def iceweak():
    body = render_template_string(
        ICEWEAK_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("iceweak", "max"),
        history=recent_scores("iceweak", 10),
    )
    return game_page("氷の弱点タップ", body)


@app.route("/games/iceweak/score", methods=["POST"])
def iceweak_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("iceweak", int(raw))
    return {"ok": True, "best": best_score("iceweak", "max")}


# ============================
# 賽銭チャレンジ
# 角度だけを決めてコインを投げ入れる（クライアント JS）。
# 放物線の着地点が賽銭箱の口の範囲なら成功。10投の成功数を POST する。
# ============================
SAISEN_TEMPLATE = r"""
  <h1>🪙 賽銭チャレンジ</h1>
  <p class="howto">スライダーで投げる角度（15〜75度）を決めて「投げる」。角度が浅いと手前に落ち、深いと奥に飛びすぎます。⛩️ 賽銭箱の口（緑の範囲）にコインが落ちたら成功。パワーは毎回少しずつ変わるので、落ちた場所を見て調整してね。10投のうち入った数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（入った数）: {{ best if best is not none else '—' }}</p>
    <p class="mid"><span id="throwNo">1</span> 投目 ／ 入った数: <span id="ins">0</span> ／ 10</p>
    <div id="stage" style="position:relative; height:220px; border:1px solid #ddd; border-radius:12px; background:#fdf6e3; overflow:hidden; margin:10px 0;">
      <div style="position:absolute; left:0; bottom:0; width:100%; height:26px; background:#d9c9a3;"></div>
      <div id="box" style="position:absolute; bottom:26px; width:64px; height:44px; background:#a33b2e; border-radius:4px; text-align:center; font-size:24px; line-height:44px;">⛩️</div>
      <div id="mouth" style="position:absolute; bottom:70px; height:6px; background:#6bcb77; border-radius:3px;"></div>
      <div id="coin" style="position:absolute; font-size:22px; display:none;">🪙</div>
      <div style="position:absolute; left:8px; bottom:30px; font-size:26px;">🙂</div>
    </div>
    <div class="row">
      <label>角度 <input type="range" id="angle" min="15" max="75" value="45" style="width:200px;"> <span id="angleVal">45</span>°</label>
    </div>
    <p class="result" id="message">角度を決めて「投げる」</p>
    <div class="row">
      <button type="button" id="startBtn">新しい10投を始める</button>
      <button type="button" id="throwBtn" disabled>投げる</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（入った数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 回</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var box = document.getElementById("box");
  var mouth = document.getElementById("mouth");
  var coin = document.getElementById("coin");
  var message = document.getElementById("message");
  var angleInput = document.getElementById("angle");
  var angleVal = document.getElementById("angleVal");
  var throwBtn = document.getElementById("throwBtn");
  var startBtn = document.getElementById("startBtn");
  var throwNoEl = document.getElementById("throwNo");
  var insEl = document.getElementById("ins");
  var W = 660, GROUND = 26, ORIGIN_X = 34, ORIGIN_Y = 200;
  var mouthLeft = 0, mouthRight = 0, power = 0;
  var throwing = false, throws = 0, ins = 0, playing = false;
  function setupBox(){
    var bx = 330 + Math.floor(Math.random() * 160);  // 330〜489
    box.style.left = bx + "px";
    mouth.style.left = (bx + 6) + "px";
    mouth.style.width = "52px";
    mouthLeft = bx + 6;
    mouthRight = bx + 58;
  }
  function newPower(){
    power = 300 + Math.random() * 130;  // 300〜430 px 相当の飛距離レンジ
  }
  function finish(){
    playing = false;
    throwBtn.disabled = true;
    startBtn.disabled = false;
    startBtn.textContent = "新しい10投を始める";
    var form = new FormData();
    form.append("score", String(ins));
    fetch("{{ url_for('saisen_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 10投終了！ " + ins + " 回入りました";
          document.getElementById("bestline").textContent = "ベスト（入った数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  angleInput.addEventListener("input", function(){
    angleVal.textContent = angleInput.value;
  });
  startBtn.addEventListener("click", function(){
    throws = 0; ins = 0; playing = true;
    throwNoEl.textContent = "1";
    insEl.textContent = "0";
    setupBox();
    newPower();
    coin.style.display = "none";
    message.textContent = "角度を決めて「投げる」";
    throwBtn.disabled = false;
    startBtn.disabled = true;
  });
  throwBtn.addEventListener("click", function(){
    if (!playing || throwing) { return; }
    throwing = true;
    throwBtn.disabled = true;
    var deg = parseInt(angleInput.value, 10);
    var rad = deg * Math.PI / 180;
    var vx = Math.cos(rad) * power;
    var vy = Math.sin(rad) * power;
    var g = 500, t = 0, last = null;
    coin.style.display = "block";
    function stepFn(ts){
      if (!last) { last = ts; }
      var dt = Math.min(0.05, (ts - last) / 1000);
      last = ts;
      t += dt;
      var x = ORIGIN_X + vx * t;
      var y = ORIGIN_Y - (vy * t - 0.5 * g * t * t);
      coin.style.left = x + "px";
      coin.style.top = y + "px";
      if (y < ORIGIN_Y) {
        requestAnimationFrame(stepFn);
        return;
      }
      // 着地
      coin.style.top = ORIGIN_Y + "px";
      throwing = false;
      throws++;
      var landed = x;
      var hit = landed >= mouthLeft && landed <= mouthRight;
      if (hit) {
        ins++;
        insEl.textContent = String(ins);
        message.textContent = "🎉 入った！ ご縁がありますように";
      } else if (landed < mouthLeft) {
        message.textContent = "手前に落ちた… もう少し角度を深く（大きく）";
      } else {
        message.textContent = "奥に飛びすぎた… 角度を浅く（小さく）";
      }
      if (throws >= 10) { setTimeout(finish, 600); return; }
      throwNoEl.textContent = String(throws + 1);
      newPower();
      throwBtn.disabled = false;
    }
    requestAnimationFrame(stepFn);
  });
})();
</script>
"""


@app.route("/games/saisen", methods=["GET"])
def saisen():
    body = render_template_string(
        SAISEN_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("saisen", "max"),
        history=recent_scores("saisen", 10),
    )
    return game_page("賽銭チャレンジ", body)


@app.route("/games/saisen/score", methods=["POST"])
def saisen_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 10):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("saisen", int(raw))
    return {"ok": True, "best": best_score("saisen", "max")}


# ============================
# すずあつめ落ちもの
# 落ちてくる鈴をかごでキャッチする落ちものゲーム（クライアント JS）。
# 通常の鈴 +1点、金の鈴 +3点、石 −2点。30秒の得点を POST する。
# ============================
SUZUATUME_TEMPLATE = r"""
  <h1>🔔 すずあつめ落ちもの</h1>
  <p class="howto">「スタート」を押すと30秒間、鈴が落ちてきます。下のかごをボタンかキー（←→）で動かしてキャッチしてください。通常の鈴は +1点、金色の鈴は +3点、石（🪨）を取ると −2点（0点未満にはなりません）。最終得点を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（最高得点）: {{ best if best is not none else '—' }}</p>
    <p class="mid">残り時間: <span id="timeLeft">30.0</span> 秒 ／ 得点: <span id="score">0</span></p>
    <div id="stage" style="position:relative; height:340px; border:1px solid #ddd; border-radius:12px; background:#fffaf0; overflow:hidden; margin:10px 0;">
      <div id="basket" style="position:absolute; bottom:6px; width:72px; text-align:center; font-size:34px;">🧺</div>
    </div>
    <div class="row">
      <button type="button" id="leftBtn">← 左</button>
      <button type="button" id="rightBtn">右 →</button>
    </div>
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
  var stage = document.getElementById("stage");
  var basket = document.getElementById("basket");
  var message = document.getElementById("message");
  var scoreEl = document.getElementById("score");
  var timeEl = document.getElementById("timeLeft");
  var startBtn = document.getElementById("startBtn");
  var playing = false, score = 0, endsAt = 0, spawnId = null, tickId = null, fallId = null;
  var basketX = 45; // %
  var items = [];
  function setBasket(){
    basket.style.left = "calc(" + basketX + "% - 36px)";
  }
  function moveBasket(d){
    basketX = Math.max(4, Math.min(96, basketX + d));
    setBasket();
  }
  function spawn(){
    if (!playing) { return; }
    var r = Math.random();
    var kind = r < 0.15 ? "stone" : (r < 0.35 ? "gold" : "bell");
    var el = document.createElement("div");
    el.textContent = kind === "stone" ? "🪨" : "🔔";
    el.style.cssText = "position:absolute; top:-36px; font-size:28px; left:" + (Math.random() * 92) + "%;"
      + (kind === "gold" ? " filter:sepia(1) saturate(4) hue-rotate(5deg);" : "");
    stage.appendChild(el);
    items.push({el: el, y: -36, kind: kind, speed: 130 + Math.random() * 130});
  }
  function fallStep(){
    if (!playing) { return; }
    var H = stage.clientHeight;
    var basketLeft = stage.clientWidth * basketX / 100 - 36;
    var basketRight = basketLeft + 72;
    items = items.filter(function(it){
      it.y += it.speed * 0.05;
      it.el.style.top = it.y + "px";
      if (it.y > H - 56) {
        var cx = it.el.offsetLeft + 14;
        var caught = cx >= basketLeft && cx <= basketRight;
        it.el.remove();
        if (caught) {
          if (it.kind === "stone") { score = Math.max(0, score - 2); }
          else if (it.kind === "gold") { score += 3; }
          else { score += 1; }
          scoreEl.textContent = String(score);
        }
        return false;
      }
      return true;
    });
  }
  function finish(){
    playing = false;
    clearInterval(spawnId);
    clearInterval(tickId);
    clearInterval(fallId);
    items.forEach(function(it){ it.el.remove(); });
    items = [];
    timeEl.textContent = "0.0";
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(score));
    fetch("{{ url_for('suzuatume_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ 得点は " + score + " 点でした";
          document.getElementById("bestline").textContent = "ベスト（最高得点）: " + d.best;
        }
      })
      .catch(function(){});
  }
  document.getElementById("leftBtn").addEventListener("click", function(){ moveBasket(-8); });
  document.getElementById("rightBtn").addEventListener("click", function(){ moveBasket(8); });
  document.addEventListener("keydown", function(e){
    if (e.key === "ArrowLeft") { moveBasket(-8); }
    if (e.key === "ArrowRight") { moveBasket(8); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    score = 0;
    scoreEl.textContent = "0";
    basketX = 45;
    setBasket();
    message.textContent = "鈴を集めよう！ 石は避けてね";
    startBtn.disabled = true;
    endsAt = Date.now() + 30000;
    spawnId = setInterval(spawn, 700);
    fallId = setInterval(fallStep, 50);
    spawn();
    tickId = setInterval(function(){
      var left = Math.max(0, endsAt - Date.now());
      timeEl.textContent = (left / 1000).toFixed(1);
      if (left <= 0) { finish(); }
    }, 100);
  });
  setBasket();
})();
</script>
"""


@app.route("/games/suzuatume", methods=["GET"])
def suzuatume():
    body = render_template_string(
        SUZUATUME_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("suzuatume", "max"),
        history=recent_scores("suzuatume", 10),
    )
    return game_page("すずあつめ落ちもの", body)


@app.route("/games/suzuatume/score", methods=["POST"])
def suzuatume_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("suzuatume", int(raw))
    return {"ok": True, "best": best_score("suzuatume", "max")}


# ============================
# トンネル顔出し当て
# 3つのトンネルから顔を出すキャラの場所と順番を覚える記憶ゲーム（JS）。
# 当てた問題数を終了時に POST する。3回ミスで終了。
# ============================
TUNNELFACE_TEMPLATE = r"""
  <h1>🚇 トンネル顔出し当て</h1>
  <p class="howto">3つのトンネルからネコ（🐱）が何回か顔を出します。出た「場所と順番」を覚えて、その通りにトンネルをクリックしてください。問題ごとに顔出しの回数が増えていきます。3回ミスで終了、当てた問題数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（当てた問題数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">問題: <span id="qno">1</span> ／ 当てた数: <span id="cleared">0</span> ／ ミス: <span id="miss">0</span> / 3</p>
    <div class="row" style="gap:14px; margin:12px 0;">
      <button type="button" class="tunnel" data-i="0" style="width:110px; height:110px; font-size:44px; background:#444; color:#fff; border-radius:50% 50% 0 0;">🕳️</button>
      <button type="button" class="tunnel" data-i="1" style="width:110px; height:110px; font-size:44px; background:#444; color:#fff; border-radius:50% 50% 0 0;">🕳️</button>
      <button type="button" class="tunnel" data-i="2" style="width:110px; height:110px; font-size:44px; background:#444; color:#fff; border-radius:50% 50% 0 0;">🕳️</button>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（当てた問題数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 問</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var tunnels = document.querySelectorAll(".tunnel");
  var message = document.getElementById("message");
  var qnoEl = document.getElementById("qno");
  var clearedEl = document.getElementById("cleared");
  var missEl = document.getElementById("miss");
  var startBtn = document.getElementById("startBtn");
  var playing = false, phase = "idle"; // idle | showing | answering
  var seq = [], answerPos = 0, qno = 1, cleared = 0, miss = 0;
  function showFace(i, on){
    tunnels[i].textContent = on ? "🐱" : "🕳️";
  }
  function playSequence(done){
    phase = "showing";
    message.textContent = "よく見て覚えて！";
    var i = 0;
    function step(){
      if (i >= seq.length) { setTimeout(done, 350); return; }
      var t = seq[i];
      showFace(t, true);
      setTimeout(function(){
        showFace(t, false);
        i++;
        setTimeout(step, 220);
      }, 480);
    }
    step();
  }
  function nextQuestion(){
    var len = 2 + qno; // 問題1は3回、増えていく
    seq = [];
    for (var i = 0; i < len; i++) { seq.push(Math.floor(Math.random() * 3)); }
    answerPos = 0;
    qnoEl.textContent = String(qno);
    playSequence(function(){
      phase = "answering";
      message.textContent = "出た順番通りにクリックしてね";
    });
  }
  function finish(){
    playing = false;
    phase = "idle";
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(cleared));
    fetch("{{ url_for('tunnelface_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + cleared + " 問当てました";
          document.getElementById("bestline").textContent = "ベスト（当てた問題数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  tunnels.forEach(function(btn){
    btn.addEventListener("click", function(){
      if (!playing || phase !== "answering") { return; }
      var i = parseInt(btn.getAttribute("data-i"), 10);
      showFace(i, true);
      setTimeout(function(){ showFace(i, false); }, 250);
      if (i === seq[answerPos]) {
        answerPos++;
        if (answerPos >= seq.length) {
          cleared++;
          clearedEl.textContent = String(cleared);
          message.textContent = "⭕ 正解！ 次の問題へ";
          qno++;
          phase = "idle";
          setTimeout(nextQuestion, 800);
        }
      } else {
        miss++;
        missEl.textContent = String(miss);
        message.textContent = "❌ 順番が違う… " + (miss >= 3 ? "" : "もう一度見せます");
        phase = "idle";
        if (miss >= 3) { setTimeout(finish, 800); return; }
        setTimeout(function(){ playSequence(function(){
          phase = "answering";
          answerPos = 0;
          message.textContent = "もう一度、順番通りにクリックしてね";
        }); }, 800);
      }
    });
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    qno = 1; cleared = 0; miss = 0;
    clearedEl.textContent = "0";
    missEl.textContent = "0";
    startBtn.disabled = true;
    message.textContent = "問題1！";
    nextQuestion();
  });
})();
</script>
"""


@app.route("/games/tunnelface", methods=["GET"])
def tunnelface():
    body = render_template_string(
        TUNNELFACE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("tunnelface", "max"),
        history=recent_scores("tunnelface", 10),
    )
    return game_page("トンネル顔出し当て", body)


@app.route("/games/tunnelface/score", methods=["POST"])
def tunnelface_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("tunnelface", int(raw))
    return {"ok": True, "best": best_score("tunnelface", "max")}


# ============================
# バッグ詰めパズルバトル
# 形の違う道具を 6×6 のバッグに詰めるパッキングパズル（サーバー側）。
# 道具は回転可。埋めたマス数で CPU（ランダム合法配置）と勝負する。
# ============================
BAGPACK_SIZE = 6
BAGPACK_ITEMS = [
    ("リュック", [(0, 0), (1, 0), (0, 1), (1, 1)]),          # 2×2
    ("水筒", [(0, 0), (0, 1), (0, 2)]),                        # 縦3
    ("傘", [(0, 0), (1, 0), (2, 0), (3, 0)]),                  # 横4
    ("本", [(0, 0), (1, 0), (0, 1)]),                          # L字3
    ("タオル", [(0, 0), (1, 0), (2, 0), (1, 1)]),              # T字4
    ("お弁当箱", [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]),  # 3×2
    ("縄跳び", [(0, 0), (1, 0)]),                              # 横2
    ("帽子", [(0, 0), (0, 1)]),                                # 縦2
]


def bagpack_rotate(cells):
    """セル集合を90度回転させる（正規化して返す）。"""
    rotated = [(c, -r) for r, c in cells]
    min_r = min(r for r, _ in rotated)
    min_c = min(c for _, c in rotated)
    return sorted((r - min_r, c - min_c) for r, c in rotated)


def bagpack_can_place(grid, cells, row: int, col: int) -> bool:
    for dr, dc in cells:
        r, c = row + dr, col + dc
        if not (0 <= r < BAGPACK_SIZE and 0 <= c < BAGPACK_SIZE):
            return False
        if grid[r][c]:
            return False
    return True


def bagpack_place(grid, cells, row: int, col: int, mark):
    new_grid = [list(line) for line in grid]
    for dr, dc in cells:
        new_grid[row + dr][col + dc] = mark
    return new_grid


def bagpack_count(grid) -> int:
    return sum(1 for line in grid for v in line if v)


def bagpack_cpu_fill(items) -> int:
    """CPU の詰め方：道具を提示順にランダムな合法位置へ置き、埋めたマス数を返す。"""
    grid = [[0] * BAGPACK_SIZE for _ in range(BAGPACK_SIZE)]
    filled = 0
    for idx, (_name, cells) in enumerate(items):
        rotations = [cells]
        cur = cells
        for _ in range(3):
            cur = bagpack_rotate(cur)
            if cur not in rotations:
                rotations.append(cur)
        options = []
        for rot in rotations:
            for r in range(BAGPACK_SIZE):
                for c in range(BAGPACK_SIZE):
                    if bagpack_can_place(grid, rot, r, c):
                        options.append((rot, r, c))
        if not options:
            continue
        rot, r, c = random.choice(options)
        grid = bagpack_place(grid, rot, r, c, idx + 1)
        filled += len(rot)
    return filled


def bagpack_new_game() -> None:
    session["bp_grid"] = [[0] * BAGPACK_SIZE for _ in range(BAGPACK_SIZE)]
    session["bp_item"] = 0
    session["bp_rot"] = 0
    session["bp_over"] = False
    session["bp_wins"] = int(session.get("bp_wins", 0))


BAGPACK_TEMPLATE = r"""
  <h1>🎒 バッグ詰めパズルバトル</h1>
  <p class="howto">6×6のバッグに、形の違う道具を順番に詰めていきます。今の道具の形を見て、置きたい左上のマスをクリック。「回転」で90度回せます。置けない道具は「スキップ」。全部終わったら、埋めたマス数で CPU の詰め方と勝負です。勝ったラウンド数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">あなたの埋めた数: {{ filled }} / 36 ／ このセッションの勝利数: {{ wins }} ／ ベスト（勝利数）: {{ best if best is not none else '—' }}</p>
    <div style="display:flex; gap:18px; flex-wrap:wrap; justify-content:center;">
      <form method="post" action="{{ url_for('bagpack_put') }}">
        <div style="display:grid; grid-template-columns: repeat(6, 40px); gap:3px;">
          {% for r in range(6) %}
            {% for c in range(6) %}
              {% if grid[r][c] %}
                <button type="button" disabled style="height:40px; background:#ffd9a0; padding:0; font-size:11px;">{{ grid[r][c] }}</button>
              {% elif over %}
                <button type="button" disabled style="height:40px; background:#f7f7f7; padding:0;">&nbsp;</button>
              {% else %}
                <button type="submit" name="cell" value="{{ r }}-{{ c }}" style="height:40px; background:#fff; padding:0;">&nbsp;</button>
              {% endif %}
            {% endfor %}
          {% endfor %}
        </div>
      </form>
      <div style="min-width:150px;">
        {% if over %}
          <p class="mid">結果は上のメッセージへ。<br>次のラウンドへどうぞ。</p>
          <form method="post" action="{{ url_for('bagpack_next') }}"><button type="submit">次のラウンド</button></form>
        {% elif item %}
          <p class="mid">今の道具：<strong>{{ item[0] }}</strong>（{{ item[1]|length }}マス）</p>
          <div style="display:grid; grid-template-columns: repeat(4, 20px); gap:2px; margin-bottom:10px;">
            {% for r in range(4) %}
              {% for c in range(4) %}
                {% if (r, c) in shape %}
                  <span style="display:block; height:20px; background:#6bcb77; border-radius:3px;"></span>
                {% else %}
                  <span style="display:block; height:20px;"></span>
                {% endif %}
              {% endfor %}
            {% endfor %}
          </div>
          <form method="post" action="{{ url_for('bagpack_rotate_route') }}" style="margin-bottom:8px;"><button type="submit">回転する</button></form>
          <form method="post" action="{{ url_for('bagpack_skip') }}"><button type="submit">この道具はスキップ</button></form>
        {% endif %}
      </div>
    </div>
    <form method="post" action="{{ url_for('bagpack_reset') }}" class="row" style="margin-top:12px;">
      <button type="submit">セッションをリセット</button>
    </form>
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


def render_bagpack(message=None):
    if "bp_grid" not in session:
        bagpack_new_game()
    idx = int(session.get("bp_item", 0))
    item = None
    shape = []
    if idx < len(BAGPACK_ITEMS):
        name, cells = BAGPACK_ITEMS[idx]
        cur = [tuple(p) for p in cells]
        for _ in range(int(session.get("bp_rot", 0)) % 4):
            cur = bagpack_rotate(cur)
        item = (name, cur)
        shape = [tuple(p) for p in cur]
    grid = [[int(v) for v in line] for line in session["bp_grid"]]
    body = render_template_string(
        BAGPACK_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        grid=grid,
        item=item,
        shape=shape,
        filled=bagpack_count(grid),
        wins=int(session.get("bp_wins", 0)),
        over=bool(session.get("bp_over", False)),
        best=best_score("bagpack", "max"),
        history=recent_scores("bagpack", 10),
        message=message,
    )
    return game_page("バッグ詰めパズルバトル", body)


def bagpack_finish_round():
    """全道具が終わった時点で CPU と比べて勝敗を付け、結果メッセージを返す。"""
    grid = [[int(v) for v in line] for line in session["bp_grid"]]
    mine = bagpack_count(grid)
    cpu = bagpack_cpu_fill(BAGPACK_ITEMS)
    session["bp_over"] = True
    if mine > cpu:
        wins = int(session.get("bp_wins", 0)) + 1
        session["bp_wins"] = wins
        record_score("bagpack", wins)
        return f"🎉 あなたの勝ち！ あなた {mine} マス vs CPU {cpu} マス。このセッション {wins} 勝目です。"
    if mine < cpu:
        return f"CPU の勝ち… あなた {mine} マス vs CPU {cpu} マス。"
    return f"引き分け！ あなた {mine} マス vs CPU {cpu} マス。"


@app.route("/games/bagpack", methods=["GET"])
def bagpack():
    return render_bagpack()


@app.route("/games/bagpack/put", methods=["POST"])
def bagpack_put():
    if "bp_grid" not in session:
        bagpack_new_game()
    if session.get("bp_over"):
        return render_bagpack()
    idx = int(session.get("bp_item", 0))
    if idx >= len(BAGPACK_ITEMS):
        return render_bagpack()
    raw = request.form.get("cell", "").strip()
    parts = raw.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return render_bagpack()
    r, c = int(parts[0]), int(parts[1])
    _name, cells = BAGPACK_ITEMS[idx]
    cur = [tuple(p) for p in cells]
    for _ in range(int(session.get("bp_rot", 0)) % 4):
        cur = bagpack_rotate(cur)
    grid = [[int(v) for v in line] for line in session["bp_grid"]]
    if not bagpack_can_place(grid, cur, r, c):
        return render_bagpack(message="そこには置けません。形がはみ出すか、他の道具と重なります。")
    session["bp_grid"] = bagpack_place(grid, cur, r, c, idx + 1)
    session["bp_item"] = idx + 1
    session["bp_rot"] = 0
    if idx + 1 >= len(BAGPACK_ITEMS):
        msg = bagpack_finish_round()
        return render_bagpack(message=msg)
    return render_bagpack()


@app.route("/games/bagpack/rotate", methods=["POST"])
def bagpack_rotate_route():
    if "bp_grid" not in session:
        bagpack_new_game()
    session["bp_rot"] = (int(session.get("bp_rot", 0)) + 1) % 4
    return render_bagpack()


@app.route("/games/bagpack/skip", methods=["POST"])
def bagpack_skip():
    if "bp_grid" not in session:
        bagpack_new_game()
    if session.get("bp_over"):
        return render_bagpack()
    idx = int(session.get("bp_item", 0)) + 1
    session["bp_item"] = idx
    session["bp_rot"] = 0
    if idx >= len(BAGPACK_ITEMS):
        msg = bagpack_finish_round()
        return render_bagpack(message=msg)
    return render_bagpack(message="道具をスキップしました。")


@app.route("/games/bagpack/next", methods=["POST"])
def bagpack_next():
    wins = int(session.get("bp_wins", 0))
    bagpack_new_game()
    session["bp_wins"] = wins
    return render_bagpack(message="新しいラウンドです。")


@app.route("/games/bagpack/reset", methods=["POST"])
def bagpack_reset():
    session.pop("bp_grid", None)
    session.pop("bp_item", None)
    session.pop("bp_rot", None)
    session.pop("bp_over", None)
    session.pop("bp_wins", None)
    flash("セッションをリセットしました。", "ok")
    return redirect(url_for("bagpack"))


# ============================
# 3ワードモンスター
# 3つの言葉の組み合わせでモンスターを生成し、ステータスで CPU と対戦
# （サーバー側）。言葉の並びと組み合わせから決定的にステータスが決まる。
# ============================
WORDMONSTER_WORDS = {
    "属性": ["ほのお", "みず", "くさ", "かみなり", "こおり", "じめん"],
    "体": ["スライム", "ドラゴン", "ゴーレム", "とり", "うま", "さかな"],
    "性格": ["おこりんぼ", "のんびり", "やんちゃ", "まじめ", "ずるい", "やさしい"],
}
WORDMONSTER_TYPES = {
    "ほのお": "炎", "みず": "水", "くさ": "草",
    "かみなり": "雷", "こおり": "氷", "じめん": "地",
}
WORDMONSTER_BEATS = {"炎": "草", "草": "水", "水": "炎", "雷": "水", "氷": "草", "地": "雷"}


def wordmonster_stats(attr: str, body: str, trait: str) -> dict:
    """3ワードから決定的にステータスを算出する（同じ組み合わせは同じ結果）。"""
    seed = (attr + "|" + body + "|" + trait).encode("utf-8")
    h = sum((i + 1) * b for i, b in enumerate(seed))
    hp = 40 + h % 41            # 40〜80
    atk = 10 + (h // 7) % 21    # 10〜30
    spd = 5 + (h // 13) % 16    # 5〜20
    return {"hp": hp, "atk": atk, "spd": spd, "type": WORDMONSTER_TYPES[attr]}


def wordmonster_battle(mine: dict, cpu: dict) -> str:
    """簡易バトル。タイプ相性で攻撃が1.5倍（切り捨て）。先手は素早さ順。
    'win' / 'lose' / 'draw' を返す。"""
    def eff(attacker, defender):
        dmg = attacker["atk"]
        if WORDMONSTER_BEATS.get(attacker["type"]) == defender["type"]:
            dmg = dmg * 3 // 2
        return dmg
    hp_m, hp_c = mine["hp"], cpu["hp"]
    order = ["me", "cpu"] if mine["spd"] >= cpu["spd"] else ["cpu", "me"]
    for _ in range(100):
        for turn in order:
            if turn == "me":
                hp_c -= eff(mine, cpu)
                if hp_c <= 0:
                    return "win"
            else:
                hp_m -= eff(cpu, mine)
                if hp_m <= 0:
                    return "lose"
    return "draw"


WORDMONSTER_TEMPLATE = r"""
  <h1>👹 3ワードモンスター</h1>
  <p class="howto">属性・体・性格の3つの言葉を1つずつ選ぶとモンスターが生まれます。組み合わせで HP・攻撃・素早さとタイプが決まります（同じ組み合わせはいつも同じ結果）。「生成して対戦」で CPU のモンスターとバトル。タイプ相性（炎＞草＞水＞炎、雷＞水、氷＞草、地＞雷）で攻撃が1.5倍です。勝利数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">このセッションの勝利数: {{ wins }} ／ ベスト（勝利数）: {{ best if best is not none else '—' }}</p>
    {% if result %}
      <div class="split">
        <div class="panel">
          <h3>あなたの モンスター</h3>
          <p class="mid">{{ result.mine_name }}</p>
          <p>タイプ: {{ result.mine.type }} ／ HP {{ result.mine.hp }} ／ 攻撃 {{ result.mine.atk }} ／ 素早さ {{ result.mine.spd }}</p>
        </div>
        <div class="panel right">
          <h3>CPU のモンスター</h3>
          <p class="mid">{{ result.cpu_name }}</p>
          <p>タイプ: {{ result.cpu.type }} ／ HP {{ result.cpu.hp }} ／ 攻撃 {{ result.cpu.atk }} ／ 素早さ {{ result.cpu.spd }}</p>
        </div>
      </div>
    {% endif %}
    <form method="post" action="{{ url_for('wordmonster_battle_route') }}">
      <div class="split">
        {% for group, words in word_groups %}
          <div>
            <p class="mid">{{ group }}</p>
            {% for w in words %}
              <label style="display:block; margin:4px 0;"><input type="radio" name="{{ group }}" value="{{ w }}" {% if loop.first %}checked{% endif %}> {{ w }}</label>
            {% endfor %}
          </div>
        {% endfor %}
      </div>
      <div class="row" style="margin-top:12px;">
        <button type="submit">生成して対戦</button>
      </div>
    </form>
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


def render_wordmonster(message=None, result=None):
    body = render_template_string(
        WORDMONSTER_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        word_groups=list(WORDMONSTER_WORDS.items()),
        wins=int(session.get("wm_wins", 0)),
        result=result,
        best=best_score("wordmonster", "max"),
        history=recent_scores("wordmonster", 10),
        message=message,
    )
    return game_page("3ワードモンスター", body)


@app.route("/games/wordmonster", methods=["GET"])
def wordmonster():
    return render_wordmonster()


@app.route("/games/wordmonster/battle", methods=["POST"])
def wordmonster_battle_route():
    attr = request.form.get("属性", "")
    body_w = request.form.get("体", "")
    trait = request.form.get("性格", "")
    if attr not in WORDMONSTER_WORDS["属性"] or body_w not in WORDMONSTER_WORDS["体"] or trait not in WORDMONSTER_WORDS["性格"]:
        return render_wordmonster(message="言葉を3つ選んでください。")
    mine = wordmonster_stats(attr, body_w, trait)
    cpu_words = [random.choice(WORDMONSTER_WORDS["属性"]),
                 random.choice(WORDMONSTER_WORDS["体"]),
                 random.choice(WORDMONSTER_WORDS["性格"])]
    cpu = wordmonster_stats(*cpu_words)
    verdict = wordmonster_battle(mine, cpu)
    result = {
        "mine": mine, "cpu": cpu,
        "mine_name": f"{attr}の{body_w}（{trait}）",
        "cpu_name": f"{cpu_words[0]}の{cpu_words[1]}（{cpu_words[2]}）",
    }
    if verdict == "win":
        wins = int(session.get("wm_wins", 0)) + 1
        session["wm_wins"] = wins
        record_score("wordmonster", wins)
        return render_wordmonster(message=f"🎉 あなたのモンスターの勝ち！ このセッション {wins} 勝目です。", result=result)
    if verdict == "lose":
        return render_wordmonster(message="CPU のモンスターの勝ち…。言葉の組み合わせを変えて再挑戦！", result=result)
    return render_wordmonster(message="引き分けでした。別の組み合わせで再挑戦！", result=result)


# ============================
# もじおとし
# 落ちてくるひらがなを並べて言葉を作ると消えるパズル（クライアント JS）。
# フィールドに下から積み上がり、上まで埋まると終了。消した言葉数を POST 。
# ============================
MOJIOTOSHI_TEMPLATE = r"""
  <h1>🗑️ もじおとし</h1>
  <p class="howto">ひらがなが1文字ずつ落ちてきます。←→ボタンかキーで落下位置を動かし、下のマスに積み上げていきます。横一列に並んだ文字で言葉ができたら消えます（例：す・し／ら・ー・め・ん）。一番上まで埋まると終了。消した言葉の数を記録します。言葉リストは内蔵のものを使います。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（消した言葉）: {{ best if best is not none else '—' }}</p>
    <p class="mid">消した言葉: <span id="cleared">0</span> つ ／ 次の文字: <span id="nextChar">—</span></p>
    <div id="board" style="display:grid; grid-template-columns: repeat(6, 44px); gap:3px; justify-content:center; margin:10px 0;"></div>
    <div class="row">
      <button type="button" id="leftBtn">← 左</button>
      <button type="button" id="dropBtn">落とす ⬇</button>
      <button type="button" id="rightBtn">右 →</button>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（消した言葉）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} つ</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var boardEl = document.getElementById("board");
  var message = document.getElementById("message");
  var clearedEl = document.getElementById("cleared");
  var nextEl = document.getElementById("nextChar");
  var startBtn = document.getElementById("startBtn");
  var COLS = 6, ROWS = 8;
  var WORDS = ["すし","うどん","そば","らーめん","てんぷら","やきとり","おでん","なっとう","みそしる","かれー","ぱん","けーき","ぷりん","あいす","こーひー","おちゃ","ねこ","いぬ","とり","さかな","はな","ほし","つき","ゆき","あめ","かぜ","うみ","やま","かわ","もり","そら","たいよう","りんご","みかん","ばなな","いちご","めろん","ぶどう","もも","すいか","がくせい","せんせい","がっこう","でんしゃ","ひこうき"];
  var POOL = "すしうどんそばらーめんてぷやきおなっとみかれぱけあいこちゃねいとさはほつゆあかうみやわそたいりごばなちめぶどがせんがでしゃひ";
  var grid = [], falling = null, fallY = 0, col = 2, playing = false, tickId = null, cleared = 0;
  var cells = [];
  for (var i = 0; i < ROWS * COLS; i++) {
    var d = document.createElement("div");
    d.style.cssText = "height:44px; line-height:44px; text-align:center; font-size:22px; border:1px solid #eee; border-radius:6px; background:#fff;";
    boardEl.appendChild(d);
    cells.push(d);
  }
  function draw(){
    for (var r = 0; r < ROWS; r++) {
      for (var c = 0; c < COLS; c++) {
        var ch = grid[r][c];
        var el = cells[r * COLS + c];
        if (falling && r === Math.floor(fallY) && c === col) {
          el.textContent = falling;
          el.style.background = "#ffe9a8";
        } else {
          el.textContent = ch || "";
          el.style.background = ch ? "#eef5fa" : "#fff";
        }
      }
    }
  }
  function findWord(){
    // 下の行から、横並びで辞書に一致する並びを探す（長い方を優先）
    for (var r = ROWS - 1; r >= 0; r--) {
      var line = grid[r].join("");
      for (var w = 0; w < WORDS.length; w++) {
        var word = WORDS[w];
        var idx = line.indexOf(word);
        if (idx >= 0) {
          return {row: r, start: idx, len: word.length, word: word};
        }
      }
    }
    return null;
  }
  function applyGravity(){
    for (var c = 0; c < COLS; c++) {
      var stack = [];
      for (var r = ROWS - 1; r >= 0; r--) { if (grid[r][c]) { stack.push(grid[r][c]); } }
      for (var r2 = ROWS - 1; r2 >= 0; r2--) {
        grid[r2][c] = stack.length ? stack.shift() : "";
      }
    }
  }
  function settle(){
    var hit = findWord();
    if (hit) {
      for (var i = 0; i < hit.len; i++) { grid[hit.row][hit.start + i] = ""; }
      cleared++;
      clearedEl.textContent = String(cleared);
      message.textContent = "✨ 「" + hit.word + "」が消えた！";
      applyGravity();
      var again = findWord();
      if (again) { setTimeout(settle, 250); }
    }
    if (grid[0].some(function(v){ return v; })) {
      finish();
      return;
    }
    spawn();
  }
  function spawn(){
    if (!playing) { return; }
    falling = POOL[Math.floor(Math.random() * POOL.length)];
    nextEl.textContent = falling;
    col = 2;
    fallY = 0;
    draw();
  }
  function land(){
    // 落下位置の列の一番下の空きに置く
    var r = ROWS - 1;
    while (r >= 0 && grid[r][col]) { r--; }
    if (r < 0) { finish(); return; }
    grid[r][col] = falling;
    falling = null;
    draw();
    settle();
  }
  function finish(){
    playing = false;
    falling = null;
    clearInterval(tickId);
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(cleared));
    fetch("{{ url_for('mojiotoshi_score') }}", {method: "POST", body: form})
      .then(function(rr){ return rr.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 上まで埋まって終了！ " + cleared + " つの言葉を消しました";
          document.getElementById("bestline").textContent = "ベスト（消した言葉）: " + d.best;
        }
      })
      .catch(function(){});
  }
  document.getElementById("leftBtn").addEventListener("click", function(){ if (playing && falling) { col = Math.max(0, col - 1); draw(); } });
  document.getElementById("rightBtn").addEventListener("click", function(){ if (playing && falling) { col = Math.min(COLS - 1, col + 1); draw(); } });
  document.getElementById("dropBtn").addEventListener("click", function(){ if (playing && falling) { land(); } });
  document.addEventListener("keydown", function(e){
    if (!playing || !falling) { return; }
    if (e.key === "ArrowLeft") { col = Math.max(0, col - 1); draw(); }
    if (e.key === "ArrowRight") { col = Math.min(COLS - 1, col + 1); draw(); }
    if (e.key === "ArrowDown") { land(); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    cleared = 0;
    clearedEl.textContent = "0";
    grid = [];
    for (var r = 0; r < ROWS; r++) { grid.push(["", "", "", "", "", ""]); }
    message.textContent = "言葉を作って消そう！";
    startBtn.disabled = true;
    spawn();
    tickId = setInterval(function(){
      if (!playing || !falling) { return; }
      fallY += 0.5;
      // その列の積み上がり位置まで来たら着地
      var top = ROWS - 1;
      while (top >= 0 && grid[top][col]) { top--; }
      if (Math.floor(fallY) >= top) { fallY = top; land(); return; }
      draw();
    }, 400);
  });
})();
</script>
"""


@app.route("/games/mojiotoshi", methods=["GET"])
def mojiotoshi():
    body = render_template_string(
        MOJIOTOSHI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("mojiotoshi", "max"),
        history=recent_scores("mojiotoshi", 10),
    )
    return game_page("もじおとし", body)


@app.route("/games/mojiotoshi/score", methods=["POST"])
def mojiotoshi_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("mojiotoshi", int(raw))
    return {"ok": True, "best": best_score("mojiotoshi", "max")}


# ============================
# 面接吹き出しジャッジ
# 面接の質問に3つの回答候補から1つ選ぶ選択ゲーム（サーバー側）。
# 回答ごとに点数が加わり、最後に S〜D の評価を付けて記録する。
# 評価点は score として保存する（S=5, A=4, B=3, C=2, D=1）。
# ============================
MENSETSU_QUESTIONS = [
    {
        "q": "まずは自己紹介をお願いします。",
        "choices": [
            ("趣味はゲームです。よろしくお願いします。", 3),
            ("前職では営業事務として3年勤務し、資料作成と電話対応を担当しました。本日はよろしくお願いいたします。", 10),
            ("えーっと、特に話すことはないです。", 0),
        ],
    },
    {
        "q": "当社を志望した理由を教えてください。",
        "choices": [
            ("家から近いからです。", 3),
            ("御社の製品を愛用しており、サポート体制の丁寧さに感銘を受けました。その一員として働きたいと考えています。", 10),
            ("とりあえず応募してみました。", 0),
        ],
    },
    {
        "q": "あなたの長所と短所を教えてください。",
        "choices": [
            ("長所は粘り強さです。短所はこだわりが強すぎることで、時間を区切るよう意識しています。", 10),
            ("長所しかありません。短所はないです。", 0),
            ("短所は朝が弱いことです。長所は特にないです。", 3),
        ],
    },
    {
        "q": "仕事で失敗した経験はありますか？",
        "choices": [
            ("失敗したことはありません。", 0),
            ("納期を勘違いして迷惑をかけたことがあります。以後は確認リストを作り、二重チェックを徹底しています。", 10),
            ("失敗は全部、周りのせいでした。", 3),
        ],
    },
    {
        "q": "5年後、どうなっていたいですか？",
        "choices": [
            ("特に考えていません。", 0),
            ("まずは業務を一通り任せてもらえるようになり、後輩の指導もできる立場を目指したいです。", 10),
            ("社長になっていたいです。", 3),
        ],
    },
    {
        "q": "最後に、質問はありますか？",
        "choices": [
            ("特にありません。", 3),
            ("入社までに勉強しておくと良いことがあれば教えてください。", 10),
            ("残業代はちゃんと出ますか？ 休みは多いですか？", 0),
        ],
    },
]


def mensetsu_grade(points: int) -> str:
    """合計点（最大60）から S〜D の評価を返す。"""
    if points >= 55:
        return "S"
    if points >= 45:
        return "A"
    if points >= 30:
        return "B"
    if points >= 15:
        return "C"
    return "D"


def mensetsu_grade_score(grade: str) -> int:
    return {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}[grade]


def mensetsu_new_game() -> None:
    order = list(range(len(MENSETSU_QUESTIONS)))
    random.shuffle(order)
    session["ms_order"] = order
    session["ms_step"] = 0
    session["ms_points"] = 0
    session["ms_over"] = False
    session["ms_grade"] = None


MENSETSU_TEMPLATE = r"""
  <h1>💼 面接吹き出しジャッジ</h1>
  <p class="howto">面接官の質問に、3つの回答の吹き出しから一番ふさわしいものを選んでください。全6問。答え方で点数が変わり、最後に S〜D の評価が出ます。評価は記録されます（S=5点として保存）。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    {% if over %}
      <p class="big">評価: {{ grade }}</p>
      <p class="result">合計 {{ points }} 点（満点 60 点）。{{ comment }}</p>
      <form method="post" action="{{ url_for('mensetsu_reset') }}" class="row">
        <button type="submit">もう一度面接を受ける</button>
      </form>
    {% else %}
      <p class="result">質問 {{ step + 1 }} / {{ total }} ／ 現在の点数: {{ points }}</p>
      <div class="panel" style="margin-bottom:12px;">
        <h3>面接官</h3>
        <p class="mid">💬 {{ question.q }}</p>
      </div>
      <div style="display:flex; flex-direction:column; gap:10px;">
        {% for text, pts in choices %}
          <form method="post" action="{{ url_for('mensetsu_answer') }}">
            <input type="hidden" name="choice" value="{{ loop.index0 }}">
            <button type="submit" style="width:100%; text-align:left; font-size:15px;">💬 {{ text }}</button>
          </form>
        {% endfor %}
      </div>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（評価：S=5〜D=1）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ {5: 'S', 4: 'A', 3: 'B', 2: 'C', 1: 'D'}.get(s.score, s.score) }} 評価</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""

MENSETSU_COMMENTS = {
    "S": "素晴らしい受け答えでした。即戦力として期待大です！",
    "A": "しっかりした受け答えでした。好印象です。",
    "B": "まずまずの受け答えでした。もう少し具体性があると◎。",
    "C": "少し受け答えに不安が残ります。準備を重ねましょう。",
    "D": "受け答えを見直してみましょう。まず結論から話すのがコツです。",
}


def render_mensetsu(message=None):
    if "ms_order" not in session:
        mensetsu_new_game()
    step = int(session.get("ms_step", 0))
    over = bool(session.get("ms_over", False))
    question = None
    choices = []
    if not over and step < len(MENSETSU_QUESTIONS):
        question = MENSETSU_QUESTIONS[int(session["ms_order"][step])]
        choices = list(question["choices"])
        random.shuffle(choices)
        session["ms_choices"] = [int(p) for _t, p in choices]
    grade = session.get("ms_grade")
    body = render_template_string(
        MENSETSU_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        question=question,
        choices=choices,
        step=step,
        total=len(MENSETSU_QUESTIONS),
        points=int(session.get("ms_points", 0)),
        over=over,
        grade=grade,
        comment=MENSETSU_COMMENTS.get(grade, ""),
        best=best_score("mensetsu", "max"),
        history=recent_scores("mensetsu", 10),
        message=message,
    )
    return game_page("面接吹き出しジャッジ", body)


@app.route("/games/mensetsu", methods=["GET"])
def mensetsu():
    return render_mensetsu()


@app.route("/games/mensetsu/answer", methods=["POST"])
def mensetsu_answer():
    if "ms_order" not in session:
        mensetsu_new_game()
    if session.get("ms_over"):
        return render_mensetsu()
    raw = request.form.get("choice", "").strip()
    points_list = session.get("ms_choices") or []
    if not raw.isdigit() or not (0 <= int(raw) < len(points_list)):
        return render_mensetsu()
    gained = int(points_list[int(raw)])
    points = int(session.get("ms_points", 0)) + gained
    session["ms_points"] = points
    step = int(session.get("ms_step", 0)) + 1
    session["ms_step"] = step
    if step >= len(MENSETSU_QUESTIONS):
        grade = mensetsu_grade(points)
        session["ms_over"] = True
        session["ms_grade"] = grade
        record_score("mensetsu", mensetsu_grade_score(grade))
        return render_mensetsu(message=f"面接終了！ 評価は {grade} でした。")
    if gained >= 10:
        msg = "面接官がうなずいています。良い受け答えです。"
    elif gained >= 3:
        msg = "面接官は無表情です。まずまずの受け答えでした。"
    else:
        msg = "面接官の表情が曇りました…。"
    return render_mensetsu(message=msg)


@app.route("/games/mensetsu/reset", methods=["POST"])
def mensetsu_reset():
    mensetsu_new_game()
    flash("新しい面接を始めました。", "ok")
    return redirect(url_for("mensetsu"))


# ============================
# 水質バランス処理
# 水質パラメータ（濁度・pH・細菌）を読んで設備・薬剤を使い分け、
# 基準内に収めつつコストを抑える判断ゲーム（サーバー側）。全5ラウンド。
# 得点 = 品質ボーナス（基準内25点＋余裕ボーナス） − コスト。×10で保存。
# ============================
SUISHITSU_ACTIONS = {
    "filter": {"name": "ろ過装置を使う", "cost": 8, "turbidity": -30, "ph": 0, "bacteria": -5},
    "carbon": {"name": "活性炭を入れる", "cost": 6, "turbidity": -12, "ph": 0, "bacteria": -8},
    "acid": {"name": "pH調整剤（酸性）を入れる", "cost": 4, "turbidity": 0, "ph": -12, "bacteria": 0},
    "alkali": {"name": "pH調整剤（アルカリ性）を入れる", "cost": 4, "turbidity": 0, "ph": 12, "bacteria": 0},
    "chlorine": {"name": "塩素消毒する", "cost": 5, "turbidity": 0, "ph": 2, "bacteria": -40},
    "uv": {"name": "紫外線殺菌する", "cost": 9, "turbidity": 0, "ph": 0, "bacteria": -45},
    "none": {"name": "何もしない（このまま出す）", "cost": 0, "turbidity": 0, "ph": 0, "bacteria": 0},
}
# 基準: 濁度 0〜20、pH 55〜85（×10表記。5.5〜8.5）、細菌 0〜10
SUISHITSU_LIMITS = {"turbidity": (0, 20), "ph": (55, 85), "bacteria": (0, 10)}


def suishitsu_apply(state: dict, action_key: str) -> dict:
    """設備・薬剤の効果を適用した新しい水質を返す（下限は0で頭打ち）。"""
    a = SUISHITSU_ACTIONS[action_key]
    return {
        "turbidity": max(0, state["turbidity"] + a["turbidity"]),
        "ph": state["ph"] + a["ph"],
        "bacteria": max(0, state["bacteria"] + a["bacteria"]),
        "cost": state.get("cost", 0) + a["cost"],
    }


def suishitsu_in_range(state: dict) -> bool:
    return all(
        SUISHITSU_LIMITS[k][0] <= state[k] <= SUISHITSU_LIMITS[k][1]
        for k in ("turbidity", "ph", "bacteria")
    )


def suishitsu_round_score(state: dict) -> float:
    """基準内なら 25 点＋各パラメータの余裕ボーナス（最大約10点）、
    基準外は 0 点。そこからコストを引く（最低0点）。"""
    if not suishitsu_in_range(state):
        return 0.0
    bonus = 0.0
    for k in ("turbidity", "ph", "bacteria"):
        lo, hi = SUISHITSU_LIMITS[k]
        center = (lo + hi) / 2
        half = (hi - lo) / 2
        bonus += max(0.0, 1 - abs(state[k] - center) / half) * (10 / 3)
    return max(0.0, 25 + bonus - state.get("cost", 0))


def suishitsu_new_water() -> dict:
    return {
        "turbidity": random.randint(25, 70),
        "ph": random.choice([35, 40, 45, 95, 100, 105]),
        "bacteria": random.randint(25, 70),
        "cost": 0,
    }


def suishitsu_new_game() -> None:
    session["ss_round"] = 1
    session["ss_total10"] = 0
    session["ss_water"] = suishitsu_new_water()
    session["ss_over"] = False
    session["ss_log"] = []


SUISHITSU_TEMPLATE = r"""
  <h1>💧 水質バランス処理</h1>
  <p class="howto">浄水場の担当者として、入ってきた水を基準内に処理して出荷します。基準は 濁度 20 以下／pH 5.5〜8.5／細菌 10 以下。設備や薬剤は水質を変えますがコストがかかります。何回使ってもいいので、基準内に収めつつコストを抑えるほど高得点（1ラウンド最大35点）。全5ラウンドの合計得点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">ラウンド {{ round_no }} / 5 ／ 合計得点: {{ total }} 点 ／ ベスト: {{ best if best is not none else '—' }}</p>
    {% if over %}
      <p class="result">全ラウンド終了！ 合計 {{ total }} 点でした。</p>
      <form method="post" action="{{ url_for('suishitsu_reset') }}" class="row">
        <button type="submit">もう一度処理する</button>
      </form>
    {% else %}
      <div class="panel" style="margin-bottom:12px;">
        <h3>現在の水質</h3>
        <table>
          <tr><th>濁度</th><td>{{ water.turbidity }}（基準: 20以下）{% if water.turbidity > 20 %} ⚠️{% else %} ✅{% endif %}</td></tr>
          <tr><th>pH</th><td>{{ water.ph / 10 }}（基準: 5.5〜8.5）{% if water.ph < 55 or water.ph > 85 %} ⚠️{% else %} ✅{% endif %}</td></tr>
          <tr><th>細菌</th><td>{{ water.bacteria }}（基準: 10以下）{% if water.bacteria > 10 %} ⚠️{% else %} ✅{% endif %}</td></tr>
          <tr><th>この水のコスト</th><td>{{ water.cost }}</td></tr>
        </table>
      </div>
      <div style="display:flex; flex-direction:column; gap:8px;">
        {% for key, a in actions %}
          <form method="post" action="{{ url_for('suishitsu_act') }}">
            <input type="hidden" name="action" value="{{ key }}">
            <button type="submit" style="width:100%; text-align:left; font-size:15px;">{{ a.name }}（コスト {{ a.cost }}）</button>
          </form>
        {% endfor %}
      </div>
      <form method="post" action="{{ url_for('suishitsu_ship') }}" class="row" style="margin-top:12px;">
        <button type="submit">この水を出荷する（ラウンド確定）</button>
      </form>
    {% endif %}
    {% if log %}
      <h3 style="font-size:14px; margin:16px 0 8px;">これまでの結果</h3>
      <table>
        {% for line in log %}
          <tr><td>{{ line }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計得点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score / 10 }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_suishitsu(message=None):
    if "ss_water" not in session:
        suishitsu_new_game()
    total10 = int(session.get("ss_total10", 0))
    body = render_template_string(
        SUISHITSU_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        water=dict(session["ss_water"]),
        round_no=int(session.get("ss_round", 1)),
        total=total10 / 10,
        over=bool(session.get("ss_over", False)),
        log=list(session.get("ss_log", [])),
        actions=list(SUISHITSU_ACTIONS.items()),
        best=(best_score("suishitsu", "max") or 0) / 10 if best_score("suishitsu", "max") is not None else None,
        history=recent_scores("suishitsu", 10),
        message=message,
    )
    return game_page("水質バランス処理", body)


@app.route("/games/suishitsu", methods=["GET"])
def suishitsu():
    return render_suishitsu()


@app.route("/games/suishitsu/act", methods=["POST"])
def suishitsu_act():
    if "ss_water" not in session:
        suishitsu_new_game()
    if session.get("ss_over"):
        return render_suishitsu()
    key = request.form.get("action", "")
    if key not in SUISHITSU_ACTIONS or key == "none":
        return render_suishitsu()
    session["ss_water"] = suishitsu_apply(dict(session["ss_water"]), key)
    return render_suishitsu(message=f"{SUISHITSU_ACTIONS[key]['name']} を使いました。")


@app.route("/games/suishitsu/ship", methods=["POST"])
def suishitsu_ship():
    if "ss_water" not in session:
        suishitsu_new_game()
    if session.get("ss_over"):
        return render_suishitsu()
    water = dict(session["ss_water"])
    gained = suishitsu_round_score(water)
    gained10 = int(round(gained * 10))
    total10 = int(session.get("ss_total10", 0)) + gained10
    session["ss_total10"] = total10
    round_no = int(session.get("ss_round", 1))
    log = list(session.get("ss_log", []))
    ok = suishitsu_in_range(water)
    log.append(f"ラウンド{round_no}: {'基準内 ✅' if ok else '基準外 ❌'} コスト {water.get('cost', 0)} → {gained} 点")
    session["ss_log"] = log
    if round_no >= 5:
        session["ss_over"] = True
        record_score("suishitsu", total10)
        return render_suishitsu(message=f"最終ラウンドは {gained} 点でした。全ラウンド終了！")
    session["ss_round"] = round_no + 1
    session["ss_water"] = suishitsu_new_water()
    return render_suishitsu(message=f"ラウンド{round_no} は {gained} 点でした。次の水が来ました。")


@app.route("/games/suishitsu/reset", methods=["POST"])
def suishitsu_reset():
    suishitsu_new_game()
    flash("新しい水の処理を始めました。", "ok")
    return redirect(url_for("suishitsu"))



# ============================
# ブーメラン軌道アタック
# 自分の動きに連動して戻ってくるブーメランだけで敵を倒す（クライアント JS）。
# 敵に触れるとハートが減り、3つ無くなったら終了。倒した数を POST する。
# ============================
BOOMERANG_TEMPLATE = r"""
  <h1>🪃 ブーメラン軌道アタック</h1>
  <p class="howto">矢印キー（またはボタン）で移動し、「投げる」ボタンかスペースキーでブーメランを投げます。ブーメランは真っすぐ飛んで、自分の今いる場所へ戻ってきます。戻る軌道も攻撃になるので、投げた後に動くと軌道が曲がります。敵（👾）に自分が触れるとハートが1つ減り、3つ無くなると終了。倒した数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（倒した数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">倒した数: <span id="kills">0</span> ／ ハート: <span id="hearts">❤️❤️❤️</span></p>
    <div id="stage" style="position:relative; height:360px; border:1px solid #ddd; border-radius:12px; background:#eef7ee; overflow:hidden; margin:10px 0;">
      <div id="player" style="position:absolute; font-size:28px; width:32px; text-align:center;">😀</div>
      <div id="rang" style="position:absolute; font-size:24px; width:28px; text-align:center; display:none;">🪃</div>
    </div>
    <div class="row">
      <button type="button" id="upBtn">↑</button>
      <button type="button" id="leftBtn">←</button>
      <button type="button" id="downBtn">↓</button>
      <button type="button" id="rightBtn">→</button>
      <button type="button" id="throwBtn">🪃 投げる</button>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（倒した数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 体</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var player = document.getElementById("player");
  var rang = document.getElementById("rang");
  var message = document.getElementById("message");
  var killsEl = document.getElementById("kills");
  var heartsEl = document.getElementById("hearts");
  var startBtn = document.getElementById("startBtn");
  var W = 660, H = 360;
  var playing = false, px = 314, py = 290, hearts = 3, kills = 0;
  var keys = {};
  var dirX = 0, dirY = -1;
  var rangState = "idle", rx = 0, ry = 0, rdx = 0, rdy = 0, traveled = 0;
  var enemies = [], spawnId = null, tickId = null;
  function place(el, x, y){ el.style.left = x + "px"; el.style.top = y + "px"; }
  function spawn(){
    if (!playing) { return; }
    var el = document.createElement("div");
    el.textContent = "👾";
    el.style.cssText = "position:absolute; font-size:26px; width:30px; text-align:center;";
    stage.appendChild(el);
    var ex = 20 + Math.random() * (W - 60);
    enemies.push({el: el, x: ex, y: -30, speed: 0.9 + Math.random() * 0.9});
    place(el, ex, -30);
  }
  function throwRang(){
    if (!playing || rangState !== "idle") { return; }
    rangState = "out";
    rx = px + 2; ry = py + 2;
    rdx = dirX; rdy = dirY;
    if (rdx === 0 && rdy === 0) { rdy = -1; }
    traveled = 0;
    rang.style.display = "block";
    place(rang, rx, ry);
  }
  function finish(){
    playing = false;
    clearInterval(spawnId);
    clearInterval(tickId);
    enemies.forEach(function(e){ e.el.remove(); });
    enemies = [];
    rang.style.display = "none";
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(kills));
    fetch("{{ url_for('boomerang_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + kills + " 体倒しました";
          document.getElementById("bestline").textContent = "ベスト（倒した数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function tick(){
    if (!playing) { return; }
    var mx = 0, my = 0;
    if (keys.ArrowLeft) { mx -= 1; }
    if (keys.ArrowRight) { mx += 1; }
    if (keys.ArrowUp) { my -= 1; }
    if (keys.ArrowDown) { my += 1; }
    if (mx !== 0 || my !== 0) {
      dirX = mx; dirY = my;
      px = Math.max(0, Math.min(W - 32, px + mx * 5));
      py = Math.max(0, Math.min(H - 34, py + my * 5));
      place(player, px, py);
    }
    if (rangState === "out") {
      rx += rdx * 8; ry += rdy * 8;
      traveled += 8;
      if (traveled >= 180 || rx < 0 || rx > W - 28 || ry < 0 || ry > H - 28) { rangState = "back"; }
      place(rang, rx, ry);
    } else if (rangState === "back") {
      var tx = px + 2 - rx, ty = py + 2 - ry;
      var dist = Math.sqrt(tx * tx + ty * ty);
      if (dist < 12) {
        rangState = "idle";
        rang.style.display = "none";
      } else {
        rx += tx / dist * 9; ry += ty / dist * 9;
        place(rang, rx, ry);
      }
    }
    enemies = enemies.filter(function(e){
      var dx = (px + 1) - e.x, dy = (py + 2) - e.y;
      var d = Math.sqrt(dx * dx + dy * dy) || 1;
      e.x += dx / d * e.speed;
      e.y += dy / d * e.speed;
      place(e.el, e.x, e.y);
      if (rangState !== "idle") {
        var bx = (rx + 14) - (e.x + 15), by = (ry + 12) - (e.y + 13);
        if (Math.sqrt(bx * bx + by * by) < 28) {
          e.el.remove();
          kills++;
          killsEl.textContent = String(kills);
          return false;
        }
      }
      if (d < 28) {
        e.el.remove();
        hearts--;
        heartsEl.textContent = hearts > 0 ? "❤️".repeat(hearts) : "💔";
        message.textContent = "敵に当たった！ ハートが減った…";
        if (hearts <= 0) { finish(); }
        return false;
      }
      return true;
    });
  }
  function hold(id, key){
    var b = document.getElementById(id);
    b.addEventListener("pointerdown", function(e){ e.preventDefault(); keys[key] = true; });
    b.addEventListener("pointerup", function(){ keys[key] = false; });
    b.addEventListener("pointerleave", function(){ keys[key] = false; });
  }
  hold("leftBtn", "ArrowLeft");
  hold("rightBtn", "ArrowRight");
  hold("upBtn", "ArrowUp");
  hold("downBtn", "ArrowDown");
  document.getElementById("throwBtn").addEventListener("click", throwRang);
  document.addEventListener("keydown", function(e){
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].indexOf(e.key) >= 0) {
      keys[e.key] = true;
      e.preventDefault();
    }
    if (e.key === " ") { throwRang(); e.preventDefault(); }
  });
  document.addEventListener("keyup", function(e){ keys[e.key] = false; });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    kills = 0; hearts = 3;
    px = 314; py = 290;
    killsEl.textContent = "0";
    heartsEl.textContent = "❤️❤️❤️";
    place(player, px, py);
    rangState = "idle";
    rang.style.display = "none";
    message.textContent = "ブーメランで敵を倒そう！";
    startBtn.disabled = true;
    spawn();
    spawnId = setInterval(spawn, 1100);
    tickId = setInterval(tick, 50);
  });
  place(player, px, py);
})();
</script>
"""


@app.route("/games/boomerang", methods=["GET"])
def boomerang():
    body = render_template_string(
        BOOMERANG_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("boomerang", "max"),
        history=recent_scores("boomerang", 10),
    )
    return game_page("ブーメラン軌道アタック", body)


@app.route("/games/boomerang/score", methods=["POST"])
def boomerang_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("boomerang", int(raw))
    return {"ok": True, "best": best_score("boomerang", "max")}


# ============================
# タイミング返球テニス
# 打つタイミングで返球の質が変わるテニス風ゲーム（クライアント JS）。
# パーフェクト返球は +2 点で加速、通常返球は +1 点。3回ミスで終了。
# ============================
TIMINGTENNIS_TEMPLATE = r"""
  <h1>🎾 タイミング返球テニス</h1>
  <p class="howto">ボールが左のラケットに近づいたら「打つ」ボタン（またはスペースキー）。タイミングがぴったりだとパーフェクト返球（+2点）でボールが速くなり、少しずれると通常返球（+1点）。打ち損じるとミスで、3回ミスで終了です。右の CPU が打ち損じると +3 点ボーナス。合計点を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（合計点）: {{ best if best is not none else '—' }}</p>
    <p class="mid">得点: <span id="points">0</span> ／ ラリー: <span id="rally">0</span> ／ ミス: <span id="miss">0</span> / 3</p>
    <div id="court" style="position:relative; height:200px; border:1px solid #ddd; border-radius:12px; background:#b7e0a8; overflow:hidden; margin:10px 0;">
      <div style="position:absolute; left:46px; top:0; width:4px; height:100%; background:rgba(255,255,255,.65);"></div>
      <div style="position:absolute; left:8px; top:86px; font-size:26px;">🎾</div>
      <div style="position:absolute; right:8px; top:86px; font-size:26px;">🤖</div>
      <div id="ball" style="position:absolute; font-size:20px; display:none;">🟢</div>
      <div id="zone" style="position:absolute; left:24px; top:0; width:52px; height:100%; background:rgba(255,255,0,.25); display:none;"></div>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="hitBtn" disabled>🏸 打つ</button>
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var ball = document.getElementById("ball");
  var zone = document.getElementById("zone");
  var message = document.getElementById("message");
  var pointsEl = document.getElementById("points");
  var rallyEl = document.getElementById("rally");
  var missEl = document.getElementById("miss");
  var hitBtn = document.getElementById("hitBtn");
  var startBtn = document.getElementById("startBtn");
  var RACKET = 46, CPU_X = 596, W = 660;
  var playing = false, bx = 300, bvx = 0, baseSpeed = 4.2, speed = 4.2;
  var points = 0, rally = 0, miss = 0, tickId = null, lockUntil = 0;
  function serve(dir){
    bx = dir > 0 ? 120 : 540;
    bvx = dir * speed;
    ball.style.display = "block";
    zone.style.display = "block";
    ball.style.top = "90px";
  }
  function finish(){
    playing = false;
    clearInterval(tickId);
    ball.style.display = "none";
    zone.style.display = "none";
    hitBtn.disabled = true;
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(points));
    fetch("{{ url_for('timing_tennis_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 試合終了！ 合計 " + points + " 点でした";
          document.getElementById("bestline").textContent = "ベスト（合計点）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function tick(){
    if (!playing) { return; }
    bx += bvx;
    if (bvx > 0 && bx >= CPU_X) {
      if (Math.random() < 0.88) {
        bvx = -speed;
        bx = CPU_X;
      } else {
        points += 3;
        pointsEl.textContent = String(points);
        message.textContent = "CPU が打ち損じた！ +3 点ボーナス";
        speed = baseSpeed;
        serve(1);
        return;
      }
    }
    if (bvx < 0 && bx <= 14) {
      miss++;
      missEl.textContent = String(miss);
      rally = 0;
      rallyEl.textContent = "0";
      speed = baseSpeed;
      message.textContent = "打ち損じた… ミス " + miss + " 回目";
      if (miss >= 3) { finish(); return; }
      serve(-1);
      return;
    }
    ball.style.left = bx + "px";
  }
  function hit(){
    if (!playing || bvx >= 0) { return; }
    if (Date.now() < lockUntil) { return; }
    var dist = bx - RACKET;
    if (dist >= -6 && dist <= 22) {
      points += 2;
      rally++;
      speed = Math.min(11, speed * 1.16);
      bvx = speed;
      message.textContent = "パーフェクト返球！ +2 点";
    } else if (dist >= -24 && dist <= 52) {
      points += 1;
      rally++;
      bvx = speed;
      message.textContent = "返球成功 +1 点";
    } else {
      lockUntil = Date.now() + 350;
      message.textContent = "早すぎ／遅すぎ！ タイミングを合わせて";
      return;
    }
    pointsEl.textContent = String(points);
    rallyEl.textContent = String(rally);
  }
  hitBtn.addEventListener("click", hit);
  document.addEventListener("keydown", function(e){
    if (e.key === " ") { hit(); e.preventDefault(); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    points = 0; rally = 0; miss = 0; speed = baseSpeed;
    pointsEl.textContent = "0";
    rallyEl.textContent = "0";
    missEl.textContent = "0";
    message.textContent = "ボールが来たらタイミングよく打とう！";
    hitBtn.disabled = false;
    startBtn.disabled = true;
    serve(-1);
    tickId = setInterval(tick, 30);
  });
})();
</script>
"""


@app.route("/games/timing-tennis", methods=["GET"])
def timing_tennis():
    body = render_template_string(
        TIMINGTENNIS_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("timing-tennis", "max"),
        history=recent_scores("timing-tennis", 10),
    )
    return game_page("タイミング返球テニス", body)


@app.route("/games/timing-tennis/score", methods=["POST"])
def timing_tennis_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("timing-tennis", int(raw))
    return {"ok": True, "best": best_score("timing-tennis", "max")}


# ============================
# ひみつネーム即死当て
# 秘密の名前（動物のカタカナ名）を、文字の一致ヒントで当てる推理ゲーム
# （サーバー側セッション）。別の「即死ネーム」を言ってしまうと即ゲームオーバー。
# 6回以内に当てると、残り回数に応じた得点を記録する。
# ============================
SECRETNAME_WORDS = [
    "ライオン", "ペンギン", "アルパカ", "シマウマ", "フラミンゴ",
    "カメレオン", "カンガルー", "キリン", "コアラ", "ラッコ",
    "モグラ", "タヌキ", "ウサギ", "ハリネズミ", "レッサーパンダ",
]
SECRETNAME_MARKS = {"exact": "◎", "present": "△", "absent": "×"}


def secretname_feedback(secret: str, guess: str):
    """各文字について exact（位置も一致）/ present（文字はある）/ absent を返す。"""
    n = len(secret)
    marks = ["absent"] * n
    remaining = {}
    for i in range(n):
        if i < len(guess) and guess[i] == secret[i]:
            marks[i] = "exact"
        else:
            remaining[secret[i]] = remaining.get(secret[i], 0) + 1
    for i in range(n):
        if marks[i] == "exact" or i >= len(guess):
            continue
        ch = guess[i]
        if remaining.get(ch, 0) > 0:
            marks[i] = "present"
            remaining[ch] -= 1
    return marks


def secretname_win_score(tries_used: int) -> int:
    """当てた回数（1〜6）から得点を返す。早いほど高い。"""
    return max(0, (7 - tries_used) * 20)


def secretname_new_game() -> None:
    secret = random.choice(SECRETNAME_WORDS)
    traps = [w for w in SECRETNAME_WORDS if w != secret and len(w) == len(secret)]
    session["sn_secret"] = secret
    session["sn_trap"] = random.choice(traps) if traps else ""
    session["sn_tries"] = []
    session["sn_over"] = False
    session["sn_win"] = False
    session["sn_dead"] = False


SECRETNAME_TEMPLATE = r"""
  <h1>🤫 ひみつネーム即死当て</h1>
  <p class="howto">秘密の名前（動物のカタカナ名）を当てる推理ゲーム。名前の長さだけが最初から分かります。予想を入力すると、文字ごとに ◎（文字も場所も一致）／△（文字はあるが場所が違う）／×（含まれない）が返ります。6回以内に当てればクリア。ただし、この名前とは別に「即死ネーム」が1つ隠れていて、それを言ってしまうとその場でゲームオーバーです…。得点は早く当てるほど高くなります。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">秘密の名前は {{ length }} 文字（動物）／ 残り {{ left }} 回</p>
    {% if tries %}
      <table>
        {% for guess, marks in tries %}
          <tr>
            <td>{{ guess }}</td>
            <td>{% for mk in marks %}{{ {'exact': '◎', 'present': '△', 'absent': '×'}[mk] }}{% endfor %}</td>
          </tr>
        {% endfor %}
      </table>
    {% endif %}
    {% if over %}
      {% if win %}
        <p class="big">🎉 正解！</p>
        <p class="result">秘密の名前は「{{ secret }}」でした。</p>
      {% elif dead %}
        <p class="big">💀 即死…</p>
        <p class="result">それは即死ネーム「{{ trap }}」でした。秘密の名前は「{{ secret }}」。</p>
      {% else %}
        <p class="big">残念…</p>
        <p class="result">秘密の名前は「{{ secret }}」でした（即死ネームは「{{ trap }}」）。</p>
      {% endif %}
      <form method="post" action="{{ url_for('secret_name_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% else %}
      <form method="post" action="{{ url_for('secret_name_guess') }}" class="row">
        <input type="text" name="guess" placeholder="カタカナで入力" autocomplete="off" />
        <button type="submit">これだと思う</button>
      </form>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（得点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_secretname(message=None):
    if "sn_secret" not in session:
        secretname_new_game()
    secret = session["sn_secret"]
    tries = session.get("sn_tries", [])
    body = render_template_string(
        SECRETNAME_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        length=len(secret),
        left=max(0, 6 - len(tries)),
        tries=tries,
        over=bool(session.get("sn_over", False)),
        win=bool(session.get("sn_win", False)),
        dead=bool(session.get("sn_dead", False)),
        secret=secret if session.get("sn_over") else "",
        trap=session.get("sn_trap", "") if session.get("sn_over") else "",
        history=recent_scores("secret-name", 10),
        message=message,
    )
    return game_page("ひみつネーム即死当て", body)


@app.route("/games/secret-name", methods=["GET"])
def secret_name():
    return render_secretname()


@app.route("/games/secret-name/guess", methods=["POST"])
def secret_name_guess():
    if "sn_secret" not in session:
        secretname_new_game()
    if session.get("sn_over"):
        return render_secretname()
    secret = session["sn_secret"]
    guess = (request.form.get("guess") or "").strip()
    if len(guess) != len(secret) or not all("ァ" <= ch <= "ヶ" or ch == "ー" for ch in guess):
        return render_secretname(message=f"カタカナ{len(secret)}文字で入力してください。")
    if guess == session.get("sn_trap"):
        session["sn_over"] = True
        session["sn_dead"] = True
        tries = session.get("sn_tries", [])
        tries.append([guess, ["absent"] * len(secret)])
        session["sn_tries"] = tries
        record_score("secret-name", 0)
        return render_secretname(message="それは即死ネームでした…。")
    marks = secretname_feedback(secret, guess)
    tries = session.get("sn_tries", [])
    tries.append([guess, marks])
    session["sn_tries"] = tries
    if guess == secret:
        session["sn_over"] = True
        session["sn_win"] = True
        score = secretname_win_score(len(tries))
        record_score("secret-name", score)
        return render_secretname(message=f"正解！ {score} 点を記録しました。")
    if len(tries) >= 6:
        session["sn_over"] = True
        best_exact = max(sum(1 for mk in secretname_feedback(secret, g) if mk == "exact") for g, _m in tries)
        record_score("secret-name", best_exact * 5)
        return render_secretname(message="6回使い切ってしまいました。")
    return render_secretname(message="ヒントを頼りに、次を考えよう。")


@app.route("/games/secret-name/reset", methods=["POST"])
def secret_name_reset():
    secretname_new_game()
    flash("新しい秘密の名前になりました。", "ok")
    return redirect(url_for("secret_name"))


# ============================
# 海流ながれ弾シューティング
# 海流の帯を通る自弾が横に流されるインベーダー風シューティング（クライアント JS）。
# 敵を全滅させると次のウェーブ。敵が下まで来るか90秒経過で終了。倒した数を記録。
# ============================
CURRENTSHOT_TEMPLATE = r"""
  <h1>🌊 海流ながれ弾シューティング</h1>
  <p class="howto">←→キー（またはボタン）で船を動かし、「撃つ」ボタンかスペースキーで弾を撃ちます。画面の2本の海流の帯（青い帯）を通る弾は、矢印の向きに流されて曲がります。流れを読んで敵（🦑）を撃ち落としてください。全滅させると次のウェーブ。敵が下まで到達するか、90秒経つと終了。倒した数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（倒した数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">倒した数: <span id="kills">0</span> ／ ウェーブ: <span id="wave">1</span> ／ 残り: <span id="timeLeft">90</span> 秒</p>
    <div id="stage" style="position:relative; height:400px; border:1px solid #ddd; border-radius:12px; background:#0d2b45; overflow:hidden; margin:10px 0;">
      <div id="band1" style="position:absolute; left:0; width:100%; height:46px; top:110px; background:rgba(80,170,255,.30); color:#dff2ff; font-size:20px; line-height:46px; white-space:nowrap; overflow:hidden;">➡️ ➡️ ➡️ ➡️ ➡️ ➡️ ➡️ ➡️</div>
      <div id="band2" style="position:absolute; left:0; width:100%; height:46px; top:210px; background:rgba(80,170,255,.30); color:#dff2ff; font-size:20px; line-height:46px; white-space:nowrap; overflow:hidden;">⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️</div>
      <div id="ship" style="position:absolute; font-size:28px; width:34px; text-align:center; bottom:6px;">⛵</div>
    </div>
    <div class="row">
      <button type="button" id="leftBtn">← 左</button>
      <button type="button" id="shootBtn">🔫 撃つ</button>
      <button type="button" id="rightBtn">右 →</button>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（倒した数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 体</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var ship = document.getElementById("ship");
  var band1 = document.getElementById("band1");
  var band2 = document.getElementById("band2");
  var message = document.getElementById("message");
  var killsEl = document.getElementById("kills");
  var waveEl = document.getElementById("wave");
  var timeEl = document.getElementById("timeLeft");
  var startBtn = document.getElementById("startBtn");
  var W = 660, H = 400;
  var playing = false, shipX = 313, kills = 0, wave = 0;
  var keys = {}, bullets = [], enemies = [], tickId = null, endsAt = 0, lastShot = 0;
  var sway = 0, swayDir = 1, descend = 0.3;
  var bands = [
    {top: 110, bottom: 156, drift: 2.2},
    {top: 210, bottom: 256, drift: -2.2}
  ];
  function placeShip(){ ship.style.left = shipX + "px"; }
  function makeWave(){
    wave++;
    waveEl.textContent = String(wave);
    descend = 0.25 + wave * 0.08;
    var rows = Math.min(3, 1 + Math.floor(wave / 2));
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < 6; c++) {
        var el = document.createElement("div");
        el.textContent = "🦑";
        el.style.cssText = "position:absolute; font-size:24px; width:28px; text-align:center;";
        stage.appendChild(el);
        enemies.push({el: el, x: 70 + c * 88, y: 16 + r * 40});
      }
    }
    sway = 0;
  }
  function shoot(){
    if (!playing) { return; }
    var now = Date.now();
    if (now - lastShot < 220 || bullets.length >= 4) { return; }
    lastShot = now;
    var el = document.createElement("div");
    el.textContent = "🔹";
    el.style.cssText = "position:absolute; font-size:14px; width:16px; text-align:center;";
    stage.appendChild(el);
    bullets.push({el: el, x: shipX + 9, y: H - 52});
  }
  function finish(reason){
    playing = false;
    clearInterval(tickId);
    bullets.forEach(function(b){ b.el.remove(); });
    enemies.forEach(function(e){ e.el.remove(); });
    bullets = []; enemies = [];
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(kills));
    fetch("{{ url_for('current_shot_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 " + reason + " " + kills + " 体倒しました";
          document.getElementById("bestline").textContent = "ベスト（倒した数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function tick(){
    if (!playing) { return; }
    var left = Math.max(0, endsAt - Date.now());
    timeEl.textContent = String(Math.ceil(left / 1000));
    if (left <= 0) { finish("時間切れ！"); return; }
    if (keys.ArrowLeft) { shipX = Math.max(0, shipX - 6); }
    if (keys.ArrowRight) { shipX = Math.min(W - 34, shipX + 6); }
    placeShip();
    sway += swayDir * 0.7;
    if (sway > 26 || sway < -26) { swayDir *= -1; }
    var reached = false;
    enemies.forEach(function(e){
      e.y += descend;
      e.el.style.left = (e.x + sway) + "px";
      e.el.style.top = e.y + "px";
      if (e.y > H - 66) { reached = true; }
    });
    if (reached) { finish("敵が到達した！"); return; }
    bullets = bullets.filter(function(b){
      b.y -= 8;
      bands.forEach(function(band){
        if (b.y >= band.top && b.y <= band.bottom) { b.x += band.drift; }
      });
      b.el.style.left = b.x + "px";
      b.el.style.top = b.y + "px";
      if (b.y < -10 || b.x < -10 || b.x > W) { b.el.remove(); return false; }
      return true;
    });
    bullets = bullets.filter(function(b){
      var hitIdx = -1;
      enemies.forEach(function(e, i){
        if (hitIdx >= 0) { return; }
        var ex = e.x + sway + 14, ey = e.y + 12;
        var dx = (b.x + 8) - ex, dy = (b.y + 7) - ey;
        if (Math.sqrt(dx * dx + dy * dy) < 22) { hitIdx = i; }
      });
      if (hitIdx >= 0) {
        enemies[hitIdx].el.remove();
        enemies.splice(hitIdx, 1);
        b.el.remove();
        kills++;
        killsEl.textContent = String(kills);
        if (enemies.length === 0) { makeWave(); }
        return false;
      }
      return true;
    });
  }
  function hold(id, key){
    var b = document.getElementById(id);
    b.addEventListener("pointerdown", function(e){ e.preventDefault(); keys[key] = true; });
    b.addEventListener("pointerup", function(){ keys[key] = false; });
    b.addEventListener("pointerleave", function(){ keys[key] = false; });
  }
  hold("leftBtn", "ArrowLeft");
  hold("rightBtn", "ArrowRight");
  document.getElementById("shootBtn").addEventListener("click", shoot);
  document.addEventListener("keydown", function(e){
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { keys[e.key] = true; e.preventDefault(); }
    if (e.key === " ") { shoot(); e.preventDefault(); }
  });
  document.addEventListener("keyup", function(e){ keys[e.key] = false; });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    // 海流の向きはゲームごとにランダム
    bands[0].drift = (Math.random() < 0.5 ? -1 : 1) * 2.2;
    bands[1].drift = (Math.random() < 0.5 ? -1 : 1) * 2.2;
    band1.textContent = bands[0].drift > 0 ? "➡️ ➡️ ➡️ ➡️ ➡️ ➡️ ➡️ ➡️" : "⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️";
    band2.textContent = bands[1].drift > 0 ? "➡️ ➡️ ➡️ ➡️ ➡️ ➡️ ➡️ ➡️" : "⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️ ⬅️";
    playing = true;
    kills = 0; wave = 0;
    killsEl.textContent = "0";
    shipX = 313;
    placeShip();
    message.textContent = "海流を読んで撃とう！";
    startBtn.disabled = true;
    makeWave();
    endsAt = Date.now() + 90000;
    tickId = setInterval(tick, 40);
  });
  placeShip();
})();
</script>
"""


@app.route("/games/current-shot", methods=["GET"])
def current_shot():
    body = render_template_string(
        CURRENTSHOT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("current-shot", "max"),
        history=recent_scores("current-shot", 10),
    )
    return game_page("海流ながれ弾シューティング", body)


@app.route("/games/current-shot/score", methods=["POST"])
def current_shot_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("current-shot", int(raw))
    return {"ok": True, "best": best_score("current-shot", "max")}


# ============================
# ティアならべパーティ
# お題の項目を S/A/B/C のティア表に並べる創作ゲーム（サーバー側セッション）。
# 隠れた「みんなの感覚」ティアと一致するほど得点が高い。全テーマ共通で
# 得点計算は tierparty_score() に切り出してある。
# ============================
TIERPARTY_TIERS = ["S", "A", "B", "C"]
TIERPARTY_THEMES = [
    {
        "title": "コンビニスイーツ",
        "items": ["シュークリーム", "カスタードプリン", "ロールケーキ", "どら焼き",
                  "エクレア", "ベイクドチーズケーキ", "わらび餅", "あんぱん"],
        "consensus": [0, 0, 1, 2, 1, 1, 3, 2],
    },
    {
        "title": "動物園の人気者",
        "items": ["パンダ", "ライオン", "キリン", "ゾウ",
                  "ペンギン", "コアラ", "レッサーパンダ", "カバ"],
        "consensus": [0, 1, 1, 0, 1, 2, 2, 3],
    },
    {
        "title": "学校の給食メニュー",
        "items": ["カレーライス", "揚げパン", "ソフト麺", "牛乳",
                  "わかめごはん", "フルーツポンチ", "唐揚げ", "コッペパン"],
        "consensus": [0, 1, 2, 3, 2, 1, 0, 3],
    },
]


def tierparty_score(player, consensus) -> int:
    """一致で10点、1段ずれで4点。全ティアを使ったら +5 点ボーナス。"""
    total = 0
    for p, c in zip(player, consensus):
        d = abs(int(p) - int(c))
        if d == 0:
            total += 10
        elif d == 1:
            total += 4
    if len(set(int(p) for p in player)) >= 4:
        total += 5
    return total


def tierparty_new_game() -> None:
    session["tp_theme"] = random.randrange(len(TIERPARTY_THEMES))
    session["tp_done"] = False
    session["tp_player"] = []
    session["tp_score"] = 0


TIERPARTY_TEMPLATE = r"""
  <h1>🎚️ ティアならべパーティ</h1>
  <p class="howto">お題の8項目を、S（最高）／A／B／C のティア表に並べるゲーム。隠れている「みんなの感覚」ティアと一致するほど得点が高く、1段ずれでも少しもらえます。4つのティアを全部使うとボーナス +5 点。感覚の合う／合わないを楽しんでね。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">お題：{{ theme.title }}</p>
    {% if done %}
      <p class="big">{{ score }} 点</p>
      <table>
        <tr><th>項目</th><th>あなた</th><th>みんなの感覚</th><th>得点</th></tr>
        {% for item, mine, cons, pts in rows %}
          <tr><td>{{ item }}</td><td>{{ mine }}</td><td>{{ cons }}</td><td>{{ pts }}</td></tr>
        {% endfor %}
      </table>
      <form method="post" action="{{ url_for('tier_party_reset') }}" class="row" style="margin-top:12px;">
        <button type="submit">別のお題で遊ぶ</button>
      </form>
    {% else %}
      <form method="post" action="{{ url_for('tier_party_submit') }}">
        <table>
          <tr><th>項目</th><th>ティア</th></tr>
          {% for item in theme['items'] %}
            <tr>
              <td>{{ item }}</td>
              <td>
                <select name="item{{ loop.index0 }}">
                  {% for t in tiers %}
                    <option value="{{ loop.index0 }}" {% if loop.index0 == 1 %}selected{% endif %}>{{ t }}</option>
                  {% endfor %}
                </select>
              </td>
            </tr>
          {% endfor %}
        </table>
        <div class="row" style="margin-top:12px;">
          <button type="submit">これで決定！</button>
        </div>
      </form>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（得点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_tierparty(message=None):
    if "tp_theme" not in session or "tp_done" not in session:
        tierparty_new_game()
    theme = TIERPARTY_THEMES[int(session["tp_theme"])]
    rows = []
    if session.get("tp_done"):
        player = session.get("tp_player", [])
        for i, item in enumerate(theme["items"]):
            p = int(player[i]) if i < len(player) else 1
            c = int(theme["consensus"][i])
            d = abs(p - c)
            pts = 10 if d == 0 else (4 if d == 1 else 0)
            rows.append((item, TIERPARTY_TIERS[p], TIERPARTY_TIERS[c], pts))
    body = render_template_string(
        TIERPARTY_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        theme=theme,
        tiers=TIERPARTY_TIERS,
        done=bool(session.get("tp_done", False)),
        score=int(session.get("tp_score", 0)),
        rows=rows,
        history=recent_scores("tier-party", 10),
        message=message,
    )
    return game_page("ティアならべパーティ", body)


@app.route("/games/tier-party", methods=["GET"])
def tier_party():
    return render_tierparty()


@app.route("/games/tier-party/submit", methods=["POST"])
def tier_party_submit():
    if "tp_theme" not in session:
        tierparty_new_game()
    if session.get("tp_done"):
        return render_tierparty()
    theme = TIERPARTY_THEMES[int(session["tp_theme"])]
    player = []
    for i in range(len(theme["items"])):
        raw = (request.form.get(f"item{i}") or "1").strip()
        player.append(int(raw) if raw.isdigit() and 0 <= int(raw) <= 3 else 1)
    score = tierparty_score(player, theme["consensus"])
    session["tp_player"] = player
    session["tp_score"] = score
    session["tp_done"] = True
    record_score("tier-party", score)
    return render_tierparty(message=f"採点しました！ {score} 点を記録しました。")


@app.route("/games/tier-party/reset", methods=["POST"])
def tier_party_reset():
    tierparty_new_game()
    flash("新しいお題になりました。", "ok")
    return redirect(url_for("tier_party"))


# ============================
# おてほん書道採点
# お手本の漢字をキャンバスでなぞり、なぞり具合（被覆率と正確さ）を
# クライアント JS で採点して POST する。得点は 0〜100。
# ============================
SHODO_TEMPLATE = r"""
  <h1>🖌️ おてほん書道採点</h1>
  <p class="howto">薄く表示されたお手本の漢字を、マウスや指でなぞってください。「採点する」を押すと、お手本をどれだけなぞれているか（被覆率）と、はみ出しの少なさ（正確さ）から 100 点満点で採点します。太い筆でゆっくりなぞるのがコツ。得点を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（得点）: {{ best if best is not none else '—' }}</p>
    <p class="mid">お手本： <span id="modelName" style="font-size:20px;">—</span></p>
    <div style="text-align:center;">
      <canvas id="pad" width="320" height="320" style="border:1px solid #ccc; border-radius:8px; background:#fff; touch-action:none;"></canvas>
    </div>
    <p class="result" id="message">お手本をなぞってみよう</p>
    <div class="row">
      <button type="button" id="clearBtn">消す</button>
      <button type="button" id="nextBtn">お手本を変える</button>
      <button type="button" id="scoreBtn">採点する</button>
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
  var KANJI = ["永", "山", "川", "心", "光", "夢", "風", "空", "月", "花"];
  var pad = document.getElementById("pad");
  var ctx = pad.getContext("2d");
  var user = document.createElement("canvas");
  user.width = 320; user.height = 320;
  var uctx = user.getContext("2d");
  var model = document.createElement("canvas");
  model.width = 320; model.height = 320;
  var mctx = model.getContext("2d");
  var message = document.getElementById("message");
  var modelName = document.getElementById("modelName");
  var current = "";
  var drawing = false, lastX = 0, lastY = 0, hasInk = false;
  function drawModel(){
    mctx.clearRect(0, 0, 320, 320);
    mctx.fillStyle = "#000";
    mctx.font = "250px serif";
    mctx.textAlign = "center";
    mctx.textBaseline = "middle";
    mctx.fillText(current, 160, 168);
    ctx.clearRect(0, 0, 320, 320);
    ctx.fillStyle = "#e3e3e3";
    ctx.font = "250px serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(current, 160, 168);
    uctx.clearRect(0, 0, 320, 320);
    hasInk = false;
  }
  function newModel(){
    current = KANJI[Math.floor(Math.random() * KANJI.length)];
    modelName.textContent = "「" + current + "」";
    drawModel();
    message.textContent = "お手本をなぞってみよう";
  }
  function pos(e){
    var r = pad.getBoundingClientRect();
    return {x: (e.clientX - r.left) * 320 / r.width, y: (e.clientY - r.top) * 320 / r.height};
  }
  pad.addEventListener("pointerdown", function(e){
    drawing = true;
    var p = pos(e);
    lastX = p.x; lastY = p.y;
    pad.setPointerCapture(e.pointerId);
  });
  pad.addEventListener("pointermove", function(e){
    if (!drawing) { return; }
    var p = pos(e);
    [ctx, uctx].forEach(function(c){
      c.strokeStyle = "#222";
      c.lineWidth = 15;
      c.lineCap = "round";
      c.lineJoin = "round";
      c.beginPath();
      c.moveTo(lastX, lastY);
      c.lineTo(p.x, p.y);
      c.stroke();
    });
    hasInk = true;
    lastX = p.x; lastY = p.y;
  });
  pad.addEventListener("pointerup", function(){ drawing = false; });
  pad.addEventListener("pointercancel", function(){ drawing = false; });
  document.getElementById("clearBtn").addEventListener("click", function(){
    drawModel();
    message.textContent = "消しました。もう一度なぞってね";
  });
  document.getElementById("nextBtn").addEventListener("click", newModel);
  document.getElementById("scoreBtn").addEventListener("click", function(){
    if (!hasInk) {
      message.textContent = "まずお手本をなぞってから採点してね";
      return;
    }
    var md = mctx.getImageData(0, 0, 320, 320).data;
    var ud = uctx.getImageData(0, 0, 320, 320).data;
    function alphaAt(data, x, y){
      if (x < 0 || x > 319 || y < 0 || y > 319) { return 0; }
      return data[(y * 320 + x) * 4 + 3];
    }
    function nearInk(data, x, y){
      if (alphaAt(data, x, y) > 60) { return true; }
      var offs = [[5, 0], [-5, 0], [0, 5], [0, -5]];
      for (var i = 0; i < offs.length; i++) {
        if (alphaAt(data, x + offs[i][0], y + offs[i][1]) > 60) { return true; }
      }
      return false;
    }
    var modelTotal = 0, covered = 0, userTotal = 0, userOn = 0;
    for (var y = 3; y < 320; y += 6) {
      for (var x = 3; x < 320; x += 6) {
        var mInk = alphaAt(md, x, y) > 60;
        var uInk = alphaAt(ud, x, y) > 0;
        if (mInk) {
          modelTotal++;
          if (nearInk(ud, x, y)) { covered++; }
        }
        if (uInk) {
          userTotal++;
          if (nearInk(md, x, y)) { userOn++; }
        }
      }
    }
    var recall = modelTotal ? covered / modelTotal : 0;
    var precision = userTotal ? userOn / userTotal : 0;
    var score = Math.round(100 * (0.65 * recall + 0.35 * precision));
    score = Math.max(0, Math.min(100, score));
    var form = new FormData();
    form.append("score", String(score));
    fetch("{{ url_for('shodo_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          var comment = score >= 80 ? "見事な筆づかいです！" : (score >= 55 ? "よくかけています。" : (score >= 30 ? "もう少しゆっくりなぞろう。" : "お手本の上を太くゆっくりなぞってみて。"));
          message.textContent = "採点： " + score + " 点！ " + comment;
          document.getElementById("bestline").textContent = "ベスト（得点）: " + d.best;
        }
      })
      .catch(function(){});
  });
  newModel();
})();
</script>
"""


@app.route("/games/shodo", methods=["GET"])
def shodo():
    body = render_template_string(
        SHODO_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("shodo", "max"),
        history=recent_scores("shodo", 10),
    )
    return game_page("おてほん書道採点", body)


@app.route("/games/shodo/score", methods=["POST"])
def shodo_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 100):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("shodo", int(raw))
    return {"ok": True, "best": best_score("shodo", "max")}


# ============================
# 一息ろうそく消し
# 息（長押し）を吹きかけてろうそくの火を消すゲーム（クライアント JS）。
# 息ゲージが続く範囲で吹け、空になると自動で息継ぎ。60秒で消した本数を記録。
# ============================
ROUSOKU_TEMPLATE = r"""
  <h1>🕯️ 一息ろうそく消し</h1>
  <p class="howto">ろうそくを押し続ける（タップ長押し）と息を吹きかけて、火が少しずつ小さくなります。手を離すと火は少し戻ります。息ゲージが空になると自動で息継ぎ（その間は吹けません）。60秒のあいだに何本消せるか挑戦してね。消した本数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（消した本数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">残り: <span id="timeLeft">60</span> 秒 ／ 消した数: <span id="out">0</span> / 12</p>
    <div style="height:14px; border:1px solid #bbb; border-radius:7px; overflow:hidden; margin:8px 0;">
      <div id="breath" style="height:100%; width:100%; background:#7ec8f7;"></div>
    </div>
    <p class="muted" style="text-align:center;">息ゲージ（青）／ 息継ぎ中は赤くなります</p>
    <div id="stage" style="display:grid; grid-template-columns:repeat(4, 1fr); gap:10px; margin:12px 0;"></div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（消した本数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 本</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var message = document.getElementById("message");
  var outEl = document.getElementById("out");
  var timeEl = document.getElementById("timeLeft");
  var breathEl = document.getElementById("breath");
  var startBtn = document.getElementById("startBtn");
  var N = 12;
  var playing = false, out = 0, endsAt = 0, tickId = null;
  var breath = 80, inhaling = 0, blowing = -1;
  var candles = [];
  function buildCandles(){
    stage.innerHTML = "";
    candles = [];
    for (var i = 0; i < N; i++) {
      var el = document.createElement("button");
      el.type = "button";
      el.textContent = "🕯️";
      el.style.cssText = "font-size:40px; padding:8px 0; touch-action:none;";
      stage.appendChild(el);
      (function(idx, btn){
        btn.addEventListener("pointerdown", function(e){
          e.preventDefault();
          blowing = idx;
        });
        btn.addEventListener("pointerup", function(){ if (blowing === idx) { blowing = -1; } });
        btn.addEventListener("pointerleave", function(){ if (blowing === idx) { blowing = -1; } });
      })(i, el);
      candles.push({el: el, hp: 50 + Math.random() * 50, max: 100, alive: true});
      candles[i].max = candles[i].hp;
    }
  }
  function finish(){
    playing = false;
    clearInterval(tickId);
    blowing = -1;
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(out));
    fetch("{{ url_for('rousoku_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + out + " 本消しました";
          document.getElementById("bestline").textContent = "ベスト（消した本数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function tick(){
    if (!playing) { return; }
    var left = Math.max(0, endsAt - Date.now());
    timeEl.textContent = String(Math.ceil(left / 1000));
    if (left <= 0) { finish(); return; }
    if (inhaling > 0) {
      inhaling--;
      breathEl.style.background = "#f78e7e";
      if (inhaling === 0) { breath = 80; }
    } else {
      breathEl.style.background = "#7ec8f7";
      if (blowing >= 0 && candles[blowing] && candles[blowing].alive) {
        breath -= 1;
        var c = candles[blowing];
        c.hp -= 3.4;
        if (c.hp <= 0) {
          c.alive = false;
          c.el.textContent = "💨";
          out++;
          outEl.textContent = String(out);
          blowing = -1;
          if (out >= N) { finish(); return; }
        }
        if (breath <= 0) {
          breath = 0;
          inhaling = 24;
          blowing = -1;
        }
      }
    }
    candles.forEach(function(c){
      if (!c.alive) { return; }
      if (c.hp < c.max) {
        c.hp = Math.min(c.max, c.hp + 0.22);
      }
      var ratio = c.hp / c.max;
      c.el.style.opacity = String(0.35 + 0.65 * ratio);
      c.el.style.transform = "scale(" + (0.8 + 0.3 * ratio) + ")";
    });
    breathEl.style.width = (breath / 80 * 100) + "%";
  }
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    out = 0;
    outEl.textContent = "0";
    breath = 80;
    inhaling = 0;
    blowing = -1;
    buildCandles();
    message.textContent = "ろうそくを長押しして吹き消そう！";
    startBtn.disabled = true;
    endsAt = Date.now() + 60000;
    tickId = setInterval(tick, 50);
  });
  buildCandles();
})();
</script>
"""


@app.route("/games/rousoku", methods=["GET"])
def rousoku():
    body = render_template_string(
        ROUSOKU_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("rousoku", "max"),
        history=recent_scores("rousoku", 10),
    )
    return game_page("一息ろうそく消し", body)


@app.route("/games/rousoku/score", methods=["POST"])
def rousoku_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 99):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("rousoku", int(raw))
    return {"ok": True, "best": best_score("rousoku", "max")}


# ============================
# 胸ポケットの盾文字
# 選んだ漢字の輪郭（字のインク部分）を盾にして、落ちてくる玉を防ぐゲーム
# （クライアント JS / Canvas）。字の空白部分は玉がすり抜ける。防いだ数を記録。
# ============================
SHIELDMOJI_TEMPLATE = r"""
  <h1>🛡️ 胸ポケットの盾文字</h1>
  <p class="howto">盾にする漢字を選んでスタート。漢字は胸の前に浮かび、マウスや←→キーで左右に動かせます。落ちてくる玉（🔴）が字の「インクの部分」に当たれば防げますが、字の空白部分はすり抜けます。すり抜けた玉が体に当たるとダメージ（3回で終了）。60秒で防いだ数を記録します。大きな字ほど守りやすいけれど、空白の形は字それぞれです。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（防いだ数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">防いだ数: <span id="blocked">0</span> ／ ハート: <span id="hearts">❤️❤️❤️</span> ／ 残り: <span id="timeLeft">60</span> 秒</p>
    <div class="row" style="margin-bottom:8px;">
      <span class="muted">盾の文字：</span>
      <button type="button" class="mojibtn" data-m="一">一（細い）</button>
      <button type="button" class="mojibtn" data-m="山">山（ふつう）</button>
      <button type="button" class="mojibtn" data-m="鬱">鬱（大きい）</button>
    </div>
    <div style="text-align:center;">
      <canvas id="cv" width="480" height="360" style="border:1px solid #ddd; border-radius:12px; background:#fdfdf5; max-width:100%;"></canvas>
    </div>
    <p class="result" id="message">文字を選んで「スタート」</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（防いだ数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 個</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var cv = document.getElementById("cv");
  var ctx = cv.getContext("2d");
  var message = document.getElementById("message");
  var blockedEl = document.getElementById("blocked");
  var heartsEl = document.getElementById("hearts");
  var timeEl = document.getElementById("timeLeft");
  var startBtn = document.getElementById("startBtn");
  var W = 480, H = 360, BOX = 120, CELL = 8, GRID = 15;
  var moji = "山", grid = null;
  var playing = false, cx = 240, hearts = 3, blocked = 0;
  var balls = [], tickId = null, spawnId = null, endsAt = 0;
  var keys = {};
  function buildGrid(){
    var off = document.createElement("canvas");
    off.width = BOX; off.height = BOX;
    var octx = off.getContext("2d");
    octx.fillStyle = "#000";
    octx.font = "104px serif";
    octx.textAlign = "center";
    octx.textBaseline = "middle";
    octx.fillText(moji, BOX / 2, BOX / 2 + 6);
    var data = octx.getImageData(0, 0, BOX, BOX).data;
    grid = [];
    for (var gy = 0; gy < GRID; gy++) {
      var row = [];
      for (var gx = 0; gx < GRID; gx++) {
        var px = Math.floor((gx + 0.5) * BOX / GRID);
        var py = Math.floor((gy + 0.5) * BOX / GRID);
        row.push(data[(py * BOX + px) * 4 + 3] > 80);
      }
      grid.push(row);
    }
  }
  function inkAt(x, y){
    var boxLeft = cx - BOX / 2, boxTop = H - 150;
    var gx = Math.floor((x - boxLeft) / CELL);
    var gy = Math.floor((y - boxTop) / CELL);
    if (gx < 0 || gx >= GRID || gy < 0 || gy >= GRID || !grid) { return false; }
    return grid[gy][gx];
  }
  function draw(){
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#fdfdf5";
    ctx.fillRect(0, 0, W, H);
    ctx.font = "104px serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "rgba(40,80,160,.82)";
    ctx.fillText(moji, cx, H - 150 + BOX / 2 + 6);
    ctx.font = "30px serif";
    ctx.fillText("🧍", cx, H - 14);
    balls.forEach(function(b){
      ctx.font = "20px serif";
      ctx.fillText("🔴", b.x, b.y);
    });
  }
  function spawn(){
    if (!playing) { return; }
    balls.push({x: 20 + Math.random() * (W - 40), y: -14, speed: 2.1 + Math.random() * 1.4});
  }
  function finish(){
    playing = false;
    clearInterval(tickId);
    clearInterval(spawnId);
    balls = [];
    draw();
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(blocked));
    fetch("{{ url_for('shield_moji_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + blocked + " 個防ぎました";
          document.getElementById("bestline").textContent = "ベスト（防いだ数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function tick(){
    if (!playing) { return; }
    var left = Math.max(0, endsAt - Date.now());
    timeEl.textContent = String(Math.ceil(left / 1000));
    if (left <= 0) { finish(); return; }
    if (keys.ArrowLeft) { cx = Math.max(BOX / 2, cx - 6); }
    if (keys.ArrowRight) { cx = Math.min(W - BOX / 2, cx + 6); }
    balls = balls.filter(function(b){
      b.y += b.speed;
      if (b.y >= H - 150 && b.y <= H - 30 && inkAt(b.x, b.y)) {
        blocked++;
        blockedEl.textContent = String(blocked);
        return false;
      }
      if (b.y >= H - 26) {
        if (Math.abs(b.x - cx) <= 26) {
          hearts--;
          heartsEl.textContent = hearts > 0 ? "❤️".repeat(hearts) : "💔";
          message.textContent = "体に当たった！";
          if (hearts <= 0) { finish(); }
        }
        return false;
      }
      return true;
    });
    draw();
  }
  document.querySelectorAll(".mojibtn").forEach(function(btn){
    btn.addEventListener("click", function(){
      if (playing) { return; }
      moji = btn.getAttribute("data-m");
      buildGrid();
      draw();
      message.textContent = "盾は「" + moji + "」。「スタート」を押してね";
    });
  });
  cv.addEventListener("pointermove", function(e){
    var r = cv.getBoundingClientRect();
    cx = Math.max(BOX / 2, Math.min(W - BOX / 2, (e.clientX - r.left) * W / r.width));
    if (!playing) { draw(); }
  });
  document.addEventListener("keydown", function(e){
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { keys[e.key] = true; e.preventDefault(); }
  });
  document.addEventListener("keyup", function(e){ keys[e.key] = false; });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    buildGrid();
    playing = true;
    blocked = 0; hearts = 3; cx = 240;
    blockedEl.textContent = "0";
    heartsEl.textContent = "❤️❤️❤️";
    message.textContent = "玉を字のインクで防ごう！";
    startBtn.disabled = true;
    endsAt = Date.now() + 60000;
    spawn();
    spawnId = setInterval(spawn, 620);
    tickId = setInterval(tick, 40);
  });
  buildGrid();
  draw();
})();
</script>
"""


@app.route("/games/shield-moji", methods=["GET"])
def shield_moji():
    body = render_template_string(
        SHIELDMOJI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("shield-moji", "max"),
        history=recent_scores("shield-moji", 10),
    )
    return game_page("胸ポケットの盾文字", body)


@app.route("/games/shield-moji/score", methods=["POST"])
def shield_moji_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("shield-moji", int(raw))
    return {"ok": True, "best": best_score("shield-moji", "max")}


# ============================
# ラーメン油あつめ
# 丼の中の油の粒を、箸（ポインタのドラッグ）で寄せ集めて中央の
# まとめゾーンに集めるゲーム（クライアント JS）。制限時間45秒、
# 最後にゾーン内に入った粒の数を POST する。
# ============================
RAMENOIL_TEMPLATE = r"""
  <h1>🍜 ラーメン油あつめ</h1>
  <p class="howto">丼の中に浮いた油の粒（黄色い点）を、ドラッグ（箸）で寄せ集めてください。ドラッグ中、近くの粒が箸先に引き寄せられます。中央の丸い「まとめゾーン」の中に入った粒が集まった分です。45秒で何粒集められるか挑戦。途中で「これで完成」ボタンでも終われます。集めた数を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（集めた数）: {{ best if best is not none else '—' }}</p>
    <p class="mid">残り: <span id="timeLeft">45</span> 秒 ／ 集まった粒: <span id="gathered">0</span> / 24</p>
    <div style="text-align:center;">
      <div id="bowl" style="position:relative; width:380px; height:380px; max-width:92vw; aspect-ratio:1; margin:0 auto; border-radius:50%; border:6px solid #b5533c; background:#fff3d6; overflow:hidden; touch-action:none;">
        <div id="zone" style="position:absolute; left:50%; top:50%; width:116px; height:116px; margin:-58px 0 0 -58px; border:2px dashed #d99100; border-radius:50%; background:rgba(255,214,64,.18);"></div>
      </div>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="startBtn">スタート</button>
      <button type="button" id="doneBtn" disabled>これで完成</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（集めた数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 粒</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var bowl = document.getElementById("bowl");
  var message = document.getElementById("message");
  var gatheredEl = document.getElementById("gathered");
  var timeEl = document.getElementById("timeLeft");
  var startBtn = document.getElementById("startBtn");
  var doneBtn = document.getElementById("doneBtn");
  var N = 24, R = 190, ZONE_R = 58, DOT_R = 160;
  var playing = false, dragging = false, tickId = null, endsAt = 0;
  var drops = [];
  function countGathered(){
    var n = 0;
    drops.forEach(function(d){
      var dx = d.x - R, dy = d.y - R;
      if (Math.sqrt(dx * dx + dy * dy) <= ZONE_R) { n++; }
    });
    return n;
  }
  function build(){
    drops.forEach(function(d){ d.el.remove(); });
    drops = [];
    for (var i = 0; i < N; i++) {
      var el = document.createElement("div");
      el.style.cssText = "position:absolute; width:12px; height:12px; border-radius:50%; background:#f5b301; border:1px solid #d99100; pointer-events:none;";
      bowl.appendChild(el);
      var ang = Math.random() * Math.PI * 2;
      var rad = 70 + Math.random() * 85;
      var d = {el: el, x: R + Math.cos(ang) * rad, y: R + Math.sin(ang) * rad};
      el.style.left = (d.x - 6) + "px";
      el.style.top = (d.y - 6) + "px";
      drops.push(d);
    }
    gatheredEl.textContent = "0";
  }
  function finish(){
    playing = false;
    dragging = false;
    clearInterval(tickId);
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    doneBtn.disabled = true;
    var score = countGathered();
    var form = new FormData();
    form.append("score", String(score));
    fetch("{{ url_for('ramen_oil_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + score + " 粒集めました";
          document.getElementById("bestline").textContent = "ベスト（集めた数）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function tick(){
    if (!playing) { return; }
    var left = Math.max(0, endsAt - Date.now());
    timeEl.textContent = String(Math.ceil(left / 1000));
    gatheredEl.textContent = String(countGathered());
    if (left <= 0) { finish(); }
  }
  function pointerPos(e){
    var r = bowl.getBoundingClientRect();
    return {
      x: (e.clientX - r.left) * 380 / r.width,
      y: (e.clientY - r.top) * 380 / r.height
    };
  }
  bowl.addEventListener("pointerdown", function(e){
    if (!playing) { return; }
    dragging = true;
    bowl.setPointerCapture(e.pointerId);
  });
  bowl.addEventListener("pointermove", function(e){
    if (!playing || !dragging) { return; }
    var p = pointerPos(e);
    drops.forEach(function(d){
      var dx = p.x - d.x, dy = p.y - d.y;
      var dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < 74 && dist > 1) {
        d.x += dx * 0.35;
        d.y += dy * 0.35;
      }
      var cx = d.x - R, cy = d.y - R;
      var cd = Math.sqrt(cx * cx + cy * cy);
      if (cd > DOT_R) {
        d.x = R + cx / cd * DOT_R;
        d.y = R + cy / cd * DOT_R;
      }
      d.el.style.left = (d.x - 6) + "px";
      d.el.style.top = (d.y - 6) + "px";
    });
    gatheredEl.textContent = String(countGathered());
  });
  bowl.addEventListener("pointerup", function(){ dragging = false; });
  bowl.addEventListener("pointercancel", function(){ dragging = false; });
  doneBtn.addEventListener("click", function(){ if (playing) { finish(); } });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    build();
    message.textContent = "ドラッグで油を中央へ寄せ集めよう！";
    startBtn.disabled = true;
    doneBtn.disabled = false;
    endsAt = Date.now() + 45000;
    tickId = setInterval(tick, 100);
  });
  build();
})();
</script>
"""


@app.route("/games/ramen-oil", methods=["GET"])
def ramen_oil():
    body = render_template_string(
        RAMENOIL_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("ramen-oil", "max"),
        history=recent_scores("ramen-oil", 10),
    )
    return game_page("ラーメン油あつめ", body)


@app.route("/games/ramen-oil/score", methods=["POST"])
def ramen_oil_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 99):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("ramen-oil", int(raw))
    return {"ok": True, "best": best_score("ramen-oil", "max")}


# ============================
# イカサマ割合ハイボール
# ウイスキーの割合を決めて客に出す読み合いゲーム（サーバー側セッション）。
# 薄いほど儲かるが、客の許容ライン（割合の下限）を下回るとバレて
# ストライク。3ストライクか10人接客で終了し、合計利益を記録する。
# ============================
IKASAMA_TYPES = [
    {"name": "近所の常連さん", "lo": 30, "hi": 45, "hint": "しっかりした味が好きそうだ"},
    {"name": "学生さん", "lo": 15, "hi": 30, "hint": "安さ重視。多少薄くても気づきにくいかも"},
    {"name": "会社の社長さん", "lo": 40, "hi": 55, "hint": "舌が肥えている。ごまかしは利かなそう"},
    {"name": "仕事帰りの会社員さん", "lo": 25, "hi": 40, "hint": "ふつうの濃さが好きそうだ"},
    {"name": "観光で来た人", "lo": 20, "hi": 35, "hint": "この店の味の基準はよく知らないようだ"},
]


def ikasama_profit(ratio: int) -> int:
    """割合（%）が低いほど利益が大きい。"""
    return 80 - int(ratio)


def ikasama_judge(ratio: int, tolerance: int):
    """(バレたか, コメント種別) を返す。許容ラインは客が薄いと感じる下限。"""
    ratio = int(ratio)
    tolerance = int(tolerance)
    if ratio < tolerance:
        return True, "busted"
    margin = ratio - tolerance
    if margin <= 5:
        return False, "close"
    if margin <= 15:
        return False, "ok"
    return False, "rich"


IKASAMA_COMMENTS = {
    "busted": "「薄っ！ 水で割ってるだろ！」バレました…。",
    "close": "「ん…？ まあいいか」危ないところでした。",
    "ok": "「うん、ちょうどいい」満足そうです。",
    "rich": "「濃いなあ！」満足そうですが、原価がかさんでいます。",
}


def ikasama_next_customer() -> None:
    t = random.choice(IKASAMA_TYPES)
    session["ik_type"] = t["name"]
    session["ik_hint"] = t["hint"]
    session["ik_tolerance"] = random.randint(int(t["lo"]), int(t["hi"]))
    session["ik_range"] = f"{t['lo']}〜{t['hi']}%"


def ikasama_new_game() -> None:
    session["ik_served"] = 0
    session["ik_strikes"] = 0
    session["ik_profit"] = 0
    session["ik_over"] = False
    session["ik_log"] = []
    ikasama_next_customer()


IKASAMA_TEMPLATE = r"""
  <h1>🥃 イカサマ割合ハイボール</h1>
  <p class="howto">あなたはバーの店主。ハイボールのウイスキー割合（%）を決めて客に出します。薄いほど儲かりますが、客ごとの「これ以上薄いとバレる」許容ラインを下回るとバレてストライク。3ストライクで閉店です。客のタイプから許容ラインの範囲（%）の見当はつきます。10人接客するか閉店までの合計利益を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">接客 {{ served }} / 10 人 ／ ストライク {{ strikes }} / 3 ／ 合計利益 {{ profit }} 円</p>
    {% if over %}
      <p class="big">{% if strikes >= 3 %}🚨 閉店…{% else %}🎉 営業終了！{% endif %}</p>
      <p class="result">合計利益は {{ profit }} 円でした。</p>
      <form method="post" action="{{ url_for('ikasama_reset') }}" class="row">
        <button type="submit">もう一度開店する</button>
      </form>
    {% else %}
      <div class="panel" style="margin-bottom:12px;">
        <h3>次の客：{{ ctype }}</h3>
        <p class="mid">様子：{{ hint }}</p>
        <p class="muted">許容ラインは {{ range_text }} のどこからしい…</p>
      </div>
      <form method="post" action="{{ url_for('ikasama_serve') }}" class="row">
        <label>ウイスキー割合 <input type="number" name="ratio" min="5" max="70" value="35" /> %</label>
        <button type="submit">この割合で出す</button>
      </form>
    {% endif %}
    {% if log %}
      <h3 style="font-size:14px; margin:16px 0 8px;">接客ログ</h3>
      <table>
        {% for line in log %}
          <tr><td>{{ line }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計利益）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 円</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_ikasama(message=None):
    if "ik_served" not in session:
        ikasama_new_game()
    body = render_template_string(
        IKASAMA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        served=int(session.get("ik_served", 0)),
        strikes=int(session.get("ik_strikes", 0)),
        profit=int(session.get("ik_profit", 0)),
        over=bool(session.get("ik_over", False)),
        ctype=session.get("ik_type", ""),
        hint=session.get("ik_hint", ""),
        range_text=session.get("ik_range", ""),
        log=list(session.get("ik_log", [])),
        history=recent_scores("ikasama", 10),
        message=message,
    )
    return game_page("イカサマ割合ハイボール", body)


@app.route("/games/ikasama", methods=["GET"])
def ikasama():
    return render_ikasama()


@app.route("/games/ikasama/serve", methods=["POST"])
def ikasama_serve():
    if "ik_served" not in session:
        ikasama_new_game()
    if session.get("ik_over"):
        return render_ikasama()
    raw = (request.form.get("ratio") or "").strip()
    if not raw.isdigit() or not (5 <= int(raw) <= 70):
        return render_ikasama(message="割合は 5〜70 の整数で入力してください。")
    ratio = int(raw)
    tolerance = int(session.get("ik_tolerance", 30))
    busted, kind = ikasama_judge(ratio, tolerance)
    ctype = session.get("ik_type", "客")
    log = list(session.get("ik_log", []))
    strikes = int(session.get("ik_strikes", 0))
    profit = int(session.get("ik_profit", 0))
    if busted:
        strikes += 1
        session["ik_strikes"] = strikes
        log.append(f"{ctype}：{ratio}% で出した → バレた！（許容ラインは {tolerance}%）")
        msg = IKASAMA_COMMENTS["busted"]
    else:
        gained = ikasama_profit(ratio)
        profit += gained
        session["ik_profit"] = profit
        log.append(f"{ctype}：{ratio}% で出した → 利益 +{gained} 円（許容ラインは {tolerance}%）")
        msg = IKASAMA_COMMENTS[kind] + f" 利益 +{gained} 円。"
    session["ik_log"] = log[-10:]
    served = int(session.get("ik_served", 0)) + 1
    session["ik_served"] = served
    if strikes >= 3 or served >= 10:
        session["ik_over"] = True
        record_score("ikasama", profit)
        return render_ikasama(message=msg + " 営業を終了しました。")
    ikasama_next_customer()
    return render_ikasama(message=msg)


@app.route("/games/ikasama/reset", methods=["POST"])
def ikasama_reset():
    ikasama_new_game()
    flash("新しい営業を始めました。", "ok")
    return redirect(url_for("ikasama"))


# ============================
# まちがいカード見抜き
# 表示されたトランプと「これは○○の○だ」という説明文を見比べて、
# 間違いが「ある」か「ない」かを当てるゲーム（サーバー側セッション）。
# 全10問、正解数を記録する。
# ============================
MACHIGAI_SUITS = ["スペード", "ハート", "ダイヤ", "クラブ"]
MACHIGAI_MARKS = {"スペード": "♠", "ハート": "♥", "ダイヤ": "♦", "クラブ": "♣"}
MACHIGAI_RED = {"ハート", "ダイヤ"}


def machigai_rank_label(rank: int) -> str:
    return {1: "A", 11: "J", 12: "Q", 13: "K"}.get(int(rank), str(rank))


def machigai_make_claim(suit: str, rank: int, wrong: bool, rng) -> tuple:
    """説明文の（スート, ランク）を返す。wrong=True なら必ずどちらかを変える。"""
    cs, cr = suit, int(rank)
    if wrong:
        if rng.random() < 0.5:
            cs = rng.choice([s for s in MACHIGAI_SUITS if s != suit])
        else:
            cr = rng.choice([r for r in range(1, 14) if r != int(rank)])
    return cs, cr


def machigai_is_wrong(card, claim) -> bool:
    return tuple(card) != tuple(claim)


def machigai_new_card() -> None:
    suit = random.choice(MACHIGAI_SUITS)
    rank = random.randint(1, 13)
    wrong = random.random() < 0.5
    cs, cr = machigai_make_claim(suit, rank, wrong, random)
    session["mg_card"] = [suit, rank]
    session["mg_claim"] = [cs, cr]


def machigai_new_game() -> None:
    session["mg_round"] = 1
    session["mg_correct"] = 0
    session["mg_over"] = False
    session["mg_log"] = []
    machigai_new_card()


MACHIGAI_TEMPLATE = r"""
  <h1>🃏 まちがいカード見抜き</h1>
  <p class="howto">大きなカードと、そのカードについての説明文が表示されます。説明文に間違いが「ある」か「ない」かを見抜いてください。間違いがあるときは、スートか数字のどちらかが実際と違います。全10問、正解数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">問題 {{ round_no }} / 10 ／ 正解 {{ correct }} 問</p>
    {% if over %}
      <p class="big">🎉 終了！ {{ correct }} 問正解</p>
      <form method="post" action="{{ url_for('machigai_card_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% else %}
      <p class="big" style="color: {{ 'red' if is_red else '#222' }};">{{ mark }} {{ rank_label }}</p>
      <p class="mid">説明：「これは {{ claim_suit }} の {{ claim_rank }} です」</p>
      <div class="row">
        <form method="post" action="{{ url_for('machigai_card_answer') }}">
          <input type="hidden" name="answer" value="wrong" />
          <button type="submit">❌ 間違いがある</button>
        </form>
        <form method="post" action="{{ url_for('machigai_card_answer') }}">
          <input type="hidden" name="answer" value="right" />
          <button type="submit">⭕ 間違いはない</button>
        </form>
      </div>
    {% endif %}
    {% if log %}
      <h3 style="font-size:14px; margin:16px 0 8px;">これまでの判定</h3>
      <table>
        {% for line in log %}
          <tr><td>{{ line }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（正解数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 問</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_machigai(message=None):
    if "mg_round" not in session:
        machigai_new_game()
    card = session.get("mg_card", ["スペード", 1])
    claim = session.get("mg_claim", card)
    body = render_template_string(
        MACHIGAI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        round_no=int(session.get("mg_round", 1)),
        correct=int(session.get("mg_correct", 0)),
        over=bool(session.get("mg_over", False)),
        mark=MACHIGAI_MARKS.get(card[0], "?"),
        rank_label=machigai_rank_label(int(card[1])),
        is_red=card[0] in MACHIGAI_RED,
        claim_suit=claim[0],
        claim_rank=machigai_rank_label(int(claim[1])),
        log=list(session.get("mg_log", [])),
        history=recent_scores("machigai-card", 10),
        message=message,
    )
    return game_page("まちがいカード見抜き", body)


@app.route("/games/machigai-card", methods=["GET"])
def machigai_card():
    return render_machigai()


@app.route("/games/machigai-card/answer", methods=["POST"])
def machigai_card_answer():
    if "mg_round" not in session:
        machigai_new_game()
    if session.get("mg_over"):
        return render_machigai()
    answer = (request.form.get("answer") or "").strip()
    if answer not in ("wrong", "right"):
        return render_machigai()
    card = session.get("mg_card", ["スペード", 1])
    claim = session.get("mg_claim", card)
    actual_wrong = machigai_is_wrong(card, claim)
    said_wrong = answer == "wrong"
    log = list(session.get("mg_log", []))
    card_text = f"{card[0]}の{machigai_rank_label(int(card[1]))}"
    if said_wrong == actual_wrong:
        session["mg_correct"] = int(session.get("mg_correct", 0)) + 1
        log.append(f"{card_text}：正解！（間違い{'あり' if actual_wrong else 'なし'}）")
        msg = "正解！"
    else:
        log.append(f"{card_text}：はずれ（間違い{'あり' if actual_wrong else 'なし'}でした）")
        msg = "残念、見抜けませんでした。"
    session["mg_log"] = log[-10:]
    round_no = int(session.get("mg_round", 1))
    if round_no >= 10:
        session["mg_over"] = True
        record_score("machigai-card", int(session.get("mg_correct", 0)))
        return render_machigai(message=msg + " 全10問が終わりました。")
    session["mg_round"] = round_no + 1
    machigai_new_card()
    return render_machigai(message=msg)


@app.route("/games/machigai-card/reset", methods=["POST"])
def machigai_card_reset():
    machigai_new_game()
    flash("新しい問題になりました。", "ok")
    return redirect(url_for("machigai_card"))


# ============================
# 2ボタンぽよんリズム
# 左・右の2ボタンだけのリズムゲーム（クライアント JS）。
# 落ちてくるノートが判定ラインに重なった瞬間に対応ボタンを押す。
# パーフェクト +100／グッド +50、40秒の合計点を POST する。
# ============================
POYONRHYTHM_TEMPLATE = r"""
  <h1>🎵 2ボタンぽよんリズム</h1>
  <p class="howto">左（🔵）と右（🟣）のレーンにノートが落ちてきます。下の判定ラインに重なった瞬間に、左は ← キーか F キー（または左ボタン）、右は → キーか J キー（または右ボタン）を押してください。タイミングでパーフェクト（+100）／グッド（+50）。コンボも続きます。40秒の合計点を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（合計点）: {{ best if best is not none else '—' }}</p>
    <p class="mid">得点: <span id="points">0</span> ／ コンボ: <span id="combo">0</span> ／ 残り: <span id="timeLeft">40</span> 秒</p>
    <div id="stage" style="position:relative; width:480px; max-width:100%; height:360px; margin:10px auto; border:1px solid #ddd; border-radius:12px; background:#20242e; overflow:hidden;">
      <div style="position:absolute; left:25%; top:0; width:1px; height:100%; background:rgba(255,255,255,.15);"></div>
      <div style="position:absolute; left:50%; top:0; width:1px; height:100%; background:rgba(255,255,255,.3);"></div>
      <div style="position:absolute; left:75%; top:0; width:1px; height:100%; background:rgba(255,255,255,.15);"></div>
      <div style="position:absolute; left:0; top:308px; width:50%; text-align:center; font-size:34px;">⭕</div>
      <div style="position:absolute; left:50%; top:308px; width:50%; text-align:center; font-size:34px;">⭕</div>
      <div style="position:absolute; left:0; top:306px; width:100%; height:2px; background:rgba(255,255,255,.5);"></div>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="leftBtn">🔵 左（F）</button>
      <button type="button" id="startBtn">スタート</button>
      <button type="button" id="rightBtn">右（J）🟣</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var stage = document.getElementById("stage");
  var message = document.getElementById("message");
  var pointsEl = document.getElementById("points");
  var comboEl = document.getElementById("combo");
  var timeEl = document.getElementById("timeLeft");
  var startBtn = document.getElementById("startBtn");
  var TARGET_Y = 318, SPEED = 4.4;
  var playing = false, points = 0, combo = 0, notes = [];
  var tickId = null, spawnId = null, endsAt = 0;
  function spawn(){
    if (!playing) { return; }
    var lane = Math.random() < 0.5 ? 0 : 1;
    var el = document.createElement("div");
    el.textContent = lane === 0 ? "🔵" : "🟣";
    el.style.cssText = "position:absolute; font-size:32px; width:40px; text-align:center; top:-40px; left:calc(" + (lane === 0 ? "25%" : "75%") + " - 20px);";
    stage.appendChild(el);
    notes.push({el: el, lane: lane, y: -40, judged: false});
  }
  function finish(){
    playing = false;
    clearInterval(tickId);
    clearInterval(spawnId);
    notes.forEach(function(n){ n.el.remove(); });
    notes = [];
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(points));
    fetch("{{ url_for('poyon_rhythm_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ 合計 " + points + " 点でした";
          document.getElementById("bestline").textContent = "ベスト（合計点）: " + d.best;
        }
      })
      .catch(function(){});
  }
  function judge(lane){
    if (!playing) { return; }
    var best = null, bestDist = 1e9;
    notes.forEach(function(n){
      if (n.lane !== lane || n.judged) { return; }
      var d = Math.abs(n.y - TARGET_Y);
      if (d < bestDist) { bestDist = d; best = n; }
    });
    if (!best || bestDist > 46) {
      combo = 0;
      comboEl.textContent = "0";
      message.textContent = "空振り…";
      return;
    }
    best.judged = true;
    best.el.remove();
    notes = notes.filter(function(n){ return n !== best; });
    combo++;
    if (bestDist <= 15) {
      points += 100;
      message.textContent = "パーフェクト！ +100";
    } else {
      points += 50;
      message.textContent = "グッド +50";
    }
    pointsEl.textContent = String(points);
    comboEl.textContent = String(combo);
  }
  function tick(){
    if (!playing) { return; }
    var left = Math.max(0, endsAt - Date.now());
    timeEl.textContent = String(Math.ceil(left / 1000));
    if (left <= 0) { finish(); return; }
    notes = notes.filter(function(n){
      n.y += SPEED;
      n.el.style.top = n.y + "px";
      if (n.y > TARGET_Y + 46) {
        n.el.remove();
        combo = 0;
        comboEl.textContent = "0";
        message.textContent = "ミス…";
        return false;
      }
      return true;
    });
  }
  document.getElementById("leftBtn").addEventListener("click", function(){ judge(0); });
  document.getElementById("rightBtn").addEventListener("click", function(){ judge(1); });
  document.addEventListener("keydown", function(e){
    if (e.key === "ArrowLeft" || e.key === "f" || e.key === "F") { judge(0); }
    if (e.key === "ArrowRight" || e.key === "j" || e.key === "J") { judge(1); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    points = 0; combo = 0;
    pointsEl.textContent = "0";
    comboEl.textContent = "0";
    message.textContent = "ノートに合わせてボタンを押そう！";
    startBtn.disabled = true;
    endsAt = Date.now() + 40000;
    spawn();
    spawnId = setInterval(spawn, 540);
    tickId = setInterval(tick, 30);
  });
})();
</script>
"""


@app.route("/games/poyon-rhythm", methods=["GET"])
def poyon_rhythm():
    body = render_template_string(
        POYONRHYTHM_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("poyon-rhythm", "max"),
        history=recent_scores("poyon-rhythm", 10),
    )
    return game_page("2ボタンぽよんリズム", body)


@app.route("/games/poyon-rhythm/score", methods=["POST"])
def poyon_rhythm_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 9999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("poyon-rhythm", int(raw))
    return {"ok": True, "best": best_score("poyon-rhythm", "max")}


# ============================
# カラフルバブルシュート
# バブルシューティング（クライアント JS / Canvas）。同じ色を3つ以上
# つなげて消す。全3ステージ（元ネタの6ステージから簡略化）。
# 消した得点＋ステージクリアボーナスを POST する。
# ============================
BUBBLESHOT_TEMPLATE = r"""
  <h1>🫧 カラフルバブルシュート</h1>
  <p class="howto">マウスで狙ってクリック（またはスペースキー）でバブルを発射。同じ色が3つ以上つながると消えます。天井からぶら下がらなくなったバブルも落ちて得点になります。全3ステージ。バブルが下のラインに届くとゲームオーバー。得点を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト（得点）: {{ best if best is not none else '—' }}</p>
    <p class="mid">得点: <span id="points">0</span> ／ ステージ: <span id="stageNo">1</span> / 3</p>
    <div style="text-align:center;">
      <canvas id="cv" width="440" height="500" style="border:1px solid #ddd; border-radius:12px; background:#1d2733; max-width:100%; touch-action:none;"></canvas>
    </div>
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
  var cv = document.getElementById("cv");
  var ctx = cv.getContext("2d");
  var message = document.getElementById("message");
  var pointsEl = document.getElementById("points");
  var stageEl = document.getElementById("stageNo");
  var startBtn = document.getElementById("startBtn");
  var COLORS = ["#e74c3c", "#3498db", "#f1c40f", "#2ecc71"];
  var R = 17, X0 = 30, Y0 = 30, COLS = 11, ROWH = 29, MAXROW = 15;
  var DANGER_Y = 448, SHOT_Y = 472;
  var STAGES = [
    {rows: 4, colors: 3},
    {rows: 5, colors: 4},
    {rows: 6, colors: 4}
  ];
  var playing = false, grid = {}, stage = 1, points = 0;
  var aim = -Math.PI / 2, flying = null, curColor = 0, rafId = null;
  function key(r, c){ return r + "," + c; }
  function center(r, c){
    return {x: X0 + c * (2 * R) + (r % 2 ? R : 0), y: Y0 + r * ROWH};
  }
  function neighbors(r, c){
    var cand;
    if (r % 2 === 0) {
      cand = [[c - 1, r], [c + 1, r], [c - 1, r - 1], [c, r - 1], [c - 1, r + 1], [c, r + 1]];
    } else {
      cand = [[c - 1, r], [c + 1, r], [c, r - 1], [c + 1, r - 1], [c, r + 1], [c + 1, r + 1]];
    }
    return cand.filter(function(p){ return p[0] >= 0 && p[0] < COLS && p[1] >= 0 && p[1] < MAXROW; });
  }
  function presentColors(){
    var set = {};
    Object.keys(grid).forEach(function(k){ set[grid[k]] = true; });
    return Object.keys(set).map(function(s){ return parseInt(s, 10); });
  }
  function nextColor(){
    var pc = presentColors();
    if (!pc.length) { pc = [0, 1, 2]; }
    return pc[Math.floor(Math.random() * pc.length)];
  }
  function setupStage(){
    grid = {};
    var conf = STAGES[stage - 1];
    for (var r = 0; r < conf.rows; r++) {
      for (var c = 0; c < COLS; c++) {
        if (r % 2 === 1 && c === COLS - 1) { continue; }
        grid[key(r, c)] = Math.floor(Math.random() * conf.colors);
      }
    }
    curColor = nextColor();
    stageEl.textContent = String(stage);
  }
  function draw(){
    ctx.clearRect(0, 0, 440, 500);
    ctx.strokeStyle = "rgba(255,80,80,.7)";
    ctx.setLineDash([6, 6]);
    ctx.beginPath();
    ctx.moveTo(0, DANGER_Y);
    ctx.lineTo(440, DANGER_Y);
    ctx.stroke();
    ctx.setLineDash([]);
    Object.keys(grid).forEach(function(k){
      var parts = k.split(",");
      var p = center(parseInt(parts[0], 10), parseInt(parts[1], 10));
      drawBubble(p.x, p.y, grid[k]);
    });
    // 照準
    ctx.strokeStyle = "rgba(255,255,255,.45)";
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(220, SHOT_Y);
    ctx.lineTo(220 + Math.cos(aim) * 60, SHOT_Y + Math.sin(aim) * 60);
    ctx.stroke();
    ctx.setLineDash([]);
    if (flying) {
      drawBubble(flying.x, flying.y, flying.color);
    } else if (playing) {
      drawBubble(220, SHOT_Y, curColor);
    }
  }
  function drawBubble(x, y, colorIdx){
    ctx.beginPath();
    ctx.arc(x, y, R - 1, 0, Math.PI * 2);
    ctx.fillStyle = COLORS[colorIdx];
    ctx.fill();
    ctx.beginPath();
    ctx.arc(x - 5, y - 5, 5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255,255,255,.55)";
    ctx.fill();
  }
  function snapAndResolve(fx, fy, colorIdx){
    var bestK = null, bestD = 1e18;
    for (var r = 0; r < MAXROW; r++) {
      for (var c = 0; c < COLS; c++) {
        if (grid[key(r, c)] !== undefined) { continue; }
        var p = center(r, c);
        var d = (p.x - fx) * (p.x - fx) + (p.y - fy) * (p.y - fy);
        if (d < bestD) { bestD = d; bestK = [r, c]; }
      }
    }
    if (!bestK) { return; }
    var br = bestK[0], bc = bestK[1];
    grid[key(br, bc)] = colorIdx;
    // 同色クラスタ
    var seen = {}, stack = [[br, bc]], cluster = [];
    seen[key(br, bc)] = true;
    while (stack.length) {
      var cur = stack.pop();
      cluster.push(cur);
      neighbors(cur[0], cur[1]).forEach(function(nb){
        var nk = key(nb[1], nb[0]);
        if (!seen[nk] && grid[nk] === colorIdx) {
          seen[nk] = true;
          stack.push([nb[1], nb[0]]);
        }
      });
    }
    if (cluster.length >= 3) {
      cluster.forEach(function(cell){ delete grid[key(cell[0], cell[1])]; });
      points += cluster.length * 10;
      // 浮いたバブルを落とす
      var anchored = {}, queue = [];
      for (var c0 = 0; c0 < COLS; c0++) {
        if (grid[key(0, c0)] !== undefined) {
          anchored[key(0, c0)] = true;
          queue.push([0, c0]);
        }
      }
      while (queue.length) {
        var cur2 = queue.pop();
        neighbors(cur2[0], cur2[1]).forEach(function(nb){
          var nk = key(nb[1], nb[0]);
          if (!anchored[nk] && grid[nk] !== undefined) {
            anchored[nk] = true;
            queue.push([nb[1], nb[0]]);
          }
        });
      }
      var dropped = 0;
      Object.keys(grid).forEach(function(k){
        if (!anchored[k]) { delete grid[k]; dropped++; }
      });
      points += dropped * 10;
      if (dropped > 0) {
        message.textContent = cluster.length + " 個消えて、" + dropped + " 個落ちた！";
      } else {
        message.textContent = cluster.length + " 個消えた！";
      }
    }
    pointsEl.textContent = String(points);
    // 敗北判定
    var lost = false;
    Object.keys(grid).forEach(function(k){
      var parts = k.split(",");
      var p = center(parseInt(parts[0], 10), parseInt(parts[1], 10));
      if (p.y + R >= DANGER_Y) { lost = true; }
    });
    if (lost) { finish(false); return; }
    if (Object.keys(grid).length === 0) {
      points += 200;
      pointsEl.textContent = String(points);
      if (stage >= 3) {
        finish(true);
        return;
      }
      stage++;
      message.textContent = "ステージクリア！ +200 点。次のステージへ";
      setupStage();
    }
    curColor = nextColor();
  }
  function step(){
    if (!playing) { return; }
    if (flying) {
      flying.x += flying.vx;
      flying.y += flying.vy;
      if (flying.x < R) { flying.x = R; flying.vx *= -1; }
      if (flying.x > 440 - R) { flying.x = 440 - R; flying.vx *= -1; }
      var hit = flying.y <= Y0 + R;
      if (!hit) {
        Object.keys(grid).forEach(function(k){
          if (hit) { return; }
          var parts = k.split(",");
          var p = center(parseInt(parts[0], 10), parseInt(parts[1], 10));
          var dx = flying.x - p.x, dy = flying.y - p.y;
          if (Math.sqrt(dx * dx + dy * dy) < 2 * R - 3) { hit = true; }
        });
      }
      if (hit) {
        var fx = flying.x, fy = flying.y, col = flying.color;
        flying = null;
        snapAndResolve(fx, fy, col);
      }
    }
    draw();
    if (playing) { rafId = requestAnimationFrame(step); }
  }
  function finish(clearedAll){
    playing = false;
    if (rafId) { cancelAnimationFrame(rafId); }
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(points));
    fetch("{{ url_for('bubble_shot_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = clearedAll
            ? "🎉 全ステージクリア！ 得点 " + points + " 点"
            : "ラインに届いてしまった… 得点 " + points + " 点";
          document.getElementById("bestline").textContent = "ベスト（得点）: " + d.best;
        }
      })
      .catch(function(){});
    draw();
  }
  function shoot(){
    if (!playing || flying) { return; }
    var speed = 9;
    flying = {
      x: 220, y: SHOT_Y, color: curColor,
      vx: Math.cos(aim) * speed, vy: Math.sin(aim) * speed
    };
  }
  cv.addEventListener("pointermove", function(e){
    var r = cv.getBoundingClientRect();
    var mx = (e.clientX - r.left) * 440 / r.width;
    var my = (e.clientY - r.top) * 500 / r.height;
    var dx = mx - 220, dy = my - SHOT_Y;
    if (dy < -8) {
      aim = Math.atan2(dy, dx);
      aim = Math.max(-Math.PI + 0.35, Math.min(-0.35, aim));
      if (!playing) { draw(); }
    }
  });
  cv.addEventListener("click", shoot);
  document.addEventListener("keydown", function(e){
    if (e.key === " ") { shoot(); e.preventDefault(); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    stage = 1;
    points = 0;
    pointsEl.textContent = "0";
    flying = null;
    setupStage();
    message.textContent = "狙ってクリックで発射！";
    startBtn.disabled = true;
    rafId = requestAnimationFrame(step);
  });
  setupStage();
  draw();
})();
</script>
"""


@app.route("/games/bubble-shot", methods=["GET"])
def bubble_shot():
    body = render_template_string(
        BUBBLESHOT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("bubble-shot", "max"),
        history=recent_scores("bubble-shot", 10),
    )
    return game_page("カラフルバブルシュート", body)


@app.route("/games/bubble-shot/score", methods=["POST"])
def bubble_shot_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 9999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("bubble-shot", int(raw))
    return {"ok": True, "best": best_score("bubble-shot", "max")}


# ============================
# 1回交換ドローポーカー
# 5枚の手札から1回だけ交換して、役で CPU と勝負するポーカー
# （サーバー側セッション）。全5ラウンド、勝ち3点・引き分け1点で記録。
# 役判定は drawpoker_evaluate() に切り出してある。
# ============================
DRAWPOKER_SUIT_MARKS = ["♠", "♥", "♦", "♣"]
DRAWPOKER_RED = {1, 2}
DRAWPOKER_HAND_NAMES = [
    "ハイカード", "ワンペア", "ツーペア", "スリーカード", "ストレート",
    "フラッシュ", "フルハウス", "フォーカード", "ストレートフラッシュ",
]


def drawpoker_card_value(rank: int) -> int:
    """ランク（1=A, 2〜10, 11=J, 12=Q, 13=K）を比較用の大きさにする。"""
    return 14 if int(rank) == 1 else int(rank)


def drawpoker_evaluate(cards) -> tuple:
    """(役の強さ 0〜8, タイブレーク用タプル) を返す。大きいほど強い。"""
    vals = sorted((drawpoker_card_value(r) for _s, r in cards), reverse=True)
    flush = len({int(s) for s, _r in cards}) == 1
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    uniq_desc = sorted(counts.keys(), reverse=True)
    straight = False
    s_high = 0
    if len(counts) == 5:
        if uniq_desc[0] - uniq_desc[4] == 4:
            straight, s_high = True, uniq_desc[0]
        elif uniq_desc == [14, 5, 4, 3, 2]:
            straight, s_high = True, 5
    if straight and flush:
        return (8, (s_high,))
    if groups[0][1] == 4:
        return (7, (groups[0][0], groups[1][0]))
    if groups[0][1] == 3 and len(groups) > 1 and groups[1][1] == 2:
        return (6, (groups[0][0], groups[1][0]))
    if flush:
        return (5, tuple(vals))
    if straight:
        return (4, (s_high,))
    if groups[0][1] == 3:
        kickers = sorted((v for v, c in counts.items() if c == 1), reverse=True)
        return (3, (groups[0][0], *kickers))
    pairs = sorted((v for v, c in counts.items() if c == 2), reverse=True)
    if len(pairs) == 2:
        kicker = max(v for v, c in counts.items() if c == 1)
        return (2, (pairs[0], pairs[1], kicker))
    if len(pairs) == 1:
        kickers = sorted((v for v, c in counts.items() if c == 1), reverse=True)
        return (1, (pairs[0], *kickers))
    return (0, tuple(vals))


def drawpoker_compare(a, b) -> int:
    """a が強ければ 1、b が強ければ -1、引き分けは 0。"""
    return (a > b) - (a < b)


def drawpoker_cpu_discards(cards) -> list:
    """CPU の交換判断：ペア以上は残し、無役なら高い2枚を残す。"""
    vals = [drawpoker_card_value(r) for _s, r in cards]
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    paired = {v for v, c in counts.items() if c >= 2}
    if paired:
        return [i for i, v in enumerate(vals) if v not in paired][:3]
    order = sorted(range(5), key=lambda i: -vals[i])
    keep = set(order[:2])
    return [i for i in range(5) if i not in keep]


def drawpoker_card_text(card) -> str:
    s, r = int(card[0]), int(card[1])
    return f"{DRAWPOKER_SUIT_MARKS[s]} {machigai_rank_label(r)}"


def drawpoker_deal() -> None:
    deck = [[s, r] for s in range(4) for r in range(1, 14)]
    random.shuffle(deck)
    session["dp_player"] = deck[:5]
    session["dp_cpu"] = deck[5:10]
    session["dp_deck"] = deck[10:]
    session["dp_phase"] = "select"


def drawpoker_new_game() -> None:
    session["dp_round"] = 1
    session["dp_points"] = 0
    session["dp_over"] = False
    session["dp_log"] = []
    session["dp_result"] = ""
    drawpoker_deal()


DRAWPOKER_TEMPLATE = r"""
  <h1>🂡 1回交換ドローポーカー</h1>
  <p class="howto">5枚の手札から、交換したいカードを選んで1回だけ交換できます（交換しないのもOK）。CPU も1回交換します。役の強さで勝負し、勝ち3点・引き分け1点。全5ラウンドの合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">ラウンド {{ round_no }} / 5 ／ 合計 {{ points }} 点</p>
    {% if over %}
      <p class="big">🎉 全ラウンド終了！ {{ points }} 点</p>
      <form method="post" action="{{ url_for('draw_poker_reset') }}" class="row">
        <button type="submit">もう一度対戦</button>
      </form>
    {% elif phase == 'select' %}
      <p class="mid">あなたの手札（交換したいカードにチェック）</p>
      <form method="post" action="{{ url_for('draw_poker_exchange') }}">
        <div class="row" style="gap:14px;">
          {% for card in player %}
            <label style="font-size:26px; border:1px solid #ccc; border-radius:8px; padding:10px 8px; background:#fff; color: {{ 'red' if card[0] in red_suits else '#222' }};">
              <input type="checkbox" name="discard" value="{{ loop.index0 }}" /> {{ card_text(card) }}
            </label>
          {% endfor %}
        </div>
        <div class="row" style="margin-top:12px;">
          <button type="submit">交換して勝負</button>
        </div>
      </form>
      <p class="muted">CPU の手札は交換が終わるまで伏せられています。</p>
    {% else %}
      <p class="mid">あなた：{% for card in player %}<span style="font-size:22px; color: {{ 'red' if card[0] in red_suits else '#222' }};">{{ card_text(card) }} </span>{% endfor %}→ {{ player_hand }}</p>
      <p class="mid">CPU：{% for card in cpu %}<span style="font-size:22px; color: {{ 'red' if card[0] in red_suits else '#222' }};">{{ card_text(card) }} </span>{% endfor %}→ {{ cpu_hand }}</p>
      <p class="big">{{ result }}</p>
      <form method="post" action="{{ url_for('draw_poker_next') }}" class="row">
        <button type="submit">{% if round_no >= 5 %}結果を見る{% else %}次のラウンドへ{% endif %}</button>
      </form>
    {% endif %}
    {% if log %}
      <h3 style="font-size:14px; margin:16px 0 8px;">対戦ログ</h3>
      <table>
        {% for line in log %}
          <tr><td>{{ line }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_drawpoker(message=None):
    if "dp_round" not in session:
        drawpoker_new_game()
    player = session.get("dp_player", [])
    cpu = session.get("dp_cpu", [])
    phase = session.get("dp_phase", "select")
    player_hand = cpu_hand = ""
    if phase == "result" and player and cpu:
        player_hand = DRAWPOKER_HAND_NAMES[drawpoker_evaluate(player)[0]]
        cpu_hand = DRAWPOKER_HAND_NAMES[drawpoker_evaluate(cpu)[0]]
    body = render_template_string(
        DRAWPOKER_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        round_no=int(session.get("dp_round", 1)),
        points=int(session.get("dp_points", 0)),
        over=bool(session.get("dp_over", False)),
        phase=phase,
        player=player,
        cpu=cpu,
        player_hand=player_hand,
        cpu_hand=cpu_hand,
        result=session.get("dp_result", ""),
        log=list(session.get("dp_log", [])),
        card_text=drawpoker_card_text,
        red_suits=DRAWPOKER_RED,
        history=recent_scores("draw-poker", 10),
        message=message,
    )
    return game_page("1回交換ドローポーカー", body)


@app.route("/games/draw-poker", methods=["GET"])
def draw_poker():
    return render_drawpoker()


@app.route("/games/draw-poker/exchange", methods=["POST"])
def draw_poker_exchange():
    if "dp_round" not in session:
        drawpoker_new_game()
    if session.get("dp_over") or session.get("dp_phase") != "select":
        return render_drawpoker()
    deck = list(session.get("dp_deck", []))
    player = [list(c) for c in session.get("dp_player", [])]
    cpu = [list(c) for c in session.get("dp_cpu", [])]
    discards = set()
    for raw in request.form.getlist("discard"):
        if raw.isdigit() and 0 <= int(raw) < 5:
            discards.add(int(raw))
    for i in sorted(discards):
        if deck:
            player[i] = deck.pop()
    for i in drawpoker_cpu_discards(cpu):
        if deck:
            cpu[i] = deck.pop()
    session["dp_player"] = player
    session["dp_cpu"] = cpu
    session["dp_deck"] = deck
    pe = drawpoker_evaluate(player)
    ce = drawpoker_evaluate(cpu)
    outcome = drawpoker_compare(pe, ce)
    points = int(session.get("dp_points", 0))
    round_no = int(session.get("dp_round", 1))
    log = list(session.get("dp_log", []))
    if outcome > 0:
        points += 3
        result = "🎉 あなたの勝ち！ +3 点"
        log.append(f"ラウンド{round_no}：{DRAWPOKER_HAND_NAMES[pe[0]]} vs {DRAWPOKER_HAND_NAMES[ce[0]]} → 勝ち")
    elif outcome < 0:
        result = "CPU の勝ち…"
        log.append(f"ラウンド{round_no}：{DRAWPOKER_HAND_NAMES[pe[0]]} vs {DRAWPOKER_HAND_NAMES[ce[0]]} → 負け")
    else:
        points += 1
        result = "引き分け +1 点"
        log.append(f"ラウンド{round_no}：{DRAWPOKER_HAND_NAMES[pe[0]]} vs {DRAWPOKER_HAND_NAMES[ce[0]]} → 引き分け")
    session["dp_points"] = points
    session["dp_log"] = log[-5:]
    session["dp_result"] = result
    session["dp_phase"] = "result"
    return render_drawpoker(message=result)


@app.route("/games/draw-poker/next", methods=["POST"])
def draw_poker_next():
    if "dp_round" not in session:
        drawpoker_new_game()
    if session.get("dp_over"):
        return render_drawpoker()
    if session.get("dp_phase") != "result":
        return render_drawpoker()
    round_no = int(session.get("dp_round", 1))
    if round_no >= 5:
        session["dp_over"] = True
        session["dp_phase"] = "over"
        record_score("draw-poker", int(session.get("dp_points", 0)))
        return render_drawpoker(message="全5ラウンドが終わりました。")
    session["dp_round"] = round_no + 1
    drawpoker_deal()
    return render_drawpoker()


@app.route("/games/draw-poker/reset", methods=["POST"])
def draw_poker_reset():
    drawpoker_new_game()
    flash("新しい対戦を始めました。", "ok")
    return redirect(url_for("draw_poker"))


# ============================
# 手がかり論破レスバ
# 書きこみの時刻や名前などの手がかりを集め、相手の言い分に
# つきつけてうそを言い負かす推理ゲーム（サーバー側セッション）。
# 全3シナリオ。1発正解30点、2回目20点、3回目10点で記録する。
# ============================
RONPA_SCENARIOS = [
    {
        "title": "消えたプリンのなぞ",
        "opponent": "じろう",
        "claim": "「ぼくは21時にはもう寝ていたよ。プリンが消えた22時ごろは起きていない」",
        "posts": [
            {"name": "たろう", "time": "20:48", "text": "冷蔵庫にプリンを入れた。あとで食べる"},
            {"name": "はなこ", "time": "21:15", "text": "宿題が終わった。もう寝るね"},
            {"name": "じろう", "time": "21:57", "text": "ゲームの配信を見てる。今日は遅くまでやるらしい"},
            {"name": "たろう", "time": "22:03", "text": "あれ、冷蔵庫のプリンがない！"},
            {"name": "じろう", "time": "22:05", "text": "知らないよ。ぼくは寝てたんだから"},
        ],
        "evidences": [
            {"text": "21:57の書きこみ「ゲームの配信を見てる」", "correct": True,
             "rebuttal": "21時に寝ていたはずなのに、21:57には配信を見ていた書きこみがある。起きていたはずだ！"},
            {"text": "20:48の書きこみ「冷蔵庫にプリンを入れた」", "correct": False,
             "rebuttal": "プリンがあった証拠にはなるけど、寝ていたかどうかの反証にはならない…。"},
            {"text": "22:03の書きこみ「プリンがない！」", "correct": False,
             "rebuttal": "プリンが消えたことに気づいた時刻の話で、寝ていたかは分からない…。"},
        ],
    },
    {
        "title": "借りっぱなしノート",
        "opponent": "さくら",
        "claim": "「ノートなら昨日、学校でちゃんに返したよ。だから今わたしは持っていない」",
        "posts": [
            {"name": "ちゃん", "time": "昨日 15:20", "text": "さくらに数学のノートを貸した"},
            {"name": "さくら", "time": "昨日 21:40", "text": "ノート借りっぱなしで助かった〜。写し終わった"},
            {"name": "ちゃん", "time": "今日 08:05", "text": "ノート返ってきてないんだけど…"},
            {"name": "さくら", "time": "今日 08:10", "text": "え、昨日学校で返したよ？"},
        ],
        "evidences": [
            {"text": "昨日21:40の書きこみ「ノート借りっぱなしで助かった」", "correct": True,
             "rebuttal": "昨日の夜の時点で「借りっぱなし」と自分で書いている。学校で返した後なら、こんな書きこみはしないはずだ！"},
            {"text": "昨日15:20の書きこみ「ノートを貸した」", "correct": False,
             "rebuttal": "貸した事実は分かるけど、返したかどうかの反証にはならない…。"},
            {"text": "今日08:05の書きこみ「返ってきてない」", "correct": False,
             "rebuttal": "それは被害の訴えそのもので、うその証拠にはならない…。"},
        ],
    },
    {
        "title": "深夜のゲーム音",
        "opponent": "ゆうた",
        "claim": "「0時にはスマホを置いて寝た。深夜にゲームの音なんて出していない」",
        "posts": [
            {"name": "ゆうた", "time": "23:48", "text": "今日は早めに寝る。おやすみ"},
            {"name": "母", "time": "翌 00:20", "text": "さっきゲームの音が聞こえた気がする…"},
            {"name": "ゆうた", "time": "翌 00:42", "text": "やった、今日のスコアランキング1位だ！"},
            {"name": "ゆうた", "time": "翌 07:30", "text": "夢でも見たんじゃない？ ぼくは寝てたよ"},
        ],
        "evidences": [
            {"text": "翌00:42の書きこみ「スコアランキング1位だ！」", "correct": True,
             "rebuttal": "0時に寝たはずなのに、0:42にはゲームのスコアを書きこんでいる。起きてゲームをしていた証拠だ！"},
            {"text": "23:48の書きこみ「今日は早めに寝る」", "correct": False,
             "rebuttal": "「寝る」と言っただけで、本当に寝た証拠にも反証にもならない…。"},
            {"text": "翌00:20の書きこみ「ゲームの音が聞こえた気がする」", "correct": False,
             "rebuttal": "「気がする」では弱い。確実な証拠がいる…。"},
        ],
    },
]


def ronpa_start_scenario(idx: int) -> None:
    order = list(range(len(RONPA_SCENARIOS[idx]["evidences"])))
    random.shuffle(order)
    session["rp_idx"] = idx
    session["rp_order"] = order
    session["rp_tried"] = []
    session["rp_solved"] = False
    session["rp_feedback"] = ""


def ronpa_new_game() -> None:
    session["rp_points"] = 0
    session["rp_over"] = False
    ronpa_start_scenario(0)


RONPA_TEMPLATE = r"""
  <h1>💬 手がかり論破レスバ</h1>
  <p class="howto">相手の言い分と、掲示板の書きこみ（名前・時刻つき）をよく読んでください。言い分と矛盾する「手がかり」を選んでつきつけると論破できます。1発で論破すると30点、2回目で20点、3回目で10点。全3問の合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">問題 {{ idx + 1 }} / {{ total }} ／ 合計 {{ points }} 点</p>
    {% if over %}
      <p class="big">🎉 全問終了！ {{ points }} 点</p>
      <form method="post" action="{{ url_for('ronpa_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% else %}
      <h3 style="font-size:16px; margin:0 0 6px;">{{ scenario.title }}</h3>
      <div class="panel" style="margin-bottom:12px;">
        <h3>{{ scenario.opponent }} の言い分</h3>
        <p class="mid">{{ scenario.claim }}</p>
      </div>
      <table style="margin-bottom:14px;">
        <tr><th>名前</th><th>時刻</th><th>書きこみ</th></tr>
        {% for post in scenario.posts %}
          <tr><td>{{ post.name }}</td><td>{{ post.time }}</td><td>{{ post.text }}</td></tr>
        {% endfor %}
      </table>
      {% if solved %}
        <p class="result">💥 論破！ {{ feedback }}</p>
        <form method="post" action="{{ url_for('ronpa_next') }}" class="row">
          <button type="submit">{% if idx + 1 >= total %}結果を見る{% else %}次の問題へ{% endif %}</button>
        </form>
      {% else %}
        {% if feedback %}
          <p class="result">{{ feedback }}</p>
        {% endif %}
        <p class="mid">どの手がかりをつきつける？</p>
        <div style="display:flex; flex-direction:column; gap:10px;">
          {% for ev_i, ev in evidences %}
            <form method="post" action="{{ url_for('ronpa_present') }}">
              <input type="hidden" name="ev" value="{{ ev_i }}" />
              <button type="submit" style="width:100%; text-align:left; font-size:15px;" {% if ev_i in tried %}disabled{% endif %}>
                🔎 {{ ev.text }}{% if ev_i in tried %}（これは違った）{% endif %}
              </button>
            </form>
          {% endfor %}
        </div>
      {% endif %}
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def render_ronpa(message=None):
    if "rp_idx" not in session:
        ronpa_new_game()
    idx = int(session.get("rp_idx", 0))
    scenario = RONPA_SCENARIOS[idx]
    order = session.get("rp_order", list(range(len(scenario["evidences"]))))
    evidences = [(i, scenario["evidences"][i]) for i in order]
    body = render_template_string(
        RONPA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        idx=idx,
        total=len(RONPA_SCENARIOS),
        points=int(session.get("rp_points", 0)),
        over=bool(session.get("rp_over", False)),
        scenario=scenario,
        evidences=evidences,
        tried=list(session.get("rp_tried", [])),
        solved=bool(session.get("rp_solved", False)),
        feedback=session.get("rp_feedback", ""),
        history=recent_scores("ronpa", 10),
        message=message,
    )
    return game_page("手がかり論破レスバ", body)


@app.route("/games/ronpa", methods=["GET"])
def ronpa():
    return render_ronpa()


@app.route("/games/ronpa/present", methods=["POST"])
def ronpa_present():
    if "rp_idx" not in session:
        ronpa_new_game()
    if session.get("rp_over") or session.get("rp_solved"):
        return render_ronpa()
    raw = (request.form.get("ev") or "").strip()
    idx = int(session.get("rp_idx", 0))
    scenario = RONPA_SCENARIOS[idx]
    if not raw.isdigit() or not (0 <= int(raw) < len(scenario["evidences"])):
        return render_ronpa()
    ev_i = int(raw)
    tried = list(session.get("rp_tried", []))
    if ev_i in tried:
        return render_ronpa()
    ev = scenario["evidences"][ev_i]
    if ev["correct"]:
        gained = (30, 20, 10)[min(len(tried), 2)]
        session["rp_points"] = int(session.get("rp_points", 0)) + gained
        session["rp_solved"] = True
        session["rp_feedback"] = ev["rebuttal"] + f"（+{gained} 点）"
        return render_ronpa(message="論破成功！")
    tried.append(ev_i)
    session["rp_tried"] = tried
    session["rp_feedback"] = ev["rebuttal"]
    return render_ronpa(message="その手がかりでは言い負かせなかった…。")


@app.route("/games/ronpa/next", methods=["POST"])
def ronpa_next():
    if "rp_idx" not in session:
        ronpa_new_game()
    if session.get("rp_over"):
        return render_ronpa()
    if not session.get("rp_solved"):
        return render_ronpa()
    idx = int(session.get("rp_idx", 0))
    if idx + 1 >= len(RONPA_SCENARIOS):
        session["rp_over"] = True
        record_score("ronpa", int(session.get("rp_points", 0)))
        return render_ronpa(message="全ての言い分を論破しました！")
    ronpa_start_scenario(idx + 1)
    return render_ronpa()


@app.route("/games/ronpa/reset", methods=["POST"])
def ronpa_reset():
    ronpa_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("ronpa"))



# ============================
# カーリング一投詰め
# 相手ストーンの配置を読んで、角度・強さ・曲がりを決める一投勝負（サーバー側）。
# 物理は小さなステップで積分し、ストーン同士は等質量の弾性衝突として解く。
# 3問の合計点を記録する。
# ============================
CURLING_PUZZLES = [
    {"title": "第1問：開けたハウス", "opp": [[6, 2]]},
    {"title": "第2問：正面のガード", "opp": [[0, 18], [-5, -2]]},
    {"title": "第3問：ボタン上の相手石", "opp": [[0, 0], [10, 8]]},
]


def curling_simulate(opp_stones, angle_deg, power, curl):
    """一投をシミュレーションし、最終位置 [(x, y, is_player), ...] を返す。"""
    radius = 3.0
    stones = [{"x": 0.0, "y": 60.0, "vx": 0.0, "vy": 0.0, "player": True}]
    for x, y in opp_stones:
        stones.append({"x": float(x), "y": float(y), "vx": 0.0, "vy": 0.0,
                       "player": False})
    ang = math.radians(angle_deg)
    v0 = float(power)
    stones[0]["vx"] = math.sin(ang) * v0
    stones[0]["vy"] = -math.cos(ang) * v0
    decel = 55.0
    dt = 0.02
    curl_rate = curl * 0.05
    for _ in range(20000):
        moving = [s for s in stones if math.hypot(s["vx"], s["vy"]) > 0.05]
        if not moving:
            break
        for s in moving:
            sp = math.hypot(s["vx"], s["vy"])
            if sp > 0:
                if s["player"]:
                    bend = curl_rate * dt
                    ca, sa = math.cos(bend), math.sin(bend)
                    s["vx"], s["vy"] = (s["vx"] * ca - s["vy"] * sa,
                                        s["vx"] * sa + s["vy"] * ca)
                newsp = max(0.0, sp - decel * dt)
                s["vx"] *= newsp / sp
                s["vy"] *= newsp / sp
            s["x"] += s["vx"] * dt
            s["y"] += s["vy"] * dt
        for i in range(len(stones)):
            for j in range(i + 1, len(stones)):
                a, b = stones[i], stones[j]
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                d = math.hypot(dx, dy)
                if d < 2 * radius and d > 1e-9:
                    nx, ny = dx / d, dy / d
                    overlap = 2 * radius - d
                    a["x"] -= nx * overlap / 2
                    a["y"] -= ny * overlap / 2
                    b["x"] += nx * overlap / 2
                    b["y"] += ny * overlap / 2
                    van = a["vx"] * nx + a["vy"] * ny
                    vbn = b["vx"] * nx + b["vy"] * ny
                    a["vx"] += (vbn - van) * nx
                    a["vy"] += (vbn - van) * ny
                    b["vx"] += (van - vbn) * nx
                    b["vy"] += (van - vbn) * ny
    return [(s["x"], s["y"], s["player"]) for s in stones]


def curling_points(final):
    """最終位置からこの一投の得点を決める（中心に一番近いのが自分で、
    その距離が近いほど高得点）。"""
    dists = [(math.hypot(x, y), p) for x, y, p in final]
    mine = min(d for d, p in dists if p)
    opp = min((d for d, p in dists if not p), default=999.0)
    if mine >= opp:
        return 0
    if mine <= 3:
        return 40
    if mine <= 7:
        return 30
    if mine <= 12:
        return 20
    if mine <= 18:
        return 10
    return 5


CURLING_TEMPLATE = r"""
  <h1>🥌 カーリング一投詰め</h1>
  <p class="howto">相手のストーン（青）の配置を見て、角度（-25〜25度）・強さ（30〜110）・曲がり（-10〜10、プラスで右へ曲がる）を決めて一投だけ投げます。止まった時点で、中心（真ん中の点）に一番近いのが自分のストーン（赤）なら、その近さで得点（最大40点）。相手の石に当てて弾くのも手です。全3問の合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">{{ puzzle.title }} ／ 合計: {{ points }} 点 ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div style="position:relative; width:360px; height:540px; margin:10px auto; background:#eaf4fb; border:1px solid #bcd; border-radius:12px; overflow:hidden;">
      <div style="position:absolute; left:90px; top:330px; width:180px; height:180px; border:2px solid #7ab; border-radius:50%;"></div>
      <div style="position:absolute; left:126px; top:366px; width:108px; height:108px; border:2px solid #c77; border-radius:50%;"></div>
      <div style="position:absolute; left:153px; top:393px; width:54px; height:54px; border:2px solid #7ab; border-radius:50%;"></div>
      <div style="position:absolute; left:177px; top:417px; width:6px; height:6px; background:#333; border-radius:50%;"></div>
      {% for s in stones %}
        <div style="position:absolute; left:{{ s[0] }}px; top:{{ s[1] }}px; width:34px; height:34px; border-radius:50%;
          background:{{ '#e06666' if s[2] else '#6685e0' }}; border:2px solid #fff; box-shadow:0 0 3px #999;
          text-align:center; line-height:34px; font-size:16px;">{{ '🥌' if s[2] else '' }}</div>
      {% endfor %}
      {% if not thrown %}
        <div style="position:absolute; left:163px; top:42px; font-size:30px;">🥌</div>
      {% endif %}
    </div>
    {% if over %}
      <p class="mid">全3問が終わりました。合計 {{ points }} 点です。</p>
      <form method="post" action="{{ url_for('curling_tsume_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% elif thrown %}
      <p class="mid">この一投は {{ last }} 点でした。</p>
      <form method="post" action="{{ url_for('curling_tsume_next') }}" class="row">
        <button type="submit">{{ '結果を見る' if last_puzzle else '次の問題へ' }}</button>
      </form>
    {% else %}
      <form method="post" action="{{ url_for('curling_tsume_throw') }}">
        <div class="row">
          <label>角度 <input type="number" name="angle" min="-25" max="25" value="0" style="width:80px;"></label>
          <label>強さ <input type="number" name="power" min="30" max="110" value="82" style="width:80px;"></label>
          <label>曲がり <input type="number" name="curl" min="-10" max="10" value="0" style="width:80px;"></label>
          <button type="submit">投げる</button>
        </div>
      </form>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def curling_new_game():
    session["cu_idx"] = 0
    session["cu_points"] = 0
    session["cu_result"] = None
    session["cu_last"] = 0
    session["cu_over"] = False


def render_curling(message=None):
    if "cu_idx" not in session:
        curling_new_game()
    idx = int(session.get("cu_idx", 0))
    idx = min(idx, len(CURLING_PUZZLES) - 1)
    puzzle = CURLING_PUZZLES[idx]
    result = session.get("cu_result")
    if result:
        stones = [[(x + 30) * 6 - 17, (70 - y) * 6 - 17, p] for x, y, p in result]
    else:
        stones = [[(x + 30) * 6 - 17, (70 - y) * 6 - 17, False]
                  for x, y in puzzle["opp"]]
    body = render_template_string(
        CURLING_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        puzzle=puzzle,
        stones=stones,
        thrown=result is not None,
        last=int(session.get("cu_last", 0)),
        points=int(session.get("cu_points", 0)),
        over=bool(session.get("cu_over", False)),
        last_puzzle=idx + 1 >= len(CURLING_PUZZLES),
        best=best_score("curling-tsume", "max"),
        history=recent_scores("curling-tsume", 10),
        message=message,
    )
    return game_page("カーリング一投詰め", body)


@app.route("/games/curling-tsume", methods=["GET"])
def curling_tsume():
    return render_curling()


@app.route("/games/curling-tsume/throw", methods=["POST"])
def curling_tsume_throw():
    if "cu_idx" not in session:
        curling_new_game()
    if session.get("cu_over") or session.get("cu_result") is not None:
        return render_curling()
    idx = min(int(session.get("cu_idx", 0)), len(CURLING_PUZZLES) - 1)
    try:
        angle = int(request.form.get("angle", "0"))
        power = int(request.form.get("power", "82"))
        curl = int(request.form.get("curl", "0"))
    except ValueError:
        return render_curling(message="角度・強さ・曲がりは整数で入力してください。")
    if not (-25 <= angle <= 25 and 30 <= power <= 110 and -10 <= curl <= 10):
        return render_curling(message="範囲外の値があります（角度-25〜25、強さ30〜110、曲がり-10〜10）。")
    final = curling_simulate(CURLING_PUZZLES[idx]["opp"], angle, power, curl)
    pts = curling_points(final)
    session["cu_result"] = [[round(x, 2), round(y, 2), p] for x, y, p in final]
    session["cu_last"] = pts
    session["cu_points"] = int(session.get("cu_points", 0)) + pts
    return render_curling(message=f"止まりました。この一投は {pts} 点です。")


@app.route("/games/curling-tsume/next", methods=["POST"])
def curling_tsume_next():
    if "cu_idx" not in session:
        curling_new_game()
    if session.get("cu_over"):
        return render_curling()
    if session.get("cu_result") is None:
        return render_curling()
    idx = int(session.get("cu_idx", 0))
    if idx + 1 >= len(CURLING_PUZZLES):
        session["cu_over"] = True
        record_score("curling-tsume", int(session.get("cu_points", 0)))
        return render_curling(message="全3問が終了しました！")
    session["cu_idx"] = idx + 1
    session["cu_result"] = None
    session["cu_last"] = 0
    return render_curling()


@app.route("/games/curling-tsume/reset", methods=["POST"])
def curling_tsume_reset():
    curling_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("curling_tsume"))


# ============================
# プリズム鏡あわせ
# 鏡（／と＼）を回して、左端の発射口からの光を全部のクリスタルへ届ける
# パズル（サーバー側）。ステージは解けることを検証済みの構成。
# ============================
PRISM_STAGES = [
    {"emitter": 2,
     "mirrors": [[2, 4, 1], [5, 4, 0], [0, 0, 0]],
     "init": [0, 1, 0],
     "crystals": [[4, 4], [5, 1]]},
    {"emitter": 0,
     "mirrors": [[0, 2, 1], [4, 2, 1], [1, 4, 0]],
     "init": [0, 0, 1],
     "crystals": [[2, 2], [4, 5]]},
    {"emitter": 5,
     "mirrors": [[5, 5, 0], [1, 5, 1], [1, 0, 0], [3, 3, 1]],
     "init": [1, 0, 1, 0],
     "crystals": [[3, 5], [1, 3], [3, 0]]},
]


def prism_trace(mirrors, emitter_row, crystals, size=6):
    """光の経路をたどり、(光ったクリスタルの集合, 経路セルのリスト) を返す。
    mirrors は {(r, c): 向き} で、向き 0='／'、1='＼'。"""
    dirs = [(0, 1), (1, 0), (0, -1), (-1, 0)]  # 東南西北
    r, c = emitter_row, 0
    d = 0
    lit = set()
    path = []
    crystal_set = {tuple(x) for x in crystals}
    for _ in range(500):
        path.append((r, c))
        if (r, c) in crystal_set:
            lit.add((r, c))
        if (r, c) in mirrors:
            if mirrors[(r, c)] == 0:  # ／
                d = {0: 3, 3: 0, 2: 1, 1: 2}[d]
            else:  # ＼
                d = {0: 1, 1: 0, 2: 3, 3: 2}[d]
        dr, dc = dirs[d]
        r, c = r + dr, c + dc
        if not (0 <= r < size and 0 <= c < size):
            break
    return lit, path


PRISM_TEMPLATE = r"""
  <h1>🪞 プリズム鏡あわせ</h1>
  <p class="howto">左端の 🔦 から出た光を、鏡を回して全部のクリスタル 💎 へ届けるパズル。鏡のマスを押すと ／ と ＼ が切り替わります。光の道すじは黄色く光ります。全クリスタルに届くとステージクリア。得点は1ステージ最大50点で、鏡を回すたびに2点ずつ下がります。全3ステージの合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">ステージ {{ stage_no }} / {{ stage_total }} ／ 合計: {{ points }} 点 ／
      クリスタル: {{ lit_count }} / {{ crystal_total }} ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div style="display:grid; grid-template-columns: 26px repeat(6, 46px); gap:3px; justify-content:center; margin:10px 0;">
      {% for r in range(6) %}
        <div style="text-align:center; line-height:46px;">{{ '🔦' if r == emitter else '' }}</div>
        {% for c in range(6) %}
          {% set cell = grid[r][c] %}
          {% if cell.kind == 'mirror' %}
            <form method="post" action="{{ url_for('prism_mirror_toggle') }}" style="margin:0;">
              <button type="submit" name="cell" value="{{ cell.idx }}" {% if cleared or over %}disabled{% endif %}
                style="width:46px; height:46px; font-size:24px; padding:0; background:{{ '#fff3b0' if cell.onpath else '#eef' }};">{{ '＼' if cell.ori == 1 else '／' }}</button>
            </form>
          {% elif cell.kind == 'crystal' %}
            <div style="width:46px; height:46px; line-height:46px; text-align:center; font-size:22px;
              border:1px solid #ddd; border-radius:8px; background:{{ '#ffe066' if cell.lit else '#f7f7f7' }};">💎</div>
          {% else %}
            <div style="width:46px; height:46px; border:1px solid #eee; border-radius:8px;
              background:{{ '#fff7cc' if cell.onpath else '#fff' }};"></div>
          {% endif %}
        {% endfor %}
      {% endfor %}
    </div>
    {% if over %}
      <p class="mid">全ステージ終了。合計 {{ points }} 点です。</p>
      <form method="post" action="{{ url_for('prism_mirror_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% elif cleared %}
      <form method="post" action="{{ url_for('prism_mirror_next') }}" class="row">
        <button type="submit">{{ '結果を見る' if last_stage else '次のステージへ' }}</button>
      </form>
    {% endif %}
    <form method="post" action="{{ url_for('prism_mirror_reset') }}" class="row" style="margin-top:10px;">
      <button type="submit">最初からやり直す</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def prism_new_game():
    session["pm_stage"] = 0
    session["pm_rots"] = list(PRISM_STAGES[0]["init"])
    session["pm_clicks"] = 0
    session["pm_points"] = 0
    session["pm_cleared"] = False
    session["pm_over"] = False


def prism_current():
    stage = PRISM_STAGES[int(session.get("pm_stage", 0))]
    rots = list(session.get("pm_rots", stage["init"]))
    mirrors = {}
    for i, (r, c, _sol) in enumerate(stage["mirrors"]):
        mirrors[(r, c)] = int(rots[i])
    return stage, mirrors


def render_prism(message=None):
    if "pm_stage" not in session:
        prism_new_game()
    stage, mirrors = prism_current()
    lit, path = prism_trace(mirrors, stage["emitter"], stage["crystals"])
    path_set = set(path)
    mirror_idx = {(r, c): i for i, (r, c, _s) in enumerate(stage["mirrors"])}
    crystal_set = {tuple(x) for x in stage["crystals"]}
    grid = []
    for r in range(6):
        row = []
        for c in range(6):
            if (r, c) in mirror_idx:
                row.append({"kind": "mirror", "idx": mirror_idx[(r, c)],
                            "ori": mirrors[(r, c)], "onpath": (r, c) in path_set})
            elif (r, c) in crystal_set:
                row.append({"kind": "crystal", "lit": (r, c) in lit})
            else:
                row.append({"kind": "empty", "onpath": (r, c) in path_set})
        grid.append(row)
    body = render_template_string(
        PRISM_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        grid=grid,
        emitter=stage["emitter"],
        stage_no=int(session.get("pm_stage", 0)) + 1,
        stage_total=len(PRISM_STAGES),
        points=int(session.get("pm_points", 0)),
        lit_count=len(lit),
        crystal_total=len(crystal_set),
        cleared=bool(session.get("pm_cleared", False)),
        over=bool(session.get("pm_over", False)),
        last_stage=int(session.get("pm_stage", 0)) + 1 >= len(PRISM_STAGES),
        best=best_score("prism-mirror", "max"),
        history=recent_scores("prism-mirror", 10),
        message=message,
    )
    return game_page("プリズム鏡あわせ", body)


@app.route("/games/prism-mirror", methods=["GET"])
def prism_mirror():
    return render_prism()


@app.route("/games/prism-mirror/toggle", methods=["POST"])
def prism_mirror_toggle():
    if "pm_stage" not in session:
        prism_new_game()
    if session.get("pm_over") or session.get("pm_cleared"):
        return render_prism()
    stage, _mirrors = prism_current()
    raw = (request.form.get("cell") or "").strip()
    if not raw.isdigit() or not (0 <= int(raw) < len(stage["mirrors"])):
        return render_prism()
    rots = list(session.get("pm_rots", stage["init"]))
    i = int(raw)
    rots[i] = 1 - int(rots[i])
    session["pm_rots"] = rots
    session["pm_clicks"] = int(session.get("pm_clicks", 0)) + 1
    stage2, mirrors = prism_current()
    lit, _path = prism_trace(mirrors, stage2["emitter"], stage2["crystals"])
    if len(lit) >= len(stage2["crystals"]):
        gained = max(10, 50 - 2 * int(session.get("pm_clicks", 0)))
        session["pm_points"] = int(session.get("pm_points", 0)) + gained
        session["pm_cleared"] = True
        return render_prism(message=f"💎 全部のクリスタルに光が届いた！ +{gained} 点")
    return render_prism()


@app.route("/games/prism-mirror/next", methods=["POST"])
def prism_mirror_next():
    if "pm_stage" not in session:
        prism_new_game()
    if session.get("pm_over"):
        return render_prism()
    if not session.get("pm_cleared"):
        return render_prism()
    idx = int(session.get("pm_stage", 0))
    if idx + 1 >= len(PRISM_STAGES):
        session["pm_over"] = True
        record_score("prism-mirror", int(session.get("pm_points", 0)))
        return render_prism(message="全ステージ終了しました！")
    session["pm_stage"] = idx + 1
    session["pm_rots"] = list(PRISM_STAGES[idx + 1]["init"])
    session["pm_clicks"] = 0
    session["pm_cleared"] = False
    return render_prism()


@app.route("/games/prism-mirror/reset", methods=["POST"])
def prism_mirror_reset():
    prism_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("prism_mirror"))


# ============================
# 目玉みはり倉庫番
# 箱を全部ゴールへ運ぶ倉庫番のバリアント（サーバー側）。
# 目玉の視線（同じ行・列の直線）が届くマスに立っている間は、
# 直前にいたマスへ後戻りできない。ステージは解法検証済み。
# ============================
EYEBALL_STAGES = [
    {"lines": ["#######",
               "#     #",
               "# @$ .#",
               "#  E  #",
               "#######"],
     "eyes": {(3, 3): "U"}},
    {"lines": ["########",
               "#      #",
               "# $$   #",
               "# ..@  #",
               "#   E  #",
               "########"],
     "eyes": {(4, 4): "U"}},
    {"lines": ["#########",
               "#       #",
               "# @ $ . #",
               "#   #   #",
               "# E $ . #",
               "#       #",
               "#########"],
     "eyes": {(4, 2): "R"}},
]


def eyeball_parse(stage):
    walls, goals, boxes = set(), set(), set()
    player = None
    eyeballs = {}
    for r, line in enumerate(stage["lines"]):
        for c, ch in enumerate(line):
            if ch == "#":
                walls.add((r, c))
            elif ch == ".":
                goals.add((r, c))
            elif ch == "$":
                boxes.add((r, c))
            elif ch == "*":
                boxes.add((r, c))
                goals.add((r, c))
            elif ch == "@":
                player = (r, c)
            elif ch == "E":
                eyeballs[(r, c)] = stage["eyes"][(r, c)]
    return walls, goals, boxes, player, eyeballs


def eyeball_gaze_cells(walls, eyeballs, nrows, ncols):
    dirs = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
    gaze = set()
    for (r, c), d in eyeballs.items():
        dr, dc = dirs[d]
        rr, cc = r + dr, c + dc
        while (0 <= rr < nrows and 0 <= cc < ncols
               and (rr, cc) not in walls and (rr, cc) not in eyeballs):
            gaze.add((rr, cc))
            rr += dr
            cc += dc
    return gaze


def eyeball_try_move(player, boxes, prev, drc, walls, eyeballs, gaze):
    """1手進める。(new_player, new_boxes, moved) を返す。
    player / prev は (r, c) タプル（prev は None 可）、boxes はタプルの集合。"""
    dirs = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
    dr, dc = dirs[drc]
    tgt = (player[0] + dr, player[1] + dc)
    obstacles = walls | set(eyeballs.keys())
    if tgt in obstacles:
        return player, boxes, False
    if player in gaze and prev is not None and tgt == prev:
        return player, boxes, False
    new_boxes = set(boxes)
    if tgt in new_boxes:
        beyond = (tgt[0] + dr, tgt[1] + dc)
        if beyond in obstacles or beyond in new_boxes:
            return player, boxes, False
        new_boxes.remove(tgt)
        new_boxes.add(beyond)
    return tgt, frozenset(new_boxes), True


EYEBALL_TEMPLATE = r"""
  <h1>👁️ 目玉みはり倉庫番</h1>
  <p class="howto">箱 📦 を全部ゴール ◎ へ運ぶ倉庫番。ただし目玉 👁️ の視線（ピンク色のマス）が届く場所に立っている間は、直前にいたマスへ後戻りできません（見張られている！）。矢印ボタンで移動。ステージごとに「手数」が少ないほど高得点（最大60点）。全3ステージの合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">ステージ {{ stage_no }} / {{ stage_total }} ／ 手数: {{ moves }} ／ 合計: {{ points }} 点 ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div style="display:grid; grid-template-columns: repeat({{ ncols }}, 36px); gap:2px; justify-content:center; margin:10px 0;">
      {% for r in range(nrows) %}
        {% for c in range(ncols) %}
          {% set cell = grid[r][c] %}
          <div style="width:36px; height:36px; line-height:36px; text-align:center; font-size:20px; border-radius:6px;
            background:{{ cell.bg }};">{{ cell.mark }}</div>
        {% endfor %}
      {% endfor %}
    </div>
    {% if over %}
      <p class="mid">全ステージ終了。合計 {{ points }} 点です。</p>
      <form method="post" action="{{ url_for('eyeball_sokoban_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% elif cleared %}
      <form method="post" action="{{ url_for('eyeball_sokoban_next') }}" class="row">
        <button type="submit">{{ '結果を見る' if last_stage else '次のステージへ' }}</button>
      </form>
    {% else %}
      <form method="post" action="{{ url_for('eyeball_sokoban_move') }}">
        <div style="display:grid; grid-template-columns: repeat(3, 56px); gap:6px; justify-content:center;">
          <span></span>
          <button type="submit" name="dir" value="U">⬆</button>
          <span></span>
          <button type="submit" name="dir" value="L">⬅</button>
          <button type="submit" name="dir" value="D">⬇</button>
          <button type="submit" name="dir" value="R">➡</button>
        </div>
      </form>
    {% endif %}
    <div class="row" style="margin-top:10px;">
      <form method="post" action="{{ url_for('eyeball_sokoban_restage') }}">
        <button type="submit">このステージをやり直す</button>
      </form>
      <form method="post" action="{{ url_for('eyeball_sokoban_reset') }}">
        <button type="submit">最初からやり直す</button>
      </form>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def eyeball_load_stage(idx):
    stage = EYEBALL_STAGES[idx]
    walls, goals, boxes, player, eyeballs = eyeball_parse(stage)
    session["es_stage_points_before"] = int(session.get("es_points", 0))
    session["es_stage"] = idx
    session["es_player"] = list(player)
    session["es_boxes"] = sorted(list(b) for b in boxes)
    session["es_prev"] = None
    session["es_moves"] = 0
    session["es_cleared"] = False


def eyeball_new_game():
    session["es_points"] = 0
    session["es_over"] = False
    eyeball_load_stage(0)


def render_eyeball(message=None):
    if "es_stage" not in session:
        eyeball_new_game()
    idx = int(session.get("es_stage", 0))
    stage = EYEBALL_STAGES[idx]
    walls, goals, _boxes, _player, eyeballs = eyeball_parse(stage)
    nrows = len(stage["lines"])
    ncols = len(stage["lines"][0])
    gaze = eyeball_gaze_cells(walls, eyeballs, nrows, ncols)
    player = tuple(session.get("es_player", [0, 0]))
    boxes = {tuple(b) for b in session.get("es_boxes", [])}
    grid = []
    for r in range(nrows):
        row = []
        for c in range(ncols):
            pos = (r, c)
            if pos in walls:
                row.append({"mark": "🧱", "bg": "#bbb"})
            elif pos in eyeballs:
                row.append({"mark": "👁️", "bg": "#f8d7da"})
            else:
                bg = "#fff"
                if pos in gaze:
                    bg = "#ffe3e3"
                if pos in goals:
                    bg = "#ffe9a8"
                mark = ""
                if pos in goals:
                    mark = "◎"
                if pos in boxes:
                    mark = "📦"
                    bg = "#ffe9a8" if pos in goals else "#e8f4ff"
                if pos == player:
                    mark = "🐱"
                row.append({"mark": mark, "bg": bg})
        grid.append(row)
    body = render_template_string(
        EYEBALL_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        grid=grid,
        nrows=nrows,
        ncols=ncols,
        stage_no=idx + 1,
        stage_total=len(EYEBALL_STAGES),
        moves=int(session.get("es_moves", 0)),
        points=int(session.get("es_points", 0)),
        cleared=bool(session.get("es_cleared", False)),
        over=bool(session.get("es_over", False)),
        last_stage=idx + 1 >= len(EYEBALL_STAGES),
        best=best_score("eyeball-sokoban", "max"),
        history=recent_scores("eyeball-sokoban", 10),
        message=message,
    )
    return game_page("目玉みはり倉庫番", body)


@app.route("/games/eyeball-sokoban", methods=["GET"])
def eyeball_sokoban():
    return render_eyeball()


@app.route("/games/eyeball-sokoban/move", methods=["POST"])
def eyeball_sokoban_move():
    if "es_stage" not in session:
        eyeball_new_game()
    if session.get("es_over") or session.get("es_cleared"):
        return render_eyeball()
    drc = (request.form.get("dir") or "").strip()
    if drc not in ("U", "D", "L", "R"):
        return render_eyeball()
    idx = int(session.get("es_stage", 0))
    stage = EYEBALL_STAGES[idx]
    walls, goals, _b, _p, eyeballs = eyeball_parse(stage)
    gaze = eyeball_gaze_cells(walls, eyeballs,
                               len(stage["lines"]), len(stage["lines"][0]))
    player = tuple(session.get("es_player"))
    boxes = frozenset(tuple(b) for b in session.get("es_boxes", []))
    prev_raw = session.get("es_prev")
    prev = tuple(prev_raw) if prev_raw else None
    new_player, new_boxes, moved = eyeball_try_move(
        player, boxes, prev, drc, walls, eyeballs, gaze)
    if not moved:
        if player in gaze and prev is not None:
            dr, dc = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}[drc]
            if (player[0] + dr, player[1] + dc) == prev:
                return render_eyeball(message="👁️ 見張られている！ そのマスへは後戻りできない。")
        return render_eyeball(message="そこへは動けません。")
    session["es_player"] = list(new_player)
    session["es_boxes"] = sorted(list(b) for b in new_boxes)
    session["es_prev"] = list(player)
    session["es_moves"] = int(session.get("es_moves", 0)) + 1
    if goals <= set(new_boxes):
        gained = max(10, 60 - int(session.get("es_moves", 0)))
        session["es_points"] = int(session.get("es_points", 0)) + gained
        session["es_cleared"] = True
        return render_eyeball(message=f"🎉 ステージクリア！ +{gained} 点")
    return render_eyeball()


@app.route("/games/eyeball-sokoban/next", methods=["POST"])
def eyeball_sokoban_next():
    if "es_stage" not in session:
        eyeball_new_game()
    if session.get("es_over"):
        return render_eyeball()
    if not session.get("es_cleared"):
        return render_eyeball()
    idx = int(session.get("es_stage", 0))
    if idx + 1 >= len(EYEBALL_STAGES):
        session["es_over"] = True
        record_score("eyeball-sokoban", int(session.get("es_points", 0)))
        return render_eyeball(message="全ステージ終了しました！")
    eyeball_load_stage(idx + 1)
    return render_eyeball()


@app.route("/games/eyeball-sokoban/restage", methods=["POST"])
def eyeball_sokoban_restage():
    if "es_stage" not in session:
        eyeball_new_game()
    idx = int(session.get("es_stage", 0))
    points = int(session.get("es_points", 0))
    if session.get("es_cleared"):
        # クリア済みステージの得点は取り消してやり直す
        points = int(session.get("es_stage_points_before", points))
        session["es_points"] = points
    eyeball_load_stage(idx)
    return render_eyeball(message="ステージをやり直します。")


@app.route("/games/eyeball-sokoban/reset", methods=["POST"])
def eyeball_sokoban_reset():
    eyeball_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("eyeball_sokoban"))


# ============================
# 球審ジャッジ
# 投球の着弾点を見てストライク／ボールを判定する（サーバー側）。
# ゾーンは |x|<=15 かつ |y|<=18。誤審3回か30球で終了し、正解数を記録。
# ============================
def kyushin_is_strike(x, y):
    return abs(x) <= 15 and abs(y) <= 18


def kyushin_new_pitch(rng):
    kind = rng.randrange(3)
    if kind == 0:  # はっきりストライク
        return rng.randint(-10, 10), rng.randint(-13, 13)
    if kind == 1:  # はっきりボール
        if rng.random() < 0.5:
            return rng.choice([-1, 1]) * rng.randint(22, 34), rng.randint(-20, 20)
        return rng.randint(-18, 18), rng.choice([-1, 1]) * rng.randint(25, 36)
    # 際どい球
    if rng.random() < 0.5:
        return rng.choice([-1, 1]) * rng.randint(12, 19), rng.randint(-18, 18)
    return rng.randint(-15, 15), rng.choice([-1, 1]) * rng.randint(15, 22)


KYUSHIN_TEMPLATE = r"""
  <h1>⚾ 球審ジャッジ</h1>
  <p class="howto">投げ込まれたボール ⚾ の着弾点を見て、ストライクゾーン（青い枠）の中なら「ストライク」、外なら「ボール」と判定してください。際どい球もあります。誤審3回か30球で終了し、正しく判定できた数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">{{ count }} 球目 ／ 正解: {{ correct }} ／ 誤審: {{ miss }} / 3 ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div style="position:relative; width:260px; height:300px; margin:10px auto; background:#f3e9d2; border:1px solid #cbb; border-radius:12px;">
      <div style="position:absolute; left:79px; top:89px; width:102px; height:122px; border:3px solid #36c; background:rgba(80,140,255,.12);"></div>
      {% if not over %}
        <div style="position:absolute; left:{{ ball_left }}px; top:{{ ball_top }}px; font-size:20px;">⚾</div>
      {% endif %}
    </div>
    {% if over %}
      <p class="mid">試合終了！ {{ correct }} 球を正しく判定しました。</p>
      <form method="post" action="{{ url_for('kyushin_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% else %}
      <form method="post" action="{{ url_for('kyushin_answer') }}" class="row">
        <button type="submit" name="judge" value="strike" style="font-size:18px;">ストライク</button>
        <button type="submit" name="judge" value="ball" style="font-size:18px;">ボール</button>
      </form>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（正解数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 球</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def kyushin_new_game():
    x, y = kyushin_new_pitch(random)
    session["kj_x"] = x
    session["kj_y"] = y
    session["kj_correct"] = 0
    session["kj_miss"] = 0
    session["kj_count"] = 1
    session["kj_over"] = False


def render_kyushin(message=None):
    if "kj_x" not in session:
        kyushin_new_game()
    x = int(session.get("kj_x", 0))
    y = int(session.get("kj_y", 0))
    body = render_template_string(
        KYUSHIN_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        count=int(session.get("kj_count", 1)),
        correct=int(session.get("kj_correct", 0)),
        miss=int(session.get("kj_miss", 0)),
        over=bool(session.get("kj_over", False)),
        ball_left=int(130 + x * 3.4 - 10),
        ball_top=int(150 + y * 3.4 - 10),
        best=best_score("kyushin-judge", "max"),
        history=recent_scores("kyushin-judge", 10),
        message=message,
    )
    return game_page("球審ジャッジ", body)


@app.route("/games/kyushin-judge", methods=["GET"])
def kyushin_judge():
    return render_kyushin()


@app.route("/games/kyushin-judge/answer", methods=["POST"])
def kyushin_answer():
    if "kj_x" not in session:
        kyushin_new_game()
    if session.get("kj_over"):
        return render_kyushin()
    judge = (request.form.get("judge") or "").strip()
    if judge not in ("strike", "ball"):
        return render_kyushin()
    x = int(session.get("kj_x", 0))
    y = int(session.get("kj_y", 0))
    truth = kyushin_is_strike(x, y)
    said_strike = judge == "strike"
    if said_strike == truth:
        session["kj_correct"] = int(session.get("kj_correct", 0)) + 1
        msg = "⭕ 正しい判定！ " + ("ストライクでした。" if truth else "ボールでした。")
    else:
        session["kj_miss"] = int(session.get("kj_miss", 0)) + 1
        msg = "❌ 誤審… " + ("ストライクでした。" if truth else "ボールでした。")
    count = int(session.get("kj_count", 1))
    if int(session.get("kj_miss", 0)) >= 3 or count >= 30:
        session["kj_over"] = True
        record_score("kyushin-judge", int(session.get("kj_correct", 0)))
        return render_kyushin(message=msg + " 試合終了です。")
    nx, ny = kyushin_new_pitch(random)
    session["kj_x"] = nx
    session["kj_y"] = ny
    session["kj_count"] = count + 1
    return render_kyushin(message=msg)


@app.route("/games/kyushin-judge/reset", methods=["POST"])
def kyushin_reset():
    kyushin_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("kyushin_judge"))


# ============================
# カギバンさばき
# フォローリクエストを「掟」に照らして承認／拒否にさばく（サーバー側）。
# 5件さばくごとに掟が1つ増える。ミス3回か40件で終了し、正解数を記録。
# ============================
KAGIBAN_RULES = [
    "アイコンなしは拒否",
    "投稿0件は拒否",
    "プロフィール文なしは拒否",
    "宣伝リンクありは拒否",
    "開設3日未満は拒否",
]
KAGIBAN_NAMES = ["たろう", "はな", "スカイ", "もち", "ぴよ", "ルナ",
                 "ケン", "ミント", "そら", "ゆき", "ハル", "ノア"]
KAGIBAN_BIOS = ["よろしくお願いします", "ゲームと音楽が好きです",
                "日常のことを書いています", "写真を撮るのが趣味です"]


def kagiban_should_approve(profile, n_rules):
    """有効な掟（先頭 n_rules 個）に1つでも触れたら拒否が正解。"""
    if n_rules >= 1 and not profile["icon"]:
        return False
    if n_rules >= 2 and int(profile["posts"]) == 0:
        return False
    if n_rules >= 3 and not profile["bio"]:
        return False
    if n_rules >= 4 and profile["link"]:
        return False
    if n_rules >= 5 and int(profile["days"]) < 3:
        return False
    return True


def kagiban_make_profile(rng):
    return {
        "name": rng.choice(KAGIBAN_NAMES) + rng.choice(["", "", "", "123", "_日記"]),
        "icon": rng.random() < 0.8,
        "posts": rng.choice([0, 0, 1, 3, 12, 40, 120]),
        "bio": rng.choice(KAGIBAN_BIOS) if rng.random() < 0.75 else "",
        "link": rng.random() < 0.2,
        "days": rng.choice([0, 1, 2, 5, 30, 200, 900]),
    }


KAGIBAN_TEMPLATE = r"""
  <h1>🔑 カギバンさばき</h1>
  <p class="howto">鍵アカウントへのフォローリクエストを、「掟」に照らして承認するか拒否するかさばいてください。5件さばくごとに掟が1つ増えます。間違えるとミスで、3回ミスか40件で終了。正しくさばけた数を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">さばいた数: {{ total }} ／ 正解: {{ done }} ／ ミス: {{ miss }} / 3 ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div class="panel" style="margin-bottom:12px;">
      <h3>📜 いまの掟</h3>
      <ul style="margin:6px 0; text-align:left;">
        {% for rule in rules %}
          <li>{{ rule }}</li>
        {% endfor %}
      </ul>
    </div>
    {% if over %}
      <p class="mid">終了！ {{ done }} 件を正しくさばきました。</p>
      <form method="post" action="{{ url_for('kagiban_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% else %}
      <div class="panel right" style="margin-bottom:12px;">
        <h3>フォローリクエスト</h3>
        <p class="mid">{{ '🖼️ アイコンあり' if profile.icon else '⬜ アイコンなし' }} ／ {{ profile.name }}</p>
        <p>投稿: {{ profile.posts }} 件 ／ 開設から {{ profile.days }} 日</p>
        <p>プロフィール文: {{ profile.bio if profile.bio else '（なし）' }}</p>
        <p>宣伝リンク: {{ 'あり' if profile.link else 'なし' }}</p>
      </div>
      <form method="post" action="{{ url_for('kagiban_answer') }}" class="row">
        <button type="submit" name="act" value="approve" style="font-size:18px;">✅ 承認</button>
        <button type="submit" name="act" value="reject" style="font-size:18px;">🚫 拒否</button>
      </form>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（正解数）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 件</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def kagiban_new_game():
    session["kb_profile"] = kagiban_make_profile(random)
    session["kb_done"] = 0
    session["kb_miss"] = 0
    session["kb_total"] = 0
    session["kb_rules"] = 1
    session["kb_over"] = False


def render_kagiban(message=None):
    if "kb_profile" not in session:
        kagiban_new_game()
    n_rules = int(session.get("kb_rules", 1))
    body = render_template_string(
        KAGIBAN_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        profile=session.get("kb_profile"),
        rules=KAGIBAN_RULES[:n_rules],
        total=int(session.get("kb_total", 0)),
        done=int(session.get("kb_done", 0)),
        miss=int(session.get("kb_miss", 0)),
        over=bool(session.get("kb_over", False)),
        best=best_score("kagiban", "max"),
        history=recent_scores("kagiban", 10),
        message=message,
    )
    return game_page("カギバンさばき", body)


@app.route("/games/kagiban", methods=["GET"])
def kagiban():
    return render_kagiban()


@app.route("/games/kagiban/answer", methods=["POST"])
def kagiban_answer():
    if "kb_profile" not in session:
        kagiban_new_game()
    if session.get("kb_over"):
        return render_kagiban()
    act = (request.form.get("act") or "").strip()
    if act not in ("approve", "reject"):
        return render_kagiban()
    profile = session.get("kb_profile")
    n_rules = int(session.get("kb_rules", 1))
    should = kagiban_should_approve(profile, n_rules)
    said_approve = act == "approve"
    if said_approve == should:
        session["kb_done"] = int(session.get("kb_done", 0)) + 1
        msg = "⭕ 正しい判断！" + ("承認が正解でした。" if should else "拒否が正解でした。")
    else:
        session["kb_miss"] = int(session.get("kb_miss", 0)) + 1
        msg = "❌ ミス… " + ("承認が正解でした。" if should else "拒否が正解でした。")
    total = int(session.get("kb_total", 0)) + 1
    session["kb_total"] = total
    new_rules = min(len(KAGIBAN_RULES), 1 + total // 5)
    if new_rules > n_rules:
        session["kb_rules"] = new_rules
        msg += f" 📜 新しい掟が増えた：「{KAGIBAN_RULES[new_rules - 1]}」"
    if int(session.get("kb_miss", 0)) >= 3 or total >= 40:
        session["kb_over"] = True
        record_score("kagiban", int(session.get("kb_done", 0)))
        return render_kagiban(message=msg + " 終了です。")
    session["kb_profile"] = kagiban_make_profile(random)
    return render_kagiban(message=msg)


@app.route("/games/kagiban/reset", methods=["POST"])
def kagiban_reset():
    kagiban_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("kagiban"))


# ============================
# 憑依まじょ推理
# 村人の発言と村の記録の矛盾から、悪魔に憑かれた者を当てる一人用推理
# （サーバー側）。全3問、正解までの誤答が少ないほど高得点（1問最大30点）。
# ============================
MAJYO_SCENARIOS = [
    {
        "title": "第1問：広場の足音",
        "intro": "ゆうべ、村の広場で奇妙な足音が聞こえた。悪魔は夜のあいだ1人に憑依し、"
                 "その間の出来事を平気で間違えて話すという。",
        "facts": [
            "見回り記録：22時に広場を通った村人は1人だけだった",
            "広場の明かりは22時には消えていた",
        ],
        "villagers": [
            {"name": "パン屋のトマ",
             "statement": "22時ごろ、広場のそばを通ったよ。誰にも会わなかったけどね",
             "possessed": False,
             "defense": "トマは首を振った。「おれは本当のことしか言ってない」たしかに記録と矛盾しない。"},
            {"name": "宿屋のミラ",
             "statement": "22時に広場で2人の人影とすれ違ったわ。明かりもついていたし",
             "possessed": True,
             "caught": "ミラの目が一瞬、赤く光った。「見回り記録では22時の広場は1人だけ、明かりも消えていた。2人とすれ違い、明かりがついていたという話は両方とも記録と食い違う！」"},
            {"name": "鍛冶屋のゴロ",
             "statement": "おれは21時には寝ちまった。何も知らん",
             "possessed": False,
             "defense": "ゴロは欠伸をした。記録と矛盾する話はしていない。"},
            {"name": "薬師のセラ",
             "statement": "夜中に目が覚めて、窓から月を見ていたわ",
             "possessed": False,
             "defense": "セラの話は記録と矛盾しない。憑依の証拠にはならない。"},
        ],
    },
    {
        "title": "第2問：井戸の光",
        "intro": "村外れの古井戸が光ったという噂が広がっている。今夜は満月だ。",
        "facts": [
            "言い伝え：古井戸の水が青く光るのは新月の夜だけ",
            "今夜は満月で、村は明るく照らされていた",
        ],
        "villagers": [
            {"name": "漁師のウミ",
             "statement": "井戸を見に行ったが、水は真っ暗だったよ",
             "possessed": False,
             "defense": "ウミの話は言い伝えと矛盾しない。"},
            {"name": "織屋のハナ",
             "statement": "夕方、井戸のそばを通ったら、水が青く光っていたの",
             "possessed": True,
             "caught": "ハナは口元を歪めた。「満月の今夜、井戸が青く光るはずがない。新月の夜だけだという言い伝えと真っ向から食い違っている！」"},
            {"name": "木こりのダイ",
             "statement": "おれは山小屋に泊まっていた。井戸なんて見てない",
             "possessed": False,
             "defense": "ダイの話に矛盾はない。"},
            {"name": "占い師のロゼ",
             "statement": "月明かりがまぶしくて、星占いどころじゃなかったわ",
             "possessed": False,
             "defense": "ロゼの話は今夜が満月だという事実と合っている。"},
        ],
    },
    {
        "title": "第3問：鏡台の秘密",
        "intro": "村長の家で奇妙な出来事があった。古い言い伝えが鍵になる。",
        "facts": [
            "言い伝え：悪魔に憑かれた者は、鏡に姿が映らない",
            "使用人の証言：夕方、鏡台の前で話していた2人のうち、1人だけ鏡に映っていなかった",
        ],
        "villagers": [
            {"name": "村長の娘リコ",
             "statement": "夕方、鏡台の前でアオと話していたわ。2人とも鏡に映って……いたと思う",
             "possessed": False,
             "defense": "リコの話は曖昧だが、使用人の証言と矛盾はしない。映っていなかったのは相手の方だ。"},
            {"name": "庭師のアオ",
             "statement": "鏡台の前でリコと話した。鏡なんて見ていないから分からない",
             "possessed": True,
             "caught": "アオの顔から血の気が引いた。「使用人は見ていた。鏡台の前で、リコは映っているのにアオだけが鏡に映っていなかった！」"},
            {"name": "料理人のボブ",
             "statement": "夕方はずっと厨房にいた。鏡台には近づいていない",
             "possessed": False,
             "defense": "ボブは鏡台の前にいなかった。使用人の証言の2人には入らない。"},
            {"name": "旅の商人ゼフ",
             "statement": "村長の家には昼に寄っただけだ。夕方は宿にいた",
             "possessed": False,
             "defense": "ゼフも鏡台の前にはいなかった。証言と矛盾しない。"},
        ],
    },
]


MAJYO_TEMPLATE = r"""
  <h1>🧙 憑依まじょ推理</h1>
  <p class="howto">悪魔は夜ごとに村人1人に憑依し、その村人は記録や言い伝えと食い違う話をします。「村の記録」と全員の発言を読み比べて、憑かれたと思う村人を名指ししてください。当てるまでの間違いが少ないほど高得点（1問最大30点）。全3問の合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">{{ scenario.title }}（{{ idx + 1 }} / {{ total }}）／ 合計: {{ points }} 点 ／ ベスト: {{ best if best is not none else '—' }}</p>
    <p>{{ scenario.intro }}</p>
    <div class="panel" style="margin-bottom:12px;">
      <h3>📖 村の記録</h3>
      <ul style="margin:6px 0; text-align:left;">
        {% for f in scenario.facts %}
          <li>{{ f }}</li>
        {% endfor %}
      </ul>
    </div>
    {% if feedback %}
      <p class="result">{{ feedback }}</p>
    {% endif %}
    {% if over %}
      <p class="mid">全ての問が終わりました。合計 {{ points }} 点です。</p>
      <form method="post" action="{{ url_for('majyo_suiri_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% elif solved %}
      <form method="post" action="{{ url_for('majyo_suiri_next') }}" class="row">
        <button type="submit">{{ '結果を見る' if last_one else '次の問へ' }}</button>
      </form>
    {% else %}
      <div style="display:grid; gap:8px;">
        {% for vi, v in villagers %}
          <form method="post" action="{{ url_for('majyo_suiri_accuse') }}">
            <input type="hidden" name="v" value="{{ vi }}" />
            <button type="submit" style="width:100%; text-align:left; font-size:15px;" {% if vi in tried %}disabled{% endif %}>
              🗣️ {{ v.name }}：「{{ v.statement }}」{% if vi in tried %}（違った）{% endif %}
            </button>
          </form>
        {% endfor %}
      </div>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def majyo_new_game():
    session["mj_idx"] = 0
    session["mj_points"] = 0
    session["mj_over"] = False
    majyo_start_scenario(0)


def majyo_start_scenario(idx):
    session["mj_idx"] = idx
    order = list(range(len(MAJYO_SCENARIOS[idx]["villagers"])))
    random.shuffle(order)
    session["mj_order"] = order
    session["mj_tried"] = []
    session["mj_solved"] = False
    session["mj_feedback"] = ""


def render_majyo(message=None):
    if "mj_idx" not in session:
        majyo_new_game()
    idx = int(session.get("mj_idx", 0))
    scenario = MAJYO_SCENARIOS[idx]
    order = session.get("mj_order", list(range(len(scenario["villagers"]))))
    villagers = [(i, scenario["villagers"][i]) for i in order]
    body = render_template_string(
        MAJYO_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        idx=idx,
        total=len(MAJYO_SCENARIOS),
        points=int(session.get("mj_points", 0)),
        over=bool(session.get("mj_over", False)),
        solved=bool(session.get("mj_solved", False)),
        last_one=idx + 1 >= len(MAJYO_SCENARIOS),
        scenario=scenario,
        villagers=villagers,
        tried=list(session.get("mj_tried", [])),
        feedback=session.get("mj_feedback", ""),
        best=best_score("majyo-suiri", "max"),
        history=recent_scores("majyo-suiri", 10),
        message=message,
    )
    return game_page("憑依まじょ推理", body)


@app.route("/games/majyo-suiri", methods=["GET"])
def majyo_suiri():
    return render_majyo()


@app.route("/games/majyo-suiri/accuse", methods=["POST"])
def majyo_suiri_accuse():
    if "mj_idx" not in session:
        majyo_new_game()
    if session.get("mj_over") or session.get("mj_solved"):
        return render_majyo()
    raw = (request.form.get("v") or "").strip()
    idx = int(session.get("mj_idx", 0))
    scenario = MAJYO_SCENARIOS[idx]
    if not raw.isdigit() or not (0 <= int(raw) < len(scenario["villagers"])):
        return render_majyo()
    vi = int(raw)
    tried = list(session.get("mj_tried", []))
    if vi in tried:
        return render_majyo()
    villager = scenario["villagers"][vi]
    if villager["possessed"]:
        gained = (30, 20, 10)[min(len(tried), 2)]
        session["mj_points"] = int(session.get("mj_points", 0)) + gained
        session["mj_solved"] = True
        session["mj_feedback"] = villager["caught"] + f"（+{gained} 点）"
        return render_majyo(message="🎉 憑依を見破った！")
    tried.append(vi)
    session["mj_tried"] = tried
    session["mj_feedback"] = villager["defense"]
    return render_majyo(message="その人ではないようだ…。")


@app.route("/games/majyo-suiri/next", methods=["POST"])
def majyo_suiri_next():
    if "mj_idx" not in session:
        majyo_new_game()
    if session.get("mj_over"):
        return render_majyo()
    if not session.get("mj_solved"):
        return render_majyo()
    idx = int(session.get("mj_idx", 0))
    if idx + 1 >= len(MAJYO_SCENARIOS):
        session["mj_over"] = True
        record_score("majyo-suiri", int(session.get("mj_points", 0)))
        return render_majyo(message="全ての憑依を見破りました！")
    majyo_start_scenario(idx + 1)
    return render_majyo()


@app.route("/games/majyo-suiri/reset", methods=["POST"])
def majyo_suiri_reset():
    majyo_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("majyo_suiri"))


# ============================
# 引き際ダンジョンすごろく
# サイコロすごろく×カードバトル（サーバー側）。期限（12回）内に集めた
# 財宝は「引き返す」で持ち帰れるが、力尽きると全ロスト。引き際の判断が核。
# ============================
HIKIGIWA_BOARD = [".", "T", ".", "B", ".", "H", "T", "B", ".", "X",
                  "T", ".", "B", ".", "H", "B", "T", ".", "X", "G"]
HIKIGIWA_SPACE_INFO = {
    ".": ("・", "空き地"),
    "T": ("💰", "財宝"),
    "B": ("👹", "バトル"),
    "H": ("🌿", "回復"),
    "X": ("🕳️", "落とし穴"),
    "G": ("🏆", "ゴール"),
}


def hikigiwa_battle_result(card, enemy):
    """(勝ちか, 得る財宝 or 受けるダメージ) を返す。"""
    card = int(card)
    enemy = int(enemy)
    if card >= enemy:
        return True, enemy * 3
    return False, enemy - card + 1


HIKIGIWA_TEMPLATE = r"""
  <h1>🎲 引き際ダンジョンすごろく</h1>
  <p class="howto">サイコロを振って20マスのダンジョンを進みます。💰財宝で金貨を集め、👹バトルは手札のカード1枚で勝負（敵の強さ以上で勝ち、金貨ゲット。負けると差分+1のダメージ）。HPが0になると集めた金貨は全ロスト。「引き返す」なら今の金貨を持ち帰って終了します。チャンスは12回まで。ゴールは金貨+30。持ち帰った金貨を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">HP: {{ hp }} ／ 金貨: {{ gold }} ／ 残り回数: {{ rolls }} ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div style="display:grid; grid-template-columns: repeat(5, 1fr); gap:4px; margin:10px 0;">
      {% for cell in board %}
        <div style="border:1px solid #ddd; border-radius:8px; padding:6px 2px; text-align:center; font-size:13px;
          background:{{ '#ffe9a8' if cell.pos == pos else '#fff' }};">
          {{ cell.icon }}<br>{{ cell.pos }}{{ ' 🚶' if cell.pos == pos else '' }}
        </div>
      {% endfor %}
    </div>
    {% if over %}
      <p class="mid">{{ result_text }}</p>
      <form method="post" action="{{ url_for('hikigiwa_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% elif battle %}
      <p class="mid">👹 敵が現れた！ 強さ {{ battle }}。使うカードを選んでください。</p>
      <form method="post" action="{{ url_for('hikigiwa_fight') }}" class="row">
        {% for ci, cv in cards %}
          <button type="submit" name="card" value="{{ ci }}" style="font-size:20px;">🃏 {{ cv }}</button>
        {% endfor %}
      </form>
    {% else %}
      <div class="row">
        <form method="post" action="{{ url_for('hikigiwa_roll') }}">
          <button type="submit" style="font-size:18px;">🎲 サイコロを振る</button>
        </form>
        <form method="post" action="{{ url_for('hikigiwa_retreat') }}">
          <button type="submit">🏃 引き返す（金貨 {{ gold }} を持ち帰る）</button>
        </form>
      </div>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（持ち帰った金貨）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 枚</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def hikigiwa_new_game():
    session["hd_pos"] = 0
    session["hd_hp"] = 10
    session["hd_gold"] = 0
    session["hd_rolls"] = 12
    session["hd_battle"] = None
    session["hd_cards"] = []
    session["hd_over"] = False
    session["hd_result"] = ""


def hikigiwa_finish(bank, text):
    gold = int(session.get("hd_gold", 0)) if bank else 0
    record_score("hikigiwa-dungeon", gold)
    session["hd_over"] = True
    session["hd_battle"] = None
    session["hd_result"] = text


def render_hikigiwa(message=None):
    if "hd_pos" not in session:
        hikigiwa_new_game()
    board = []
    for i, kind in enumerate(HIKIGIWA_BOARD):
        icon, _name = HIKIGIWA_SPACE_INFO[kind]
        board.append({"pos": i + 1, "icon": icon})
    battle = session.get("hd_battle")
    cards = list(enumerate(session.get("hd_cards", []))) if battle else []
    body = render_template_string(
        HIKIGIWA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        board=board,
        pos=int(session.get("hd_pos", 0)),
        hp=int(session.get("hd_hp", 10)),
        gold=int(session.get("hd_gold", 0)),
        rolls=int(session.get("hd_rolls", 12)),
        battle=battle,
        cards=cards,
        over=bool(session.get("hd_over", False)),
        result_text=session.get("hd_result", ""),
        best=best_score("hikigiwa-dungeon", "max"),
        history=recent_scores("hikigiwa-dungeon", 10),
        message=message,
    )
    return game_page("引き際ダンジョンすごろく", body)


@app.route("/games/hikigiwa-dungeon", methods=["GET"])
def hikigiwa_dungeon():
    return render_hikigiwa()


@app.route("/games/hikigiwa-dungeon/roll", methods=["POST"])
def hikigiwa_roll():
    if "hd_pos" not in session:
        hikigiwa_new_game()
    if session.get("hd_over") or session.get("hd_battle"):
        return render_hikigiwa()
    rolls = int(session.get("hd_rolls", 12))
    if rolls <= 0:
        return render_hikigiwa()
    rolls -= 1
    session["hd_rolls"] = rolls
    die = random.randint(1, 6)
    pos = min(20, int(session.get("hd_pos", 0)) + die)
    session["hd_pos"] = pos
    kind = HIKIGIWA_BOARD[pos - 1]
    msg = f"🎲 {die} が出た。{pos} マス目へ。"
    if kind == "T":
        gain = random.randint(5, 15)
        session["hd_gold"] = int(session.get("hd_gold", 0)) + gain
        msg += f" 💰 財宝！ 金貨 +{gain}。"
    elif kind == "H":
        session["hd_hp"] = min(10, int(session.get("hd_hp", 10)) + 3)
        msg += " 🌿 回復の泉。HP +3。"
    elif kind == "X":
        session["hd_hp"] = int(session.get("hd_hp", 10)) - 2
        msg += " 🕳️ 落とし穴！ HP -2。"
    elif kind == "B":
        session["hd_battle"] = random.randint(3, 9)
        session["hd_cards"] = [random.randint(1, 10) for _ in range(3)]
        return render_hikigiwa(message=msg + " 👹 バトルだ！")
    elif kind == "G":
        session["hd_gold"] = int(session.get("hd_gold", 0)) + 30
        hikigiwa_finish(True, f"🏆 ゴール！ 金貨 {session.get('hd_gold', 0)} 枚を持ち帰りました。")
        return render_hikigiwa(message=msg + " ゴール！")
    if int(session.get("hd_hp", 10)) <= 0:
        hikigiwa_finish(False, "💀 力尽きた… 集めた金貨は全て失われた。")
        return render_hikigiwa(message=msg + " 力尽きた…")
    if rolls <= 0:
        hikigiwa_finish(True, f"⏰ 期限切れ。金貨 {session.get('hd_gold', 0)} 枚を持ち帰りました。")
        return render_hikigiwa(message=msg + " 期限切れです。")
    return render_hikigiwa(message=msg)


@app.route("/games/hikigiwa-dungeon/fight", methods=["POST"])
def hikigiwa_fight():
    if "hd_pos" not in session:
        hikigiwa_new_game()
    enemy = session.get("hd_battle")
    if session.get("hd_over") or not enemy:
        return render_hikigiwa()
    raw = (request.form.get("card") or "").strip()
    cards = list(session.get("hd_cards", []))
    if not raw.isdigit() or not (0 <= int(raw) < len(cards)):
        return render_hikigiwa()
    card = int(cards[int(raw)])
    win, amount = hikigiwa_battle_result(card, int(enemy))
    session["hd_battle"] = None
    session["hd_cards"] = []
    if win:
        session["hd_gold"] = int(session.get("hd_gold", 0)) + amount
        msg = f"🃏 {card} で勝利！ 金貨 +{amount}。"
    else:
        session["hd_hp"] = int(session.get("hd_hp", 10)) - amount
        msg = f"🃏 {card} では勝てなかった… HP -{amount}。"
    if int(session.get("hd_hp", 10)) <= 0:
        hikigiwa_finish(False, "💀 力尽きた… 集めた金貨は全て失われた。")
        return render_hikigiwa(message=msg + " 力尽きた…")
    if int(session.get("hd_rolls", 0)) <= 0:
        hikigiwa_finish(True, f"⏰ 期限切れ。金貨 {session.get('hd_gold', 0)} 枚を持ち帰りました。")
        return render_hikigiwa(message=msg + " 期限切れです。")
    return render_hikigiwa(message=msg)


@app.route("/games/hikigiwa-dungeon/retreat", methods=["POST"])
def hikigiwa_retreat():
    if "hd_pos" not in session:
        hikigiwa_new_game()
    if session.get("hd_over") or session.get("hd_battle"):
        return render_hikigiwa()
    gold = int(session.get("hd_gold", 0))
    hikigiwa_finish(True, f"🏃 引き返した。金貨 {gold} 枚を持ち帰りました。")
    return render_hikigiwa(message="引き際を守りました。")


@app.route("/games/hikigiwa-dungeon/reset", methods=["POST"])
def hikigiwa_reset():
    hikigiwa_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("hikigiwa_dungeon"))


# ============================
# ドラフト目利き
# スカウト3人の報告（精度に差のある評価値）から架空選手の本当の力を読み、
# 指名する目利きゲーム（サーバー側）。全5巡の指名選手の活躍度の合計を記録。
# ============================
DRAFT_SCOUTS = [("ベテランスカウト", 8), ("若手スカウト", 20), ("ファンスカウト", 35)]
DRAFT_SURNAMES = ["佐々木", "高橋", "森田", "岡田", "西村", "藤原", "中島", "久保"]
DRAFT_GIVEN = ["翔", "蓮", "颯太", "大和", "陸", "健太", "悠真", "直樹"]
DRAFT_POSITIONS = ["投手", "捕手", "内野手", "外野手"]


def draft_make_candidates(rng):
    names = rng.sample(DRAFT_SURNAMES, 3)
    givens = rng.sample(DRAFT_GIVEN, 3)
    candidates = []
    for i in range(3):
        actual = rng.randint(25, 98)
        reports = []
        for _scout, noise in DRAFT_SCOUTS:
            rep = actual + rng.randint(-noise, noise)
            reports.append(max(1, min(99, rep)))
        sub = max(1, min(99, actual + rng.randint(-15, 15)))
        candidates.append({
            "name": names[i] + " " + givens[i],
            "pos": DRAFT_POSITIONS[rng.randrange(len(DRAFT_POSITIONS))],
            "actual": actual,
            "reports": reports,
            "sub": sub,
        })
    return candidates


DRAFT_TEMPLATE = r"""
  <h1>📋 ドラフト目利き</h1>
  <p class="howto">3人の候補から1人を指名します。各候補には3人のスカウトの評価（100点満点）が付いていますが、精度は人それぞれ：ベテランは誤差が小さく、若手は中くらい、ファンは大きく外します。育成成績も目安に、本当に活躍しそうな選手を読み取ってください。全5巡、指名した選手の「実際の活躍度」の合計を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    {% if reveal %}
      <p class="result">📣 {{ reveal.name }} の実際の活躍度は {{ reveal.actual }} でした{{ '🎉' if reveal.actual >= 80 else '' }}</p>
    {% endif %}
    <p class="result">{{ round_no }} 巡目 / 5 ／ 合計活躍度: {{ total }} ／ ベスト: {{ best if best is not none else '—' }}</p>
    {% if over %}
      <p class="mid">ドラフト終了！ 指名した5人の活躍度合計は {{ total }} でした。</p>
      <form method="post" action="{{ url_for('draft_reset') }}" class="row">
        <button type="submit">もう一度挑戦</button>
      </form>
    {% else %}
      <div style="display:grid; gap:10px;">
        {% for ci, cand in candidates %}
          <form method="post" action="{{ url_for('draft_pick') }}">
            <input type="hidden" name="c" value="{{ ci }}" />
            <button type="submit" style="width:100%; text-align:left; font-size:15px;">
              <strong>{{ cand.name }}</strong>（{{ cand.pos }}）<br>
              ベテラン評価 {{ cand.reports[0] }} ／ 若手評価 {{ cand.reports[1] }} ／ ファン評価 {{ cand.reports[2] }}<br>
              育成成績 {{ cand.sub }}
            </button>
          </form>
        {% endfor %}
      </div>
    {% endif %}
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（活躍度合計）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def draft_new_game():
    session["dm_round"] = 1
    session["dm_candidates"] = draft_make_candidates(random)
    session["dm_total"] = 0
    session["dm_over"] = False
    session["dm_reveal"] = None


def render_draft(message=None):
    if "dm_round" not in session:
        draft_new_game()
    candidates = session.get("dm_candidates", [])
    body = render_template_string(
        DRAFT_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        candidates=list(enumerate(candidates)),
        round_no=int(session.get("dm_round", 1)),
        total=int(session.get("dm_total", 0)),
        over=bool(session.get("dm_over", False)),
        reveal=session.get("dm_reveal"),
        best=best_score("draft-meate", "max"),
        history=recent_scores("draft-meate", 10),
        message=message,
    )
    return game_page("ドラフト目利き", body)


@app.route("/games/draft-meate", methods=["GET"])
def draft_meate():
    return render_draft()


@app.route("/games/draft-meate/pick", methods=["POST"])
def draft_pick():
    if "dm_round" not in session:
        draft_new_game()
    if session.get("dm_over"):
        return render_draft()
    raw = (request.form.get("c") or "").strip()
    candidates = session.get("dm_candidates", [])
    if not raw.isdigit() or not (0 <= int(raw) < len(candidates)):
        return render_draft()
    picked = candidates[int(raw)]
    total = int(session.get("dm_total", 0)) + int(picked["actual"])
    session["dm_total"] = total
    session["dm_reveal"] = {"name": picked["name"], "actual": int(picked["actual"])}
    round_no = int(session.get("dm_round", 1))
    if round_no >= 5:
        session["dm_over"] = True
        record_score("draft-meate", total)
        return render_draft(message="全ての指名が終わりました。")
    session["dm_round"] = round_no + 1
    session["dm_candidates"] = draft_make_candidates(random)
    return render_draft()


@app.route("/games/draft-meate/reset", methods=["POST"])
def draft_reset():
    draft_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("draft_meate"))


# ============================
# 回してはめこみカラー探し
# 色と形がぴったり合う場所を探し、ピースを回転させてはめ込むパズル
# （サーバー側）。置けるのは「色の付いたマスと色・形が完全一致する置き方」
# だけ。全2ステージ、解けることを検証済みの構成。
# ============================
HAMEKOMI_COLORS = {1: "#e74c3c", 2: "#3498db", 3: "#2ecc71"}
HAMEKOMI_COLOR_NAMES = {1: "赤", 2: "青", 3: "緑"}
HAMEKOMI_STAGES = [
    {"size": 5, "pieces": [
        {"name": "L字ピース", "cells": [[0, 0, 1], [0, 1, 1], [1, 0, 2]],
         "anchor": [0, 0], "init_rot": 1},
        {"name": "たて棒ピース", "cells": [[0, 0, 3], [1, 0, 3], [2, 0, 2]],
         "anchor": [0, 3], "init_rot": 2},
        {"name": "しかくピース", "cells": [[0, 0, 1], [0, 1, 3], [1, 0, 3], [1, 1, 1]],
         "anchor": [2, 1], "init_rot": 1},
    ]},
    {"size": 6, "pieces": [
        {"name": "T字ピース", "cells": [[0, 0, 2], [0, 1, 1], [0, 2, 2], [1, 1, 3]],
         "anchor": [0, 1], "init_rot": 3},
        {"name": "よこ棒ピース", "cells": [[0, 0, 3], [0, 1, 3], [0, 2, 1], [0, 3, 1]],
         "anchor": [2, 0], "init_rot": 1},
        {"name": "L字ロング", "cells": [[0, 0, 1], [1, 0, 1], [2, 0, 2], [2, 1, 2]],
         "anchor": [3, 4], "init_rot": 2},
        {"name": "しかくピース", "cells": [[0, 0, 3], [0, 1, 2], [1, 0, 2], [1, 1, 3]],
         "anchor": [4, 1], "init_rot": 1},
    ]},
]


def hamekomi_rotate(cells, times=1):
    """セル [(r, c, color), ...] を90度時計回りに times 回回転し、
    左上が (0, 0) になるよう正規化して返す。"""
    out = [tuple(c) for c in cells]
    for _ in range(times % 4):
        out = [(c, -r, col) for (r, c, col) in out]
        minr = min(r for r, _c, _col in out)
        minc = min(c for _r, c, _col in out)
        out = [(r - minr, c - minc, col) for (r, c, col) in out]
    return out


def hamekomi_targets(stage):
    """ステージの目標配置 {(r, c): color} を返す（ピースの正解配置から作る）。"""
    targets = {}
    for piece in stage["pieces"]:
        ar, ac = piece["anchor"]
        for (r, c, col) in piece["cells"]:
            targets[(ar + r, ac + c)] = col
    return targets


def hamekomi_can_place(targets, occupied, cells, ar, ac):
    """cells（回転済み）を (ar, ac) に置けるか。全セルが目標マスと色一致し、
    既に埋まっていないことが条件。"""
    for (r, c, col) in cells:
        pos = (ar + r, ac + c)
        if targets.get(pos) != col:
            return False
        if pos in occupied:
            return False
    return True


HAMEKOMI_TEMPLATE = r"""
  <h1>🧩 回してはめこみカラー探し</h1>
  <p class="howto">色の付いたマス（目標）に、ピースをぴったりはめ込むパズル。今のピースの形を見て、「回転」で向きを変え、置きたい左上のマスを押してください。置けるのは色と形が完全一致する置き方だけです。全部の目標マスが埋まればクリア。得点は1ステージ最大100点で、手数が増えるほど下がります。全2ステージの合計点を記録します。</p>
  __FLASH__
  <div class="card">
    {% if message %}
      <p class="result">{{ message }}</p>
    {% endif %}
    <p class="result">ステージ {{ stage_no }} / {{ stage_total }} ／ 合計: {{ points }} 点 ／ ベスト: {{ best if best is not none else '—' }}</p>
    <div style="display:flex; gap:18px; flex-wrap:wrap; justify-content:center;">
      <form method="post" action="{{ url_for('hamekomi_put') }}">
        <div style="display:grid; grid-template-columns: repeat({{ size }}, 40px); gap:3px;">
          {% for r in range(size) %}
            {% for c in range(size) %}
              {% set cell = grid[r][c] %}
              {% if cell.placed %}
                <button type="button" disabled style="height:40px; padding:0; background:{{ cell.color }}; border-color:#999;"></button>
              {% elif cell.target %}
                <button type="submit" name="cell" value="{{ r }}-{{ c }}" {% if cleared or over %}disabled{% endif %}
                  style="height:40px; padding:0; background:{{ cell.color }}; opacity:.38;"></button>
              {% else %}
                <button type="submit" name="cell" value="{{ r }}-{{ c }}" {% if cleared or over %}disabled{% endif %}
                  style="height:40px; padding:0; background:#fff;"></button>
              {% endif %}
            {% endfor %}
          {% endfor %}
        </div>
      </form>
      <div style="min-width:160px;">
        {% if over %}
          <p class="mid">全ステージ終了。合計 {{ points }} 点です。</p>
          <form method="post" action="{{ url_for('hamekomi_reset') }}"><button type="submit">もう一度挑戦</button></form>
        {% elif cleared %}
          <form method="post" action="{{ url_for('hamekomi_next') }}"><button type="submit">{{ '結果を見る' if last_stage else '次のステージへ' }}</button></form>
        {% elif piece %}
          <p class="mid">今のピース：<strong>{{ piece.name }}</strong></p>
          <div style="display:grid; grid-template-columns: repeat(4, 22px); gap:2px; margin-bottom:10px;">
            {% for r in range(4) %}
              {% for c in range(4) %}
                {% if (r, c) in piece_map %}
                  <span style="display:block; height:22px; border-radius:3px; background:{{ piece_map[(r, c)] }};"></span>
                {% else %}
                  <span style="display:block; height:22px;"></span>
                {% endif %}
              {% endfor %}
            {% endfor %}
          </div>
          <form method="post" action="{{ url_for('hamekomi_rotate_route') }}" style="margin-bottom:8px;">
            <button type="submit">🔄 回転する</button>
          </form>
          <form method="post" action="{{ url_for('hamekomi_undo') }}">
            <button type="submit">↩ 一つ戻す</button>
          </form>
        {% endif %}
      </div>
    </div>
    <form method="post" action="{{ url_for('hamekomi_reset') }}" class="row" style="margin-top:12px;">
      <button type="submit">最初からやり直す</button>
    </form>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（合計点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
"""


def hamekomi_load_stage(idx):
    session["ch_stage"] = idx
    session["ch_placed"] = []
    session["ch_rot"] = int(HAMEKOMI_STAGES[idx]["pieces"][0]["init_rot"])
    session["ch_stage_moves"] = 0
    session["ch_cleared"] = False


def hamekomi_new_game():
    session["ch_points"] = 0
    session["ch_over"] = False
    hamekomi_load_stage(0)


def hamekomi_occupied():
    idx = int(session.get("ch_stage", 0))
    stage = HAMEKOMI_STAGES[idx]
    occupied = {}
    for placement in session.get("ch_placed", []):
        piece = stage["pieces"][int(placement["piece"])]
        cells = hamekomi_rotate(piece["cells"], int(placement["rot"]))
        ar, ac = int(placement["r"]), int(placement["c"])
        for (r, c, col) in cells:
            occupied[(ar + r, ac + c)] = col
    return occupied


def render_hamekomi(message=None):
    if "ch_stage" not in session:
        hamekomi_new_game()
    idx = int(session.get("ch_stage", 0))
    stage = HAMEKOMI_STAGES[idx]
    targets = hamekomi_targets(stage)
    occupied = hamekomi_occupied()
    size = int(stage["size"])
    grid = []
    for r in range(size):
        row = []
        for c in range(size):
            pos = (r, c)
            if pos in occupied:
                row.append({"placed": True, "target": True,
                            "color": HAMEKOMI_COLORS[occupied[pos]]})
            elif pos in targets:
                row.append({"placed": False, "target": True,
                            "color": HAMEKOMI_COLORS[targets[pos]]})
            else:
                row.append({"placed": False, "target": False, "color": "#fff"})
        grid.append(row)
    placed_count = len(session.get("ch_placed", []))
    piece = None
    piece_map = {}
    if placed_count < len(stage["pieces"]):
        p = stage["pieces"][placed_count]
        cells = hamekomi_rotate(p["cells"], int(session.get("ch_rot", 0)))
        piece = {"name": p["name"]}
        piece_map = {(r, c): HAMEKOMI_COLORS[col] for (r, c, col) in cells}
    body = render_template_string(
        HAMEKOMI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        grid=grid,
        size=size,
        piece=piece,
        piece_map=piece_map,
        stage_no=idx + 1,
        stage_total=len(HAMEKOMI_STAGES),
        points=int(session.get("ch_points", 0)),
        cleared=bool(session.get("ch_cleared", False)),
        over=bool(session.get("ch_over", False)),
        last_stage=idx + 1 >= len(HAMEKOMI_STAGES),
        best=best_score("color-hamekomi", "max"),
        history=recent_scores("color-hamekomi", 10),
        message=message,
    )
    return game_page("回してはめこみカラー探し", body)


@app.route("/games/color-hamekomi", methods=["GET"])
def color_hamekomi():
    return render_hamekomi()


@app.route("/games/color-hamekomi/put", methods=["POST"])
def hamekomi_put():
    if "ch_stage" not in session:
        hamekomi_new_game()
    if session.get("ch_over") or session.get("ch_cleared"):
        return render_hamekomi()
    idx = int(session.get("ch_stage", 0))
    stage = HAMEKOMI_STAGES[idx]
    placed = list(session.get("ch_placed", []))
    if len(placed) >= len(stage["pieces"]):
        return render_hamekomi()
    raw = (request.form.get("cell") or "").strip()
    parts = raw.split("-")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return render_hamekomi()
    ar, ac = int(parts[0]), int(parts[1])
    piece = stage["pieces"][len(placed)]
    rot = int(session.get("ch_rot", 0))
    cells = hamekomi_rotate(piece["cells"], rot)
    targets = hamekomi_targets(stage)
    occupied = hamekomi_occupied()
    session["ch_stage_moves"] = int(session.get("ch_stage_moves", 0)) + 1
    if not hamekomi_can_place(targets, occupied, cells, ar, ac):
        return render_hamekomi(message="そこにははまりません。色と形が合う場所を探してください。")
    placed.append({"piece": len(placed), "r": ar, "c": ac, "rot": rot})
    session["ch_placed"] = placed
    if len(placed) < len(stage["pieces"]):
        session["ch_rot"] = int(stage["pieces"][len(placed)]["init_rot"])
    occupied = hamekomi_occupied()
    if set(occupied) == set(targets):
        gained = max(30, 100 - 3 * int(session.get("ch_stage_moves", 0)))
        session["ch_points"] = int(session.get("ch_points", 0)) + gained
        session["ch_cleared"] = True
        return render_hamekomi(message=f"🎉 ステージクリア！ +{gained} 点")
    return render_hamekomi()


@app.route("/games/color-hamekomi/rotate", methods=["POST"])
def hamekomi_rotate_route():
    if "ch_stage" not in session:
        hamekomi_new_game()
    if session.get("ch_over") or session.get("ch_cleared"):
        return render_hamekomi()
    session["ch_rot"] = (int(session.get("ch_rot", 0)) + 1) % 4
    session["ch_stage_moves"] = int(session.get("ch_stage_moves", 0)) + 1
    return render_hamekomi()


@app.route("/games/color-hamekomi/undo", methods=["POST"])
def hamekomi_undo():
    if "ch_stage" not in session:
        hamekomi_new_game()
    if session.get("ch_over") or session.get("ch_cleared"):
        return render_hamekomi()
    placed = list(session.get("ch_placed", []))
    if not placed:
        return render_hamekomi()
    placed.pop()
    session["ch_placed"] = placed
    idx = int(session.get("ch_stage", 0))
    stage = HAMEKOMI_STAGES[idx]
    session["ch_rot"] = int(stage["pieces"][len(placed)]["init_rot"])
    session["ch_stage_moves"] = int(session.get("ch_stage_moves", 0)) + 1
    return render_hamekomi(message="一つ戻しました。")


@app.route("/games/color-hamekomi/next", methods=["POST"])
def hamekomi_next():
    if "ch_stage" not in session:
        hamekomi_new_game()
    if session.get("ch_over"):
        return render_hamekomi()
    if not session.get("ch_cleared"):
        return render_hamekomi()
    idx = int(session.get("ch_stage", 0))
    if idx + 1 >= len(HAMEKOMI_STAGES):
        session["ch_over"] = True
        record_score("color-hamekomi", int(session.get("ch_points", 0)))
        return render_hamekomi(message="全ステージ終了しました！")
    hamekomi_load_stage(idx + 1)
    return render_hamekomi()


@app.route("/games/color-hamekomi/reset", methods=["POST"])
def hamekomi_reset():
    hamekomi_new_game()
    flash("最初から挑戦します。", "ok")
    return redirect(url_for("color_hamekomi"))


# ============================
# ウシおどかしトマト
# 猫を操作してウシに近づくと、ウシが驚いて逃げ、通り道のトマトを食べる
# （クライアント JS）。追いかけてくる人に捕まると5秒減。60秒で何個
# 食べさせられるかを記録する。
# ============================
USHITOMATO_TEMPLATE = r"""
  <h1>🐄 ウシおどかしトマト</h1>
  <p class="howto">猫 🐱 を矢印ボタン（またはキー）で動かします。ウシ 🐄 のとなりに近づくと、ウシが驚いて反対方向へ逃げ、通り道のトマト 🍅 を全部食べます（1個10点）。人 🏃 は猫を追いかけてきて、捕まると5秒減って猫と人はスタート位置に戻ります。60秒で食べさせた分が得点です。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト: {{ best if best is not none else '—' }}</p>
    <p class="mid">得点: <span id="points">0</span> ／ トマト: <span id="eaten">0</span> 個 ／ 残り: <span id="time">60</span> 秒</p>
    <div id="field" style="display:grid; grid-template-columns: repeat(10, 38px); gap:2px; justify-content:center; margin:10px 0;"></div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div style="display:grid; grid-template-columns: repeat(3, 56px); gap:6px; justify-content:center; margin-bottom:8px;">
      <span></span>
      <button type="button" data-dir="0,-1">⬆</button>
      <span></span>
      <button type="button" data-dir="-1,0">⬅</button>
      <button type="button" data-dir="0,1">⬇</button>
      <button type="button" data-dir="1,0">➡</button>
    </div>
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
  var W = 10, H = 8;
  var field = document.getElementById("field");
  var message = document.getElementById("message");
  var pointsEl = document.getElementById("points");
  var eatenEl = document.getElementById("eaten");
  var timeEl = document.getElementById("time");
  var startBtn = document.getElementById("startBtn");
  var cells = [];
  for (var i = 0; i < W * H; i++) {
    var d = document.createElement("div");
    d.style.cssText = "width:38px; height:38px; line-height:38px; text-align:center; font-size:22px; background:#f4f9f0; border:1px solid #e2ead9; border-radius:6px;";
    field.appendChild(d);
    cells.push(d);
  }
  var playing = false, tickId = null;
  var cat, cow, human, tomatoes, eaten, points, ticksLeft;
  function key(x, y){ return x + "," + y; }
  function emptyCell(){
    while (true) {
      var x = Math.floor(Math.random() * W), y = Math.floor(Math.random() * H);
      var k = key(x, y);
      if (!tomatoes.has(k) && !(cat.x === x && cat.y === y)
          && !(cow.x === x && cow.y === y) && !(human.x === x && human.y === y)) {
        return k;
      }
    }
  }
  function render(){
    for (var y = 0; y < H; y++) {
      for (var x = 0; x < W; x++) {
        var cell = cells[y * W + x];
        var t = "";
        if (tomatoes.has(key(x, y))) { t = "🍅"; }
        if (cow.x === x && cow.y === y) { t = "🐄"; }
        if (human.x === x && human.y === y) { t = "🏃"; }
        if (cat.x === x && cat.y === y) { t = "🐱"; }
        cell.textContent = t;
      }
    }
    pointsEl.textContent = String(points);
    eatenEl.textContent = String(eaten);
    timeEl.textContent = String(Math.max(0, Math.ceil(ticksLeft / 2)));
  }
  function scareCow(){
    var dx = Math.sign(cow.x - cat.x), dy = Math.sign(cow.y - cat.y);
    if (dx === 0 && dy === 0) { dx = 1; }
    for (var step = 0; step < 3; step++) {
      var nx = cow.x + dx, ny = cow.y + dy;
      if (nx < 0 || nx >= W) { dx = 0; nx = cow.x; }
      if (ny < 0 || ny >= H) { dy = 0; ny = cow.y; }
      if (nx === cow.x && ny === cow.y) { break; }
      if (nx === cat.x && ny === cat.y) { break; }
      cow.x = nx; cow.y = ny;
      var k = key(nx, ny);
      if (tomatoes.has(k)) {
        tomatoes.delete(k);
        eaten++;
        points += 10;
        tomatoes.add(emptyCell());
      }
    }
    message.textContent = "ウシが驚いて逃げた！";
  }
  function moveCat(dx, dy){
    if (!playing) { return; }
    var nx = cat.x + dx, ny = cat.y + dy;
    if (nx < 0 || nx >= W || ny < 0 || ny >= H) { return; }
    if (nx === cow.x && ny === cow.y) { return; }
    cat.x = nx; cat.y = ny;
    if (Math.abs(cat.x - cow.x) + Math.abs(cat.y - cow.y) === 1) { scareCow(); }
    render();
  }
  function tick(){
    if (!playing) { return; }
    ticksLeft--;
    // 人は猫へ1歩近づく
    var dx = Math.sign(cat.x - human.x), dy = Math.sign(cat.y - human.y);
    if (Math.abs(cat.x - human.x) >= Math.abs(cat.y - human.y)) {
      if (dx !== 0) { human.x += dx; } else { human.y += dy; }
    } else {
      if (dy !== 0) { human.y += dy; } else { human.x += dx; }
    }
    if (human.x === cow.x && human.y === cow.y) { human.x = 9; human.y = 0; }
    // ウシはときどき気ままに歩く
    if (Math.random() < 0.3) {
      var dirs = [[1,0],[-1,0],[0,1],[0,-1]];
      var d = dirs[Math.floor(Math.random() * 4)];
      var nx = cow.x + d[0], ny = cow.y + d[1];
      if (nx >= 0 && nx < W && ny >= 0 && ny < H
          && !(nx === cat.x && ny === cat.y) && !(nx === human.x && ny === human.y)) {
        cow.x = nx; cow.y = ny;
      }
    }
    if (human.x === cat.x && human.y === cat.y) {
      ticksLeft = Math.max(0, ticksLeft - 10);
      message.textContent = "捕まった！ 5秒減って振り出しへ…";
      cat = {x: 0, y: 7};
      human = {x: 9, y: 0};
    }
    if (ticksLeft <= 0) { finish(); return; }
    render();
  }
  function finish(){
    playing = false;
    clearInterval(tickId);
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(points));
    fetch("{{ url_for('ushi_tomato_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ トマト " + eaten + " 個で " + points + " 点でした";
          document.getElementById("bestline").textContent = "ベスト: " + d.best;
        }
      })
      .catch(function(){});
    render();
  }
  document.querySelectorAll("[data-dir]").forEach(function(b){
    b.addEventListener("click", function(){
      var p = b.getAttribute("data-dir").split(",");
      moveCat(parseInt(p[0], 10), parseInt(p[1], 10));
    });
  });
  document.addEventListener("keydown", function(e){
    var map = {ArrowUp: [0,-1], ArrowDown: [0,1], ArrowLeft: [-1,0], ArrowRight: [1,0],
               w: [0,-1], s: [0,1], a: [-1,0], d: [1,0]};
    if (map[e.key]) { moveCat(map[e.key][0], map[e.key][1]); e.preventDefault(); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    cat = {x: 0, y: 7};
    cow = {x: 5, y: 3};
    human = {x: 9, y: 0};
    tomatoes = new Set();
    eaten = 0; points = 0; ticksLeft = 120;
    for (var i = 0; i < 6; i++) { tomatoes.add(emptyCell()); }
    message.textContent = "ウシのとなりに近づいて驚かそう！";
    startBtn.disabled = true;
    render();
    tickId = setInterval(tick, 500);
  });
  cat = {x: 0, y: 7}; cow = {x: 5, y: 3}; human = {x: 9, y: 0};
  tomatoes = new Set(); eaten = 0; points = 0; ticksLeft = 120;
  render();
})();
</script>
"""


@app.route("/games/ushi-tomato", methods=["GET"])
def ushi_tomato():
    body = render_template_string(
        USHITOMATO_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("ushi-tomato", "max"),
        history=recent_scores("ushi-tomato", 10),
    )
    return game_page("ウシおどかしトマト", body)


@app.route("/games/ushi-tomato/score", methods=["POST"])
def ushi_tomato_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("ushi-tomato", int(raw))
    return {"ok": True, "best": best_score("ushi-tomato", "max")}


# ============================
# おやつカバ60秒
# 流れてくるおやつをタップしてバスケットへ。あふれる前に「保存」で得点化。
# 保存が続くとカバが満腹で鈍くなるので「お茶」でリフレッシュ（クライアント JS）。
# ============================
OYATSUKABA_TEMPLATE = r"""
  <h1>🦛 おやつカバ60秒</h1>
  <p class="howto">流れてくるおやつをタップしてバスケットへ集めます（8個まで）。いっぱいのままタップするとあふれてバスケットが空に…。あふれる前に「保存する」で得点化（1個10点）。保存を3回するとカバが満腹で鈍くなり（おやつが早く消える）、「お茶を飲む」でリフレッシュ。60秒の得点を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト: {{ best if best is not none else '—' }}</p>
    <p class="mid">得点: <span id="points">0</span> ／ バスケット: <span id="basket">0</span> / 8 ／ 満腹度: <span id="full">0</span> / 3 ／ 残り: <span id="time">60</span> 秒</p>
    <div id="area" style="position:relative; height:300px; border:1px solid #ddd; border-radius:12px; background:#fff8ee; overflow:hidden; margin:10px 0;"></div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="bankBtn" disabled>🧺 保存する</button>
      <button type="button" id="teaBtn" disabled>🍵 お茶を飲む</button>
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
  var pointsEl = document.getElementById("points");
  var basketEl = document.getElementById("basket");
  var fullEl = document.getElementById("full");
  var timeEl = document.getElementById("time");
  var bankBtn = document.getElementById("bankBtn");
  var teaBtn = document.getElementById("teaBtn");
  var startBtn = document.getElementById("startBtn");
  var SNACKS = ["🍩", "🍮", "🍪", "🍓", "🍰", "🧁"];
  var playing = false, points = 0, basket = 0, fullness = 0;
  var timeLeft = 60, spawnTimer = null, clockTimer = null;
  function sluggish(){ return fullness >= 3; }
  function show(){
    pointsEl.textContent = String(points);
    basketEl.textContent = String(basket);
    fullEl.textContent = String(Math.min(3, fullness));
    timeEl.textContent = String(Math.max(0, timeLeft));
  }
  function spawn(){
    if (!playing) { return; }
    var el = document.createElement("div");
    el.textContent = SNACKS[Math.floor(Math.random() * SNACKS.length)];
    el.style.cssText = "position:absolute; font-size:30px; cursor:pointer; user-select:none;";
    el.style.left = (5 + Math.random() * 85) + "%";
    el.style.top = (8 + Math.random() * 240) + "px";
    var life = sluggish() ? 3000 : 4500;
    var killer = setTimeout(function(){ el.remove(); }, life);
    el.addEventListener("click", function(){
      clearTimeout(killer);
      el.remove();
      if (basket >= 8) {
        basket = 0;
        message.textContent = "あふれた！ バスケットが空になっちゃった…";
      } else {
        basket++;
        message.textContent = "バスケットに入れた（" + basket + " / 8）";
      }
      show();
    });
    area.appendChild(el);
    spawnTimer = setTimeout(spawn, sluggish() ? 1500 : 900);
  }
  function finish(){
    playing = false;
    clearTimeout(spawnTimer);
    clearInterval(clockTimer);
    points += basket * 5;
    basket = 0;
    bankBtn.disabled = true;
    teaBtn.disabled = true;
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var form = new FormData();
    form.append("score", String(points));
    fetch("{{ url_for('oyatsu_kaba_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + points + " 点でした（残りバスケット分も加点済み）";
          document.getElementById("bestline").textContent = "ベスト: " + d.best;
        }
      })
      .catch(function(){});
    show();
  }
  bankBtn.addEventListener("click", function(){
    if (!playing || basket === 0) { return; }
    points += basket * 10;
    message.textContent = "保存した！ +" + (basket * 10) + " 点";
    basket = 0;
    fullness++;
    if (sluggish()) { message.textContent += " カバが満腹で鈍くなってきた…お茶でリフレッシュ！"; }
    show();
  });
  teaBtn.addEventListener("click", function(){
    if (!playing) { return; }
    fullness = 0;
    message.textContent = "🍵 お茶でリフレッシュ！";
    show();
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    points = 0; basket = 0; fullness = 0; timeLeft = 60;
    area.innerHTML = "";
    message.textContent = "おやつをタップして集めよう！";
    bankBtn.disabled = false;
    teaBtn.disabled = false;
    startBtn.disabled = true;
    show();
    spawn();
    clockTimer = setInterval(function(){
      timeLeft--;
      show();
      if (timeLeft <= 0) { finish(); }
    }, 1000);
  });
  show();
})();
</script>
"""


@app.route("/games/oyatsu-kaba", methods=["GET"])
def oyatsu_kaba():
    body = render_template_string(
        OYATSUKABA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("oyatsu-kaba", "max"),
        history=recent_scores("oyatsu-kaba", 10),
    )
    return game_page("おやつカバ60秒", body)


@app.route("/games/oyatsu-kaba/score", methods=["POST"])
def oyatsu_kaba_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 9999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("oyatsu-kaba", int(raw))
    return {"ok": True, "best": best_score("oyatsu-kaba", "max")}


# ============================
# スワイプ加速ウシ
# ボタンを押す（スワイプする）たびに牛が加速していくジョーク系スコア
# ゲーム（クライアント JS）。30秒で進んだ距離を記録する。
# ============================
SWIPEUSHI_TEMPLATE = r"""
  <h1>🐮 スワイプ加速ウシ</h1>
  <p class="howto">「加速」ボタンを連打（またはスペースキー）するたびに牛が速くなります。押すのをやめるとだんだん減速。30秒でどこまで進めるか。牧場を飛び出し、町を抜け、空へ、宇宙へ…？ 進んだ距離（メートル）を記録します。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト: {{ best if best is not none else '—' }}</p>
    <div id="scene" style="text-align:center; font-size:64px; margin:8px 0;">🐄</div>
    <p class="mid">速度: <span id="speed">0</span> km/h ／ 距離: <span id="dist">0</span> m ／ 残り: <span id="time">30</span> 秒</p>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="boostBtn" disabled style="font-size:20px;">💨 加速！</button>
      <button type="button" id="startBtn">スタート</button>
    </div>
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
  var scene = document.getElementById("scene");
  var message = document.getElementById("message");
  var speedEl = document.getElementById("speed");
  var distEl = document.getElementById("dist");
  var timeEl = document.getElementById("time");
  var boostBtn = document.getElementById("boostBtn");
  var startBtn = document.getElementById("startBtn");
  var playing = false, vel = 0, dist = 0, timeLeft = 30, tickId = null;
  function show(){
    speedEl.textContent = String(Math.round(vel * 5.76));
    distEl.textContent = String(Math.floor(dist));
    timeEl.textContent = String(Math.max(0, Math.ceil(timeLeft)));
    if (dist < 300) { scene.textContent = "🐄"; }
    else if (dist < 1200) { scene.textContent = "🐄💨"; }
    else if (dist < 3000) { scene.textContent = "☁️🐄☁️"; }
    else { scene.textContent = "🚀🐄🌟"; }
  }
  function boost(){
    if (!playing) { return; }
    vel = Math.min(80, vel + 1.5);
    show();
  }
  function tick(){
    if (!playing) { return; }
    dist += vel * 0.2;
    vel *= 0.93;
    timeLeft -= 0.1;
    if (vel >= 75) { message.textContent = "光速に近づいている！？"; }
    else if (dist >= 3000) { message.textContent = "宇宙に到達！"; }
    else if (dist >= 1200) { message.textContent = "空を飛んでいる！"; }
    else if (dist >= 300) { message.textContent = "牧場を飛び出した！"; }
    if (timeLeft <= 0) { finish(); return; }
    show();
  }
  function finish(){
    playing = false;
    clearInterval(tickId);
    boostBtn.disabled = true;
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    var score = Math.floor(dist);
    var form = new FormData();
    form.append("score", String(score));
    fetch("{{ url_for('swipe_ushi_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + score + " m 進みました";
          document.getElementById("bestline").textContent = "ベスト: " + d.best;
        }
      })
      .catch(function(){});
    show();
  }
  boostBtn.addEventListener("click", boost);
  document.addEventListener("keydown", function(e){
    if (e.key === " ") { boost(); e.preventDefault(); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    playing = true;
    vel = 0; dist = 0; timeLeft = 30;
    message.textContent = "連打で加速しよう！";
    boostBtn.disabled = false;
    startBtn.disabled = true;
    show();
    tickId = setInterval(tick, 100);
  });
  show();
})();
</script>
"""


@app.route("/games/swipe-ushi", methods=["GET"])
def swipe_ushi():
    body = render_template_string(
        SWIPEUSHI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("swipe-ushi", "max"),
        history=recent_scores("swipe-ushi", 10),
    )
    return game_page("スワイプ加速ウシ", body)


@app.route("/games/swipe-ushi/score", methods=["POST"])
def swipe_ushi_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 999999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("swipe-ushi", int(raw))
    return {"ok": True, "best": best_score("swipe-ushi", "max")}


# ============================
# ブロック側サバイバル
# ブロック崩しの「ブロック側」を操作して生き残る逆転アクション
# （クライアント JS）。ボールに当たるとライフ減、他のブロックが
# 壊れるとボーナス。生き残った時間でも得点が入る。
# ============================
BLOCKSURVIVE_TEMPLATE = r"""
  <h1>🧱 ブロック側サバイバル</h1>
  <p class="howto">あなたはブロック崩しの「ブロック」です。◀ ▶ で左右に動き、▲ ▼ で段を移って、跳ね回るボールから逃げてください。下のパドル（CPU）はボールを打ち返してきます。ボールに当たるとライフが減り（3回で終了）、他のブロックが壊れると +20 点。生き残るほど得点が増えます。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト: {{ best if best is not none else '—' }}</p>
    <p class="mid">得点: <span id="points">0</span> ／ ライフ: <span id="lives">❤️❤️❤️</span></p>
    <div id="field" style="position:relative; width:640px; max-width:100%; height:360px; margin:10px auto; background:#20242e; border-radius:12px; overflow:hidden;">
      <div id="player" style="position:absolute; width:64px; height:18px; background:#e67e22; border-radius:4px; border:2px solid #ffd9a0;"></div>
      <div id="paddle" style="position:absolute; width:96px; height:12px; background:#7ab8e6; border-radius:6px;"></div>
      <div id="ball" style="position:absolute; width:14px; height:14px; background:#fff; border-radius:50%;"></div>
    </div>
    <p class="result" id="message">「スタート」を押してね</p>
    <div class="row">
      <button type="button" id="leftBtn">◀</button>
      <button type="button" id="upBtn">▲ 段を上へ</button>
      <button type="button" id="downBtn">▼ 段を下へ</button>
      <button type="button" id="rightBtn">▶</button>
    </div>
    <div class="row" style="margin-top:8px;">
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
  var W = 640, H = 360;
  var field = document.getElementById("field");
  var playerEl = document.getElementById("player");
  var paddleEl = document.getElementById("paddle");
  var ballEl = document.getElementById("ball");
  var message = document.getElementById("message");
  var pointsEl = document.getElementById("points");
  var livesEl = document.getElementById("lives");
  var startBtn = document.getElementById("startBtn");
  var ROWS = [30, 62, 94];
  var playing = false, tickId = null;
  var px, prow, lives, points, bx, by, bvx, bvy, paddleX, bricks;
  function place(el, x, y){ el.style.left = x + "px"; el.style.top = y + "px"; }
  function makeBricks(){
    bricks = [];
    var colors = ["#e74c3c", "#f1c40f", "#2ecc71", "#9b59b6"];
    for (var ri = 0; ri < 3; ri++) {
      for (var i = 0; i < 8; i++) {
        if (ri === 1 && i === 4) { continue; }  // プレイヤーの初期位置は空ける
        var el = document.createElement("div");
        el.style.cssText = "position:absolute; width:64px; height:18px; border-radius:4px; background:" + colors[(ri + i) % 4] + "; opacity:.85;";
        var b = {x: i * 80 + 8, y: ROWS[ri], el: el, alive: true};
        place(el, b.x, b.y);
        field.appendChild(el);
        bricks.push(b);
      }
    }
  }
  function resetBall(){
    bx = paddleX + 41; by = 322;
    bvx = 3.4; bvy = -4.2;
  }
  function show(){
    place(playerEl, px, ROWS[prow]);
    place(paddleEl, paddleX, 340);
    place(ballEl, bx, by);
    pointsEl.textContent = String(points);
    livesEl.textContent = lives > 0 ? "❤️".repeat(lives) : "💔";
  }
  function hitTest(x, y, w, h){
    return bx + 14 > x && bx < x + w && by + 14 > y && by < y + h;
  }
  function tick(){
    if (!playing) { return; }
    points += 1;
    // パドルはボールを追う
    var target = bx + 7 - 48;
    if (paddleX < target) { paddleX = Math.min(target, paddleX + 5); }
    if (paddleX > target) { paddleX = Math.max(target, paddleX - 5); }
    paddleX = Math.max(0, Math.min(W - 96, paddleX));
    var prevBx = bx, prevBy = by;
    bx += bvx; by += bvy;
    if (bx < 0) { bx = 0; bvx = Math.abs(bvx); }
    if (bx > W - 14) { bx = W - 14; bvx = -Math.abs(bvx); }
    if (by < 0) { by = 0; bvy = Math.abs(bvy); }
    if (by > H - 14) { finish(); return; }  // パドルが取りこぼしたら最初から
    if (bvy > 0 && hitTest(paddleX, 340, 96, 12)) {
      bvy = -Math.abs(bvy);
      bvx += ((bx + 7) - (paddleX + 48)) / 24;
      bvx = Math.max(-6, Math.min(6, bvx));
      by = 326;
    }
    // プレイヤーとの衝突
    if (hitTest(px, ROWS[prow], 64, 18)) {
      lives--;
      message.textContent = "ボールに当たった！ ライフ " + lives;
      if (lives <= 0) { finish(); return; }
      resetBall();
      show();
      return;
    }
    // 他ブロックとの衝突
    for (var i = 0; i < bricks.length; i++) {
      var b = bricks[i];
      if (!b.alive) { continue; }
      if (hitTest(b.x, b.y, 64, 18)) {
        b.alive = false;
        b.el.remove();
        points += 20;
        if (prevBy + 14 <= b.y || prevBy >= b.y + 18) { bvy = -bvy; }
        else { bvx = -bvx; }
        message.textContent = "他のブロックが壊れた +20 点";
        break;
      }
    }
    show();
  }
  function finish(){
    if (!playing) { return; }
    playing = false;
    clearInterval(tickId);
    startBtn.disabled = false;
    startBtn.textContent = "もう一度";
    if (by > H - 14) { points = Math.max(0, points - 50); message.textContent = "パドルが取りこぼした… -50 点で終了"; }
    var form = new FormData();
    form.append("score", String(points));
    fetch("{{ url_for('block_survive_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🎉 終了！ " + points + " 点でした";
          document.getElementById("bestline").textContent = "ベスト: " + d.best;
        }
      })
      .catch(function(){});
    show();
  }
  function movePlayer(dx){
    if (!playing) { return; }
    px = Math.max(0, Math.min(W - 64, px + dx));
    show();
  }
  function moveRow(d){
    if (!playing) { return; }
    prow = Math.max(0, Math.min(2, prow + d));
    show();
  }
  document.getElementById("leftBtn").addEventListener("click", function(){ movePlayer(-28); });
  document.getElementById("rightBtn").addEventListener("click", function(){ movePlayer(28); });
  document.getElementById("upBtn").addEventListener("click", function(){ moveRow(-1); });
  document.getElementById("downBtn").addEventListener("click", function(){ moveRow(1); });
  document.addEventListener("keydown", function(e){
    if (e.key === "ArrowLeft") { movePlayer(-28); e.preventDefault(); }
    if (e.key === "ArrowRight") { movePlayer(28); e.preventDefault(); }
    if (e.key === "ArrowUp") { moveRow(-1); e.preventDefault(); }
    if (e.key === "ArrowDown") { moveRow(1); e.preventDefault(); }
  });
  startBtn.addEventListener("click", function(){
    if (playing) { return; }
    bricks.forEach(function(b){ if (b.el.parentNode) { b.el.remove(); } });
    makeBricks();
    playing = true;
    px = 328; prow = 1; lives = 3; points = 0;
    paddleX = 272;
    resetBall();
    message.textContent = "ボールから逃げ切れ！";
    startBtn.disabled = true;
    show();
    tickId = setInterval(tick, 30);
  });
  px = 328; prow = 1; lives = 3; points = 0; paddleX = 272;
  makeBricks();
  resetBall();
  show();
})();
</script>
"""


@app.route("/games/block-survive", methods=["GET"])
def block_survive():
    body = render_template_string(
        BLOCKSURVIVE_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("block-survive", "max"),
        history=recent_scores("block-survive", 10),
    )
    return game_page("ブロック側サバイバル", body)


@app.route("/games/block-survive/score", methods=["POST"])
def block_survive_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 99999):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("block-survive", int(raw))
    return {"ok": True, "best": best_score("block-survive", "max")}


# ============================
# 名画おなおしミニ
# 破れた名画風の絵の欠けた部分を描き足し、元の絵との一致度で採点する
# （クライアント JS、canvas）。絵は3種の配色で手続き的に描く。
# ============================
MEIGA_TEMPLATE = r"""
  <h1>🖼️ 名画おなおしミニ</h1>
  <p class="howto">名画（風の絵）の右のキャンバスは一部が破れて白くなっています。お手本を見ながら、パレットの色で破れた部分を描き足してください。「鑑定する」で元の絵との一致度（100点満点）を採点します。破れた範囲だけが採点対象です。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト: {{ best if best is not none else '—' }}</p>
    <div style="display:flex; gap:14px; flex-wrap:wrap; justify-content:center;">
      <div>
        <p class="mid">お手本</p>
        <canvas id="refCanvas" width="220" height="220" style="border:1px solid #bbb; border-radius:8px;"></canvas>
      </div>
      <div>
        <p class="mid">おなおし中（破れは白い部分）</p>
        <canvas id="workCanvas" width="220" height="220" style="border:1px solid #bbb; border-radius:8px; touch-action:none; cursor:crosshair;"></canvas>
      </div>
    </div>
    <div class="row" style="margin-top:10px;" id="palette"></div>
    <div class="row">
      <label>筆の太さ
        <select id="brushSize">
          <option value="6">細</option>
          <option value="12" selected>中</option>
          <option value="22">太</option>
        </select>
      </label>
      <button type="button" id="judgeBtn">🔍 鑑定する</button>
      <button type="button" id="retryBtn">↩ 破れた状態に戻す</button>
      <button type="button" id="newBtn">🎨 別のお題</button>
    </div>
    <p class="result" id="message">破れた部分を描き足してみよう</p>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（一致度）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var TORN = {x: 85, y: 70, w: 62, h: 76};
  var PALETTES = [
    {sky1: "#8ec9e8", sky2: "#e8f7ff", sun: "#ffd93b", hill: "#7ec850", hill2: "#4da653",
     house: "#c96f4a", roof: "#8b4a2f", trunk: "#7a4a21", leaf: "#3e9b4f"},
    {sky1: "#f7a56b", sky2: "#ffe3b3", sun: "#ffec9e", hill: "#b8a24a", hill2: "#7d8f3f",
     house: "#a85b4a", roof: "#6e3a2a", trunk: "#6b4226", leaf: "#5d7a35"},
    {sky1: "#2c3e70", sky2: "#7a86b8", sun: "#f5f3ce", hill: "#3f5a4a", hill2: "#2c4238",
     house: "#8a6a52", roof: "#54382a", trunk: "#4a3220", leaf: "#2f5d43"}
  ];
  var refCanvas = document.getElementById("refCanvas");
  var workCanvas = document.getElementById("workCanvas");
  var hidden = document.createElement("canvas");
  hidden.width = 220; hidden.height = 220;
  var message = document.getElementById("message");
  var variant = Math.floor(Math.random() * PALETTES.length);
  var color = "#c96f4a";
  function drawPainting(ctx, p){
    var g = ctx.createLinearGradient(0, 0, 0, 220);
    g.addColorStop(0, p.sky1);
    g.addColorStop(1, p.sky2);
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 220, 220);
    ctx.fillStyle = p.sun;
    ctx.beginPath(); ctx.arc(165, 52, 25, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = p.hill2;
    ctx.beginPath(); ctx.ellipse(40, 230, 150, 70, 0, Math.PI, Math.PI * 2); ctx.fill();
    ctx.fillStyle = p.hill;
    ctx.beginPath(); ctx.ellipse(200, 235, 160, 80, 0, Math.PI, Math.PI * 2); ctx.fill();
    // 家（破れた範囲と重なる位置）
    ctx.fillStyle = p.house;
    ctx.fillRect(70, 118, 72, 54);
    ctx.fillStyle = p.roof;
    ctx.beginPath();
    ctx.moveTo(60, 118); ctx.lineTo(106, 88); ctx.lineTo(152, 118); ctx.closePath(); ctx.fill();
    ctx.fillStyle = "#fff2cc";
    ctx.fillRect(96, 138, 20, 34);
    // 木
    ctx.fillStyle = p.trunk;
    ctx.fillRect(182, 138, 9, 34);
    ctx.fillStyle = p.leaf;
    ctx.beginPath(); ctx.arc(186, 122, 24, 0, Math.PI * 2); ctx.fill();
  }
  function setupWork(){
    var p = PALETTES[variant];
    drawPainting(refCanvas.getContext("2d"), p);
    drawPainting(hidden.getContext("2d"), p);
    var ctx = workCanvas.getContext("2d");
    drawPainting(ctx, p);
    ctx.fillStyle = "#f7f2e4";
    ctx.fillRect(TORN.x, TORN.y, TORN.w, TORN.h);
    ctx.strokeStyle = "#b8ab90";
    ctx.setLineDash([5, 4]);
    ctx.strokeRect(TORN.x, TORN.y, TORN.w, TORN.h);
    ctx.setLineDash([]);
    ctx.strokeStyle = "#cbbfa5";
    ctx.beginPath();
    ctx.moveTo(TORN.x + 6, TORN.y + 8);
    ctx.lineTo(TORN.x + 26, TORN.y + 34);
    ctx.lineTo(TORN.x + 16, TORN.y + 58);
    ctx.stroke();
  }
  var paletteDiv = document.getElementById("palette");
  function buildPalette(){
    paletteDiv.innerHTML = "";
    var p = PALETTES[variant];
    var colors = [p.sky1, p.sky2, p.sun, p.hill, p.hill2, p.house, p.roof, p.leaf, "#ffffff", "#333333"];
    colors.forEach(function(c){
      var b = document.createElement("button");
      b.type = "button";
      b.style.cssText = "width:34px; height:34px; padding:0; background:" + c + "; border-radius:8px;";
      b.addEventListener("click", function(){ color = c; });
      paletteDiv.appendChild(b);
    });
    color = p.house;
  }
  var drawing = false, lastX = 0, lastY = 0;
  function posOf(e){
    var rect = workCanvas.getBoundingClientRect();
    var cx = (e.touches ? e.touches[0].clientX : e.clientX);
    var cy = (e.touches ? e.touches[0].clientY : e.clientY);
    return {x: (cx - rect.left) * 220 / rect.width, y: (cy - rect.top) * 220 / rect.height};
  }
  function startDraw(e){ drawing = true; var p = posOf(e); lastX = p.x; lastY = p.y; e.preventDefault(); }
  function moveDraw(e){
    if (!drawing) { return; }
    var p = posOf(e);
    var ctx = workCanvas.getContext("2d");
    ctx.strokeStyle = color;
    ctx.lineWidth = parseInt(document.getElementById("brushSize").value, 10);
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    lastX = p.x; lastY = p.y;
    e.preventDefault();
  }
  function endDraw(){ drawing = false; }
  workCanvas.addEventListener("mousedown", startDraw);
  workCanvas.addEventListener("mousemove", moveDraw);
  document.addEventListener("mouseup", endDraw);
  workCanvas.addEventListener("touchstart", startDraw);
  workCanvas.addEventListener("touchmove", moveDraw);
  document.addEventListener("touchend", endDraw);
  document.getElementById("retryBtn").addEventListener("click", function(){
    setupWork();
    message.textContent = "破れた状態に戻しました";
  });
  document.getElementById("newBtn").addEventListener("click", function(){
    variant = (variant + 1) % PALETTES.length;
    buildPalette();
    setupWork();
    message.textContent = "別のお題になりました";
  });
  document.getElementById("judgeBtn").addEventListener("click", function(){
    var ref = hidden.getContext("2d").getImageData(TORN.x, TORN.y, TORN.w, TORN.h).data;
    var got = workCanvas.getContext("2d").getImageData(TORN.x, TORN.y, TORN.w, TORN.h).data;
    var total = 0, n = 0;
    for (var i = 0; i < ref.length; i += 16) {
      total += (Math.abs(ref[i] - got[i]) + Math.abs(ref[i + 1] - got[i + 1]) + Math.abs(ref[i + 2] - got[i + 2])) / 3;
      n++;
    }
    var mean = total / Math.max(1, n);
    var score = Math.max(0, Math.min(100, Math.round(100 - mean / 1.8)));
    var form = new FormData();
    form.append("score", String(score));
    fetch("{{ url_for('meiga_naoshi_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = "🔍 鑑定結果：一致度 " + score + " 点でした";
          document.getElementById("bestline").textContent = "ベスト: " + d.best;
        }
      })
      .catch(function(){});
  });
  buildPalette();
  setupWork();
})();
</script>
"""


@app.route("/games/meiga-naoshi", methods=["GET"])
def meiga_naoshi():
    body = render_template_string(
        MEIGA_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        best=best_score("meiga-naoshi", "max"),
        history=recent_scores("meiga-naoshi", 10),
    )
    return game_page("名画おなおしミニ", body)


@app.route("/games/meiga-naoshi/score", methods=["POST"])
def meiga_naoshi_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 100):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("meiga-naoshi", int(raw))
    return {"ok": True, "best": best_score("meiga-naoshi", "max")}


# ============================
# 証言ふくわらい捜査
# 目撃証言（位置の範囲）を頼りに福笑いで顔のパーツを再配置し、
# 本物との近さで採点する（クライアント JS）。証言に反すると減点。
# ============================
FUKUWARAI_CASE = {
    "parts": [
        {"key": "eye_r", "label": "右目", "emoji": "👁️", "target": [2, 2]},
        {"key": "eye_l", "label": "左目", "emoji": "👁️", "target": [2, 5]},
        {"key": "nose", "label": "鼻", "emoji": "👃", "target": [4, 3]},
        {"key": "mouth", "label": "口", "emoji": "👄", "target": [7, 3]},
        {"key": "mole", "label": "ほくろ", "emoji": "⚫", "target": [5, 6]},
    ],
    "statements": [
        {"part": "eye_r", "axis": "r", "min": 1, "max": 3,
         "text": "右目は顔の上のほう、上から2〜4段目にあった"},
        {"part": "eye_r", "axis": "c", "min": 1, "max": 3,
         "text": "右目は向かって左寄りだった"},
        {"part": "eye_l", "axis": "r", "min": 1, "max": 3,
         "text": "左目も右目と同じくらいの高さだった"},
        {"part": "eye_l", "axis": "c", "min": 4, "max": 6,
         "text": "左目は向かって右寄りだった"},
        {"part": "nose", "axis": "r", "min": 3, "max": 5,
         "text": "鼻は顔の真ん中あたりの高さだった"},
        {"part": "nose", "axis": "c", "min": 3, "max": 4,
         "text": "鼻はほぼ中央にあった"},
        {"part": "mouth", "axis": "r", "min": 6, "max": 8,
         "text": "口は顔の下のほうにあった"},
        {"part": "mole", "axis": "c", "min": 5, "max": 7,
         "text": "ほくろは向かって右のほほにあった"},
    ],
}


FUKUWARAI_TEMPLATE = r"""
  <h1>🔍 証言ふくわらい捜査</h1>
  <p class="howto">目撃証言を頼りに、容疑者の顔のパーツを福笑いで再現してください。パーツを選んでから、顔のマスを押して配置します（置き直しもできます）。証言は位置の範囲を示しています。全部置いたら「判定する」。本物との近さで100点満点、証言に反した配置は1件につき-5点です。</p>
  __FLASH__
  <div class="card">
    <p class="result" id="bestline">ベスト: {{ best if best is not none else '—' }}</p>
    <div class="panel" style="margin-bottom:12px;">
      <h3>🗣️ 目撃証言</h3>
      <ul style="margin:6px 0; text-align:left;">
        {% for s in statements %}
          <li>{{ s.text }}</li>
        {% endfor %}
      </ul>
    </div>
    <div class="row" id="partBtns" style="margin-bottom:10px;"></div>
    <div id="face" style="display:grid; grid-template-columns: repeat(8, 38px); gap:2px; justify-content:center;
      background:#ffe0bd; border:2px solid #d8a06a; border-radius:46% / 42%; padding:16px 10px; max-width:360px; margin:0 auto;"></div>
    <p class="result" id="message">パーツを選んで顔に置いてください</p>
    <div class="row">
      <button type="button" id="judgeBtn">⚖️ 判定する</button>
      <button type="button" id="clearBtn">↩ 全部外す</button>
    </div>
    {% if history %}
      <h3 style="font-size:14px; margin:16px 0 8px;">最近の記録（採点）</h3>
      <table>
        {% for s in history %}
          <tr><td>{{ s.score }} 点</td><td class="muted">{{ s.created_at }}</td></tr>
        {% endfor %}
      </table>
    {% endif %}
  </div>
<script>
(function(){
  var CASE = {{ case|tojson }};
  var face = document.getElementById("face");
  var partBtns = document.getElementById("partBtns");
  var message = document.getElementById("message");
  var selected = CASE.parts[0].key;
  var placed = {};
  var cells = [];
  function partOf(key){
    for (var i = 0; i < CASE.parts.length; i++) {
      if (CASE.parts[i].key === key) { return CASE.parts[i]; }
    }
    return null;
  }
  function renderParts(){
    partBtns.innerHTML = "";
    CASE.parts.forEach(function(p){
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = p.emoji + " " + p.label + (placed[p.key] ? " ✓" : "");
      if (selected === p.key) { b.style.background = "#ffe9a8"; }
      b.addEventListener("click", function(){ selected = p.key; renderParts(); });
      partBtns.appendChild(b);
    });
  }
  function renderFace(){
    for (var r = 0; r < 10; r++) {
      for (var c = 0; c < 8; c++) {
        var cell = cells[r * 8 + c];
        var t = "";
        CASE.parts.forEach(function(p){
          if (placed[p.key] && placed[p.key][0] === r && placed[p.key][1] === c) {
            t = p.emoji;
          }
        });
        cell.textContent = t;
      }
    }
  }
  for (var r = 0; r < 10; r++) {
    for (var c = 0; c < 8; c++) {
      var d = document.createElement("button");
      d.type = "button";
      d.style.cssText = "width:38px; height:38px; font-size:19px; padding:0; background:rgba(255,255,255,.55); border-color:#d8a06a;";
      (function(rr, cc){
        d.addEventListener("click", function(){
          placed[selected] = [rr, cc];
          renderFace();
          renderParts();
        });
      })(r, c);
      face.appendChild(d);
      cells.push(d);
    }
  }
  document.getElementById("clearBtn").addEventListener("click", function(){
    placed = {};
    renderFace();
    renderParts();
    message.textContent = "パーツを全部外しました";
  });
  document.getElementById("judgeBtn").addEventListener("click", function(){
    if (Object.keys(placed).length < CASE.parts.length) {
      message.textContent = "まだ置いていないパーツがあります";
      return;
    }
    var total = 0;
    CASE.parts.forEach(function(p){
      var got = placed[p.key];
      var d = Math.abs(got[0] - p.target[0]) + Math.abs(got[1] - p.target[1]);
      total += Math.max(0, 20 - 4 * d);
    });
    CASE.statements.forEach(function(s){
      var got = placed[s.part];
      var v = s.axis === "r" ? got[0] : got[1];
      if (v < s.min || v > s.max) { total -= 5; }
    });
    total = Math.max(0, Math.min(100, total));
    var form = new FormData();
    form.append("score", String(total));
    fetch("{{ url_for('fukuwarai_score') }}", {method: "POST", body: form})
      .then(function(r){ return r.json(); })
      .then(function(d){
        if (d && d.ok) {
          message.textContent = total >= 80 ? "🎉 証言どおりの再現！ " + total + " 点" : "⚖️ 判定：" + total + " 点でした";
          document.getElementById("bestline").textContent = "ベスト: " + d.best;
        }
      })
      .catch(function(){});
  });
  renderParts();
  renderFace();
})();
</script>
"""


@app.route("/games/fukuwarai", methods=["GET"])
def fukuwarai():
    body = render_template_string(
        FUKUWARAI_TEMPLATE.replace("__FLASH__", _FLASH_BLOCK),
        case=FUKUWARAI_CASE,
        statements=FUKUWARAI_CASE["statements"],
        best=best_score("fukuwarai", "max"),
        history=recent_scores("fukuwarai", 10),
    )
    return game_page("証言ふくわらい捜査", body)


@app.route("/games/fukuwarai/score", methods=["POST"])
def fukuwarai_score():
    raw = request.form.get("score", "").strip()
    if not raw.isdigit() or not (0 <= int(raw) <= 100):
        return {"ok": False, "error": "invalid score"}, 400
    record_score("fukuwarai", int(raw))
    return {"ok": True, "best": best_score("fukuwarai", "max")}

# gunicorn 等で起動した場合にも DB を用意する（作成済みなら何もしない）
init_db()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
