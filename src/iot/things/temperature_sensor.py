import asyncio
import json
import threading
import time
from datetime import datetime

from src.application import Application
from src.constants.constants import DeviceState
from src.iot.thing import Thing
from src.network.mqtt_client import MqttClient


class TemperatureSensor(Thing):
    def __init__(self):
        super().__init__("TemperatureSensor", "温度センサーデバイス")
        self.temperature = 0.0  # 初期温度値は摂氏0度
        self.humidity = 0.0  # 初期湿度値は0%
        self.last_update_time = 0  # 最後の更新時刻
        self.is_running = False
        self.mqtt_client = None
        self.app = None  # app属性をNoneで初期化

        print("[IoTデバイス] 温度センサー受信端の初期化が完了しました")

        # プロパティを定義
        self.add_property("temperature", "現在の温度(摂氏度)", lambda: self.temperature)
        self.add_property("humidity", "現在の湿度(%)", lambda: self.humidity)
        self.add_property(
            "last_update_time", "最終更新時刻", lambda: self.last_update_time
        )

        # self.add_method("getTemperature", "温度センサーデータを取得",
        #                 [],
        #                 lambda params: self.get_temperature())

        # MQTTクライアントを初期化
        self._init_mqtt()

    def _init_mqtt(self):
        """MQTTクライアントを初期化."""
        from src.utils.config_manager import ConfigManager

        config = ConfigManager.get_instance()
        try:
            self.mqtt_client = MqttClient(
                server=config.get_config("TEMPERATURE_SENSOR_MQTT_INFO.endpoint"),
                port=config.get_config("TEMPERATURE_SENSOR_MQTT_INFO.port"),
                username=config.get_config("TEMPERATURE_SENSOR_MQTT_INFO.username"),
                password=config.get_config("TEMPERATURE_SENSOR_MQTT_INFO.password"),
                # センサーデータ送信のトピックを購読
                subscribe_topic=config.get_config(
                    "TEMPERATURE_SENSOR_MQTT_INFO.subscribe_topic"
                ),
            )

            # カスタムメッセージ処理コールバックを設定
            self.mqtt_client.client.on_message = self._on_mqtt_message

            # MQTTサーバーに接続
            self.mqtt_client.connect()
            self.mqtt_client.start()
            print("[温度センサー] MQTTクライアントが接続されました")
        except Exception as e:
            print(f"[温度センサー] MQTT接続に失敗しました: {e}")

    def _on_mqtt_message(self, client, userdata, msg):
        """MQTTメッセージを処理."""
        try:
            topic = msg.topic
            payload = msg.payload.decode("utf-8")
            print(f"[温度センサー] データを受信 - トピック: {topic}, 内容: {payload}")

            # メッセージをJSONとして解析を試行
            try:
                data = json.loads(payload)

                # 受信したのが温度センサーデータの場合
                if "temperature" in data and "humidity" in data:
                    # 温度と湿度を更新
                    self.temperature = data.get("temperature")
                    self.humidity = data.get("humidity")

                    # タイムスタンプを処理 - 複数の形式をサポート
                    timestamp = data.get("timestamp")
                    if timestamp is not None:
                        # 文字列形式の場合（ISO時間）
                        if isinstance(timestamp, str):
                            try:
                                # ISO形式の時間文字列の解析を試行
                                dt = datetime.fromisoformat(
                                    timestamp.replace("Z", "+00:00")
                                )
                                self.last_update_time = int(dt.timestamp())
                            except ValueError:
                                # 解析に失敗した場合、現在時刻を使用
                                self.last_update_time = int(time.time())
                        else:
                            # 数値の場合、直接使用
                            self.last_update_time = int(timestamp)
                    else:
                        # タイムスタンプが提供されていない場合、現在時刻を使用
                        self.last_update_time = int(time.time())

                    # 更新情報を出力
                    update_time = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(self.last_update_time)
                    )

                    print(
                        f"[温度センサー] データ更新: 温度={self.temperature}°C, "
                        f"湿度={self.humidity}%, 時刻={update_time}"
                    )
                    # デバイス状態を設定してメッセージを送信
                    self.handle_temperature_update()
            except json.JSONDecodeError:
                print(f"[温度センサー] JSONメッセージを解析できません: {payload}")

        except Exception as e:
            print(f"[温度センサー] MQTTメッセージ処理中にエラーが発生しました: {e}")

    def handle_temperature_update(self):
        """温度更新後の操作を処理."""
        try:
            if self.app is None:
                self.app = Application.get_instance()

            # デバイス状態をIDLEに設定してIoT状態を更新
            self.app.set_device_state(DeviceState.IDLE)

            # スレッドを使用して非同期操作を処理、MQTTスレッドのブロッキングを回避
            threading.Thread(target=self._delayed_send_wake_word, daemon=True).start()

        except Exception as e:
            print(f"[温度センサー] 温度更新処理中にエラーが発生しました: {e}")

    def _delayed_send_wake_word(self):
        """ウェイクワードメッセージの遅延送信、接続の安定性を確保."""
        try:
            # 音声チャンネルが開かれているかチェック
            channel_opened = False
            if not self.app.protocol.is_audio_channel_opened():
                # まず音声チャンネルを開く
                future = asyncio.run_coroutine_threadsafe(
                    self.app.protocol.open_audio_channel(), self.app.loop
                )
                # 操作の完了を待ち、結果を取得
                try:
                    channel_opened = future.result(timeout=5.0)
                except Exception as e:
                    print(f"[温度センサー] 音声チャンネルのオープンに失敗しました: {e}")
                    return

                if channel_opened:
                    # 接続安定を確保するため3秒待機
                    print("[温度センサー] 音声チャンネルが開かれました、3秒待機後にウェイクワードを送信...")
                    time.sleep(3)
                else:
                    print("[温度センサー] 音声チャンネルのオープンに失敗しました")
                    return
            # IoTデバイス状態を更新
            self.app._update_iot_states(delta=True)

            # 音声チャンネルが開かれました、ウェイクワードメッセージを送信
            asyncio.run_coroutine_threadsafe(
                self.app.protocol.send_wake_word_detected(
                    "温湿度センサーデータの放送(メソッド呼び出し不要)"
                ),
                self.app.loop,
            )
            print("[温度センサー] ウェイクワードメッセージを送信しました")

        except Exception as e:
            print(f"[温度センサー] ウェイクワードの遅延送信中にエラーが発生しました: {e}")

    def _request_sensor_data(self):
        """すべてのセンサーに現在の状態の報告を要求."""
        if self.mqtt_client:
            # 2つのコマンド形式に対応
            command = {
                "command": "get_data",
                "action": "get_data",  # actionフィールドのサポートを追加
                "timestamp": int(time.time()),
            }
            self.mqtt_client.publish(json.dumps(command))
            print("[温度センサー] データ要求コマンドを送信しました")

    def send_command(self, action_name, **kwargs):
        """センサーにコマンドを送信."""
        if self.mqtt_client:
            command = {
                "command": action_name,
                "action": action_name,
                "timestamp": int(time.time()),
            }
            # 追加パラメータを追加
            command.update(kwargs)

            self.mqtt_client.publish(json.dumps(command))
            print(f"[温度センサー] コマンドを送信しました: {action_name}")
            return True
        return False

    def get_temperature(self):
        return {
            "success": True,
            "message": f"[温度センサー] データ更新: 温度={self.temperature}°C, "
            f"湿度={self.humidity}%, 時刻={self.last_update_time}",
        }

    def __del__(self):
        """デストラクタ関数、リソースが正しく解放されることを確保."""
        if self.mqtt_client:
            try:
                self.mqtt_client.stop()
            except Exception:
                pass


# テストコード
# if __name__ == "__main__":
#     # 温度センサー受信端インスタンスを作成
#     sensor = TemperatureSensor()
#
#     # センサー受信を開始
#     sensor.invoke({"method": "Start"})
#
#     try:
#         # 10分間実行
#         print("温度センサー受信端が開始されました、データ受信を待機中...")
#         print("Ctrl+Cでプログラムを停止できます")
#         print("'send'を入力してデータ要求コマンドを送信することもできます")
#
#         while True:
#             cmd = input("> ")
#             if cmd.lower() == 'send':
#                 sensor.send_command("get_data")
#             elif cmd.lower() == 'quit' or cmd.lower() == 'exit':
#                 break
#             elif cmd.lower() == 'help':
#                 print("コマンド一覧:")
#                 print("  send  - データ要求コマンドを送信")
#                 print("  quit  - プログラムを終了")
#                 print("  help  - ヘルプを表示")
#             time.sleep(0.1)
#
#     except KeyboardInterrupt:
#         print("\nプログラムがユーザーによって中断されました")
#     finally:
#         # センサー受信を停止
#         sensor.invoke({"method": "Stop"})
