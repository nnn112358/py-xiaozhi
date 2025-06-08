---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: "PY-XIAOZHI"
  tagline: py-xiaozhi は Python で実装された小智音声クライアントで、コード学習と、ハードウェア条件がない環境での AI 小智の音声機能体験を目的としています。
  actions:
    - theme: brand
      text: 使用開始
      link: /guide/00_ドキュメント目次
    - theme: alt
      text: ソースコード表示
      link: https://github.com/huangjunsen0406/py-xiaozhi

features:
  - title: AI音声インタラクション
    details: 音声入力と認識をサポートし、インテリジェントな人機交互を実現、自然で流暢な対話体験を提供。
  - title: 視覚マルチモーダル
    details: 画像認識と処理をサポートし、マルチモーダル交互作用能力を提供、画像内容を理解。
  - title: IoT デバイス統合
    details: スマートホームデバイス制御をサポート、照明、音量、温度センサーなどを含み、Home Assistant スマートホームプラットフォームを統合、カウントダウンタイマー機能を提供、複数の仮想デバイスと物理デバイスドライバーを内蔵、簡単に拡張可能。
  - title: ネットワーク音楽再生
    details: pygame ベースの高性能音楽プレーヤーを実装、再生/一時停止/停止、進行制御、歌詞表示とローカルキャッシュをサポート、より安定した音楽再生体験を提供。
  - title: 音声ウェイクアップ
    details: ウェイクワードによる交互作用の起動をサポート、手動操作の煩わしさを解消（デフォルトでは無効、手動で有効化が必要）。
  - title: 自動対話モード
    details: 連続対話体験を実現し、ユーザー交互作用の流暢性を向上。
  - title: グラフィカルインターフェース
    details: 直感的で使いやすい GUI を提供、小智の表情とテキスト表示をサポート、視覚体験を強化。
  - title: コマンドラインモード
    details: CLI 実行をサポート、組み込みデバイスや GUI なし環境に適用。
  - title: クロスプラットフォームサポート
    details: Windows 10+、macOS 10.15+ と Linux システムに対応、いつでもどこでも使用可能。
  - title: 音量制御
    details: 音量調整をサポート、異なる環境ニーズに適応、統一された音声制御インターフェース。
  - title: 暗号化音声伝送
    details: WSS プロトコルをサポート、音声データのセキュリティを保障、情報漏洩を防止。
  - title: 自動認証コード処理
    details: 初回使用時、プログラムが自動で認証コードをコピーしてブラウザを開き、ユーザー操作を簡素化。
---

<div class="developers-section">
  <p>py-xiaozhi への貢献をいただいた以下の開発者の皆様に感謝します</p>
  
  <div class="contributors-wrapper">
    <a href="https://github.com/huangjunsen0406/py-xiaozhi/graphs/contributors" class="contributors-link">
      <img src="https://contrib.rocks/image?repo=huangjunsen0406/py-xiaozhi&max=1000" alt="contributors" class="contributors-image"/>
    </a>
  </div>
  
  <div class="developers-actions">
    <a href="/py-xiaozhi/contributors" class="dev-button">特別貢献者を表示</a>
    <a href="/py-xiaozhi/contributing" class="dev-button outline">貢献に参加する方法</a>
  </div>

</div>

<style>
.developers-section {
  text-align: center;
  max-width: 960px;
  margin: 4rem auto 0;
  padding: 2rem;
  border-top: 1px solid var(--vp-c-divider);
}

.developers-section h2 {
  margin-bottom: 0.5rem;
  color: var(--vp-c-brand);
}

.contributors-wrapper {
  margin: 2rem auto;
  max-width: 800px;
  position: relative;
  overflow: hidden;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.contributors-wrapper:hover {
  transform: translateY(-5px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.contributors-link {
  display: block;
  text-decoration: none;
  background-color: var(--vp-c-bg-soft);
}

.contributors-image {
  width: 100%;
  height: auto;
  display: block;
  transition: all 0.3s ease;
}


.developers-actions {
  display: flex;
  gap: 1rem;
  justify-content: center;
  margin-top: 1.5rem;
}

.developers-actions a {
  text-decoration: none;
}

.dev-button {
  display: inline-block;
  border-radius: 20px;
  padding: 0.5rem 1.5rem;
  font-weight: 500;
  transition: all 0.2s ease;
  text-decoration: none;
}

.dev-button:not(.outline) {
  background-color: var(--vp-c-brand);
  color: white;
}

.dev-button.outline {
  border: 1px solid var(--vp-c-brand);
  color: var(--vp-c-brand);
}

.dev-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

@media (max-width: 640px) {
  .developers-actions {
    flex-direction: column;
  }
  
  .contributors-wrapper {
    margin: 1.5rem auto;
  }
}

.join-message {
  text-align: center;
  margin-top: 2rem;
  padding: 2rem;
  border-top: 1px solid var(--vp-c-divider);
}

.join-message h3 {
  margin-bottom: 1rem;
}
</style>

