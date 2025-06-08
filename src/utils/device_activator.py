"""デバイスアクティベーションモジュール

デバイスの初回登録と認証を管理するモジュールです。
サーバーとの認証プロトコルを実装し、デバイスの一意性を保証します。
"""
import json
import time

import requests

from src.utils.common_utils import handle_verification_code
from src.utils.device_fingerprint import get_device_fingerprint
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class DeviceActivator:
    """デバイスアクティベーション管理クラス - ConfigManagerと連携して使用
    
    デバイスの初回登録、認証、アクティベーション状態を管理します。
    HMAC-SHA256ベースの認証プロトコルを実装し、デバイスの一意性と
    セキュリティを保証します。
    """

    def __init__(self, config_manager):
        """デバイスアクティベータを初期化.
        
        Args:
            config_manager: 設定管理インスタンス
        """
        self.logger = get_logger(__name__)
        self.config_manager = config_manager
        # device_fingerprintインスタンスを使用してデバイスIDを管理
        self.device_fingerprint = get_device_fingerprint()
        # デバイスID情報が作成されていることを確認
        self._ensure_device_identity()

    def _ensure_device_identity(self):
        """デバイスID情報が作成されていることを確認."""
        serial_number, hmac_key, is_activated = (
            self.device_fingerprint.ensure_device_identity()
        )
        self.logger.info(
            f"デバイスID情報: シリアル番号: {serial_number}, アクティベーション状態: {'アクティベート済み' if is_activated else '未アクティベート'}"
        )

    def has_serial_number(self) -> bool:
        """シリアル番号が存在するかチェック.
        
        Returns:
            bool: シリアル番号が存在する場合True
        """
        return self.device_fingerprint.has_serial_number()

    def get_serial_number(self) -> str:
        """シリアル番号を取得.
        
        Returns:
            str: デバイスのシリアル番号
        """
        return self.device_fingerprint.get_serial_number()

    def burn_serial_number(self, serial_number: str) -> bool:
        """シリアル番号を模擬efuseに書き込み.
        
        Args:
            serial_number: 書き込むシリアル番号
            
        Returns:
            bool: 書き込みが成功した場合True
        """
        return self.device_fingerprint.burn_serial_number(serial_number)

    def burn_hmac_key(self, hmac_key: str) -> bool:
        """HMAC鍵を模擬efuseに書き込み.
        
        Args:
            hmac_key: 書き込むHMAC鍵
            
        Returns:
            bool: 書き込みが成功した場合True
        """
        return self.device_fingerprint.burn_hmac_key(hmac_key)

    def get_hmac_key(self) -> str:
        """HMAC鍵を取得.
        
        Returns:
            str: デバイスのHMAC鍵
        """
        return self.device_fingerprint.get_hmac_key()

    def set_activation_status(self, status: bool) -> bool:
        """アクティベーション状態を設定.
        
        Args:
            status: アクティベーション状態（True=アクティベート済み）
            
        Returns:
            bool: 設定が成功した場合True
        """
        return self.device_fingerprint.set_activation_status(status)

    def is_activated(self) -> bool:
        """デバイスがアクティベート済みかチェック.
        
        Returns:
            bool: アクティベート済みの場合True
        """
        return self.device_fingerprint.is_activated()

    def generate_hmac(self, challenge: str) -> str:
        """HMAC鍵を使用して署名を生成.
        
        Args:
            challenge: サーバーから受信したチャレンジ文字列
            
        Returns:
            str: HMAC-SHA256署名
        """
        return self.device_fingerprint.generate_hmac(challenge)

    def process_activation(self, activation_data: dict) -> bool:
        """アクティベーションプロセスを処理.

        Args:
            activation_data: アクティベーション情報を含む辞書、少なくともchallengeとcodeを含む必要がある

        Returns:
            bool: アクティベーションが成功したかどうか
        """
        # アクティベーションチャレンジと検証コードがあるかチェック
        if not activation_data.get("challenge"):
            self.logger.error("アクティベーションデータにchallengeフィールドがありません")
            return False

        if not activation_data.get("code"):
            self.logger.error("アクティベーションデータにcodeフィールドがありません")
            return False

        challenge = activation_data["challenge"]
        code = activation_data["code"]
        message = activation_data.get("message", "xiaozhi.meで検証コードを入力してください")

        # シリアル番号をチェック
        if not self.has_serial_number():
            self.logger.error("デバイスにシリアル番号がありません、アクティベーションできません")
            print(
                "\nエラー: デバイスにシリアル番号がありません、アクティベーションできません。efuse.jsonファイルが正しく作成されていることを確認してください"
            )
            print("デバイスID情報を再作成して再試行します...")

            # device_fingerprintを使用してシリアル番号とHMACキーを生成
            serial_number, hmac_key, _ = (
                self.device_fingerprint.ensure_device_identity()
            )

            if serial_number and hmac_key:
                self.logger.info("デバイスシリアル番号とHMACキーを自動作成しました")
                print(f"デバイスシリアル番号を自動作成しました: {serial_number}")
            else:
                self.logger.error("シリアル番号またはHMACキーの作成に失敗しました")
                return False

        # ユーザーにアクティベーション情報を表示
        self.logger.info(f"アクティベーションプロンプト: {message}")
        self.logger.info(f"検証コード: {code}")

        # 検証コードプロンプトテキストを構築して表示
        text = f"コントロールパネルにログインしてデバイスを追加し、検証コードを入力してください：{' '.join(code)}"
        print("\n==================")
        print(text)
        print("==================\n")
        handle_verification_code(text)
        # 音声で検証コードを再生
        try:
            # 非ブロッキングスレッドで音声を再生
            from src.utils.common_utils import play_audio_nonblocking

            play_audio_nonblocking(text)
            self.logger.info("検証コードの音声プロンプトを再生中")
        except Exception as e:
            self.logger.error(f"検証コード音声の再生に失敗しました: {e}")

        # デバイスのアクティベーションを試行
        return self.activate(challenge)

    def activate(self, challenge: str) -> bool:
        """アクティベーションプロセスを実行.

        Args:
            challenge: サーバーから送信されたチャレンジ文字列

        Returns:
            bool: アクティベーションが成功したかどうか
        """
        # シリアル番号をチェック
        serial_number = self.get_serial_number()
        if not serial_number:
            self.logger.error("デバイスにシリアル番号がありません、HMAC検証ステップを完了できません")
            return False

        # HMAC署名を計算
        hmac_signature = self.generate_hmac(challenge)
        if not hmac_signature:
            self.logger.error("HMAC署名を生成できません、アクティベーションに失敗しました")
            return False

        # サーバーの期待する形式に合わせて外部ペイロードをラップ
        payload = {
            "Payload": {
                "algorithm": "hmac-sha256",
                "serial_number": serial_number,
                "challenge": challenge,
                "hmac": hmac_signature,
            }
        }

        # アクティベーションURLを取得
        ota_url = self.config_manager.get_config(
            "SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL"
        )
        if not ota_url:
            self.logger.error("OTA URL設定が見つかりません")
            return False

        # URLがスラッシュで終わることを確認
        if not ota_url.endswith("/"):
            ota_url += "/"

        activate_url = f"{ota_url}activate"

        # リクエストヘッダーを設定
        headers = {
            "Activation-Version": "2",
            "Device-Id": self.config_manager.get_config("SYSTEM_OPTIONS.DEVICE_ID"),
            "Client-Id": self.config_manager.get_config("SYSTEM_OPTIONS.CLIENT_ID"),
            "Content-Type": "application/json",
        }

        # リトライロジック
        max_retries = 60  # リトライ回数を増やし、最大5分間待機
        retry_interval = 5  # 5秒のリトライ間隔を設定

        error_count = 0
        last_error = None

        for attempt in range(max_retries):
            try:
                self.logger.info(f"アクティベーションを試行中 (試行 {attempt + 1}/{max_retries})...")

                # アクティベーションリクエストを送信
                response = requests.post(
                    activate_url, headers=headers, json=payload, timeout=10
                )

                # 完全なレスポンスを表示
                print(f"\nアクティベーションレスポンス (HTTP {response.status_code}):")
                try:
                    response_json = response.json()
                    print(json.dumps(response_json, indent=2))
                except Exception:
                    print(response.text)

                # レスポンスステータスコードをチェック
                if response.status_code == 200:
                    # アクティベーション成功
                    self.logger.info("デバイスのアクティベーションに成功しました！")
                    print("\n*** デバイスのアクティベーションに成功しました！ ***\n")
                    self.set_activation_status(True)
                    return True
                elif response.status_code == 202:
                    # ユーザーの検証コード入力を待機
                    self.logger.info("ユーザーの検証コード入力を待機中、待機を継続します...")
                    print("\nユーザーがウェブサイトで検証コードを入力するのを待機中、待機を継続します...\n")
                    time.sleep(retry_interval)
                else:
                    # その他のエラーを処理しながらリトライを継続
                    error_msg = "不明なエラー"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get(
                            "error", f"不明なエラー (ステータスコード: {response.status_code})"
                        )
                    except Exception:
                        error_msg = f"サーバーエラーが返されました (ステータスコード: {response.status_code})"

                    # エラーを記録するがプロセスは終了しない
                    if error_msg != last_error:
                        # エラーメッセージが変更された場合のみ記録し、重複ログを回避
                        self.logger.warning(
                            f"サーバーレスポンス: {error_msg}、検証コードのアクティベーションを待機中"
                        )
                        print(f"\nサーバーレスポンス: {error_msg}、検証コードのアクティベーションを待機中...\n")
                        last_error = error_msg

                    # 連続する同じエラーをカウント
                    if "Device not found" in error_msg:
                        error_count += 1
                        if error_count >= 5 and error_count % 5 == 0:
                            # 同じエラーが5回ごとに、新しい検証コードを取得する必要があるかもしれないことをユーザーに提示
                            print(
                                "\nヒント: エラーが続く場合は、ウェブサイトでページを更新して新しい検証コードを取得する必要があるかもしれません\n"
                            )

                    time.sleep(retry_interval)

            except requests.Timeout:
                time.sleep(retry_interval)
            except Exception as e:
                self.logger.warning(f"アクティベーションプロセス中にエラーが発生しました: {e}、リトライ中...")
                print(f"アクティベーションプロセス中にエラーが発生しました: {e}、リトライ中...")
                time.sleep(retry_interval)

        # 最大リトライ回数に達した場合のみ本当に失敗とする
        self.logger.error(
            f"アクティベーションに失敗しました、最大リトライ回数 ({max_retries}) に達しました、最後のエラー: {last_error}"
        )
        print("\nアクティベーションに失敗しました、最大待機時間に達しました。新しい検証コードを取得して再度アクティベーションを試みてください\n")
        return False
