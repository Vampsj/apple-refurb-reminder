# Apple Refurb Reminder

Apple 日本の整備済 MacBook Pro 在庫を監視し、Discord と Email に通知する CLI です。

> [!IMPORTANT]
> Version 0.1 is a working early release for one Japan MacBook Pro rule.
> Public V1 is under development and will add an English setup wizard, up to
> three rules, JP/US/CN/HK regions, and Mac/iPhone/iPad support.

This is an independent open-source project and is not affiliated with or
endorsed by Apple Inc. Use it responsibly and comply with Apple's website
terms and applicable local rules. The project collects no telemetry.

## Mac mini 一键安装

Mac mini 建议关闭自动睡眠并保持联网。克隆仓库后，在项目目录运行：

```bash
chmod +x scripts/*.sh
./scripts/install-macos.sh
```

安装程序会：

- 使用 `uv` 准备 Python 3.13 隔离环境；
- 将运行副本部署到 `~/Library/Application Support/Apple Refurb Reminder`；
- 交互式读取 Discord Webhook 和可选的 Gmail 应用专用密码；
- 将秘密配置保存为仅当前用户可读；
- 安装并启动用户级 `launchd` 服务；
- 保留状态文件，避免更新后重复提醒。

检查状态：

```bash
./scripts/status-macos.sh
```

从 GitHub 拉取新版代码后更新运行副本：

```bash
git pull
./scripts/update-macos.sh
```

停止服务但保留配置和状态：

```bash
./scripts/uninstall-macos.sh
```

## セットアップ

Python 3.13 以上と `uv` を推奨します。

```bash
uv sync --dev
cp .env.example .env
```

`.env` に Discord Webhook と、必要なら SMTP 設定を記入します。購読条件は
`subscriptions.yaml` にあります。秘密情報を Git に追加しないでください。

この環境のように `uv` がない場合は、標準の仮想環境でも実行できます。

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## 安全な初回確認

```bash
.venv/bin/apple-refurb-reminder validate-config
.venv/bin/apple-refurb-reminder check-once
.venv/bin/apple-refurb-reminder test-notifications
```

実在庫がないことを確認したうえで TEST の無在庫通知を送りたい場合：

```bash
.venv/bin/apple-refurb-reminder check-once --send-test-if-empty
```

長期監視：

```bash
.venv/bin/apple-refurb-reminder run
```

状態確認：

```bash
.venv/bin/apple-refurb-reminder status
```

## テスト

```bash
.venv/bin/pytest
.venv/bin/ruff check .
```

## launchd

macOS のプライバシー保護により、`launchd` は `Documents` 内の実行ファイルを直接起動
できない場合があります。この端末では、実行用コピーを次の場所へ配置します。

```text
~/Library/Application Support/Apple Refurb Reminder
```

LaunchAgent は `~/Library/LaunchAgents/com.apple-refurb-reminder.plist` にインストール
されます。ログイン時に起動し、異常終了時に再起動します。開発元のコードや設定を変更した
場合は、実行用コピーへ再デプロイして LaunchAgent を再起動する必要があります。

状態確認：

```bash
launchctl print gui/$(id -u)/com.apple-refurb-reminder
```

停止：

```bash
launchctl bootout gui/$(id -u)/com.apple-refurb-reminder
```

再登録：

```bash
launchctl bootstrap gui/$(id -u) \
  "$HOME/Library/LaunchAgents/com.apple-refurb-reminder.plist"
```
