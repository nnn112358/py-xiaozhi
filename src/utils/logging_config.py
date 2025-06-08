"""
ログ設定モジュール

アプリケーション全体のログシステムを設定・管理するモジュールです。
コンソールとファイルへの出力、ログローテーション、カラー表示などの機能を提供します。
"""
import logging
from logging.handlers import TimedRotatingFileHandler

from colorlog import ColoredFormatter


def setup_logging():
    """ログシステムを設定.
    
    プロジェクト全体のログシステムを初期化し、コンソールとファイルの
    両方にログを出力するように設定します。ログファイルは日別にローテーションされ、
    30日分が保持されます。
    
    Returns:
        Path: ログファイルのパス
    """
    from .resource_finder import get_project_root

    # resource_finderを使用してプロジェクトルートディレクトリを取得し、logsディレクトリを作成
    project_root = get_project_root()
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)

    # ログファイルパス
    log_file = log_dir / "app.log"

    # ルートロガーを作成
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # ルートログレベルを設定

    # 既存のハンドラーをクリア（重複追加を回避）
    if root_logger.handlers:
        root_logger.handlers.clear()

    # コンソールハンドラーを作成
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 日次ローテーションファイルハンドラーを作成
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",  # 毎日深夜にローテーション
        interval=1,  # 1日ごと
        backupCount=30,  # 30日分のログを保持
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.suffix = "%Y-%m-%d.log"  # ログファイルのサフィックス形式

    # フォーマッターを作成
    formatter = logging.Formatter(
        "%(asctime)s[%(name)s] - %(levelname)s - %(message)s - %(threadName)s"
    )

    # コンソール用カラーフォーマッター
    color_formatter = ColoredFormatter(
        "%(green)s%(asctime)s%(reset)s[%(blue)s%(name)s%(reset)s] - "
        "%(log_color)s%(levelname)s%(reset)s - %(green)s%(message)s%(reset)s - "
        "%(cyan)s%(threadName)s%(reset)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "white",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={"asctime": {"green": "green"}, "name": {"blue": "blue"}},
    )
    console_handler.setFormatter(color_formatter)
    file_handler.setFormatter(formatter)

    # ハンドラーをルートロガーに追加
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # ログ設定情報を出力
    logging.info("ログシステムが初期化されました。ログファイル: %s", log_file)

    return log_file


def get_logger(name):
    """統一設定されたロガーを取得.

    Args:
        name: ロガー名、通常はモジュール名

    Returns:
        logging.Logger: 設定済みのロガー

    使用例:
        logger = get_logger(__name__)
        logger.info("これは情報メッセージです")
        logger.error("エラーが発生しました: %s", error_msg)
    """
    logger = logging.getLogger(name)

    # ヘルパーメソッドを追加
    def log_error_with_exc(msg, *args, **kwargs):
        """エラーを記録し、自動的に例外スタックトレースを含める."""
        kwargs["exc_info"] = True
        logger.error(msg, *args, **kwargs)

    # ロガーに追加
    logger.error_exc = log_error_with_exc

    return logger
