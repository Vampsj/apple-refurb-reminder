# Apple 翻新产品库存提醒

[English](../README.md) · [日本語](README.ja.md)

Apple Refurb Reminder 是一个独立的命令行库存监控工具。它按照合理的检查间隔监控
Apple 官方翻新产品，并通过 Discord、电子邮件或两者同时发送即时通知。

> [!IMPORTANT]
> 稳定版 `v0.1.0` 目前只监控日本地区的一条 MacBook Pro 配置。多地区 V1 正在
> Draft PR #1 中开发，暂不建议用于无人值守的正式运行。

## V1 范围

- 地区：日本、美国、中国大陆、中国香港（繁体中文）。
- 产品：所有 Mac 电脑、iPhone 和 iPad。
- 每次安装只选择一个地区，最多建立三条相互独立的监控规则。
- 每条规则必须指定一个准确型号；其他适用配置可以选择一个准确值或 `Any`。
- 通知方式：Discord、Email 或两者同时使用。
- 通知语言跟随所选 Apple 地区。
- 正式支持 macOS 14 及以上版本，包括 Apple 芯片和 Intel。
- Linux CLI 为实验性支持；不支持 Windows。

Apple Watch、AirPods、Apple TV、HomePod、显示器和配件不在 V1 范围内。

## 开发环境

推荐使用 Python 3.13 和 `uv`：

```bash
uv sync --dev
cp .env.example .env
cp subscriptions.example.yaml subscriptions.yaml
```

运行英文设置向导：

```bash
.venv/bin/apple-refurb-reminder setup
```

后续管理命令：

```bash
.venv/bin/apple-refurb-reminder setup add
.venv/bin/apple-refurb-reminder setup list
.venv/bin/apple-refurb-reminder setup edit RULE_ID
.venv/bin/apple-refurb-reminder setup remove RULE_ID
.venv/bin/apple-refurb-reminder setup notifications
.venv/bin/apple-refurb-reminder setup region US
```

向导会从对应地区的 Apple 实时目录读取型号和配置。如果某个配置暂时没有库存，也可以
手动输入。切换地区时会归档旧规则和状态、重置库存历史，同时保留通知设置。

## 安全检查

```bash
.venv/bin/apple-refurb-reminder validate-config
.venv/bin/apple-refurb-reminder check-once
.venv/bin/apple-refurb-reminder test-notifications
```

默认检查间隔为 10 分钟，最低允许 5 分钟。

## 密钥与可靠性

macOS 使用 Keychain 保存 Discord Webhook 和 SMTP 密码；实验性 Linux 版本使用权限
为 `0600` 的本地密钥文件。所选通知通道必须先成功发送 TEST 通知，配置才会保存。

程序会先使用目录数据筛选候选商品，只在必要时读取详情页。详情请求会跨规则共享，最大
并发数为 3，并使用可自动清理的持久缓存。网络错误、超时、异常页面、疑似验证码和解析
异常均不会累计商品缺席次数。同一类别连续失败三次后会发送异常通知，恢复时发送恢复通知。

本项目不收集遥测数据。

## 声明

本项目与 Apple Inc. 没有隶属或认可关系。库存、价格和页面结构可能随时变化。请合理
使用，并遵守 Apple 网站条款及当地适用规则。软件依据 [MIT License](../LICENSE)
按“现状”提供，不附带任何保证。
