# システム設定管理モジュール
# アプリケーションの設定ファイルの読み込み、保存、管理を行う

import json
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import requests

from src.utils.device_activator import DeviceActivator
from src.utils.device_fingerprint import get_device_fingerprint
from src.utils.logging_config import get_logger
from src.utils.resource_finder import find_config_dir, find_file, get_app_path

logger = get_logger(__name__)


class ConfigManager:
    """
    設定管理クラス - シングルトンパターン
    
    アプリケーションの全設定を一元管理し、設定ファイルの読み書きを行う。
    スレッドセーフなシングルトンパターンで実装されており、
    アプリケーション全体で同一のインスタンスが使用される。
    
    主な機能:
    - 設定ファイルの自動読み込み・保存
    - デフォルト設定との統合
    - 設定値の取得・更新
    - デバイスID・クライアントIDの自動生成
    - OTAサーバーからの最新設定取得
    """

    _instance = None
    _lock = threading.Lock()

    # 設定ファイルのパス定義
    CONFIG_DIR = find_config_dir()
    if not CONFIG_DIR:
        # 設定ディレクトリが見つからない場合、プロジェクトルート下のconfigフォルダを使用
        CONFIG_DIR = Path(get_app_path()) / "config"
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE = CONFIG_DIR / "config.json"

    # 設定ファイルのパスをログに記録
    logger.info(f"設定ディレクトリ: {CONFIG_DIR.absolute()}")
    logger.info(f"設定ファイル: {CONFIG_FILE.absolute()}")
    CONFIG_FILE = CONFIG_DIR / "config.json" if CONFIG_DIR else None

    # 設定ファイルのパスをログに記録
    if CONFIG_DIR:
        logger.info(f"設定ディレクトリ: {CONFIG_DIR.absolute()}")
        logger.info(f"設定ファイル: {CONFIG_FILE.absolute()}")
    else:
        logger.warning("設定ディレクトリが見つかりません。デフォルト設定を使用します")

    # デフォルト設定値の定義
    DEFAULT_CONFIG = {
        "SYSTEM_OPTIONS": {
            "CLIENT_ID": None,  # 自動生成されるクライアントID
            "DEVICE_ID": None,  # デバイス固有のID（MACアドレスベース）
            "NETWORK": {
                "OTA_VERSION_URL": "https://api.tenclass.net/xiaozhi/ota/",  # OTAサーバーURL
                "WEBSOCKET_URL": None,  # WebSocket接続URL
                "WEBSOCKET_ACCESS_TOKEN": None,  # WebSocket認証トークン
                "MQTT_INFO": None,  # MQTT接続情報
                "ACTIVATION_VERSION": "v2",  # アクティベーションバージョン（v1, v2）
                "AUTHORIZATION_URL": "https://xiaozhi.me/",  # 認証URL
            },
        },
        "WAKE_WORD_OPTIONS": {
            "USE_WAKE_WORD": False,  # ウェイクワード機能の有効/無効
            "MODEL_PATH": "models/vosk-model-small-cn-0.22",  # 音声認識モデルのパス
            "WAKE_WORDS": ["小智", "小美"],  # 設定されたウェイクワード
        },
        "TEMPERATURE_SENSOR_MQTT_INFO": {
            "endpoint": "あなたのMQTT接続アドレス",  # MQTTブローカーのエンドポイント
            "port": 1883,  # MQTTポート番号
            "username": "admin",  # MQTT認証ユーザー名
            "password": "123456",  # MQTT認証パスワード
            "publish_topic": "sensors/temperature/command",  # 温度センサー制御トピック
            "subscribe_topic": "sensors/temperature/device_001/state",  # 温度センサー状態トピック
        },
        "HOME_ASSISTANT": {
            "URL": "http://localhost:8123",  # Home AssistantのURL
            "TOKEN": "",  # Home Assistant APIトークン
            "DEVICES": []  # 管理対象デバイスリスト
        },
        "CAMERA": {
            "camera_index": 0,  # カメラデバイスインデックス
            "frame_width": 640,  # 映像フレーム幅
            "frame_height": 480,  # 映像フレーム高さ
            "fps": 30,  # フレームレート
            "Loacl_VL_url": "https://open.bigmodel.cn/api/paas/v4/",  # ビジュアル言語モデルAPI URL
            "VLapi_key": "あなた自身のAPIキー",  # VL API認証キー
            "models": "glm-4v-plus",  # 使用するVLモデル名
        },
    }

    def __new__(cls):
        """
        シングルトンパターンの実装
        
        クラスのインスタンスが既に存在する場合はそれを返し、
        存在しない場合は新しいインスタンスを作成する。
        
        Returns:
            ConfigManager: シングルトンインスタンス
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        設定管理クラスの初期化
        
        シングルトンパターンのため、初期化は一度だけ実行される。
        設定ファイルの読み込み、デバイス情報の初期化、
        各種IDの生成・設定を行う。
        """
        self.logger = logger
        # 既に初期化済みの場合はスキップ
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.device_activator = None  # デバイスアクティベーター（後で初期化）
        
        # 設定ファイルを読み込み
        self._config = self._load_config()
        
        # デバイスフィンガープリント生成器を初期化
        self.device_fingerprint = get_device_fingerprint()
        self.device_fingerprint._ensure_efuse_file()
        
        # 必要なIDを初期化
        self._initialize_client_id()  # クライアントID生成
        self._initialize_device_id()  # デバイスID生成
        # self._initialize_mqtt_info()  # MQTT情報は必要時に取得

    def _load_config(self) -> Dict[str, Any]:
        """
        設定ファイルを読み込み、存在しない場合は作成する
        
        リソースファインダーを使用して設定ファイルを検索し、
        見つからない場合はデフォルト設定でファイルを作成する。
        既存の設定とデフォルト設定をマージして返す。
        
        Returns:
            Dict[str, Any]: 読み込まれた設定データ
        """
        try:
            # resource_finderを使用して設定ファイルを検索
            config_file_path = find_file("config/config.json")
            if config_file_path and config_file_path.exists():
                config = json.loads(config_file_path.read_text(encoding="utf-8"))
                return self._merge_configs(self.DEFAULT_CONFIG, config)

            # 設定ファイルが見つからない場合、クラス変数のパスを試行
            if self.CONFIG_FILE and self.CONFIG_FILE.exists():
                config = json.loads(self.CONFIG_FILE.read_text(encoding="utf-8"))
                return self._merge_configs(self.DEFAULT_CONFIG, config)
            else:
                # デフォルト設定で新しい設定ファイルを作成
                if self.CONFIG_DIR:
                    self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                    self._save_config(self.DEFAULT_CONFIG)
                return self.DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"設定読み込みエラー: {e}")
            return self.DEFAULT_CONFIG.copy()

    def _save_config(self, config: dict) -> bool:
        """
        設定をファイルに保存する
        
        指定された設定データをJSON形式で設定ファイルに書き込む。
        ディレクトリが存在しない場合は自動作成する。
        
        Args:
            config (dict): 保存する設定データ
            
        Returns:
            bool: 保存に成功した場合True、失敗した場合False
        """
        try:
            if self.CONFIG_DIR and self.CONFIG_FILE:
                # 設定ディレクトリを作成（存在しない場合）
                self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                # 設定をJSONファイルに書き込み（UTF-8エンコーディング、整形あり）
                self.CONFIG_FILE.write_text(
                    json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                return True
            else:
                logger.error("設定ディレクトリまたはファイルパスが見つかりません。設定を保存できません")
                return False
        except Exception as e:
            logger.error(f"設定保存エラー: {e}")
            return False

    @staticmethod
    def _merge_configs(default: dict, custom: dict) -> dict:
        """
        設定辞書を再帰的にマージする
        
        デフォルト設定とカスタム設定を統合し、カスタム設定が優先される。
        ネストされた辞書も再帰的にマージされる。
        
        Args:
            default (dict): デフォルト設定
            custom (dict): カスタム設定（優先される）
            
        Returns:
            dict: マージされた設定
        """
        result = default.copy()
        for key, value in custom.items():
            # 両方が辞書の場合は再帰的にマージ
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigManager._merge_configs(result[key], value)
            else:
                # そうでなければカスタム設定で上書き
                result[key] = value
        return result

    def get_config(self, path: str, default: Any = None) -> Any:
        """
        パス指定で設定値を取得する
        
        ドット区切りのパス文字列を使用して、ネストされた設定値にアクセスする。
        指定されたパスが存在しない場合はデフォルト値を返す。
        
        Args:
            path (str): ドット区切りの設定パス（例: "SYSTEM_OPTIONS.NETWORK.MQTT_INFO"）
            default (Any, optional): パスが存在しない場合のデフォルト値
            
        Returns:
            Any: 設定値またはデフォルト値
            
        Example:
            >>> config_manager.get_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", False)
        """
        try:
            value = self._config
            # パスを分割して順次アクセス
            for key in path.split("."):
                value = value[key]
            return value
        except (KeyError, TypeError):
            # パスが存在しない場合はデフォルト値を返す
            return default

    def update_config(self, path: str, value: Any) -> bool:
        """
        指定された設定項目を更新する
        
        ドット区切りのパスを使用して設定値を更新し、
        変更を設定ファイルに保存する。
        
        Args:
            path (str): ドット区切りの設定パス（例: "SYSTEM_OPTIONS.CLIENT_ID"）
            value (Any): 設定する値
            
        Returns:
            bool: 更新と保存に成功した場合True、失敗した場合False
            
        Example:
            >>> config_manager.update_config("WAKE_WORD_OPTIONS.USE_WAKE_WORD", True)
        """
        try:
            current = self._config
            # パスを分割して最後の要素以外をたどる
            *parts, last = path.split(".")
            for part in parts:
                # 中間パスが存在しない場合は空の辞書を作成
                current = current.setdefault(part, {})
            # 最終的な値を設定
            current[last] = value
            # 設定ファイルに保存
            return self._save_config(self._config)
        except Exception as e:
            logger.error(f"設定更新エラー {path}: {e}")
            return False

    @classmethod
    def get_instance(cls):
        """
        設定管理クラスのインスタンスを取得する（スレッドセーフ）
        
        マルチスレッド環境で安全にシングルトンインスタンスを取得する。
        ロックを使用してインスタンスの重複作成を防ぐ。
        
        Returns:
            ConfigManager: シングルトンインスタンス
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def generate_uuid(self) -> str:
        """
        UUID v4を生成する
        
        ランダムなUUID（Universally Unique Identifier）を生成し、
        クライアントIDなどの一意識別子として使用する。
        
        Returns:
            str: 生成されたUUID文字列
        """
        # Pythonのuuidモジュールを使用してUUID v4を生成
        return str(uuid.uuid4())

    def get_local_ip(self):
        """
        ローカルIPアドレスを取得する
        
        Google DNSサーバーへの仮想接続を作成して、
        ローカルマシンのプライベートIPアドレスを取得する。
        ネットワークエラーの場合はローカルホストアドレスを返す。
        
        Returns:
            str: ローカルIPアドレス（取得失敗時は "127.0.0.1"）
        """
        try:
            # Google DNSサーバーへの仮想接続でローカルIPを取得
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]  # 接続に使用されたローカルIPを取得
            s.close()
            return ip
        except Exception:
            # ネットワークエラーの場合はローカルホストを返す
            return "127.0.0.1"

    def _initialize_client_id(self):
        """
        クライアントIDの初期化
        
        クライアントIDが設定されていない場合、新しいUUIDを生成して設定する。
        クライアントIDはアプリケーションインスタンスの一意識別に使用される。
        """
        if not self.get_config("SYSTEM_OPTIONS.CLIENT_ID"):
            # 新しいクライアントIDを生成
            client_id = self.generate_uuid()
            success = self.update_config("SYSTEM_OPTIONS.CLIENT_ID", client_id)
            if success:
                logger.info(f"新しいクライアントIDを生成しました: {client_id}")
            else:
                logger.error("クライアントIDの保存に失敗しました")

    def _initialize_device_id(self):
        """
        デバイスIDの初期化
        
        デバイスIDが設定されていない場合、デバイスフィンガープリントから
        MACアドレスを取得してデバイスIDとして設定する。
        デバイスIDはハードウェア固有の識別に使用される。
        """
        if not self.get_config("SYSTEM_OPTIONS.DEVICE_ID"):
            try:
                # デバイスフィンガープリントからMACアドレスを取得
                device_hash = self.device_fingerprint.generate_fingerprint().get(
                    "mac_address"
                )
                success = self.update_config("SYSTEM_OPTIONS.DEVICE_ID", device_hash)
                if success:
                    logger.info(f"新しいデバイスIDを生成しました: {device_hash}")
                else:
                    logger.error("デバイスIDの保存に失敗しました")
            except Exception as e:
                logger.error(f"デバイスID生成エラー: {e}")

    def _initialize_mqtt_info(self):
        """
        MQTT情報の初期化
        
        起動時にOTAサーバーから最新のMQTT設定情報を取得し、
        WebSocket情報、デバイスアクティベーション処理も併せて実行する。
        
        Returns:
            dict: MQTT設定情報（取得失敗時は保存済み設定を返す）
        """
        try:
            # OTAサーバーから最新のMQTT情報を取得
            response_data = self._get_ota_version()

            # MQTT情報を処理
            self.handle_mqtt_json(response_data)

            # アクティベーションバージョン設定を取得
            activation_version_setting = self.get_config(
                "SYSTEM_OPTIONS.NETWORK.ACTIVATION_VERSION", "v2"
            )

            # WebSocket設定情報の処理
            if "websocket" in response_data:
                websocket_info = response_data["websocket"]
                self.logger.info("WebSocket設定情報を検出しました")

                # WebSocket URLの更新
                if "url" in websocket_info:
                    self.update_config(
                        "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_URL", websocket_info["url"]
                    )
                    self.logger.info(f"WebSocket URLが更新されました: {websocket_info['url']}")

                # WebSocket トークンの更新
                if "token" in websocket_info:
                    token_value = websocket_info["token"] or "test-token"
                else:
                    token_value = "test-token"

                self.update_config(
                    "SYSTEM_OPTIONS.NETWORK.WEBSOCKET_ACCESS_TOKEN", token_value
                )
                self.logger.info("WebSocket トークンが更新されました")

            # 使用するアクティベーションプロトコルのバージョンを決定
            if activation_version_setting in ["v1", "1"]:
                activation_version = "1"
            else:
                activation_version = "2"
                time.sleep(1)  # サーバー処理の待機
                self.handle_v2_register(response_data)

            self.logger.info(
                f"OTAリクエストでアクティベーションバージョンを使用: {activation_version} "
                f"(設定値: {activation_version_setting})"
            )

        except Exception as e:
            self.logger.error(f"MQTT情報の初期化に失敗しました: {e}")
            # エラー発生時は保存済み設定を返す
            return self.get_config("MQTT_INFO")

    def handle_v2_register(self, response_data):
        """
        v2アクティベーション登録の処理
        
        デバイスアクティベーターを初期化し、サーバーからの
        アクティベーション要求を処理する。既にアクティベート済みの
        デバイスでも再アクティベーションが要求される場合がある。
        
        Args:
            response_data (dict): OTAサーバーからのレスポンスデータ
        """
        # デバイスアクティベーターを初期化（ネットワーク設定前に実行）
        self.device_activator = DeviceActivator(self)
        
        # アクティベーション情報の処理
        if "activation" in response_data:
            self.logger.info("アクティベーション要求を検出、デバイスアクティベーション処理を開始")
            
            # 既にアクティベート済みでもサーバーが要求する場合は再アクティベーション
            if self.device_activator.is_activated():
                self.logger.warning("デバイスは既にアクティベート済みですが、サーバーが再アクティベーションを要求しています")

            # アクティベーション処理を実行
            activation_success = self.device_activator.process_activation(
                response_data["activation"]
            )

            if not activation_success:
                self.logger.error("デバイスアクティベーションに失敗しました")
                # 新規デバイスでアクティベーション失敗時は既存設定を返す
                return self.get_config("SYSTEM_OPTIONS.NETWORK.MQTT_INFO")
            else:
                self.logger.info("デバイスアクティベーションが成功しました。設定を再取得します")
                # 再度OTAレスポンスを取得（アクティベーション情報は含まれないはず）
                response_data = self._get_ota_version()
            # WebSocket設定を処理

    def handle_mqtt_json(self, response_data):
        """
        MQTT JSONデータの処理
        
        OTAサーバーからのレスポンスに含まれるMQTT設定情報を
        抽出し、アプリケーション設定に反映する。
        
        Args:
            response_data (dict): OTAサーバーからのレスポンスデータ
            
        Returns:
            dict: MQTT設定情報（取得失敗時は既存設定）
        """
        # MQTT情報の存在確認
        if "mqtt" in response_data:
            self.logger.info("MQTTサーバー情報が更新されました")
            mqtt_info = response_data["mqtt"]
            if mqtt_info:
                # 設定を更新
                self.update_config("SYSTEM_OPTIONS.NETWORK.MQTT_INFO", mqtt_info)
                self.logger.info("MQTT情報が正常に更新されました")
                return mqtt_info
            else:
                self.logger.warning("MQTT情報の取得に失敗しました。保存済み設定を使用します")
                return self.get_config("SYSTEM_OPTIONS.NETWORK.MQTT_INFO")

    def _get_ota_version(self):
        """
        OTAサーバーからMQTT情報とその他の設定を取得する
        
        デバイス情報とアプリケーション情報をペイロードとして送信し、
        サーバーから最新のMQTT設定、WebSocket設定、アクティベーション情報を取得する。
        
        Returns:
            dict: OTAサーバーからのレスポンスデータ
            
        Raises:
            ValueError: リクエスト失敗時やタイムアウト時
        """
        # 設定からデバイス情報を取得
        MAC_ADDR = self.get_config("SYSTEM_OPTIONS.DEVICE_ID")
        OTA_VERSION_URL = self.get_config("SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL")

        # アプリケーション情報の定義
        app_name = "xiaozhi"
        app_version = "1.6.0"  # アプリケーションバージョン
        board_type = "lc-esp32-s3"  # 立創ESP32-S3開発ボード

        # HTTPリクエストヘッダーの設定
        headers = {
            "Activation-Version": app_version,  # アクティベーションバージョン
            "Device-Id": MAC_ADDR,  # デバイス識別子
            "Client-Id": self.get_config("SYSTEM_OPTIONS.CLIENT_ID"),  # クライアント識別子
            "Content-Type": "application/json",  # コンテントタイプ
            "User-Agent": f"{board_type}/{app_name}-{app_version}",  # ユーザーエージェント
            "Accept-Language": "zh-CN",  # 言語設定（C++版と同一）
        }

        # デバイス情報ペイロードの構築
        payload = {
            "version": 2,  # プロトコルバージョン
            "flash_size": 16777216,  # フラッシュメモリサイズ (16MB)
            "psram_size": 8388608,  # PSRAMサイズ (8MB)
            "minimum_free_heap_size": 7265024,  # 最小利用可能ヒープメモリ
            "mac_address": MAC_ADDR,  # デバイスMACアドレス
            "uuid": self.get_config("SYSTEM_OPTIONS.CLIENT_ID"),  # 一意識別子
            "chip_model_name": "esp32s3",  # チップモデル名
            "chip_info": {
                "model": 9,  # ESP32-S3モデル番号
                "cores": 2,  # CPUコア数
                "revision": 0,  # チップリビジョン番号
                "features": 20,  # 機能フラグ (WiFi + BLE + PSRAM)
            },
            "application": {
                "name": "xiaozhi",  # アプリケーション名
                "version": "1.6.0",  # アプリケーションバージョン
                "compile_time": "2025-4-16T12:00:00Z",  # コンパイル時刻
                "idf_version": "v5.3.2",  # ESP-IDFバージョン
            },
            "partition_table": [  # パーティションテーブル情報
                {
                    "label": "nvs",  # NVS（不揮発性ストレージ）
                    "type": 1,
                    "subtype": 2,
                    "address": 36864,
                    "size": 24576,
                },
                {
                    "label": "otadata",  # OTAデータパーティション
                    "type": 1,
                    "subtype": 0,
                    "address": 61440,
                    "size": 8192,
                },
                {
                    "label": "app0",  # アプリケーションパーティション0
                    "type": 0,
                    "subtype": 0,
                    "address": 65536,
                    "size": 1966080,
                },
                {
                    "label": "app1",  # アプリケーションパーティション1
                    "type": 0,
                    "subtype": 0,
                    "address": 2031616,
                    "size": 1966080,
                },
                {
                    "label": "spiffs",  # SPIFFSファイルシステム
                    "type": 1,
                    "subtype": 130,
                    "address": 3997696,
                    "size": 1966080,
                },
            ],
            "ota": {"label": "app0"},  # 現在のOTAパーティション
            "board": {
                "type": "lc-esp32-s3",  # ボードタイプ
                "name": "立創ESP32-S3開発ボード",  # ボード名
                "features": ["wifi", "ble", "psram", "octal_flash"],  # ボード機能
                "ip": self.get_local_ip(),  # ローカルIPアドレス
                "mac": MAC_ADDR,  # MACアドレス
            },
        }

        try:
            # OTAサーバーへのPOSTリクエスト送信
            response = requests.post(
                OTA_VERSION_URL,
                headers=headers,
                json=payload,
                timeout=10,  # タイムアウト設定（リクエストがハングするのを防ぐ）
                proxies={"http": None, "https": None},  # プロキシを無効化
            )

            # HTTPステータスコードの確認
            if response.status_code != 200:
                self.logger.error(f"OTAサーバーエラー: HTTP {response.status_code}")
                raise ValueError(f"OTAサーバーがエラーステータスコードを返しました: {response.status_code}")

            # JSONレスポンスデータの解析
            response_data = response.json()
            # デバッグ情報：完全なOTAレスポンスを出力
            self.logger.debug(
                f"OTAサーバーレスポンスデータ: "
                f"{json.dumps(response_data, indent=4, ensure_ascii=False)}"
            )

            # レスポンスデータをコンソールに出力（デバッグ用）
            print(json.dumps(response_data, indent=4, ensure_ascii=False))

            return response_data

        except requests.Timeout:
            self.logger.error("OTAリクエストがタイムアウトしました。ネットワークまたはサーバーの状態を確認してください")
            raise ValueError("OTAリクエストがタイムアウトしました。しばらく経ってから再試行してください。")

        except requests.RequestException as e:
            self.logger.error(f"OTAリクエストが失敗しました: {e}")
            raise ValueError("OTAサーバーに接続できません。ネットワーク接続を確認してください。")

    def get_app_path(self) -> Path:
        """
        アプリケーションのベースパスを取得する
        
        開発環境とパッケージ環境の両方に対応し、
        アプリケーションのルートディレクトリパスを返す。
        
        Returns:
            Path: アプリケーションのベースパス
        """
        return get_app_path()
