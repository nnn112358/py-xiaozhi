"""
py-xiaozhi メインエントリーポイント

AI音声アシスタント小智のPythonクライアント実装
- GUI/CLIモードをサポート
- WebSocket/MQTTプロトコルに対応
- 音声認識、IoT制御、視覚認識機能を提供
"""
import argparse
import io
import signal
import sys

from src.application import Application
from src.utils.logging_config import get_logger, setup_logging

# ロガーを初期化
logger = get_logger(__name__)


def parse_args():
    """コマンドライン引数を解析する."""
    # sys.stdout と sys.stderr が None でないことを確保
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    # 引数パーサーを作成
    parser = argparse.ArgumentParser(description="小智AIクライアント")

    # インターフェースモードパラメータを追加
    parser.add_argument(
        "--mode",
        choices=["gui", "cli"],
        default="gui",
        help="実行モード：gui(グラフィカルインターフェース) または cli(コマンドライン)",
    )

    # プロトコル選択パラメータを追加
    parser.add_argument(
        "--protocol",
        choices=["mqtt", "websocket"],
        default="websocket",
        help="通信プロトコル：mqtt または websocket",
    )

    return parser.parse_args()


def signal_handler(sig, frame):
    """Ctrl+C シグナルを処理する."""
    logger.info("中断シグナルを受信しました。終了中...")
    app = Application.get_instance()
    app.shutdown()
    sys.exit(0)


def main():
    """プログラムのエントリーポイント."""
    # シグナルハンドラーを登録
    signal.signal(signal.SIGINT, signal_handler)
    
    # コマンドライン引数を解析
    args = parse_args()
    
    try:
        # ログを設定
        setup_logging()
        
        # アプリケーションを作成して実行
        app = Application.get_instance()

        logger.info("アプリケーションが開始されました。終了するには Ctrl+C を押してください")

        # パラメータを渡してアプリケーションを開始
        app.run(mode=args.mode, protocol=args.protocol)

        # GUI モードで PyQt インターフェースを使用している場合、Qt イベントループを開始
        if args.mode == "gui":
            # QApplication インスタンスを取得してイベントループを実行
            try:
                from PyQt5.QtWidgets import QApplication

                qt_app = QApplication.instance()
                if qt_app:
                    logger.info("Qt イベントループを開始")
                    qt_app.exec_()
                    logger.info("Qt イベントループが終了")
            except ImportError:
                logger.warning("PyQt5 がインストールされていません。Qt イベントループを開始できません")
            except Exception as e:
                logger.error(f"Qt イベントループでエラーが発生: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"プログラムでエラーが発生: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
