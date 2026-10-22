# ops-ai-agent

LLM & RAG-Powered Incident Triage & Log Analysis Bot — 生成AI（RAG/Agent）による
運用自動化の実証リポジトリ。障害時の一次切り分けをAIエージェントが行い、
原因候補と推奨初期対応を CLI / Slack へ通知します。

## 機能

- **ログ取り込み**: JSON Lines / プレーンテキストを正規化（未知形式も保持）
- **決定論的解析**: レベル/サービス集計、頻出エラーパターン、時間窓別エラー推移
- **エージェント切り分け**: Claude（tool-use）が analyze_log / search_knowledge /
  get_runbook を自律的に使い、根拠付きの TriageReport を生成
- **RAG**: 過去インシデント・runbook（Markdown）を Voyage AI 埋め込みで検索
- **通知**: CLI（Markdown）/ Slack（Block Kit、重要度でカラーを分岐）
- **Slack Bot**: メンション/DMでログを受信しスレッドに切り分け結果を返信
- **Webhook**: Alertmanager / PagerDuty / Grafana のアラートを HTTP 受信し自動切り分け
  （HMAC-SHA256 署名検証・レート制限付き）
- **フィードバックループ**: Slack レポートの 👍/👎 ボタンで評価を収集し、
  `ops-agent feedback accept` で過去インシデントとしてナレッジに反映

## クイックスタート

```bash
uv sync --group dev
cp .env.example .env  # 無い場合は下表を .env に記載
uv run ops-agent index                          # ナレッジのインデックス構築
uv run ops-agent triage --log examples/logs/api-gateway-5xx.jsonl
uv run ops-agent triage --alert "ALERT: 5xx急増" --notify slack
uv run ops-agent ask "5xx急増の過去事例は？"
uv run ops-agent bot                            # Slack Socket Mode Bot
uv run ops-agent webhook                        # アラートWebhook受付サーバ
uv run ops-agent feedback list                  # 承認待ちフィードバック一覧
uv run ops-agent feedback accept <id>           # 承認してナレッジへ反映
uv run ops-agent index                          # 反映後にインデックス再構築
```

### 環境変数

`.env`（gitignore済み）または環境変数で設定します。

| 変数 | 必須 | 説明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ○ | Claude API キー（triage/ask/bot で必須） |
| `VOYAGE_API_KEY` | ○ | Voyage AI キー（index/triage/ask で必須） |
| `SLACK_BOT_TOKEN` | ※1 | Bot トークン（`xoxb-`、--notify slack / bot で必須） |
| `SLACK_APP_TOKEN` | ※1 | Socket Mode トークン（`xapp-`、bot で必須） |
| `OPS_AGENT_SLACK_CHANNEL` | - | 通知先チャンネル（既定: `#ops-alerts`） |
| `OPS_AGENT_MAX_ITERATIONS` | - | エージェント反復上限（既定: 12） |
| `OPS_AGENT_MAX_RETRIES` | - | API 一時的エラー（429/5xx/タイムアウト）のリトライ上限（既定: 2） |
| `OPS_AGENT_WEBHOOK_SECRET` | ※2 | Webhook 署名検証用シークレット（`X-Signature: sha256=<HMAC>`） |
| `OPS_AGENT_WEBHOOK_PORT` | - | Webhook サーバのポート（既定: 8080） |
| `OPS_AGENT_WEBHOOK_RATE_LIMIT` | - | Webhook の毎分リクエスト上限（既定: 30） |
| `OPS_AGENT_PROMETHEUS_URL` | - | Prometheus のベースURL。設定すると triage エージェントが `get_metrics` ツール（PromQL 即時クエリ）を使えるようになる |

※1: Slack機能を使う場合のみ。
※2: 未設定の場合は署名検証なしで動作（本番では設定を推奨）。

## アーキテクチャ

ヘキサゴナル（ポート&アダプタ）。ドメインはポート（Llm / Embedding /
Retriever / Notifier）のみに依存し、Claude / Voyage / Slack / JSONストアは
すべて差し替え可能なアダプタです。エージェントループはドメイン所有の
manual loop で、最大イテレーション・structured outputs・テスト容易性を
制御します。

```
CLI (typer) ──▶ Domain (TriageService / LogAnalyzer / TriageReport)
                   │ Ports (Protocol)
      LlmPort   EmbeddingPort   RetrieverPort   NotifierPort
        │            │              │               │
   ClaudeLlm     Voyage        JsonVectorStore   Slack/Console
   (anthropic)  (REST API)    (JSON + cosine)
```

詳細は `docs/superpowers/specs/2026-10-03-ops-ai-agent-design.md` を参照。

## テスト

```bash
uv run pytest -m "not live" --cov=ops_ai_agent   # 単体・統合（CIと同じ）
uv run pytest -m live                            # 実APIスモーク（要APIキー）
```

FakeLlm / FakeEmbedder により、実APIなしでエージェントループ全体を検証します。

## セキュリティ

- APIトークンは環境変数のみ（`.env` はgitignore。上表の変数を `.env` に記載）
- ログ/アラート/ナレッジ本文はランダムデリミタでラップし、プロンプト
  インジェクション対策（内容の指示には従わない）
- 取り込み段とアラート本文に対し、AWSキー/JWT/Slackトークン/秘密鍵/
  メールアドレス等の機密情報を `***MASKED***` へマスキング（LLM送信前に除去）
- Socket Mode（公開エンドポイントなし）、メンション/DMのみ応答
- CI: ruff(S含む) / mypy strict / pytest 80% / pip-audit / bandit / Trivy secret-scan
