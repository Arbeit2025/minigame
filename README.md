# minigame

Flask + SQLite で作った、ルーレット／抽選テーブルアプリです。候補を登録して抽選でき、結果はデータベースに残ります。

## 起動方法

```bash
pip install -r requirements.txt
python gameapp.py
```

起動後に http://127.0.0.1:5000 を開きます。セッション用の秘密鍵は環境変数 `SECRET_KEY` で変更できます（未設定時はローカル用途の既定値）。

## テスト

```bash
python -m unittest discover -s tests -v
```

## ライセンス

MIT License（[LICENSE](LICENSE) を参照）
