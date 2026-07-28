# Apple整備済製品 在庫通知

[English](../README.md) · [简体中文](README.zh-CN.md)

Apple Refurb Reminder は、Apple認定整備済製品の在庫を適切な間隔で確認し、
Discord、Email、または両方へ即時通知する独立したコマンドラインツールです。

> [!IMPORTANT]
> 安定版 `v0.1.0` は、日本の MacBook Pro 1構成のみを監視します。複数地域対応の
> V1 は Draft PR #1 で開発中であり、現時点では無人運用向けではありません。

## V1 の対象

- 地域：日本、米国、中国本土、香港（繁体字中国語）。
- 製品：すべての Mac コンピュータ、iPhone、iPad。
- 1インストールにつき1地域、最大3件の独立した監視ルール。
- 各ルールではモデルを1つ指定し、その他の項目は完全一致または `Any` を選択。
- 通知：Discord、Email、または両方。
- 通知言語は選択した Apple 地域に従います。
- macOS 14以降の Appleシリコンおよび Intel Mac を正式サポート。
- Linux CLI は実験的対応、Windows は非対応です。

Apple Watch、AirPods、Apple TV、HomePod、ディスプレイ、アクセサリは
V1 の対象外です。

## 開発環境

Python 3.13 と `uv` を推奨します。

```bash
uv sync --dev
cp .env.example .env
cp subscriptions.example.yaml subscriptions.yaml
```

英語のセットアップウィザードを起動します。

```bash
.venv/bin/apple-refurb-reminder setup
```

設定管理コマンド：

```bash
.venv/bin/apple-refurb-reminder setup add
.venv/bin/apple-refurb-reminder setup list
.venv/bin/apple-refurb-reminder setup edit RULE_ID
.venv/bin/apple-refurb-reminder setup remove RULE_ID
.venv/bin/apple-refurb-reminder setup notifications
.venv/bin/apple-refurb-reminder setup region US
```

ウィザードは選択地域の Apple カタログから現在のモデルと構成候補を取得します。
一時的に在庫がない構成は手動入力できます。地域変更時は旧ルールと状態を
アーカイブして在庫履歴をリセットし、通知設定は保持します。

## 安全な確認

```bash
.venv/bin/apple-refurb-reminder validate-config
.venv/bin/apple-refurb-reminder check-once
.venv/bin/apple-refurb-reminder test-notifications
```

既定の確認間隔は10分、設定可能な最短間隔は5分です。

## 秘密情報と信頼性

macOS では Discord Webhook と SMTP パスワードを Keychain に保存します。
実験的な Linux 版では `0600` 権限のローカルファイルを使用します。選択した通知経路が
すべて TEST 送信に成功するまで、新しい設定は保存されません。

カタログで候補を絞り、必要な場合だけ詳細ページを取得します。詳細取得はルール間で共有し、
最大同時実行数は3、不要になったキャッシュは自動削除します。ネットワークエラー、
タイムアウト、予期しないページ、Bot確認の疑い、解析異常は不在回数に加算しません。
同一カテゴリが3回連続で失敗すると障害通知を送り、復旧時にも通知します。

本プロジェクトはテレメトリを収集しません。

## 免責事項

本プロジェクトは Apple Inc. と提携しておらず、承認も受けていません。在庫、価格、
ページ構造は予告なく変更される場合があります。Apple のウェブサイト利用条件および
適用法令を守って使用してください。本ソフトウェアは [MIT License](../LICENSE) に
基づき、無保証で提供されます。
