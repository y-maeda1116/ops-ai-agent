---
service: postgres
title: PostgreSQL 障害対応手順
---

# PostgreSQL 障害対応手順

1. 接続数・プール使用率・max_connections を確認（1分）
2. `pg_stat_activity` で長時間トランザクションと待ち状態を特定
3. 接続枯渇時はリーク疑いのアプリケーションを特定し、当該ワーカーを再起動
4. slow query の急増があればクエリキャンセルと実行計画確認を検討
5. 復旧後、コネクション取得/解放のメトリクスを確認し再発防止策を起票
