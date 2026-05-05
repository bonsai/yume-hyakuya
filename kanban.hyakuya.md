# 曇晴筆記 (yume-hyakuya) カンバン

**最終更新**: 2026-05-05 13:10

## 現状確認 (STATUS)

### 動作
- ローカルサーバー起動中 (`http://127.0.0.1:5000`)
- `/api/dream/random` で 500 エラー発生中
- マス目表示は修正済み（border-color 調整）

### 環境
- **Python**: 3.10
- **Flask**: 2.3.3
- **DB**: SQLite (`yume.db`)
- **AI**: Sakura AI (gpt-oss-120b)
- **Docker**: デーモン未起動 (Windows)

### 設計
- 原稿用紙風 UI (20x20 マス目)
- 星新一風夢生成 AI (Sakura AI)

### 開発
- バグ修正フェーズ (API エラー対応中)
- フォルダ構成整理済み (kanban 移動)

### デプロイ
- Firebase Functions 構成あり (`firebase.json`)
- 現在ローカル開発中

### マネタイズ
- 検討中 (KPI/KGI 未定義)

## DOING

*(なし)*

## TODO

### 🔴 API 500エラー調査
- **症状**: `expected string or bytes-like object`
- **影響**: ランダム夢生成が機能しない
- **関連ファイル**: `app.py`, `dream_service.py`, `dream_diary.py`

### 🟡 Docker フォールバック
- **症状**: Docker デーモン未起動時にビルド失敗

###  favicon 未設定
- **症状**: `/favicon.ico` で 404

## DONE

### ✅ agents.how.debug.md 作成: デバッグ手法と環境を分離 (2026-05-05 13:10)
- デバッグ手法と開発環境を `agents.how.debug.md` に移動
- STATUS に環境情報を統合

### ✅ AGENTS.md 作成: カンバン即座確認ルール + 作業ログ時刻記載 (2026-05-05 12:30)
- ルートに AGENTS.md 配置
- 「作業開始前に必ず kanban*.md を即座に読む」を明文化
- 作業ログに YYYY-MM-DD HH:MM を必須記載
- 「作業ログから未来は作られる」方針を記載
- スクリーンショットは `debug/` フォルダにまとめるルール追記

### ✅ kanban.hyakuya.md 整理: フォルダ内移動 + デバッグ手法追記 (2026-05-05 12:28)
- ルートから yume-hyakuya/ 内に移動
- デバッグ手法セクション追加
- 開発環境テーブル追加

### ✅ 原稿用紙マス目 border-color 修正 (2026-05-05 12:15)
- 変更: `#e2d6bb` → `#c4b48a`, 外枠 `2px solid #a89470` 追加