# 48時間の費用概算

確認日: 2026-11-07。Azure Retail Prices APIのJPY価格を参照した設計時の概算であり、実際の課金額ではない。取得した主要単価は[pricing-snapshot.json](pricing-snapshot.json)に記録する。

## 前提

- 日本リージョン、従量課金、Linux B1プラン1台を2つのApp Serviceで共有。App Serviceは割り当てのある西日本、Foundry・ACR・Stateは東日本を使用する。東日本・西日本のLinux B1単価はいずれも3.0064円/時だった。
- MCPとFoundryのPrivate Endpointを計2個。
- ACR Basic 1個。GitHub-hosted Runnerを利用し、常設VMは作らない。
- 小さなStateとコンテナーのみ。AIは少量の動作検証に限定。
- 作成から最大48時間を目安に削除する。作り直し時も当初の検証期限を引き継ぐ。

## 計算

| 項目 | JPY単価 | 48時間の概算 |
| --- | --- | --- |
| Linux App Service B1 × 1 | 3.0064円/時 | 約144.31円 |
| Private Endpoint × 2 | 1.5823円/個・時 | 約151.90円 |
| ACR Basic × 1 | 26.3611円/日 | 約52.72円 |
| 上記の小計 | | 約348.93円 |

上記にPrivate DNS、Storage、通信、AIトークン、適用される税などが加わる。Private DNSは利用するFoundryのエンドポイントに応じて必要なZoneを選び、3〜4 Zoneを見込む。月額79.115円/Zoneを仮に丸1か月分計上すると約237〜316円となる。実際の時間按分は請求仕様と利用時間で確認する。

gpt-4.1-mini Regionalの取得単価は入力0.0766円/1,000 tokens、出力0.3063円/1,000 tokens。例として、ツール定義・ツール結果・繰り返しの推論をすべて含めて入力100,000 tokens、出力30,000 tokensなら約16.85円。出力制限と呼び出し回数制限をアプリに設ける。

少量利用を前提に、税等の余裕を含めて総額500〜800円を目安とし、1,000円以内を目標にする。これは料金の確約や課金のハードリミットではない。利用時点の契約単価、失敗した再作成、削除の遅延、推論量で変わるため、デプロイ前にモデルと料金を再確認する。

## 削除と記録

- 検証完了時に環境を削除し、48時間後の削除も予備として設定する。
- App Serviceのアプリ停止・削除だけではプランの課金が残るため、プラン、Private Endpoint、ACR等を含めて削除する。
- 自動削除の成功を確認する。失敗時に実行できる手動削除手順も残す。
- State用Storageや認証のbootstrapリソースも削除・残存を確認する。
- 最終的な使用量とCost Managementの反映後の費用を、見積もりと分けて検証記録に追記する。

今回の環境は検証完了後に削除した。[Cost Managementの照会結果](evidence/cost-status.json)はまだ明細が空で、最終請求額は未確定。空の結果を0円とは扱わない。

## 取得元

- [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
- [App Service料金](https://azure.microsoft.com/ja-jp/pricing/details/app-service/linux/)
- [Private Link料金](https://azure.microsoft.com/en-us/pricing/details/private-link/)
- [DNS料金](https://azure.microsoft.com/en-us/pricing/details/dns/)
- [App Serviceの費用管理](https://learn.microsoft.com/en-us/azure/app-service/overview-manage-costs)
