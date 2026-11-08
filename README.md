# App Serviceから非公開MCPとFoundryを使う

Entra IDでログインした利用者が、AIチャットから架空の商品と在庫を照会する検証環境です。Python製のフロントとMCPサーバーを別々のApp Serviceに配置し、TerraformとGitHub Actionsでデプロイします。

実Azureでのデプロイとチャットの検証は完了し、費用を止めるため検証環境を削除しました。Deploy/Cleanupは無効化しています。[検証記録](docs/verification.md)に成功したWorkflowと削除確認を残しています。

まずローカルでテストできます。Azureへの課金は発生しません。

```sh
uv sync --frozen
uv run pytest -q
```

テストで、MCPの実HTTP通信、ツール実行、トークンの検証、呼び出し回数制限、削除対象の保護を確認します。Foundryの実モデルを使う検証はAzureデプロイ後に行います。

## 構成

```mermaid
flowchart TD
    User[利用者] -->|Entra IDログイン| Front[App Service: チャット・AI処理]
    Front -->|VNet統合| Subnet
    subgraph VNet
        Subnet[統合用Subnet] --> McpPe[MCP Private Endpoint]
        Subnet --> AiPe[Foundry Private Endpoint]
    end
    McpPe --> Mcp[別のApp Service: MCP]
    AiPe --> Foundry[Foundry: gpt-4.1-mini]
    Actions[GitHub Actions] -->|OIDC| ARM[Azure管理API]
    Actions -->|コンテナーをPush| ACR[ACR Basic]
    Front -. Managed IdentityでPull .-> ACR
    Mcp -. Managed IdentityでPull .-> ACR
```

- 2つのApp Serviceは、日本リージョンのLinux B1プラン1台を共有します。今回の実環境では東日本のB1割り当てが0のため、App ServiceとVNetを西日本、Foundry・ACR・Stateを東日本に配置します。
- フロントだけを公開します。MCPとFoundryの公開ネットワークアクセスは無効です。
- フロントはManaged IdentityでMCPとFoundryに接続します。MCPは専用audience、呼び出し元、`Mcp.Invoke`ロールを検証します。
- Easy AuthのログインにもManaged Identityのフェデレーションを使います。クライアントシークレットやモデルAPIキーを設定する必要はありません。
- Private DNS ZoneをVNetにリンクし、統合用とPrivate Endpoint用のSubnetを分けます。
- ACRとTerraform State用Storageは認証付きの公開エンドポイントを使います。GitHub-hosted Runnerから利用し、常設RunnerやVPNは作りません。

## Azureへデプロイする

必要なものはPython 3.12、uv、Terraform（[指定バージョン](.terraform-version)）、Azure CLI、GitHub CLIです。DockerはGitHub ActionsのRunnerで使用します。実行者には、Azureリソース・ロール割り当てと、Entraアプリ・アプリロール割り当てを作成できる権限が必要です。

1. このコードを自分の公開GitHubリポジトリに置き、mainを既定ブランチにします。
2. `az login --tenant TENANT_ID` と `gh auth login` を済ませ、利用するAzureサブスクリプションを選びます。
3. 自分のリポジトリ名でbootstrapを実行します。

   ```sh
   python scripts/manage.py bootstrap --repository OWNER/REPOSITORY
   ```

   最初に日本リージョンのApp Service割り当てを確認します。東日本が使えない場合は西日本を選び、両方に枠がなければ作成を止めます。割り当ては物理的な空き容量の保証ではないため、最終的な作成の成否も確認します。

   初期State用Storage、Managed Identity、Entraアプリ、ロール、GitHub OIDC信頼を作り、必要なIDをGitHub Variablesへ設定します。ローカルの設定・bootstrap StateはGit対象外の `.local/` に置きます。**最初のbootstrap開始時に48時間後の期限を決め、再実行しても延長しません。**

4. mainへのアプリ・インフラ変更のPush、またはActionsの `Deploy` の手動実行でデプロイします。解説文だけの更新では再デプロイしません。

   ```sh
   gh workflow run deploy.yml --ref main
   ```

   Terraformのplan/apply → コンテナービルド・ACR Push → 2つのアプリを再起動 → 実環境の確認の順に実行します。初回はイメージの存在前にApp Serviceを作りますが、Push後の再起動と検証が成功するまでデプロイ成功とは扱いません。

5. App ServiceのフロントURLを開き、許可した本人でログインします。「商品ID PC001 の在庫は？」と質問すると、MCPの固定データである12台を根拠に回答します。画面には実際に呼んだツール名も表示されます。

## CI/CDで確認すること

`Validate` はAzure認証を使わず、テスト、lint、Terraformの構文、コンテナービルドを確認します。PRのコードにはAzureの権限を渡しません。

`Deploy` はmainのOIDCトークンだけを信頼します。フロントは起動時に自分のManaged Identityで内部検証を実行し、公開の `/health` には成功フラグとコミットSHAだけを返します。ヘルスチェックを何回呼んでも追加の推論は実行しません。

- MCPとFoundryの名前がVNetのPrivate IPに解決される。
- MCPがトークンなし・宛先違いのトークンを拒否する。
- FoundryがMCPの在庫ツールを呼び、結果を使って回答する。
- 未ログインのフロントアクセスはログインへ転送される。
- 外部からMCPへはアクセスできず、Foundryの公開アクセス・キー認証も無効になっている。
- デプロイ直後のTerraform planに差分がない。

ブラウザでのログイン成功は別に確認し、自動テストだけで検証済みとは記録しません。

## 削除する

検証後は `Cleanup` を手動実行します。`confirm_prefix` にbootstrapで表示された `azmcp` から始まる環境名を指定してください。

```sh
gh workflow run cleanup.yml --ref main -f confirm_prefix=azmcpXXXXXX
```

削除忘れに備え、毎時17分に期限を確認し、48時間を過ぎた環境を自動削除します。GitHubのスケジュールは遅れる場合があるため、厳密な48時間の停止保証ではありません。成功を確認してください。

Cleanupは対象名と所有タグを確認してから、ワークロードをTerraformで削除します。続いて今回のEntraアプリと2つのリソースグループの削除を要求します。Terraformの削除が失敗した場合も、確認済みの検証用グループに限定します。CIは自分のManaged Identityと権限も消すため、グループ削除は非同期で要求し、完了済みとは記録しません。Deploy/Cleanupを無効化した後、管理者アカウントで両グループが存在しないことを別途確認してください。

```sh
az group exists --name azmcpXXXXXX-workload
az group exists --name azmcpXXXXXX-bootstrap
```

両方が `false` になるまで削除完了とは扱いません。今回の検証では初版のCIが削除後の権限エラーで止まったため、管理者で残りを削除し、両グループ・実リソース・Entraアプリの不存在を確認しました。非同期削除への修正はテストで確認しており、新しいAzure環境を作っての再検証は行っていません。

再検証は新しい作業コピーでbootstrapから開始し、Workflowを有効化してください。検証記録とコードを削除する処理はありません。

## 費用と制限

48時間・少量利用で総額500〜800円を目安にしています。[費用概算と前提](docs/cost-estimate.md)を確認してください。1,000円のハードリミットを保証する仕組みではありません。

チャットは1プロセスで同時に1件、1分に5件、起動から100件までです。1質問につき最大4回のモデル推論と4回のツール実行、推論出力は各400 tokensです。カウンターは再起動でリセットされます。起動時の検証も少量の推論を使います。デモは本人だけに制限し、費用は実際の使用量でも確認します。

会話履歴の保存、購入・更新操作、独自ドメイン、可用性の保証は初期範囲に含めません。B1のCPUとメモリは2アプリで共有します。

## 解説と検証記録

- [Pythonから理解する初心者向け詳細解説](docs/beginner-guide.md)
- [合意した要件](docs/requirements.md)
- [設計と認証の解説](docs/architecture.md)
- [検証記録](docs/verification.md)
- [ブログの下書き](docs/blog-draft.md)
