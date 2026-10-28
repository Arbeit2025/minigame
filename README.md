# minigame（自作ミニゲーム集）

Flask + SQLite で作った、**全部作者の自作ゲームだけを集めたミニゲームポータル**です。トップページがゲーム一覧になっていて、ジャンルとゲームカードから各ゲームへ入って遊べます。登録不要・無料。

## 収録ゲーム

| ゲーム | ジャンル | 内容 |
| --- | --- | --- |
| 🎲 ルーレット抽選 | 抽選・占い | 候補を登録して抽選でき、結果はデータベースに残ります。重み（当たりやすさ）も付けられます |

**公開サイト：https://minigame-b1qp.onrender.com/**

新しいゲームは `gameapp.py` の `GAMES` リストに1件追加し、対応するルートとテンプレートを用意すると、トップとジャンル別一覧に自動で並びます。

## 起動方法（ローカル）

```bash
pip install -r requirements.txt
python gameapp.py
```

起動後に http://127.0.0.1:5000 を開きます。セッション用の秘密鍵は環境変数 `SECRET_KEY` で変更できます（未設定時はローカル用途の既定値）。

## 公開方法（Render）

このリポジトリには Render 用の `render.yaml` が入っています。

1. Render で **New → Blueprint** を選び、このリポジトリを指定する（手動で Web Service を作る場合は Build Command: `pip install -r requirements.txt`、Start Command: `gunicorn gameapp:app`、Health Check Path: `/healthz`）
2. 環境変数 `SECRET_KEY` は render.yaml 側で自動生成される
3. デプロイされた URL がそのまま公開サイトになる

注意：無料プランでは SQLite のデータ（ルーレットのテーブル・抽選結果）は再デプロイや再起動で消えることがあります。サイト上でもその旨を案内しています。

## テスト

```bash
python -m unittest discover -s tests -v
```

## ライセンス

MIT License（[LICENSE](LICENSE) を参照）
