import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional


class BaseDisplay(ABC):
    """ディスプレイインターフェースの抽象基底クラス.
    
    このクラスは、異なるディスプレイ実装（CLI、GUI等）の共通インターフェースを定義します。
    音量制御、状態更新、感情表示、キーボード監視などの機能を提供します。
    """

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.current_volume = 70  # デフォルト音量値
        self.volume_controller = None

        # 音量制御の依存関係をチェック
        try:
            from src.utils.volume_controller import VolumeController

            if VolumeController.check_dependencies():
                self.volume_controller = VolumeController()
                self.logger.info("音量制御器の初期化が成功しました")
                # システムの現在の音量を読み取り
                try:
                    self.current_volume = self.volume_controller.get_volume()
                    self.logger.info(f"システム音量を読み取りました: {self.current_volume}%")
                except Exception as e:
                    self.logger.warning(
                        f"初期システム音量の取得に失敗しました: {e}、デフォルト値 {self.current_volume}% を使用します"
                    )
            else:
                self.logger.warning("音量制御の依存関係が満たされていません、デフォルト音量制御を使用します")
        except Exception as e:
            self.logger.warning(f"音量制御器の初期化に失敗しました: {e}、模擬音量制御を使用します")

    @abstractmethod
    def set_callbacks(
        self,
        press_callback: Optional[Callable] = None,
        release_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        text_callback: Optional[Callable] = None,
        emotion_callback: Optional[Callable] = None,
        mode_callback: Optional[Callable] = None,
        auto_callback: Optional[Callable] = None,
        abort_callback: Optional[Callable] = None,
        send_text_callback: Optional[Callable] = None,
    ):  # 中断コールバックパラメータを追加
        """コールバック関数を設定します.
        
        Args:
            press_callback: ボタン押下時のコールバック
            release_callback: ボタン離し時のコールバック
            status_callback: ステータス更新コールバック
            text_callback: テキスト更新コールバック
            emotion_callback: 感情更新コールバック
            mode_callback: モード変更コールバック
            auto_callback: 自動対話コールバック
            abort_callback: 中断コールバック
            send_text_callback: テキスト送信コールバック
        """

    @abstractmethod
    def update_button_status(self, text: str):
        """ボタンのステータスを更新します.
        
        Args:
            text: 表示するボタンテキスト
        """

    @abstractmethod
    def update_status(self, status: str):
        """ステータステキストを更新します.
        
        Args:
            status: 表示するステータス文字列
        """

    @abstractmethod
    def update_text(self, text: str):
        """TTSテキストを更新します.
        
        Args:
            text: 表示するTTSテキスト
        """

    @abstractmethod
    def update_emotion(self, emotion: str):
        """感情を更新します.
        
        Args:
            emotion: 表示する感情（絵文字またはGIFファイルパス）
        """

    def get_current_volume(self):
        """現在の音量を取得します.
        
        Returns:
            int: 現在の音量レベル（0-100）
        """
        if self.volume_controller:
            try:
                # システムから最新の音量を取得
                self.current_volume = self.volume_controller.get_volume()
                # 取得成功、音量制御器が正常に動作していることをマーク
                if hasattr(self, "volume_controller_failed"):
                    self.volume_controller_failed = False
            except Exception as e:
                self.logger.debug(f"システム音量の取得に失敗しました: {e}")
                # 音量制御器の動作異常をマーク
                self.volume_controller_failed = True
        return self.current_volume

    def update_volume(self, volume: int):
        """システム音量を更新します.
        
        Args:
            volume: 設定する音量レベル（0-100）
        """
        # 音量が有効範囲内であることを確認
        volume = max(0, min(100, volume))

        # 内部音量値を更新
        self.current_volume = volume
        self.logger.info(f"音量を設定: {volume}%")

        # システム音量の更新を試行
        if self.volume_controller:
            try:
                self.volume_controller.set_volume(volume)
                self.logger.debug(f"システム音量が設定されました: {volume}%")
            except Exception as e:
                self.logger.warning(f"システム音量の設定に失敗しました: {e}")

    @abstractmethod
    def start(self):
        """ディスプレイを開始します."""

    @abstractmethod
    def on_close(self):
        """ディスプレイを閉じます."""

    @abstractmethod
    def start_keyboard_listener(self):
        """キーボード監視を開始します."""

    @abstractmethod
    def stop_keyboard_listener(self):
        """キーボード監視を停止します."""
