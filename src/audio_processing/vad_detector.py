import logging
import threading
import time

import numpy as np
import pyaudio
import webrtcvad

from src.constants.constants import AbortReason, DeviceState

# ログ設定
logger = logging.getLogger("VADDetector")


class VADDetector:
    """WebRTC VADベースの音声活動検出器。
    
    ユーザーの発話による中断を検出するために使用されます。
    音声活動検出（Voice Activity Detection）により、音声とノイズを区別し、
    一定時間連続して音声が検出された場合に中断イベントをトリガーします。
    
    特徴:
    - WebRTC VADエンジンによる高精度な音声検出
    - エネルギー閾値による誤検出の抑制
    - 連続フレーム解析による信頼性の向上
    - 独立したオーディオストリームによる干渉回避
    """

    def __init__(self, audio_codec, protocol, app_instance, loop):
        """VAD検出器を初期化します。

        Args:
            audio_codec: オーディオコーデックインスタンス
            protocol: 通信プロトコルインスタンス
            app_instance: アプリケーションインスタンス
            loop: イベントループ
        """
        self.audio_codec = audio_codec
        self.protocol = protocol
        self.app = app_instance
        self.loop = loop

        # VAD設定
        self.vad = webrtcvad.Vad()
        self.vad.set_mode(3)  # 最高感度に設定（0:最低 〜 3:最高）

        # パラメータ設定
        self.sample_rate = 16000  # サンプリングレート（Hz）
        self.frame_duration = 20  # フレーム長（ミリ秒）
        self.frame_size = int(self.sample_rate * self.frame_duration / 1000)  # フレームサイズ（サンプル数）
        self.speech_window = 5  # 中断をトリガーするのに必要な連続音声フレーム数
        self.energy_threshold = 300  # エネルギー閾値（誤検出防止用）

        # 状態変数
        self.running = False  # 検出器の実行状態
        self.paused = False  # 一時停止状態
        self.thread = None  # 検出スレッド
        self.speech_count = 0  # 連続音声フレーム数
        self.silence_count = 0  # 連続無音フレーム数
        self.triggered = False  # トリガー済みフラグ

        # メインオーディオストリームとの競合を避けるため、独立したPyAudioインスタンスとストリームを作成
        self.pa = None
        self.stream = None

    def start(self):
        """VAD検出器を開始します。
        
        独立したオーディオストリームを初期化し、
        バックグラウンドで音声活動検出を実行するスレッドを開始します。
        """
        if self.thread and self.thread.is_alive():
            logger.warning("VAD検出器は既に実行中です")
            return

        self.running = True
        self.paused = False

        # PyAudioとストリームを初期化
        self._initialize_audio_stream()

        # 検出スレッドを開始
        self.thread = threading.Thread(target=self._detection_loop, daemon=True)
        self.thread.start()
        logger.info("VAD検出器を開始しました")

    def stop(self):
        """VAD検出器を停止します。
        
        オーディオストリームを閉じ、検出スレッドを終了させます。
        """
        self.running = False

        # オーディオストリームを閉じる
        self._close_audio_stream()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        logger.info("VAD検出器を停止しました")

    def pause(self):
        """VAD検出を一時停止します。"""
        self.paused = True
        logger.info("VAD検出器を一時停止しました")

    def resume(self):
        """VAD検出を再開します。"""
        self.paused = False
        # 状態をリセット
        self.speech_count = 0
        self.silence_count = 0
        self.triggered = False
        logger.info("VAD検出器を再開しました")

    def is_running(self):
        """VAD検出器が実行中かどうかを確認します。
        
        Returns:
            bool: 実行中かつ一時停止中でない場合True
        """
        return self.running and not self.paused

    def _initialize_audio_stream(self):
        """独立したオーディオストリームを初期化します。
        
        Returns:
            bool: 初期化が成功した場合True
        """
        try:
            # PyAudioインスタンスを作成
            self.pa = pyaudio.PyAudio()

            # デフォルトの入力デバイスを取得
            device_index = None
            for i in range(self.pa.get_device_count()):
                device_info = self.pa.get_device_info_by_index(i)
                if device_info["maxInputChannels"] > 0:
                    device_index = i
                    break

            if device_index is None:
                logger.error("利用可能な入力デバイスが見つかりません")
                return False

            # 入力ストリームを作成
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.frame_size,
                start=True,
            )

            logger.info(f"VAD検出器のオーディオストリームを初期化しました。使用デバイスインデックス: {device_index}")
            return True

        except Exception as e:
            logger.error(f"VADオーディオストリームの初期化に失敗しました: {e}")
            return False

    def _close_audio_stream(self):
        """オーディオストリームを閉じます。"""
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

            if self.pa:
                self.pa.terminate()
                self.pa = None

            logger.info("VAD検出器のオーディオストリームを閉じました")
        except Exception as e:
            logger.error(f"VADオーディオストリームの終了に失敗しました: {e}")

    def _detection_loop(self):
        """VAD検出のメインループ。
        
        音声フレームを連続的に読み取り、WebRTC VADとエネルギー閾値を使用して
        音声活動を検出します。一定数の連続音声フレームが検出された場合、
        中断イベントをトリガーします。
        """
        logger.info("VAD検出ループを開始しました")

        while self.running:
            # 一時停止中またはオーディオストリームが未初期化の場合はスキップ
            if self.paused or not self.stream:
                time.sleep(0.1)
                continue

            try:
                # デバイスが話している状態でのみ検出を実行
                if self.app.device_state == DeviceState.SPEAKING:
                    # オーディオフレームを読み取り
                    frame = self._read_audio_frame()
                    if not frame:
                        time.sleep(0.01)
                        continue

                    # 音声かどうかを検出
                    is_speech = self._detect_speech(frame)

                    # 音声が検出され、トリガー条件を満たした場合、中断を処理
                    if is_speech:
                        self._handle_speech_frame(frame)
                    else:
                        self._handle_silence_frame(frame)
                else:
                    # 話していない状態の場合、状態をリセット
                    self._reset_state()

            except Exception as e:
                logger.error(f"VAD検出ループでエラーが発生しました: {e}")

            time.sleep(0.01)  # CPU使用率を下げるための小さな遅延

        logger.info("VAD検出ループを終了しました")

    def _read_audio_frame(self):
        """1フレーム分のオーディオデータを読み取ります。
        
        Returns:
            bytes: オーディオデータ、失敗した場合はNone
        """
        try:
            if not self.stream or not self.stream.is_active():
                return None

            # オーディオデータを読み取り
            data = self.stream.read(self.frame_size, exception_on_overflow=False)
            return data
        except Exception as e:
            logger.error(f"オーディオフレームの読み取りに失敗しました: {e}")
            return None

    def _detect_speech(self, frame):
        """音声かどうかを検出します。
        
        WebRTC VADとエネルギー閾値を組み合わせて、
        より正確な音声検出を行います。
        
        Args:
            frame (bytes): オーディオフレーム
            
        Returns:
            bool: 有効な音声が検出された場合True
        """
        try:
            # フレーム長が正しいことを確認
            if len(frame) != self.frame_size * 2:  # 16ビットオーディオ、サンプルあたり2バイト
                return False

            # VAD検出を使用
            is_speech = self.vad.is_speech(frame, self.sample_rate)

            # オーディオエネルギーを計算
            audio_data = np.frombuffer(frame, dtype=np.int16)
            energy = np.mean(np.abs(audio_data))

            # VADとエネルギー閾値を組み合わせ
            is_valid_speech = is_speech and energy > self.energy_threshold

            if is_valid_speech:
                logger.debug(
                    f"音声を検出しました [エネルギー: {energy:.2f}] [連続音声フレーム: {self.speech_count+1}]"
                )

            return is_valid_speech
        except Exception as e:
            logger.error(f"音声検出に失敗しました: {e}")
            return False

    def _handle_speech_frame(self, frame):
        """音声フレームを処理します。
        
        連続音声フレーム数をカウントし、閾値に達した場合に
        中断イベントをトリガーします。
        
        Args:
            frame (bytes): 音声フレーム
        """
        self.speech_count += 1
        self.silence_count = 0

        # 十分な連続音声フレームが検出されたら、中断をトリガー
        if self.speech_count >= self.speech_window and not self.triggered:
            self.triggered = True
            logger.info("持続的な音声を検出しました。中断をトリガーします！")
            self._trigger_interrupt()

            # 重複トリガーを防ぐため、即座に自身を一時停止
            self.paused = True
            logger.info("重複トリガーを防ぐため、VAD検出器を自動的に一時停止しました")

            # 状態をリセット
            self.speech_count = 0
            self.silence_count = 0
            self.triggered = False

    def _handle_silence_frame(self, frame):
        """無音フレームを処理します。
        
        Args:
            frame (bytes): 無音フレーム
        """
        self.silence_count += 1
        self.speech_count = 0

    def _reset_state(self):
        """状態をリセットします。"""
        self.speech_count = 0
        self.silence_count = 0
        self.triggered = False

    def _trigger_interrupt(self):
        """中断をトリガーします。
        
        アプリケーションに現在の音声出力を中止するよう通知します。
        """
        # アプリケーションに現在の音声出力の中止を通知
        self.app.schedule(
            lambda: self.app.abort_speaking(AbortReason.WAKE_WORD_DETECTED)
        )
