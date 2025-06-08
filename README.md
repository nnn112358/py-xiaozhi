# py-xiaozhi
<p align="center">
  <a href="https://github.com/huangjunsen0406/py-xiaozhi/releases/latest">
    <img src="https://img.shields.io/github/v/release/huangjunsen0406/py-xiaozhi?style=flat-square&logo=github&color=blue" alt="Release"/>
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License: MIT"/>
  </a>
  <a href="https://github.com/huangjunsen0406/py-xiaozhi/stargazers">
    <img src="https://img.shields.io/github/stars/huangjunsen0406/py-xiaozhi?style=flat-square&logo=github" alt="Stars"/>
  </a>
  <a href="https://github.com/huangjunsen0406/py-xiaozhi/releases/latest">
    <img src="https://img.shields.io/github/downloads/huangjunsen0406/py-xiaozhi/total?style=flat-square&logo=github&color=52c41a1&maxAge=86400" alt="Download"/>
  </a>
  <a href="https://gitee.com/huang-jun-sen/py-xiaozhi">
    <img src="https://img.shields.io/badge/Gitee-FF5722?style=flat-square&logo=gitee" alt="Gitee"/>
  </a>
  <a href="https://huangjunsen0406.github.io/py-xiaozhi/guide/00_%E6%96%87%E6%A1%A3%E7%9B%AE%E5%BD%95.html">
    <img alt="使用ドキュメント" src="https://img.shields.io/badge/使用ドキュメント-クリックして表示-blue?labelColor=2d2d2d" />
  </a>
</p>



日本語 | [English](README.en.md)

## プロジェクト概要
py-xiaozhi は Python で実装された小智音声クライアントで、コード学習とハードウェア環境がない状況でも AI 小智の音声機能を体験することを目的としています。
本リポジトリは [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) を移植したものです

## デモ
- [Bilibili デモ動画](https://www.bilibili.com/video/BV1HmPjeSED2/#reply255921347937)

![Image](./documents/docs/guide/images/系統界面.png)

## 機能特徴
- **AI音声インタラクション**：音声入力と認識をサポートし、インテリジェントな人機交互を実現、自然で流暢な対話体験を提供。
- **視覚マルチモーダル**：画像認識と処理をサポートし、マルチモーダル交互能力を提供、画像内容を理解。
- **IoT デバイス統合**：
  - スマートホームデバイス制御をサポート、照明、音量、温度センサーなどを含む
  - Home Assistantスマートホームプラットフォームを統合、照明器具、スイッチ、数値コントローラー、ボタンデバイスを制御
  - カウントダウンタイマー機能を提供、遅延実行コマンドをサポート
  - 多種の仮想デバイスと物理デバイスドライバーを内蔵、簡単に拡張可能
- **オンライン音楽再生**：pygame基盤の高性能音楽プレーヤー、再生/一時停止/停止、進行制御、歌詞表示、ローカルキャッシュをサポート、より安定した音楽再生体験を提供。
- **音声ウェイクアップ**：ウェイクワードによる交互活性化をサポート、手動操作の煩わしさを解消（デフォルト無効、手動有効化が必要）。
- **自動対話モード**：連続対話体験を実現、ユーザー交互の流暢性を向上。
- **グラフィカルインターフェース**：直感的で使いやすい GUI を提供、小智の表情とテキスト表示をサポート、視覚体験を強化。
- **コマンドラインモード**：CLI 実行をサポート、組み込みデバイスや GUI なし環境に適用。
- **クロスプラットフォームサポート**：Windows 10+、macOS 10.15+、Linux システムと互換、いつでもどこでも使用可能。
- **音量制御**：音量調節をサポート、異なる環境ニーズに適応、統一音声制御インターフェース。
- **セッション管理**：多回対話を効果的に管理、交互の連続性を保持。
- **暗号化音声伝送**：WSS プロトコルをサポート、音声データの安全性を保障、情報漏洩を防止。
- **自動認証コード処理**：初回使用時、プログラムが自動的に認証コードをコピーしブラウザを開く、ユーザー操作を簡素化。
- **自動 MAC アドレス取得**：MAC アドレスの競合を回避、接続安定性を向上。
- **コードモジュール化**：コードを分割しクラスとして封装、職責が明確、二次開発に便利。
- **安定性最適化**：多項目の問題を修正、断線再接続、クロスプラットフォーム互換などを含む。

## システム要件
- 3.9 >= Python バージョン <= 3.12
- サポート対象 OS：Windows 10+、macOS 10.15+、Linux
- マイクとスピーカーデバイス

## まず最初にお読みください！
- [プロジェクトドキュメント](https://huangjunsen0406.github.io/py-xiaozhi/) を詳しくお読みください　起動チュートリアルとファイル説明が含まれています
- main は最新コード、更新の度に手動で pip 依存関係を再インストールする必要があります。新しい依存関係を追加した後、ローカルに存在しない可能性があるためです

[ゼロから始める小智クライアント使用方法（動画チュートリアル）](https://www.bilibili.com/video/BV1dWQhYEEmq/?vd_source=2065ec11f7577e7107a55bbdc3d12fce)

## 設定システム
プロジェクトは階層設定システムを使用し、主に以下を含みます：

1. **基本設定**：基本実行パラメータの設定、`config/config.json` に配置
2. **デバイス活性化**：デバイス身元情報、`config/efuse.json` に保存
3. **ウェイクワード設定**：音声ウェイクアップ関連設定
4. **IoT デバイス**：各種 IoT デバイスの設定をサポート、温度センサーと Home Assistant 統合を含む

詳細設定説明については [設定説明ドキュメント](./documents/docs/guide/02_設定説明.md) をご参照ください

## IoT 機能
py-xiaozhi は豊富な IoT デバイス制御機能を提供：

- **仮想デバイス**：照明制御、音量調節、カウントダウンタイマーなど
- **物理デバイス統合**：温度センサー、カメラなど
- **Home Assistant 統合**：HTTP API を通じてスマートホームシステムに接続
- **カスタムデバイス拡張**：完全なデバイス定義と登録フレームワークを提供

サポートするデバイスタイプと使用例については [IoT 機能説明](./documents/docs/guide/05_IoT機能説明.md) をご参照ください

## 状態遷移図

```
                        +----------------+
                        |                |
                        v                |
+------+  ウェイクワード/ボタン  +------------+   |   +------------+
| IDLE | -----------> | CONNECTING | --+-> | LISTENING  |
+------+              +------------+       +------------+
   ^                                            |
   |                                            | 音声認識完了
   |          +------------+                    v
   +--------- |  SPEAKING  | <-----------------+
     再生完了 +------------+
```

## 実装予定機能
- [ ] **新 GUI（Electron）**：より現代的で美しいユーザーインターフェースを提供、交互体験を最適化。

## よくある質問
- **音声デバイスが見つからない**：マイクとスピーカーが正常に接続され有効になっているか確認してください。
- **ウェイクワードが反応しない**：`config.json` の `USE_WAKE_WORD` 設定が `true` になっているか、モデルパスが正しいか確認してください。
- **ネットワーク接続失敗**：ネットワーク設定とファイアウォール設定を確認し、WebSocket または MQTT 通信がブロックされていないことを確認してください。
- **パッケージ化失敗**：PyInstaller がインストール済み (`pip install pyinstaller`) で、すべての依存関係がインストールされていることを確認してください。その後 `python scripts/build.py` を再実行してください
- **IoT デバイスが反応しない**：対応するデバイスの設定情報が正しいか確認してください。Home Assistant の URL と Token など。

## 関連サードパーティオープンソースプロジェクト
[小智スマートフォン端末](https://github.com/TOM88812/xiaozhi-android-client)

[xiaozhi-esp32-server（オープンソースサーバー）](https://github.com/xinnan-tech/xiaozhi-esp32-server)

[XiaoZhiAI_server32_Unity(Unity 開発)](https://gitee.com/vw112266/XiaoZhiAI_server32_Unity)

[IntelliConnect(AIoT ミドルウェア)](https://github.com/ruanrongman/IntelliConnect)

[open-xiaoai(小愛スピーカー小智接続)](https://github.com/idootop/open-xiaoai.git)

## プロジェクト構造

```
├── .github                 # GitHub 関連設定
├── assets                  # リソースファイル（表情アニメーションなど）
├── cache                   # キャッシュディレクトリ（音楽などの一時ファイル）
├── config                  # 設定ファイルディレクトリ
├── documents               # ドキュメントディレクトリ
├── hooks                   # PyInstaller フックディレクトリ
├── libs                    # 依存ライブラリディレクトリ
├── scripts                 # ユーティリティスクリプトディレクトリ
├── src                     # ソースコードディレクトリ
│   ├── audio_codecs        # 音声エンコード・デコードモジュール
│   ├── audio_processing    # 音声処理モジュール
│   ├── constants           # 定数定義
│   ├── display             # 表示インターフェースモジュール
│   ├── iot                 # IoT デバイス関連モジュール
│   │   └── things          # 具体的デバイス実装ディレクトリ
│   ├── network             # ネットワーク通信モジュール
│   ├── protocols           # 通信プロトコルモジュール
│   └── utils               # ユーティリティクラスモジュール
```

## 貢献ガイド
問題報告とコード貢献を歓迎します。以下の規範に従ってください：

1. コードスタイルが PEP8 規範に準拠
2. 提出する PR に適切なテストを含む
3. 関連ドキュメントを更新

## コミュニティとサポート

### 以下のオープンソース貢献者に感謝
> 順不同

[Xiaoxia](https://github.com/78)
[zhh827](https://github.com/zhh827)
[四博智联-李洪刚](https://github.com/SmartArduino)
[HonestQiao](https://github.com/HonestQiao)
[vonweller](https://github.com/vonweller)
[孙卫公](https://space.bilibili.com/416954647)
[isamu2025](https://github.com/isamu2025)
[Rain120](https://github.com/Rain120)
[kejily](https://github.com/kejily)
[电波bilibili君](https://space.bilibili.com/119751)

### スポンサーサポート

<div align="center">
  <h3>すべてのスポンサーのサポートに感謝 ❤️</h3>
  <p>インターフェースリソース、デバイス互換性テスト、資金サポートにかかわらず、すべての支援がプロジェクトをより完璧にしています</p>
  
  <a href="https://huangjunsen0406.github.io/py-xiaozhi/sponsors/" target="_blank">
    <img src="https://img.shields.io/badge/表示-スポンサー一覧-brightgreen?style=for-the-badge&logo=github" alt="スポンサー一覧">
  </a>
  <a href="https://huangjunsen0406.github.io/py-xiaozhi/sponsors/" target="_blank">
    <img src="https://img.shields.io/badge/なる-プロジェクトスポンサー-orange?style=for-the-badge&logo=heart" alt="スポンサーになる">
  </a>
</div>

## プロジェクト統計
[![Star History Chart](https://api.star-history.com/svg?repos=huangjunsen0406/py-xiaozhi&type=Date)](https://www.star-history.com/#huangjunsen0406/py-xiaozhi&Date)

## ライセンス
[MIT License](LICENSE)