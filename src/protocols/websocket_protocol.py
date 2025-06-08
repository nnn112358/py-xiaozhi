"""
WebSocketプロトコル実装

このモジュールは、WebSocketを使用した双方向通信プロトコルを実装します。
リアルタイム音声通信とJSONメッセージ交換をサポートし、AI音声アシスタント
との安全で高速な通信を提供します。

WebSocketの接続管理、音声データのストリーミング、セッション管理、
エラーハンドリングなどの機能を包括的に実装しています。
"""
import asyncio
import json
import ssl

import websockets

from src.constants.constants import AudioConfig
from src.protocols.protocol import Protocol
from src.utils.config_manager import ConfigManager
from src.utils.logging_config import get_logger

# SSL証明書の検証を無効にしたコンテキストを作成
# 本番環境では適切な証明書検証を実装することを推奨
ssl_context = ssl._create_unverified_context()

logger = get_logger(__name__)


class WebsocketProtocol(Protocol):
    """
    WebSocketプロトコルの実装クラス
    
    WebSocketを使用してサーバーとリアルタイム通信を行います。
    音声データとJSONメッセージの双方向通信をサポートし、
    認証、セッション管理、エラーハンドリングを提供します。
    
    Attributes:
        config (ConfigManager): 設定管理インスタンス
        websocket: WebSocket接続オブジェクト
        connected (bool): 接続状態フラグ
        hello_received (asyncio.Event): サーバーからのhello受信イベント
        WEBSOCKET_URL (str): WebSocketサーバーのURL
        HEADERS (dict): 接続時に送信するHTTPヘッダー
    """
    
    def __init__(self):
        """WebSocketプロトコルインスタンスを初期化します。"""
        super().__init__()
        # 設定管理器インスタンスを取得
        self.config = ConfigManager.get_instance()
        self.websocket = None
        self.connected = False
        self.hello_received = None  # 初期化時はNoneに設定
        
        # 設定からWebSocket接続情報を取得
        self.WEBSOCKET_URL = self.config.get_config(
            "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL"
        )
        access_token = self.config.get_config(
            "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_ACCESS_TOKEN"
        )
        device_id = self.config.get_config("SYSTEM_OPTIONS.DEVICE_ID")
        client_id = self.config.get_config("SYSTEM_OPTIONS.CLIENT_ID")

        # 認証と識別のためのHTTPヘッダーを設定
        self.HEADERS = {
            "Authorization": f"Bearer {access_token}",  # Bearer認証トークン
            "Protocol-Version": "1",  # プロトコルバージョン
            "Device-Id": device_id,  # デバイス識別子（MACアドレス等）
            "Client-Id": client_id,  # クライアント識別子
        }

    async def connect(self) -> bool:
        """WebSocketサーバーへの接続を確立します。
        
        サーバーとの接続を確立し、認証とハンドシェイクを実行します。
        接続成功時にはメッセージ処理ループを開始し、音声通信の準備を完了します。
        
        Returns:
            bool: 接続が成功した場合True、失敗した場合False
            
        Raises:
            Exception: 接続処理中にエラーが発生した場合
        """
        try:
            # 接続時にEventオブジェクトを作成（正しいイベントループ内で）
            self.hello_received = asyncio.Event()

            # SSL使用の判定
            current_ssl_context = None
            if self.WEBSOCKET_URL.startswith("wss://"):
                current_ssl_context = ssl_context

            # WebSocket接続の確立（Pythonバージョン互換性を考慮）
            try:
                # 新しい記法（Python 3.11+版本）
                self.websocket = await websockets.connect(
                    uri=self.WEBSOCKET_URL,
                    ssl=current_ssl_context,
                    additional_headers=self.HEADERS,
                )
            except TypeError:
                # 古い記法（以前のPythonバージョン用）
                self.websocket = await websockets.connect(
                    self.WEBSOCKET_URL,
                    ssl=current_ssl_context,
                    extra_headers=self.HEADERS,
                )

            # メッセージ処理ループを開始
            asyncio.create_task(self._message_handler())

            # クライアント側helloメッセージを送信
            hello_message = {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",  # Opusオーディオコーデック
                    "sample_rate": AudioConfig.INPUT_SAMPLE_RATE,
                    "channels": AudioConfig.CHANNELS,
                    "frame_duration": AudioConfig.FRAME_DURATION,
                },
            }
            await self.send_text(json.dumps(hello_message))

            # サーバーからのhello応答を待機
            try:
                await asyncio.wait_for(self.hello_received.wait(), timeout=10.0)
                self.connected = True
                logger.info("WebSocketサーバーに接続しました")
                return True
            except asyncio.TimeoutError:
                logger.error("サーバーからのhello応答がタイムアウトしました")
                if self.on_network_error:
                    self.on_network_error("応答待機タイムアウト")
                return False

        except Exception as e:
            logger.error(f"WebSocket接続に失敗しました: {e}")
            if self.on_network_error:
                self.on_network_error(f"サービスに接続できません: {str(e)}")
            return False

    async def _message_handler(self):
        """WebSocketメッセージの受信と処理を行います。
        
        WebSocketから受信したメッセージを解析し、タイプに応じて適切な処理を実行します。
        JSONメッセージ（制御信号）と音声データ（バイナリ）を区別して処理し、
        対応するコールバック関数を呼び出します。
        
        エラー処理：
        - 接続切断時の適切なクリーンアップ
        - JSONパースエラーの処理
        - ネットワークエラーの通知
        """
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    # テキストメッセージ（JSON）の処理
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")
                        if msg_type == "hello":
                            # サーバーからのhelloメッセージを処理
                            await self._handle_server_hello(data)
                        else:
                            # その他のJSONメッセージを処理
                            if self.on_incoming_json:
                                self.on_incoming_json(data)
                    except json.JSONDecodeError as e:
                        logger.error(f"無効なJSONメッセージです: {message}, エラー: {e}")
                elif self.on_incoming_audio:
                    # バイナリメッセージ（音声データ）の処理
                    self.on_incoming_audio(message)

        except websockets.ConnectionClosed:
            logger.info("WebSocket接続が閉じられました")
            self.connected = False
            if self.on_audio_channel_closed:
                # メインスレッドでコールバックが実行されるようにスケジュール
                await self.on_audio_channel_closed()
        except Exception as e:
            logger.error(f"メッセージ処理エラー: {e}")
            self.connected = False
            if self.on_network_error:
                # メインスレッドでエラー処理が実行されるようにスケジュール
                self.on_network_error(f"接続エラー: {str(e)}")

    async def send_audio(self, data: bytes):
        """音声データをサーバーに送信します。
        
        WebSocketを通じて音声データ（通常はOpusエンコード済み）をリアルタイムで送信します。
        接続状態を確認してから送信を実行し、エラー時には適切な処理を行います。
        
        Args:
            data (bytes): 送信する音声データ（バイナリ形式）
            
        Note:
            音声チャネルが開いていない場合は送信をスキップします。
        """
        if not self.is_audio_channel_opened():
            return

        try:
            await self.websocket.send(data)
        except Exception as e:
            if self.on_network_error:
                self.on_network_error(f"音声データの送信に失敗しました: {str(e)}")

    async def send_text(self, message: str):
        """テキストメッセージをサーバーに送信します。
        
        JSONフォーマットの制御メッセージやコマンドを送信するために使用されます。
        送信エラー時には接続を閉じ、適切なエラー処理を実行します。
        
        Args:
            message (str): 送信するテキストメッセージ（通常はJSON文字列）
            
        Note:
            送信失敗時には音声チャネルを閉じてエラーコールバックを呼び出します。
        """
        if self.websocket:
            try:
                await self.websocket.send(message)
            except Exception as e:
                logger.error(f"テキストメッセージの送信に失敗しました: {e}")
                await self.close_audio_channel()
                if self.on_network_error:
                    self.on_network_error("クライアントが閉じられました")

    def is_audio_channel_opened(self) -> bool:
        """音声チャネルが開いているかどうかを確認します。
        
        WebSocket接続が確立され、音声通信が可能な状態かどうかを判定します。
        
        Returns:
            bool: 音声チャネルが利用可能な場合True、そうでなければFalse
        """
        return self.websocket is not None and self.connected

    async def open_audio_channel(self) -> bool:
        """音声チャネルを開きます。

        まだ接続されていない場合は、新しいWebSocket接続を確立します。
        既に接続されている場合は、現在の接続を使用します。
        
        Returns:
            bool: 接続が成功した場合True、失敗した場合False
        """
        if not self.connected:
            return await self.connect()
        return True

    async def _handle_server_hello(self, data: dict):
        """サーバーからのhelloメッセージを処理します。
        
        サーバーとのハンドシェイクを完了し、セッションを確立します。
        トランスポート方式を確認し、音声チャネルの開通を通知します。
        
        Args:
            data (dict): サーバーから受信したhelloメッセージのデータ
            
        Note:
            サポートされていないトランスポート方式の場合はエラーを出力します。
        """
        try:
            # トランスポート方式の検証
            transport = data.get("transport")
            if not transport or transport != "websocket":
                logger.error(f"サポートされていないトランスポート方式です: {transport}")
                return
            print("サービス接続から初期化設定が返されました", data)

            # hello受信イベントを設定
            self.hello_received.set()

            # 音声チャネル開通の通知
            if self.on_audio_channel_opened:
                await self.on_audio_channel_opened()

            logger.info("サーバーからのhelloメッセージを正常に処理しました")

        except Exception as e:
            logger.error(f"サーバーからのhelloメッセージ処理中にエラーが発生しました: {e}")
            if self.on_network_error:
                self.on_network_error(f"サーバー応答の処理に失敗しました: {str(e)}")

    async def close_audio_channel(self):
        """音声チャネルを閉じます。
        
        WebSocket接続を安全に切断し、関連するリソースをクリーンアップします。
        接続状態をリセットし、チャネル閉鎖のコールバックを実行します。
        
        Note:
            接続切断中にエラーが発生した場合でも、状態のリセットは実行されます。
        """
        if self.websocket:
            try:
                await self.websocket.close()
                self.websocket = None
                self.connected = False
                if self.on_audio_channel_closed:
                    await self.on_audio_channel_closed()
            except Exception as e:
                logger.error(f"WebSocket接続の切断に失敗しました: {e}")
