# 検証記録

更新日: 2026-11-07。実施した項目と未実施の項目を区別する。

| 項目 | 現在の結果 |
| --- | --- |
| アプリ・運用テスト | ローカル・GitHub CIで26件成功。JWTの不正署名・期限・audience・呼び出し元・ロール、MCPの実HTTP通信、ツール呼び出し、UIの入口、入力・回数制限、削除保護、OIDC形式、ログイン先の検証を確認 |
| Python lint / format | 成功 |
| Terraform bootstrap / workload validate | 成功 |
| Azure接続 | 成功。対象テナントを指定してMFAを実施 |
| Azure権限 | 実行者のSubscription OwnerとEntra Global Administratorを確認 |
| モデル | 東日本でgpt-4.1-mini 2025-04-14 / Standardの提供と空きクォータを確認 |
| GitHub CI | [26件のテスト・Terraform・コンテナービルド成功](https://github.com/kazu-dota/azure-mcp-appservice/actions/runs/42375644873) |
| GitHub ActionsからのAzureデプロイ | [Workflow全体が成功](https://github.com/kazu-dota/azure-mcp-appservice/actions/runs/42375644780)。OIDC→Terraform apply→ACR Push→再起動→実接続と認証確認→差分なしまで完走 |
| 実環境のPrivate DNS・認証拒否・AI/MCP連携 | 成功。フロントの実Managed Identityで5項目すべて成功。実モデルがget_inventoryを呼びPC001の在庫12を回答に使用 |
| 本人によるブラウザログイン | 成功。本人から「ログインしてチャット画面が表示された」「うまく実行できた」と報告。ブラウザ操作でも実環境のチャット画面を確認 |
| コード変更の反映・Terraform差分なし | db1aed5→c056621→e740bfcの反映を実環境のSHAで確認。最終Deployが新しいSHAの準備完了とworkloadのNo changesを確認。bootstrapもIDトークン設定追加後にNo changes |
| 環境削除と残存確認 | 本人の停止依頼を受け[Cleanupを実行中](https://github.com/kazu-dota/azure-mcp-appservice/actions/runs/42382924904)。Deployは無効化済み |
| 実際の課金 | 未集計。Cost Managementの反映後に追記 |

ローカルのモデル応答はテスト用の固定応答であり、Azure上のFoundry実モデルによる成功を意味しない。MCPはテスト時も実HTTPサーバーと実SDKを使用する。

実環境の証跡は[startup-checks.json](evidence/startup-checks.json)、[deployment-checks.json](evidence/deployment-checks.json)、[browser-checks.json](evidence/browser-checks.json)を参照する。自動チェックの `interactive_login_verified: false` は、Workflow自身がブラウザのログインを確認したとは主張しないための値。本人の確認結果は別の証跡に記録する。
