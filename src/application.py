"""小智ESP32アプリケーションのメインモジュール

このモジュールは小智ESP32システムのコアアプリケーションクラスを提供します。
音声認識、TTS、IoTデバイス制御、ウェイクワード検出などの機能を統合管理します。
"""

import asyncio
import json
import platform
import sys
import threading
import time
from pathlib import Path

from src.constants.constants import (
    AbortReason,
    AudioConfig,
    DeviceState,
    EventType,
    ListeningMode,
)
from src.display import cli_display, gui_display
from src.protocols.mqtt_protocol import MqttProtocol
from src.protocols.websocket_protocol import WebsocketProtocol
from src.utils.common_utils import handle_verification_code
from src.utils.config_manager import ConfigManager
from src.utils.logging_config import get_logger

# opuslibをインポートする前にopus動的ライブラリを処理
from src.utils.opus_loader import setup_opus

setup_opus()

# ロギング設定
logger = get_logger(__name__)

# opuslibをインポート
try:
    import opuslib  # noqa: F401
except Exception as e:
    logger.critical("opuslibのインポートに失敗: %s", e, exc_info=True)
    logger.critical("opus動的ライブラリが正しくインストールされているか、正しい場所にあることを確認してください")
    sys.exit(1)


class Application:
    """小智ESP32システムのメインアプリケーションクラス
    
    このクラスはシステム全体を管理し、以下の機能を提供します：
    - 音声認識（STT）
    - 音声合成（TTS）
    - ウェイクワード検出
    - IoTデバイス制御
    - ネットワーク通信（WebSocket/MQTT）
    - GUI/CLIインターフェース
    
    シングルトンパターンを使用して、アプリケーション全体で単一のインスタンスを保証します。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        """シングルトンインスタンスを取得
        
        Returns:
            Application: アプリケーションのシングルトンインスタンス
        """
        if cls._instance is None:
            logger.debug("Applicationシングルトンインスタンスを作成")
            cls._instance = Application()
        return cls._instance

    def __init__(self):
        """アプリケーションを初期化
        
        Note:
            このコンストラクタは直接呼び出さず、get_instance()を使用してください
        """
        # シングルトンパターンの確保
        if Application._instance is not None:
            logger.error("Applicationの複数インスタンス作成を試行")
            raise Exception("Applicationはシングルトンクラスです。get_instance()を使用してインスタンスを取得してください")
        Application._instance = self

        logger.debug("Applicationインスタンスを初期化")
        
        # 設定管理器インスタンスを取得
        self.config = ConfigManager.get_instance()
        self.config._initialize_mqtt_info()
        
        # システム状態変数
        self.device_state = DeviceState.IDLE  # デバイスの現在の状態
        self.voice_detected = False  # 音声検出フラグ
        self.keep_listening = False  # 継続リスニングフラグ
        self.aborted = False  # 中断フラグ
        self.current_text = ""  # 現在表示中のテキスト
        self.current_emotion = "neutral"  # 現在の感情表現

        # 音声処理関連
        self.audio_codec = None  # _initialize_audioで初期化される
        self._tts_lock = threading.Lock()  # TTS状態のスレッドセーフアクセス用
        # DisplayのプレイステートはGUIでのみ使用され、Music_playerでは不便なため、
        # TTSが再生中であることを示すフラグを追加
        self.is_tts_playing = False

        # イベントループとスレッド管理
        self.loop = asyncio.new_event_loop()  # 非同期処理用イベントループ
        self.loop_thread = None  # イベントループ実行スレッド
        self.running = False  # アプリケーション実行フラグ
        self.input_event_thread = None  # 音声入力イベント処理スレッド
        self.output_event_thread = None  # 音声出力イベント処理スレッド

        # タスクキューとロック
        self.main_tasks = []  # メインスレッドで実行されるタスクキュー
        self.mutex = threading.Lock()  # タスクキューの排他制御用

        # 通信プロトコルインスタンス
        self.protocol = None  # WebSocket/MQTTプロトコル

        # コールバック関数リスト
        self.on_state_changed_callbacks = []  # 状態変更時のコールバック

        # イベントオブジェクトの初期化
        self.events = {
            EventType.SCHEDULE_EVENT: threading.Event(),
            EventType.AUDIO_INPUT_READY_EVENT: threading.Event(),
            EventType.AUDIO_OUTPUT_READY_EVENT: threading.Event(),
        }

        # 表示インターフェース
        self.display = None  # GUI/CLIディスプレイインスタンス

        # ウェイクワード検出器
        self.wake_word_detector = None
        logger.debug("Applicationインスタンスの初期化完了")

    def run(self, **kwargs):
        """アプリケーションを起動
        
        Args:
            **kwargs: 起動オプション
                mode (str): 表示モード ('gui' または 'cli')
                protocol (str): 通信プロトコル ('websocket' または 'mqtt')
        """
        logger.info("アプリケーションを起動、パラメータ: %s", kwargs)
        mode = kwargs.get("mode", "gui")
        protocol = kwargs.get("protocol", "websocket")

        # メインループスレッドを起動
        logger.debug("メインループスレッドを起動")
        main_loop_thread = threading.Thread(target=self._main_loop)
        main_loop_thread.daemon = True
        main_loop_thread.start()

        # 通信プロトコルを初期化
        logger.debug("プロトコルタイプを設定: %s", protocol)
        self.set_protocol_type(protocol)

        # イベントループスレッドを作成・起動
        logger.debug("イベントループスレッドを起動")
        self.loop_thread = threading.Thread(target=self._run_event_loop)
        self.loop_thread.daemon = True
        self.loop_thread.start()

        # イベントループの準備完了を待機
        time.sleep(0.1)

        # アプリケーションコンポーネントを初期化（自動接続は除外）
        logger.debug("アプリケーションコンポーネントを初期化")
        asyncio.run_coroutine_threadsafe(self._initialize_without_connect(), self.loop)

        # IoTデバイスを初期化
        self._initialize_iot_devices()

        logger.debug("表示タイプを設定: %s", mode)
        self.set_display_type(mode)
        # 表示インターフェースを起動
        logger.debug("表示インターフェースを起動")
        self.display.start()

    def _run_event_loop(self):
        """イベントループを実行するスレッド関数
        
        非同期処理用のイベントループを別スレッドで実行します。
        """
        logger.debug("イベントループを設定して起動")
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def set_is_tts_playing(self, value: bool):
        """TTS再生状態を設定
        
        Args:
            value (bool): TTS再生状態
        """
        with self._tts_lock:
            self.is_tts_playing = value

    def get_is_tts_playing(self) -> bool:
        """TTS再生状態を取得
        
        Returns:
            bool: TTS再生中の場合True、そうでなければFalse
        """
        with self._tts_lock:
            return self.is_tts_playing

    async def _initialize_without_connect(self):
        """アプリケーションコンポーネントを初期化（接続は確立しない）
        
        システムの基本コンポーネントを初期化しますが、
        サーバーへの接続は確立しません。
        """
        logger.info("アプリケーションコンポーネントを初期化中...")

        # デバイス状態を待機状態に設定
        logger.debug("初期デバイス状態をIDLEに設定")
        self.schedule(lambda: self.set_device_state(DeviceState.IDLE))

        # 音声コーデックを初期化
        logger.debug("音声コーデックを初期化")
        self._initialize_audio()

        # ウェイクワード検出を初期化・起動
        self._initialize_wake_word_detector()

        # ネットワークプロトコルのコールバックを設定（MQTT および WebSocket）
        logger.debug("プロトコルコールバック関数を設定")
        self.protocol.on_network_error = self._on_network_error
        self.protocol.on_incoming_audio = self._on_incoming_audio
        self.protocol.on_incoming_json = self._on_incoming_json
        self.protocol.on_audio_channel_opened = self._on_audio_channel_opened
        self.protocol.on_audio_channel_closed = self._on_audio_channel_closed

        logger.info("アプリケーションコンポーネントの初期化完了")

    def _initialize_audio(self):
        """音声デバイスとコーデックを初期化
        
        音声の入出力ストリームとOpusコーデックを初期化します。
        また、システム音量コントローラーの利用可能性もチェックします。
        """
        try:
            logger.debug("音声コーデックの初期化を開始")
            from src.audio_codecs.audio_codec import AudioCodec

            self.audio_codec = AudioCodec()
            logger.info("音声コーデックの初期化成功")

            # 音量制御の状態を記録
            has_volume_control = (
                hasattr(self.display, "volume_controller")
                and self.display.volume_controller
            )
            if has_volume_control:
                logger.info("システム音量制御が有効")
            else:
                logger.info("システム音量制御が無効、シミュレート音量制御を使用")

        except Exception as e:
            logger.error("音声デバイスの初期化に失敗: %s", e, exc_info=True)
            self.alert("エラー", f"音声デバイスの初期化に失敗: {e}")

    def set_protocol_type(self, protocol_type: str):
        """プロトコルタイプを設定
        
        Args:
            protocol_type (str): プロトコルタイプ ('mqtt' または 'websocket')
        """
        logger.debug("プロトコルタイプを設定: %s", protocol_type)
        if protocol_type == "mqtt":
            self.protocol = MqttProtocol(self.loop)
            logger.debug("MQTTプロトコルインスタンスを作成")
        else:  # websocket
            self.protocol = WebsocketProtocol()
            logger.debug("WebSocketプロトコルインスタンスを作成")

    def set_display_type(self, mode: str):
        """表示インターフェースを初期化
        
        Args:
            mode (str): 表示モード ('gui' または 'cli')
        """
        logger.debug("表示インターフェースタイプを設定: %s", mode)
        # アダプターパターンで異なる表示モードを管理
        if mode == "gui":
            self.display = gui_display.GuiDisplay()
            logger.debug("GUI表示インターフェースを作成")
            self.display.set_callbacks(
                press_callback=self.start_listening,
                release_callback=self.stop_listening,
                status_callback=self._get_status_text,
                text_callback=self._get_current_text,
                emotion_callback=self._get_current_emotion,
                mode_callback=self._on_mode_changed,
                auto_callback=self.toggle_chat_state,
                abort_callback=lambda: self.abort_speaking(
                    AbortReason.WAKE_WORD_DETECTED
                ),
                send_text_callback=self._send_text_tts,
            )
        else:
            self.display = cli_display.CliDisplay()
            logger.debug("CLI表示インターフェースを作成")
            self.display.set_callbacks(
                auto_callback=self.toggle_chat_state,
                abort_callback=lambda: self.abort_speaking(
                    AbortReason.WAKE_WORD_DETECTED
                ),
                status_callback=self._get_status_text,
                text_callback=self._get_current_text,
                emotion_callback=self._get_current_emotion,
                send_text_callback=self._send_text_tts,
            )
        logger.debug("表示インターフェースのコールバック関数設定完了")

    def _main_loop(self):
        """アプリケーションのメインループ
        
        イベントを監視し、適切なハンドラーを呼び出します。
        音声入力、音声出力、スケジュールされたタスクの処理を行います。
        """
        logger.info("メインループを起動")
        self.running = True

        while self.running:
            # イベントを待機
            for event_type, event in self.events.items():
                if event.is_set():
                    event.clear()
                    logger.debug("イベントを処理: %s", event_type)

                    if event_type == EventType.AUDIO_INPUT_READY_EVENT:
                        self._handle_input_audio()
                    elif event_type == EventType.AUDIO_OUTPUT_READY_EVENT:
                        self._handle_output_audio()
                    elif event_type == EventType.SCHEDULE_EVENT:
                        self._process_scheduled_tasks()

            # CPU使用率を抑えるための短時間スリープ
            time.sleep(0.01)

    def _process_scheduled_tasks(self):
        """スケジュールされたタスクを処理
        
        メインスレッドキューに登録されたタスクを順次実行します。
        """
        with self.mutex:
            tasks = self.main_tasks.copy()
            self.main_tasks.clear()

        logger.debug("%d個のスケジュールタスクを処理", len(tasks))
        for task in tasks:
            try:
                task()
            except Exception as e:
                logger.error("スケジュールタスクの実行中にエラー: %s", e, exc_info=True)

    def schedule(self, callback):
        """タスクをメインループにスケジュール
        
        Args:
            callback: 実行する関数またはラムダ
        """
        with self.mutex:
            self.main_tasks.append(callback)
        self.events[EventType.SCHEDULE_EVENT].set()

    def _handle_input_audio(self):
        """音声入力を処理
        
        リスニング状態の時に音声データを読み取り、サーバーに送信します。
        """
        if self.device_state != DeviceState.LISTENING:
            return

        # 音声データを読み取って送信
        encoded_data = self.audio_codec.read_audio()
        if encoded_data and self.protocol and self.protocol.is_audio_channel_opened():
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_audio(encoded_data), self.loop
            )

    async def _send_text_tts(self, text):
        """テキストをウェイクワードとして送信
        
        Args:
            text (str): 送信するテキスト
        """
        if not self.protocol.is_audio_channel_opened():
            await self.protocol.open_audio_channel()

        await self.protocol.send_wake_word_detected(text)

    def _handle_output_audio(self):
        """音声出力を処理
        
        話している状態の時に音声データを再生します。
        """
        if self.device_state != DeviceState.SPEAKING:
            return
        self.set_is_tts_playing(True)  # 再生開始
        self.audio_codec.play_audio()

    def _on_network_error(self, error_message=None):
        """ネットワークエラーのコールバック
        
        Args:
            error_message (str, optional): エラーメッセージ
        """
        if error_message:
            logger.error(error_message)

        self.keep_listening = False
        self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
        # ウェイクワード検出を復旧
        if self.wake_word_detector and self.wake_word_detector.paused:
            self.wake_word_detector.resume()

        if self.device_state != DeviceState.CONNECTING:
            logger.info("接続断線を検出")
            self.schedule(lambda: self.set_device_state(DeviceState.IDLE))

            # 既存の接続を閉じるが、音声ストリームは閉じない
            if self.protocol:
                asyncio.run_coroutine_threadsafe(
                    self.protocol.close_audio_channel(), self.loop
                )

    def _on_incoming_audio(self, data):
        """音声データ受信コールバック
        
        Args:
            data: 受信した音声データ
        """
        if self.device_state == DeviceState.SPEAKING:
            self.audio_codec.write_audio(data)
            self.events[EventType.AUDIO_OUTPUT_READY_EVENT].set()

    def _on_incoming_json(self, json_data):
        """JSONデータ受信コールバック
        
        Args:
            json_data: 受信したJSONデータ
        """
        try:
            if not json_data:
                return

            # JSONデータを解析
            if isinstance(json_data, str):
                data = json.loads(json_data)
            else:
                data = json_data
            # 異なるタイプのメッセージを処理
            msg_type = data.get("type", "")
            if msg_type == "tts":
                self._handle_tts_message(data)
            elif msg_type == "stt":
                self._handle_stt_message(data)
            elif msg_type == "llm":
                self._handle_llm_message(data)
            elif msg_type == "iot":
                self._handle_iot_message(data)
            else:
                logger.warning(f"未知のタイプのメッセージを受信: {msg_type}")
        except Exception as e:
            logger.error(f"JSONメッセージの処理中にエラー: {e}")

    def _handle_tts_message(self, data):
        """TTSメッセージを処理
        
        Args:
            data: TTSメッセージデータ
        """
        state = data.get("state", "")
        if state == "start":
            self.schedule(lambda: self._handle_tts_start())
        elif state == "stop":
            self.schedule(lambda: self._handle_tts_stop())
        elif state == "sentence_start":
            text = data.get("text", "")
            if text:
                logger.info(f"<< {text}")
                self.schedule(lambda: self.set_chat_message("assistant", text))

                # 認証コード情報が含まれているかチェック
                import re

                match = re.search(r"((?:\d\s*){6,})", text)
                if match:
                    self.schedule(lambda: handle_verification_code(text))

    def _handle_tts_start(self):
        """TTS開始イベントを処理
        
        TTS再生の開始時に必要な状態設定と音声キューのクリアを行います。
        """
        self.aborted = False
        self.set_is_tts_playing(True)  # 再生開始
        # 既存の古い音声データをクリア
        self.audio_codec.clear_audio_queue()

        if (
            self.device_state == DeviceState.IDLE
            or self.device_state == DeviceState.LISTENING
        ):
            self.schedule(lambda: self.set_device_state(DeviceState.SPEAKING))

        # VAD検出器復旧のコードはコメントアウト
        # if hasattr(self, 'vad_detector') and self.vad_detector:
        #     self.vad_detector.resume()

    def _handle_tts_stop(self):
        """TTS停止イベントを処理
        
        TTS再生の終了時に音声キューの完全な再生を待機し、
        その後適切な状態に遷移します。
        """
        if self.device_state == DeviceState.SPEAKING:
            # 音声再生にバッファ時間を与え、すべての音声が再生完了することを保証
            def delayed_state_change():
                # 音声キューが空になるまで待機
                # 音声が完全に再生されることを保証するため、待機再試行回数を増加
                max_wait_attempts = 30  # 待機試行回数を増加
                wait_interval = 0.1  # 各回の待機時間間隔
                attempts = 0

                # キューが空になるまで、または最大試行回数を超えるまで待機
                while (
                    not self.audio_codec.audio_decode_queue.empty()
                    and attempts < max_wait_attempts
                ):
                    time.sleep(wait_interval)
                    attempts += 1

                # すべてのデータが再生されることを保証
                # 最後のデータが処理されることを保証するため、さらに少し待機
                if self.get_is_tts_playing():
                    time.sleep(0.5)

                # TTS再生状態をFalseに設定
                self.set_is_tts_playing(False)

                # 状態遷移
                if self.keep_listening:
                    asyncio.run_coroutine_threadsafe(
                        self.protocol.send_start_listening(ListeningMode.AUTO_STOP),
                        self.loop,
                    )
                    self.schedule(lambda: self.set_device_state(DeviceState.LISTENING))
                else:
                    self.schedule(lambda: self.set_device_state(DeviceState.IDLE))

            # --- 入力ストリームの強制再初期化 ---
            if platform.system() == "Linux":

                try:
                    if self.audio_codec:
                        self.audio_codec._reinitialize_stream(
                            is_input=True
                        )  # 再初期化を呼び出し
                    else:
                        logger.warning(
                            "強制再初期化できません、audio_codecがNoneです。"
                        )
                except Exception as force_reinit_e:
                    logger.error(
                        f"強制再初期化に失敗: {force_reinit_e}",
                        exc_info=True,
                    )
                    self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
                    if self.wake_word_detector and self.wake_word_detector.paused:
                        self.wake_word_detector.resume()
                    return
            # --- 強制再初期化終了 ---

            # 遅延実行をスケジュール
            # threading.Thread(target=delayed_state_change, daemon=True).start()
            self.schedule(delayed_state_change)

    def _handle_stt_message(self, data):
        """STTメッセージを処理
        
        Args:
            data: STTメッセージデータ
        """
        text = data.get("text", "")
        if text:
            logger.info(f">> {text}")
            self.schedule(lambda: self.set_chat_message("user", text))

    def _handle_llm_message(self, data):
        """LLMメッセージを処理
        
        Args:
            data: LLMメッセージデータ
        """
        emotion = data.get("emotion", "")
        if emotion:
            self.schedule(lambda: self.set_emotion(emotion))

    async def _on_audio_channel_opened(self):
        """音声チャンネルオープンコールバック
        
        音声チャンネルが開かれた時に音声ストリームを開始し、
        IoTデバイス記述子を送信します。
        """
        logger.info("音声チャンネルが開かれました")
        self.schedule(lambda: self._start_audio_streams())

        # IoTデバイス記述子を送信
        from src.iot.thing_manager import ThingManager

        thing_manager = ThingManager.get_instance()
        asyncio.run_coroutine_threadsafe(
            self.protocol.send_iot_descriptors(thing_manager.get_descriptors_json()),
            self.loop,
        )
        self._update_iot_states(False)

    def _start_audio_streams(self):
        """音声ストリームを開始
        
        入力・出力ストリームがアクティブでない場合に開始し、
        音声処理用のイベントトリガースレッドを起動します。
        """
        try:
            # ストリームを閉じて再開することはせず、アクティブ状態であることのみを確保
            if (
                self.audio_codec.input_stream
                and not self.audio_codec.input_stream.is_active()
            ):
                try:
                    self.audio_codec.input_stream.start_stream()
                except Exception as e:
                    logger.warning(f"入力ストリーム開始時にエラー: {e}")
                    # エラー時のみ再初期化
                    self.audio_codec._reinitialize_stream(is_input=True)

            if (
                self.audio_codec.output_stream
                and not self.audio_codec.output_stream.is_active()
            ):
                try:
                    self.audio_codec.output_stream.start_stream()
                except Exception as e:
                    logger.warning(f"出力ストリーム開始時にエラー: {e}")
                    # エラー時のみ再初期化
                    self.audio_codec._reinitialize_stream(is_input=False)

            # イベントトリガーを設定
            if (
                self.input_event_thread is None
                or not self.input_event_thread.is_alive()
            ):
                self.input_event_thread = threading.Thread(
                    target=self._audio_input_event_trigger, daemon=True
                )
                self.input_event_thread.start()
                logger.info("入力イベントトリガースレッドを開始")

            # 出力イベントスレッドをチェック
            if (
                self.output_event_thread is None
                or not self.output_event_thread.is_alive()
            ):
                self.output_event_thread = threading.Thread(
                    target=self._audio_output_event_trigger, daemon=True
                )
                self.output_event_thread.start()
                logger.info("出力イベントトリガースレッドを開始")

            logger.info("音声ストリームを開始")
        except Exception as e:
            logger.error(f"音声ストリームの開始に失敗: {e}")

    def _audio_input_event_trigger(self):
        """音声入力イベントトリガー
        
        リスニング状態の時に定期的に音声入力イベントを発火します。
        フレーム長に応じて適切な間隔で処理を行います。
        """
        while self.running:
            try:
                # アクティブリスニング状態の時のみ入力イベントを発火
                if (
                    self.device_state == DeviceState.LISTENING
                    and self.audio_codec.input_stream
                ):
                    self.events[EventType.AUDIO_INPUT_READY_EVENT].set()
            except OSError as e:
                logger.error(f"音声入力ストリームエラー: {e}")
                # ループを終了せず、継続して試行
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"音声入力イベントトリガーエラー: {e}")
                time.sleep(0.5)

            # フレーム長が大きくても十分な発火頻度を保証
            # 最大発火間隔として20msを使用し、フレーム長が60msでも十分なサンプリングレートを確保
            sleep_time = min(20, AudioConfig.FRAME_DURATION) / 1000
            time.sleep(sleep_time)  # フレーム長に応じて発火するが、最小発火頻度を保証

    def _audio_output_event_trigger(self):
        """音声出力イベントトリガー
        
        話している状態の時に音声キューにデータがある場合に
        出力イベントを発火します。
        """
        while self.running:
            try:
                # 出力ストリームがアクティブであることを確保
                if (
                    self.device_state == DeviceState.SPEAKING
                    and self.audio_codec
                    and self.audio_codec.output_stream
                ):

                    # 出力ストリームが非アクティブの場合、再アクティブ化を試行
                    if not self.audio_codec.output_stream.is_active():
                        try:
                            self.audio_codec.output_stream.start_stream()
                        except Exception as e:
                            logger.warning(f"出力ストリーム開始に失敗、再初期化を試行: {e}")
                            self.audio_codec._reinitialize_stream(is_input=False)

                    # キューにデータがある時のみイベントを発火
                    if not self.audio_codec.audio_decode_queue.empty():
                        self.events[EventType.AUDIO_OUTPUT_READY_EVENT].set()
            except Exception as e:
                logger.error(f"音声出力イベントトリガーエラー: {e}")

            time.sleep(0.02)  # チェック間隔を少し延長

    async def _on_audio_channel_closed(self):
        """音声チャンネルクローズコールバック
        
        音声チャンネルが閉じられた時に適切な状態に設定し、
        ウェイクワード検出が正常に動作することを確保します。
        """
        logger.info("音声チャンネルが閉じられました")
        # アイドル状態に設定するが音声ストリームは閉じない
        self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
        self.keep_listening = False

        # ウェイクワード検出が正常に動作することを確保
        if self.wake_word_detector:
            if not self.wake_word_detector.is_running():
                logger.info("アイドル状態でウェイクワード検出を開始")
                # AudioCodecインスタンスを強制要求
                if hasattr(self, "audio_codec") and self.audio_codec:
                    success = self.wake_word_detector.start(self.audio_codec)
                    if not success:
                        logger.error("ウェイクワード検出器の開始に失敗、ウェイクワード機能を無効化")
                        self.config.update_config(
                            "WAKE_WORD_OPTIONS.USE_WAKE_WORD", False
                        )
                        self.wake_word_detector = None
                else:
                    logger.error("音声コーデックが利用不可、ウェイクワード検出器を開始できません")
                    self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
                    self.wake_word_detector = None
            elif self.wake_word_detector.paused:
                logger.info("アイドル状態でウェイクワード検出を復旧")
                self.wake_word_detector.resume()

    def set_device_state(self, state):
        """デバイス状態を設定
        
        Args:
            state: 設定するデバイス状態
        """
        if self.device_state == state:
            return

        self.device_state = state

        # 状態に応じて適切な操作を実行
        if state == DeviceState.IDLE:
            self.display.update_status("待機")
            # self.display.update_emotion("😶")
            self.set_emotion("neutral")
            # ウェイクワード検出を復旧（安全性チェック付き）
            if (
                self.wake_word_detector
                and hasattr(self.wake_word_detector, "paused")
                and self.wake_word_detector.paused
            ):
                self.wake_word_detector.resume()
                logger.info("ウェイクワード検出が復旧")
            # 音声入力ストリームを復旧
            if self.audio_codec and self.audio_codec.is_input_paused():
                self.audio_codec.resume_input()
        elif state == DeviceState.CONNECTING:
            self.display.update_status("接続中...")
        elif state == DeviceState.LISTENING:
            self.display.update_status("リスニング中...")
            self.set_emotion("neutral")
            self._update_iot_states(True)
            # ウェイクワード検出を一時停止（安全性チェック付き）
            if (
                self.wake_word_detector
                and hasattr(self.wake_word_detector, "is_running")
                and self.wake_word_detector.is_running()
            ):
                self.wake_word_detector.pause()
                logger.info("ウェイクワード検出が一時停止")
            # 音声入力ストリームがアクティブであることを確保
            if self.audio_codec:
                if self.audio_codec.is_input_paused():
                    self.audio_codec.resume_input()
        elif state == DeviceState.SPEAKING:
            self.display.update_status("話しています...")
            if (
                self.wake_word_detector
                and hasattr(self.wake_word_detector, "paused")
                and self.wake_word_detector.paused
            ):
                self.wake_word_detector.resume()

        # 状態変更を通知
        for callback in self.on_state_changed_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"状態変更コールバックの実行中にエラー: {e}")

    def _get_status_text(self):
        """現在の状態テキストを取得
        
        Returns:
            str: 現在のデバイス状態の日本語表示
        """
        states = {
            DeviceState.IDLE: "待機",
            DeviceState.CONNECTING: "接続中...",
            DeviceState.LISTENING: "リスニング中...",
            DeviceState.SPEAKING: "話しています...",
        }
        return states.get(self.device_state, "未知")

    def _get_current_text(self):
        """現在表示中のテキストを取得
        
        Returns:
            str: 現在表示中のテキスト
        """
        return self.current_text

    def _get_current_emotion(self):
        """現在の感情を取得
        
        感情に応じたGIFファイルのパスを返します。
        キャッシュ機能付きで、同じ感情の場合はキャッシュされたパスを返します。
        
        Returns:
            str: 感情GIFファイルの絶対パス
        """
        # 感情が変更されていない場合、キャッシュされたパスを直接返す
        if (
            hasattr(self, "_last_emotion")
            and self._last_emotion == self.current_emotion
        ):
            return self._last_emotion_path

        # 基本パスを取得
        if getattr(sys, "frozen", False):
            # パッケージ化環境
            if hasattr(sys, "_MEIPASS"):
                base_path = Path(sys._MEIPASS)
            else:
                base_path = Path(sys.executable).parent
        else:
            # 開発環境
            base_path = Path(__file__).parent.parent

        emotion_dir = base_path / "assets" / "emojis"

        emotions = {
            "neutral": str(emotion_dir / "neutral.gif"),
            "happy": str(emotion_dir / "happy.gif"),
            "laughing": str(emotion_dir / "laughing.gif"),
            "funny": str(emotion_dir / "funny.gif"),
            "sad": str(emotion_dir / "sad.gif"),
            "angry": str(emotion_dir / "angry.gif"),
            "crying": str(emotion_dir / "crying.gif"),
            "loving": str(emotion_dir / "loving.gif"),
            "embarrassed": str(emotion_dir / "embarrassed.gif"),
            "surprised": str(emotion_dir / "surprised.gif"),
            "shocked": str(emotion_dir / "shocked.gif"),
            "thinking": str(emotion_dir / "thinking.gif"),
            "winking": str(emotion_dir / "winking.gif"),
            "cool": str(emotion_dir / "cool.gif"),
            "relaxed": str(emotion_dir / "relaxed.gif"),
            "delicious": str(emotion_dir / "delicious.gif"),
            "kissy": str(emotion_dir / "kissy.gif"),
            "confident": str(emotion_dir / "confident.gif"),
            "sleepy": str(emotion_dir / "sleepy.gif"),
            "silly": str(emotion_dir / "silly.gif"),
            "confused": str(emotion_dir / "confused.gif"),
        }

        # 現在の感情と対応するパスを保存
        self._last_emotion = self.current_emotion
        self._last_emotion_path = emotions.get(
            self.current_emotion, str(emotion_dir / "neutral.gif")
        )

        logger.debug(f"感情パス: {self._last_emotion_path}")
        return self._last_emotion_path

    def set_chat_message(self, role, message):
        """チャットメッセージを設定
        
        Args:
            role (str): メッセージの役割 ('user' または 'assistant')
            message (str): メッセージ内容
        """
        self.current_text = message
        # 表示を更新
        if self.display:
            self.display.update_text(message)

    def set_emotion(self, emotion):
        """感情を設定
        
        Args:
            emotion (str): 設定する感情名
        """
        self.current_emotion = emotion
        # 表示を更新
        if self.display:
            self.display.update_emotion(self._get_current_emotion())

    def start_listening(self):
        """リスニングを開始
        
        ユーザーが手動でリスニングを開始するためのエントリポイントです。
        """
        self.schedule(self._start_listening_impl)

    def _start_listening_impl(self):
        """リスニング開始の実装
        
        プロトコルの初期化状態をチェックし、音声チャンネルを開いてリスニングを開始します。
        """
        if not self.protocol:
            logger.error("プロトコルが初期化されていません")
            return

        self.keep_listening = False

        # ウェイクワード検出器の存在をチェック
        if self.wake_word_detector:
            self.wake_word_detector.pause()

        if self.device_state == DeviceState.IDLE:
            self.schedule(
                lambda: self.set_device_state(DeviceState.CONNECTING)
            )  # デバイス状態を接続中に設定
            # 音声チャンネルを開くことを試行
            if not self.protocol.is_audio_channel_opened():
                try:
                    # 非同期操作の完了を待機
                    future = asyncio.run_coroutine_threadsafe(
                        self.protocol.open_audio_channel(), self.loop
                    )
                    # 操作の完了を待ち、結果を取得
                    success = future.result(timeout=10.0)  # タイムアウト時間を追加

                    if not success:
                        self.alert("エラー", "音声チャンネルのオープンに失敗")  # エラーメッセージを表示
                        self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
                        return

                except Exception as e:
                    logger.error(f"音声チャンネルのオープン中にエラーが発生: {e}")
                    self.alert("エラー", f"音声チャンネルのオープンに失敗: {str(e)}")
                    self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
                    return

            # --- 入力ストリームの強制再初期化 ---
            try:
                if self.audio_codec:
                    self.audio_codec._reinitialize_stream(
                        is_input=True
                    )  # 再初期化を呼び出し
                else:
                    logger.warning(
                        "強制再初期化できません、audio_codecがNoneです。"
                    )
            except Exception as force_reinit_e:
                logger.error(
                    f"強制再初期化に失敗: {force_reinit_e}", exc_info=True
                )
                self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
                if self.wake_word_detector and self.wake_word_detector.paused:
                    self.wake_word_detector.resume()
                return
            # --- 強制再初期化終了 ---

            asyncio.run_coroutine_threadsafe(
                self.protocol.send_start_listening(ListeningMode.MANUAL), self.loop
            )
            self.schedule(lambda: self.set_device_state(DeviceState.LISTENING))
        elif self.device_state == DeviceState.SPEAKING:
            if not self.aborted:
                self.abort_speaking(AbortReason.WAKE_WORD_DETECTED)

    async def _open_audio_channel_and_start_manual_listening(self):
        """音声チャンネルを開いて手動リスニングを開始
        
        音声チャンネルのオープンに成功した場合、手動モードでリスニングを開始します。
        """
        if not await self.protocol.open_audio_channel():
            self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
            self.alert("エラー", "音声チャンネルのオープンに失敗")
            return

        await self.protocol.send_start_listening(ListeningMode.MANUAL)
        self.schedule(lambda: self.set_device_state(DeviceState.LISTENING))

    def toggle_chat_state(self):
        """チャット状態を切り替え
        
        アイドル状態の場合はリスニングを開始し、
        リスニング中の場合は停止します。
        """
        # ウェイクワード検出器の存在をチェック
        if self.wake_word_detector:
            self.wake_word_detector.pause()
        self.schedule(self._toggle_chat_state_impl)

    def _toggle_chat_state_impl(self):
        """チャット状態切り替えの具体的な実装
        
        デバイスの現在の状態に応じて適切なアクションを実行します。
        """
        # プロトコルが初期化されているかチェック
        if not self.protocol:
            logger.error("プロトコルが初期化されていません")
            return

        # デバイスが現在アイドル状態の場合、接続してリスニングを開始
        if self.device_state == DeviceState.IDLE:
            self.schedule(
                lambda: self.set_device_state(DeviceState.CONNECTING)
            )  # デバイス状態を接続中に設定

            # スレッドを使用して接続操作を処理し、ブロッキングを回避
            def connect_and_listen():
                # 音声チャンネルを開くことを試行
                if not self.protocol.is_audio_channel_opened():
                    try:
                        # 非同期操作の完了を待機
                        future = asyncio.run_coroutine_threadsafe(
                            self.protocol.open_audio_channel(), self.loop
                        )
                        # 操作の完了を待ち、結果を取得、短いタイムアウト時間を使用
                        try:
                            success = future.result(timeout=5.0)
                        except asyncio.TimeoutError:
                            logger.error("音声チャンネルのオープンがタイムアウト")
                            self.schedule(
                                lambda: self.set_device_state(DeviceState.IDLE)
                            )
                            self.alert("エラー", "音声チャンネルのオープンがタイムアウト")
                            return
                        except Exception as e:
                            logger.error(f"音声チャンネルのオープン中に未知のエラーが発生: {e}")
                            self.schedule(
                                lambda: self.set_device_state(DeviceState.IDLE)
                            )
                            self.alert("エラー", f"音声チャンネルのオープンに失敗: {str(e)}")
                            return

                        if not success:
                            self.alert("エラー", "音声チャンネルのオープンに失敗")  # エラーメッセージを表示
                            self.schedule(
                                lambda: self.set_device_state(DeviceState.IDLE)
                            )
                            return

                    except Exception as e:
                        logger.error(f"音声チャンネルのオープン中にエラーが発生: {e}")
                        self.alert("エラー", f"音声チャンネルのオープンに失敗: {str(e)}")
                        self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
                        return

                self.keep_listening = True  # リスニング開始
                # 自動停止モードのリスニングを開始
                try:
                    asyncio.run_coroutine_threadsafe(
                        self.protocol.send_start_listening(ListeningMode.AUTO_STOP),
                        self.loop,
                    )
                    self.schedule(lambda: self.set_device_state(DeviceState.LISTENING))
                except Exception as e:
                    logger.error(f"リスニング開始中にエラーが発生: {e}")
                    self.set_device_state(DeviceState.IDLE)
                    self.alert("エラー", f"リスニング開始に失敗: {str(e)}")

            # 接続スレッドを開始
            threading.Thread(target=connect_and_listen, daemon=True).start()

        # デバイスが話している場合、現在の発話を停止
        elif self.device_state == DeviceState.SPEAKING:
            self.abort_speaking(AbortReason.NONE)  # 発話を中断

        # デバイスがリスニング中の場合、音声チャンネルを閉じる
        elif self.device_state == DeviceState.LISTENING:
            # スレッドでクローズ操作を処理し、ブロッキングを回避
            def close_audio_channel():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        self.protocol.close_audio_channel(), self.loop
                    )
                    future.result(timeout=3.0)  # 短いタイムアウトを使用
                except Exception as e:
                    logger.error(f"音声チャンネルのクローズ中にエラーが発生: {e}")

            threading.Thread(target=close_audio_channel, daemon=True).start()
            # クローズの完了を待たずに、即座にアイドル状態に設定
            self.schedule(lambda: self.set_device_state(DeviceState.IDLE))

    def stop_listening(self):
        """リスニングを停止
        
        ユーザーが手動でリスニングを停止するためのエントリポイントです。
        """
        self.schedule(self._stop_listening_impl)

    def _stop_listening_impl(self):
        """リスニング停止の実装
        
        リスニング中の場合にサーバーに停止メッセージを送信し、アイドル状態に戻します。
        """
        if self.device_state == DeviceState.LISTENING:
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_stop_listening(), self.loop
            )
            self.set_device_state(DeviceState.IDLE)

    def abort_speaking(self, reason):
        """音声出力を中断
        
        Args:
            reason: 中断理由（AbortReasonエナム値）
        """
        # 既に中断済みの場合、重複処理を行わない
        if self.aborted:
            logger.debug(f"既に中断済み、重複の中断リクエストを無視: {reason}")
            return

        logger.info(f"音声出力を中断、理由: {reason}")
        self.aborted = True

        # TTS再生状態をFalseに設定
        self.set_is_tts_playing(False)

        # 音声キューを即座にクリア
        if self.audio_codec:
            self.audio_codec.clear_audio_queue()

        # ウェイクワードによる音声中断の場合、Voskアサーションエラーを回避するため先にウェイクワード検出器を一時停止
        if reason == AbortReason.WAKE_WORD_DETECTED and self.wake_word_detector:
            if (
                hasattr(self.wake_word_detector, "is_running")
                and self.wake_word_detector.is_running()
            ):
                # ウェイクワード検出器を一時停止
                self.wake_word_detector.pause()
                logger.debug("並行処理を回避するためウェイクワード検出器を一時一時停止")
                # ウェイクワード検出器が停止処理を完了することを保証するため短時間待機
                time.sleep(0.1)

        # スレッドで状態変更と非同期操作を処理し、メインスレッドのブロッキングを回避
        def process_abort():
            # まず中断コマンドを送信
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.protocol.send_abort_speaking(reason), self.loop
                )
                # 長時間のブロッキングを回避するため短いタイムアウトを使用
                future.result(timeout=1.0)
            except Exception as e:
                logger.error(f"中断コマンドの送信中にエラー: {e}")

            # 次に状態を設定
            # self.set_device_state(DeviceState.IDLE)
            self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
            # ウェイクワードによる中断で、自動リスニングが有効な場合、自動的に録音モードに移行
            if (
                reason == AbortReason.WAKE_WORD_DETECTED
                and self.keep_listening
                and self.protocol.is_audio_channel_opened()
            ):
                # abortコマンドが処理されることを保証するため短時間待機
                time.sleep(0.1)  # 待機時間を短縮
                self.schedule(lambda: self.toggle_chat_state())

        # 処理スレッドを開始
        threading.Thread(target=process_abort, daemon=True).start()

    def alert(self, title, message):
        """警告情報を表示
        
        Args:
            title (str): 警告のタイトル
            message (str): 警告メッセージ
        """
        logger.warning(f"警告: {title}, {message}")
        # GUIで警告を表示
        if self.display:
            self.display.update_text(f"{title}: {message}")

    def on_state_changed(self, callback):
        """状態変更コールバックを登録
        
        Args:
            callback: 状態変更時に呼び出される関数
        """
        self.on_state_changed_callbacks.append(callback)

    def shutdown(self):
        """アプリケーションをシャットダウン
        
        すべてのコンポーネントを適切に停止・閉じてアプリケーションを終了します。
        """
        logger.info("アプリケーションをシャットダウン中...")
        self.running = False

        # 音声コーデックを閉じる
        if self.audio_codec:
            self.audio_codec.close()

        # プロトコルを閉じる
        if self.protocol:
            asyncio.run_coroutine_threadsafe(
                self.protocol.close_audio_channel(), self.loop
            )

        # イベントループを停止
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

        # イベントループスレッドの終了を待機
        if self.loop_thread and self.loop_thread.is_alive():
            self.loop_thread.join(timeout=1.0)

        # ウェイクワード検出を停止
        if self.wake_word_detector:
            self.wake_word_detector.stop()

        # VAD検出器を閉じる
        # if hasattr(self, 'vad_detector') and self.vad_detector:
        #     self.vad_detector.stop()

        logger.info("アプリケーションのシャットダウン完了")

    def _on_mode_changed(self, auto_mode):
        """会話モード変更を処理
        
        Args:
            auto_mode (bool): 自動モードの場合True、手動モードの場合False
            
        Returns:
            bool: モード変更に成功した場合True
        """
        # IDLE状態でのみモード切り替えを許可
        if self.device_state != DeviceState.IDLE:
            self.alert("ヒント", "待機状態でのみ会話モードを切り替えできます")
            return False

        self.keep_listening = auto_mode
        logger.info(f"会話モードを切り替え: {'自動' if auto_mode else '手動'}")
        return True

    def _initialize_wake_word_detector(self):
        """ウェイクワード検出器を初期化
        
        設定ファイルでウェイクワード機能が有効になっている場合に
        ウェイクワード検出器を作成・初期化します。
        """
        # まず設定でウェイクワード機能が有効になっているかチェック
        if not self.config.get_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False):
            logger.info("ウェイクワード機能が設定で無効、初期化をスキップ")
            self.wake_word_detector = None
            return

        try:
            from src.audio_processing.wake_word_detect import WakeWordDetector

            # 検出器インスタンスを作成
            self.wake_word_detector = WakeWordDetector()

            # ウェイクワード検出器が無効化されている場合（内部故障）、設定を更新
            if not getattr(self.wake_word_detector, "enabled", True):
                logger.warning("ウェイクワード検出器が無効化（内部故障）")
                self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
                self.wake_word_detector = None
                return

            # ウェイクワード検出コールバックとエラーハンドリングを登録
            self.wake_word_detector.on_detected(self._on_wake_word_detected)

            # lambdaでselfをキャプチャし、別の関数を定義しない
            self.wake_word_detector.on_error = lambda error: (
                self._handle_wake_word_error(error)
            )

            logger.info("ウェイクワード検出器の初期化成功")

            # ウェイクワード検出器を開始
            self._start_wake_word_detector()

        except Exception as e:
            logger.error(f"ウェイクワード検出器の初期化に失敗: {e}")
            import traceback

            logger.error(traceback.format_exc())

            # ウェイクワード機能を無効化するが、プログラムの他の機能には影響しない
            self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
            logger.info("初期化失敗のためウェイクワード機能を無効化しましたが、プログラムは継続実行します")
            self.wake_word_detector = None

    def _handle_wake_word_error(self, error):
        """ウェイクワード検出器エラーを処理
        
        Args:
            error: 発生したエラー
        """
        logger.error(f"ウェイクワード検出エラー: {error}")
        # 検出器の再起動を試行
        if self.device_state == DeviceState.IDLE:
            self.schedule(lambda: self._restart_wake_word_detector())

    def _start_wake_word_detector(self):
        """ウェイクワード検出器を開始
        
        音声コーデックが初期化されていることを確認し、
        ウェイクワード検出器を開始します。
        """
        if not self.wake_word_detector:
            return

        # 音声コーデックの初期化を強制要求
        if hasattr(self, "audio_codec") and self.audio_codec:
            logger.info("音声コーデックを使用してウェイクワード検出器を開始")
            success = self.wake_word_detector.start(self.audio_codec)
            if not success:
                logger.error("ウェイクワード検出器の開始に失敗、ウェイクワード機能を無効化")
                self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
                self.wake_word_detector = None
        else:
            logger.error("音声コーデックが利用不可、ウェイクワード検出器を開始できません")
            self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
            self.wake_word_detector = None

    def _on_wake_word_detected(self, wake_word, full_text):
        """ウェイクワード検出コールバック
        
        Args:
            wake_word (str): 検出されたウェイクワード
            full_text (str): 完全なテキスト
        """
        logger.info(f"ウェイクワードを検出: {wake_word} (完全テキスト: {full_text})")
        self.schedule(lambda: self._handle_wake_word_detected(wake_word))

    def _handle_wake_word_detected(self, wake_word):
        """ウェイクワード検出イベントを処理
        
        Args:
            wake_word (str): 検出されたウェイクワード
        """
        if self.device_state == DeviceState.IDLE:
            # ウェイクワード検出を一時停止
            if self.wake_word_detector:
                self.wake_word_detector.pause()

            # 接続とリスニングを開始
            self.schedule(lambda: self.set_device_state(DeviceState.CONNECTING))
            # サーバーへの接続と音声チャンネルのオープンを試行
            asyncio.run_coroutine_threadsafe(
                self._connect_and_start_listening(wake_word), self.loop
            )
        elif self.device_state == DeviceState.SPEAKING:
            self.abort_speaking(AbortReason.WAKE_WORD_DETECTED)

    async def _connect_and_start_listening(self, wake_word):
        """连接服务器并开始监听."""
        # 首先尝试连接服务器
        if not await self.protocol.connect():
            logger.error("连接服务器失败")
            self.alert("错误", "连接服务器失败")
            self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
            # 恢复唤醒词检测
            if self.wake_word_detector:
                self.wake_word_detector.resume()
            return

        # 然后尝试打开音频通道
        if not await self.protocol.open_audio_channel():
            logger.error("打开音频通道失败")
            self.schedule(lambda: self.set_device_state(DeviceState.IDLE))
            self.alert("错误", "打开音频通道失败")
            # 恢复唤醒词检测
            if self.wake_word_detector:
                self.wake_word_detector.resume()
            return

        await self.protocol.send_wake_word_detected(wake_word)
        # 设置为自动监听模式
        self.keep_listening = True
        await self.protocol.send_start_listening(ListeningMode.AUTO_STOP)
        self.schedule(lambda: self.set_device_state(DeviceState.LISTENING))

    def _restart_wake_word_detector(self):
        """重新启动唤醒词检测器（仅支持AudioCodec共享流模式）"""
        logger.info("尝试重新启动唤醒词检测器")
        try:
            # 停止现有的检测器
            if self.wake_word_detector:
                self.wake_word_detector.stop()
                time.sleep(0.5)  # 给予一些时间让资源释放

            # 强制要求音频编解码器
            if hasattr(self, "audio_codec") and self.audio_codec:
                success = self.wake_word_detector.start(self.audio_codec)
                if success:
                    logger.info("使用音频编解码器重新启动唤醒词检测器成功")
                else:
                    logger.error("唤醒词检测器重新启动失败，禁用唤醒词功能")
                    self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
                    self.wake_word_detector = None
            else:
                logger.error("音频编解码器不可用，无法重新启动唤醒词检测器")
                self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
                self.wake_word_detector = None
        except Exception as e:
            logger.error(f"重新启动唤醒词检测器失败: {e}")
            self.config.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
            self.wake_word_detector = None

    def _initialize_iot_devices(self):
        """初始化物联网设备."""
        from src.iot.thing_manager import ThingManager
        from src.iot.things.CameraVL.Camera import Camera

        # 导入新的倒计时器设备
        from src.iot.things.countdown_timer import CountdownTimer
        from src.iot.things.lamp import Lamp
        from src.iot.things.music_player import MusicPlayer
        from src.iot.things.speaker import Speaker

        # 获取物联网设备管理器实例
        thing_manager = ThingManager.get_instance()

        # 添加设备
        thing_manager.add_thing(Lamp())
        thing_manager.add_thing(Speaker())
        thing_manager.add_thing(MusicPlayer())
        # 默认不启用以下示例
        thing_manager.add_thing(Camera())

        # 添加倒计时器设备
        thing_manager.add_thing(CountdownTimer())
        logger.info("已添加倒计时器设备,用于计时执行命令用")

        # 判断是否配置了home assistant才注册
        if self.config.get_config("HOME_ASSISTANT.TOKEN"):
            # 导入Home Assistant设备控制类
            from src.iot.things.ha_control import (
                HomeAssistantButton,
                HomeAssistantLight,
                HomeAssistantNumber,
                HomeAssistantSwitch,
            )

            # 添加Home Assistant设备
            ha_devices = self.config.get_config("HOME_ASSISTANT.DEVICES", [])
            for device in ha_devices:
                entity_id = device.get("entity_id")
                friendly_name = device.get("friendly_name")
                if entity_id:
                    # 根据实体ID判断设备类型
                    if entity_id.startswith("light."):
                        # 灯设备
                        thing_manager.add_thing(
                            HomeAssistantLight(entity_id, friendly_name)
                        )
                        logger.info(
                            f"已添加Home Assistant灯设备: {friendly_name or entity_id}"
                        )
                    elif entity_id.startswith("switch."):
                        # 开关设备
                        thing_manager.add_thing(
                            HomeAssistantSwitch(entity_id, friendly_name)
                        )
                        logger.info(
                            f"已添加Home Assistant开关设备: {friendly_name or entity_id}"
                        )
                    elif entity_id.startswith("number."):
                        # 数值设备（如音量控制）
                        thing_manager.add_thing(
                            HomeAssistantNumber(entity_id, friendly_name)
                        )
                        logger.info(
                            f"已添加Home Assistant数值设备: {friendly_name or entity_id}"
                        )
                    elif entity_id.startswith("button."):
                        # 按钮设备
                        thing_manager.add_thing(
                            HomeAssistantButton(entity_id, friendly_name)
                        )
                        logger.info(
                            f"已添加Home Assistant按钮设备: {friendly_name or entity_id}"
                        )
                    else:
                        # 默认作为灯设备处理
                        thing_manager.add_thing(
                            HomeAssistantLight(entity_id, friendly_name)
                        )
                        logger.info(
                            f"已添加Home Assistant设备(默认作为灯处理):{friendly_name or entity_id}"
                        )

        logger.info("物联网设备初始化完成")

    def _handle_iot_message(self, data):
        """处理物联网消息."""
        from src.iot.thing_manager import ThingManager

        thing_manager = ThingManager.get_instance()

        commands = data.get("commands", [])
        for command in commands:
            try:
                result = thing_manager.invoke(command)
                logger.info(f"执行物联网命令结果: {result}")
                # self.schedule(lambda: self._update_iot_states())
            except Exception as e:
                logger.error(f"执行物联网命令失败: {e}")

    def _update_iot_states(self, delta=None):
        """更新物联网设备状态.

        Args:
            delta: 是否只发送变化的部分
                   - None: 使用原始行为，总是发送所有状态
                   - True: 只发送变化的部分
                   - False: 发送所有状态并重置缓存
        """
        from src.iot.thing_manager import ThingManager

        thing_manager = ThingManager.get_instance()

        # 处理向下兼容
        if delta is None:
            # 保持原有行为：获取所有状态并发送
            states_json = thing_manager.get_states_json_str()  # 调用旧方法

            # 发送状态更新
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_iot_states(states_json), self.loop
            )
            logger.info("物联网设备状态已更新")
            return

        # 使用新方法获取状态
        changed, states_json = thing_manager.get_states_json(delta=delta)
        # delta=False总是发送，delta=True只在有变化时发送
        if not delta or changed:
            asyncio.run_coroutine_threadsafe(
                self.protocol.send_iot_states(states_json), self.loop
            )
            if delta:
                logger.info("物联网设备状态已更新(增量)")
            else:
                logger.info("物联网设备状态已更新(完整)")
        else:
            logger.debug("物联网设备状态无变化，跳过更新")

    def _update_wake_word_detector_stream(self):
        """更新唤醒词检测器的音频流."""
        if (
            self.wake_word_detector
            and self.audio_codec
            and self.wake_word_detector.is_running()
        ):
            # 直接引用AudioCodec实例中的输入流
            if (
                self.audio_codec.input_stream
                and self.audio_codec.input_stream.is_active()
            ):
                self.wake_word_detector.stream = self.audio_codec.input_stream
                self.wake_word_detector.external_stream = True
                logger.info("已更新唤醒词检测器的音频流引用")
