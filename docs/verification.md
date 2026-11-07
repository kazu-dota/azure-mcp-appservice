# 検証記録

更新日: 2026-11-07。実施した項目と未実施の項目を区別する。

| 項目 | 現在の結果 |
| --- | --- |
| アプリ・運用テスト | ローカルで26件成功。JWTの不正署名・期限・audience・呼び出し元・ロール、MCPの実HTTP通信、ツール呼び出し、UIの入口、入力・回数制限、削除保護、OIDC形式、ログイン先の検証を確認 |
| Python lint / format | 成功 |
| Terraform bootstrap / workload validate | 成功 |
| Azure接続 | 成功。対象テナントを指定してMFAを実施 |
| Azure権限 | 実行者のSubscription OwnerとEntra Global Administratorを確認 |
| モデル | 東日本でgpt-4.1-mini 2025-04-14 / Standardの提供と空きクォータを確認 |
| GitHub CI | [24件のテスト・Terraform・コンテナービルド成功](https://github.com/kazu-dota/azure-mcp-appservice/actions/runs/42374079517)。26件版は次のPRで確認 |
| GitHub ActionsからのAzureデプロイ | OIDC、Terraform apply、ACR Push、再起動まで成功。最後のログイン遷移テストのヘッダー不足を修正し、Workflow全体の再検証を行う |
| 実環境のPrivate DNS・認証拒否・AI/MCP連携 | 成功。フロントの実Managed Identityで5項目すべて成功。実モデルがget_inventoryを呼びPC001の在庫12を回答に使用 |
| 本人によるブラウザログイン | 確認待ち。自動チェックはEntraへの遷移先・client_id・callbackを確認するが、本人のログイン成功を代替しない |
| コード変更の反映・Terraform差分なし | db1aed5→c056621への反映を実環境のSHAで確認。c056621で修正後のsmokeをローカルから実行し、公開アクセス拒否とTerraform No changesも成功 |
| 環境削除と残存確認 | これから実施 |
| 実際の課金 | 未集計。Cost Managementの反映後に追記 |

ローカルのモデル応答はテスト用の固定応答であり、Azure上のFoundry実モデルによる成功を意味しない。MCPはテスト時も実HTTPサーバーと実SDKを使用する。

実環境の証跡は[startup-checks.json](evidence/startup-checks.json)と[deployment-checks.json](evidence/deployment-checks.json)を参照する。後者は現時点ではローカルから実環境へ実行した結果であり、Actions全体の成功記録とは区別する。
