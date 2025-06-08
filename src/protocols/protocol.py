"""
プロトコル基底クラス

このモジュールは、WebSocketやMQTTなどの異なる通信プロトコルで
共通のインターフェースを提供する抽象基底クラスを定義します。
音声通信とメッセージ通信の統一したインターフェースを提供し、
具体的な実装は各サブクラスで行います。
"""
import json

from src.constants.constants import AbortReason, ListeningMode


class Protocol:
    """
    通信プロトコルの基底クラス
    
    WebSocket、MQTT、その他の通信プロトコルで共通のインターフェースを提供します。
    音声データとJSONメッセージの送受信、音声チャネルの管理、
    ネットワークエラーハンドリングなどの機能を抽象化します。
    
    Attributes:
        session_id (str): 現在のセッションID
        on_incoming_json (callable): JSONメッセージ受信時のコールバック関数
        on_incoming_audio (callable): 音声データ受信時のコールバック関数
        on_audio_channel_opened (callable): 音声チャネル開通時のコールバック関数
        on_audio_channel_closed (callable): 音声チャネル閉鎖時のコールバック関数
        on_network_error (callable): ネットワークエラー発生時のコールバック関数
    """
    
    def __init__(self):
        """プロトコルインスタンスを初期化します。"""
        self.session_id = ""
        # コールバック関数を初期化（最初はすべてNone）
        self.on_incoming_json = None
        self.on_incoming_audio = None
        self.on_audio_channel_opened = None
        self.on_audio_channel_closed = None
        self.on_network_error = None

    def on_incoming_json(self, callback):
        """JSONメッセージ受信時のコールバック関数を設定します。
        
        Args:
            callback (callable): JSONメッセージを受信したときに呼び出される関数
        """
        self.on_incoming_json = callback

    def on_incoming_audio(self, callback):
        """音声データ受信時のコールバック関数を設定します。
        
        Args:
            callback (callable): 音声データを受信したときに呼び出される関数
        """
        self.on_incoming_audio = callback

    def on_audio_channel_opened(self, callback):
        """音声チャネル開通時のコールバック関数を設定します。
        
        Args:
            callback (callable): 音声チャネルが開通したときに呼び出される関数
        """
        self.on_audio_channel_opened = callback

    def on_audio_channel_closed(self, callback):
        """音声チャネル閉鎖時のコールバック関数を設定します。
        
        Args:
            callback (callable): 音声チャネルが閉鎖されたときに呼び出される関数
        """
        self.on_audio_channel_closed = callback

    def on_network_error(self, callback):
        """ネットワークエラー発生時のコールバック関数を設定します。
        
        Args:
            callback (callable): ネットワークエラーが発生したときに呼び出される関数
        """
        self.on_network_error = callback

    async def send_text(self, message):
        """テキストメッセージを送信する抽象メソッド。
        
        このメソッドはサブクラスで実装する必要があります。
        各プロトコル（WebSocket、MQTT等）に応じた送信方法を実装します。
        
        Args:
            message (str): 送信するテキストメッセージ
            
        Raises:
            NotImplementedError: このメソッドはサブクラスで実装する必要があります
        """
        raise NotImplementedError("send_textメソッドはサブクラスで実装する必要があります")

    async def send_abort_speaking(self, reason):
        """音声出力の中止メッセージを送信します。
        
        音声合成や再生を中止する必要がある場合に使用します。
        唤醒词検出時など、緊急に音声出力を停止する必要がある際に呼び出されます。
        
        Args:
            reason (AbortReason): 中止の理由（唤醒词検出など）
        """
        message = {"session_id": self.session_id, "type": "abort"}
        if reason == AbortReason.WAKE_WORD_DETECTED:
            message["reason"] = "wake_word_detected"
        await self.send_text(json.dumps(message))

    async def send_wake_word_detected(self, wake_word):
        """唤醒词検出メッセージを送信します。
        
        ユーザーが唤醒词を発話したことを検出した際に、
        サーバーに検出結果を通知するために使用します。
        これにより音声認識とAI応答のプロセスが開始されます。
        
        Args:
            wake_word (str): 検出された唤醒词のテキスト
        """
        message = {
            "session_id": self.session_id,
            "type": "listen",
            "state": "detect",
            "text": wake_word,
        }
        await self.send_text(json.dumps(message))

    async def send_start_listening(self, mode):
        """音声認識開始メッセージを送信します。
        
        指定されたモードで音声認識を開始することをサーバーに通知します。
        モードにより音声認識の動作が異なります：
        - ALWAYS_ON: リアルタイム継続音声認識
        - AUTO_STOP: 自動停止音声認識
        - MANUAL: 手動制御音声認識
        
        Args:
            mode (ListeningMode): 音声認識のモード
        """
        mode_map = {
            ListeningMode.ALWAYS_ON: "realtime",
            ListeningMode.AUTO_STOP: "auto",
            ListeningMode.MANUAL: "manual",
        }
        message = {
            "session_id": self.session_id,
            "type": "listen",
            "state": "start",
            "mode": mode_map[mode],
        }
        await self.send_text(json.dumps(message))

    async def send_stop_listening(self):
        """音声認識停止メッセージを送信します。
        
        現在進行中の音声認識を停止することをサーバーに通知します。
        ユーザーの発話が終了した場合や、手動で音声認識を
        停止する必要がある場合に使用されます。
        """
        message = {"session_id": self.session_id, "type": "listen", "state": "stop"}
        await self.send_text(json.dumps(message))

    async def send_iot_descriptors(self, descriptors):
        """IoTデバイス記述情報を送信します。
        
        システムで利用可能なIoTデバイスの仕様や機能を
        サーバーに通知するために使用します。この情報により
        AIアシスタントがデバイス制御コマンドを理解できるようになります。
        
        Args:
            descriptors (str | dict): IoTデバイスの記述情報（JSON文字列またはdict）
        """
        message = {
            "session_id": self.session_id,
            "type": "iot",
            "descriptors": (
                json.loads(descriptors) if isinstance(descriptors, str) else descriptors
            ),
        }
        await self.send_text(json.dumps(message))

    async def send_iot_states(self, states):
        """IoTデバイスの状態情報を送信します。
        
        現在のIoTデバイスの状態（電源オン/オフ、温度、湿度など）を
        サーバーに送信します。この情報によりAIアシスタントが
        デバイスの現在状態を把握し、適切な応答や制御を行えます。
        
        Args:
            states (str | dict): IoTデバイスの状態情報（JSON文字列またはdict）
        """
        message = {
            "session_id": self.session_id,
            "type": "iot",
            "states": json.loads(states) if isinstance(states, str) else states,
        }
        await self.send_text(json.dumps(message))
