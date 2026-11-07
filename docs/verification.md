# 検証記録

更新日: 2026-11-07。実施した項目と未実施の項目を区別する。

| 項目 | 現在の結果 |
| --- | --- |
| アプリ・運用テスト | GitHub CIで21件成功。JWTの不正署名・期限・audience・呼び出し元・ロール、MCPの実HTTP通信、ツール呼び出し、UIの入口、入力・回数制限、削除保護、OIDC形式を確認 |
| Python lint / format | 成功 |
| Terraform bootstrap / workload validate | 成功 |
| Azure接続 | 成功。対象テナントを指定してMFAを実施 |
| Azure権限 | 実行者のSubscription OwnerとEntra Global Administratorを確認 |
| モデル | 東日本でgpt-4.1-mini 2025-04-14 / Standardの提供と空きクォータを確認 |
| GitHub CI | [テスト・Terraform・コンテナービルド成功](https://github.com/kazu-dota/azure-mcp-appservice/actions/runs/42369789455) |
| GitHub ActionsからのAzureデプロイ | 実施中。OIDC認証成功。FoundryのIdentity前提を修正し、実接続planで26リソースの追加計画が成功 |
| 実環境のPrivate DNS・認証拒否・AI/MCP連携 | これから実施 |
| 本人によるブラウザログイン | これから実施 |
| コード変更の反映・Terraform差分なし | これから実施 |
| 環境削除と残存確認 | これから実施 |
| 実際の課金 | 未集計。Cost Managementの反映後に追記 |

ローカルのモデル応答はテスト用の固定応答であり、Azure上のFoundry実モデルによる成功を意味しない。MCPはテスト時も実HTTPサーバーと実SDKを使用する。
