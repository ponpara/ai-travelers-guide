# AI Traveler's Guide

現在地または指定した場所周辺の観光スポット情報を収集し、生成AIを用いて「プロ品質のオーディオガイド」をリアルタイムに生成・再生するWebアプリケーション。

## 実行方法

1. 仮想環境の作成と有効化 (推奨)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

2. 依存関係のインストール
```bash
pip install -r requirements.txt
```

3. サーバーの起動
```bash
python server.py
```

4. ブラウザでアクセス
http://localhost:5000

## 注意
- `server.py` 内の `GOOGLE_API_KEY` はご自身のキーに設定されていますが、公開しないように注意してください。
- Google Maps APIキーもフロントエンドコードに含まれています。
