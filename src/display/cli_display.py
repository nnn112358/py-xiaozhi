import asyncio
import os
import platform
import threading
import time
from typing import Callable, Optional

from src.display.base_display import BaseDisplay

# 異なるOSでのpynputインポートを処理
try:
    if platform.system() == "Windows":
        from pynput import keyboard as pynput_keyboard
    elif os.environ.get("DISPLAY"):
        from pynput import keyboard as pynput_keyboard
    else:
        pynput_keyboard = None
except ImportError:
    pynput_keyboard = None

from src.utils.logging_config import get_logger


class CliDisplay(BaseDisplay):
    def __init__(self):
        super().__init__()  # 親クラスの初期化を呼び出し
        """CLIディスプレイを初期化."""
        self.logger = get_logger(__name__)
        self.running = True

        # ステータス関連
        self.current_status = "未接続"
        self.current_text = "待機中"
        self.current_emotion = "😊"
        self.current_volume = 0  # 現在の音量属性を追加

        # コールバック関数
        self.auto_callback = None
        self.status_callback = None
        self.text_callback = None
        self.emotion_callback = None
        self.abort_callback = None
        self.send_text_callback = None
        # キー状態
        self.is_r_pressed = False
        # 組み合わせキーサポートを追加
        self.pressed_keys = set()

        # ステータスキャッシュ
        self.last_status = None
        self.last_text = None
        self.last_emotion = None
        self.last_volume = None

        # キーボードリスナー
        self.keyboard_listener = None

        # 非同期操作のためのイベントループを追加
        self.loop = asyncio.new_event_loop()

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
    ):
        """コールバック関数を設定."""
        self.status_callback = status_callback
        self.text_callback = text_callback
        self.emotion_callback = emotion_callback
        self.auto_callback = auto_callback
        self.abort_callback = abort_callback
        self.send_text_callback = send_text_callback

    def update_button_status(self, text: str):
        """ボタンステータスを更新."""
        print(f"ボタンステータス: {text}")

    def update_status(self, status: str):
        """ステータステキストを更新."""
        if status != self.current_status:
            self.current_status = status
            self._print_current_status()

    def update_text(self, text: str):
        """TTSテキストを更新."""
        if text != self.current_text:
            self.current_text = text
            self._print_current_status()

    def update_emotion(self, emotion_path: str):
        """表情を更新
        emotion_path: GIFファイルパスまたは表情文字列
        """
        if emotion_path != self.current_emotion:
            # GIFファイルパスの場合、ファイル名を表情名として抽出
            if emotion_path.endswith(".gif"):
                # パスからファイル名を抽出し、.gif拡張子を削除
                emotion_name = os.path.basename(emotion_path)
                emotion_name = emotion_name.replace(".gif", "")
                self.current_emotion = f"[{emotion_name}]"
            else:
                # GIFパスでない場合、そのまま使用
                self.current_emotion = emotion_path

            self._print_current_status()

    def is_combo(self, *keys):
        """一組のキーが同時に押されているかを判定."""
        return all(k in self.pressed_keys for k in keys)

    def start_keyboard_listener(self):
        """キーボード監視を開始."""
        # pynputが利用できない場合、警告をログに記録して戻る
        if pynput_keyboard is None:
            self.logger.warning(
                "キーボード監視利用不可：pynputライブラリが正しく読み込まれませんでした。基本的なコマンドライン入力を使用します。"
            )
            return

        try:

            def on_press(key):
                try:
                    # 押されたキーを記録
                    if (
                        key == pynput_keyboard.Key.alt_l
                        or key == pynput_keyboard.Key.alt_r
                    ):
                        self.pressed_keys.add("alt")
                    elif (
                        key == pynput_keyboard.Key.shift_l
                        or key == pynput_keyboard.Key.shift_r
                    ):
                        self.pressed_keys.add("shift")
                    elif hasattr(key, "char") and key.char:
                        self.pressed_keys.add(key.char.lower())

                    # 自動対話モード - Alt+Shift+A
                    if self.is_combo("alt", "shift", "a") and self.auto_callback:
                        self.auto_callback()

                    # 対話を中断 - Alt+Shift+X
                    if self.is_combo("alt", "shift", "x") and self.abort_callback:
                        self.abort_callback()

                except Exception as e:
                    self.logger.error(f"キーボードイベント処理エラー: {e}")

            def on_release(key):
                try:
                    # 解放されたキーをクリア
                    if (
                        key == pynput_keyboard.Key.alt_l
                        or key == pynput_keyboard.Key.alt_r
                    ):
                        self.pressed_keys.discard("alt")
                    elif (
                        key == pynput_keyboard.Key.shift_l
                        or key == pynput_keyboard.Key.shift_r
                    ):
                        self.pressed_keys.discard("shift")
                    elif hasattr(key, "char") and key.char:
                        self.pressed_keys.discard(key.char.lower())
                except Exception as e:
                    self.logger.error(f"キーボードイベント処理エラー: {e}")

            # リスナーを作成して開始
            self.keyboard_listener = pynput_keyboard.Listener(
                on_press=on_press, on_release=on_release
            )
            self.keyboard_listener.start()
            self.logger.info("キーボードリスナー初期化成功")
        except Exception as e:
            self.logger.error(f"キーボードリスナー初期化失敗: {e}")

    def stop_keyboard_listener(self):
        """キーボード監視を停止."""
        if self.keyboard_listener:
            try:
                self.keyboard_listener.stop()
                self.keyboard_listener = None
                self.logger.info("キーボードリスナーが停止されました")
            except Exception as e:
                self.logger.error(f"キーボードリスナー停止失敗: {e}")

    def start(self):
        """CLIディスプレイを開始."""
        self._print_help()

        # ステータス更新スレッドを開始
        self.start_update_threads()

        # キーボード監視スレッドを開始
        keyboard_thread = threading.Thread(target=self._keyboard_listener)
        keyboard_thread.daemon = True
        keyboard_thread.start()

        # キーボード監視を開始
        self.start_keyboard_listener()

        # メインループ
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.on_close()

    def on_close(self):
        """CLIディスプレイを閉じる."""
        self.running = False
        print("\nアプリケーションを終了中...")
        self.stop_keyboard_listener()

    def _print_help(self):
        """ヘルプ情報を表示."""
        print("\n=== 小智AIコマンドライン制御 ===")
        print("利用可能なコマンド：")
        print("  r     - 対話を開始/停止")
        print("  x     - 現在の対話を中断")
        print("  s     - 現在のステータスを表示")
        print("  v 数字 - 音量設定(0-100)")
        print("  q     - プログラム終了")
        print("  h     - このヘルプ情報を表示")
        print("ショートカットキー：")
        print("  Alt+Shift+A - 自動対話モード")
        print("  Alt+Shift+X - 現在の対話を中断")
        print("=====================\n")

    def _keyboard_listener(self):
        """キーボード監視スレッド."""
        try:
            while self.running:
                cmd = input().lower().strip()
                if cmd == "q":
                    self.on_close()
                    break
                elif cmd == "h":
                    self._print_help()
                elif cmd == "r":
                    if self.auto_callback:
                        self.auto_callback()
                elif cmd == "x":
                    if self.abort_callback:
                        self.abort_callback()
                elif cmd == "s":
                    self._print_current_status()
                elif cmd.startswith("v "):  # 音量コマンド処理を追加
                    try:
                        volume = int(cmd.split()[1])  # 音量値を取得
                        if 0 <= volume <= 100:
                            self.update_volume(volume)
                            print(f"音量が設定されました: {volume}%")
                        else:
                            print("音量は0-100の間である必要があります")
                    except (IndexError, ValueError):
                        print("無効な音量値です。形式：v <0-100>")
                else:
                    if self.send_text_callback:
                        # アプリケーションのイベントループを取得してその中でコルーチンを実行
                        from src.application import Application

                        app = Application.get_instance()
                        if app and app.loop:
                            asyncio.run_coroutine_threadsafe(
                                self.send_text_callback(cmd), app.loop
                            )
                        else:
                            print("アプリケーションインスタンスまたはイベントループが利用できません")
        except Exception as e:
            self.logger.error(f"キーボード監視エラー: {e}")

    def start_update_threads(self):
        """更新スレッドを開始."""

        def update_loop():
            while self.running:
                try:
                    # ステータスを更新
                    if self.status_callback:
                        status = self.status_callback()
                        if status and status != self.current_status:
                            self.update_status(status)

                    # テキストを更新
                    if self.text_callback:
                        text = self.text_callback()
                        if text and text != self.current_text:
                            self.update_text(text)

                    # 表情を更新
                    if self.emotion_callback:
                        emotion = self.emotion_callback()
                        if emotion and emotion != self.current_emotion:
                            self.update_emotion(emotion)

                except Exception as e:
                    self.logger.error(f"ステータス更新エラー: {e}")
                time.sleep(0.1)

        # 更新スレッドを開始
        threading.Thread(target=update_loop, daemon=True).start()

    def _print_current_status(self):
        """現在のステータスを表示."""
        # ステータスの変化があるかチェック
        status_changed = (
            self.current_status != self.last_status
            or self.current_text != self.last_text
            or self.current_emotion != self.last_emotion
            or self.current_volume != self.last_volume
        )

        if status_changed:
            print("\n=== 現在のステータス ===")
            print(f"ステータス: {self.current_status}")
            print(f"テキスト: {self.current_text}")
            print(f"表情: {self.current_emotion}")
            print(f"音量: {self.current_volume}%")
            print("===============\n")

            # キャッシュを更新
            self.last_status = self.current_status
            self.last_text = self.current_text
            self.last_emotion = self.current_emotion
            self.last_volume = self.current_volume
