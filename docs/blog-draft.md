# Entra IDで守るApp Service・MCP・FoundryをTerraformとGitHub Actionsで作る

> 執筆用の下書き。実測値・実環境の成功可否は[検証記録](verification.md)を根拠に追記する。

## 作りたいもの

ログインした利用者が「商品ID PC001 の在庫は？」と質問すると、AIがMCPツールで在庫を照会し、その結果を使って答える。フロントとMCPは別のApp Service、モデルはFoundryから呼び出すAzure OpenAIのgpt-4.1-miniを使う。

制約は日本リージョン、検証1〜2日、予算約1,000円。そこで2つのアプリはLinux B1プランを共有し、GitHub-hosted RunnerとACRを使う。

## 認証を3つの経路で考える

利用者→フロントはEntra IDログイン、フロント→MCPはManaged IdentityとMCP専用のアプリロール、フロント→FoundryはManaged IdentityとAzure RBACを使う。ユーザーのトークンを下流へ引き回す構成にはしない。

認証フローと設定の詳細は[設計解説](architecture.md)にまとめた。ログインの認可コード交換もManaged Identityのフェデレーションを使い、クライアントシークレットの管理を減らす。

## VNet統合だけではMCPは非公開にならない

VNet統合はフロントの送信に使う。MCPの受信にはPrivate Endpointを作り、公開アクセスを無効化する。Foundryも同様に非公開化し、Private DNS ZoneをVNetへリンクする。統合用とPrivate Endpoint用のSubnetは分ける。

## AIはどこでMCPを呼ぶのか

今回はFoundry Agent Serviceを使わず、フロントのPythonが処理のループを実装する。MCPからツールのスキーマを取得し、モデルへ渡し、モデルの要求をMCPのツール呼び出しに変換する。モデル自体にAzureやMCPの認証情報を渡す必要はない。

## 非公開のApp Serviceへのデプロイをどうするか

SCMへ直接ソースを送る方式には、Runnerから非公開エンドポイントへの経路が必要になる。今回はコンテナーイメージをACRへ置き、App Service自身がManaged Identityで取得する。Azure管理APIの操作はGitHub OIDCで認証する。

デプロイの成功条件は「Terraformが終了した」だけではない。新しいコミットのコンテナーが動き、Private DNS・不正な認証の拒否・実モデルとMCPの連携まで通ったことを確認する。

## 実際の検証で記録するもの

初回はGitHub OIDCのsubject不一致で `AADSTS700213` が発生した。2026年7月以降の新規リポジトリには所有者・リポジトリの不変IDが含まれるため、旧形式の名前だけのsubjectでは認証できなかった。GitHubの設定APIからprefixを取得し、Terraformへ渡す方法に修正した。[公式仕様](https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims)

また、Foundryの `project_management_enabled = true` には、Foundryリソース自身のManaged Identityが必要だった。`terraform validate` は通っても、この前提はplanで検出された。System Assigned Identityを追加して実接続のplanを確認した。フロントがMCPやFoundryを呼ぶIDとは別のIDである。

東日本でApp Serviceを作る際には、権限があってもB1の割り当てが0で失敗した。App Service用の地域別Usage APIを確認すると、西日本には地域VM枠があった。App ServiceとVNetを西日本、モデルを東日本に分け、今後は作成前に割り当てを確認するようにした。Owner権限、モデルのクォータ、App Serviceのクォータは別々に確認する必要がある。

リージョンを変えるときは名前と依存関係も見直した。同名のNSGを異なるリージョンに作り直す操作は競合し、VNetの削除で消えたSubnetの再作成も必要だった。ネットワーク名にリージョンを含めて親子の変更をTerraformへ明示するようにした。

- GitHub Actionsの成功した実行へのリンク。
- 未ログイン時の遷移と本人でのログイン。
- 画面の在庫回答と呼び出したツール名。
- トークンなし・誤ったaudienceの拒否、Private IP解決の検証結果。
- コードを変更して再デプロイした結果。
- Terraform再実行時の差分と、削除後の残存確認。
- 見積もりと実際の課金の差。未反映の費用は未確定として扱う。

## 削除までIaCの検証に含める

App Serviceを止めるだけではプランの課金は止まらない。検証後はプラン、Private Endpoint、ACR、State用Storageを含めて削除する。48時間後の期限チェックも用意し、GitHubのスケジュール遅延を前提に削除の成功まで確認する。

コードの再現手順は[README](../README.md)、見積もりの計算は[費用概算](cost-estimate.md)を参照する。
