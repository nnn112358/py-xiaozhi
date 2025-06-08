import platform

from src.utils.config_manager import ConfigManager

config = ConfigManager.get_instance()


class ListeningMode:
    """リスニングモード."""

    ALWAYS_ON = "always_on"
    AUTO_STOP = "auto_stop"
    MANUAL = "manual"


class AbortReason:
    """中断理由."""

    NONE = "none"
    WAKE_WORD_DETECTED = "wake_word_detected"
    USER_INTERRUPTION = "user_interruption"


class DeviceState:
    """デバイスステータス."""

    IDLE = "idle"
    CONNECTING = "connecting"
    LISTENING = "listening"
    SPEAKING = "speaking"


class EventType:
    """イベントタイプ."""

    SCHEDULE_EVENT = "schedule_event"
    AUDIO_INPUT_READY_EVENT = "audio_input_ready_event"
    AUDIO_OUTPUT_READY_EVENT = "audio_output_ready_event"


def is_official_server(ws_addr: str) -> bool:
    """小智公式サーバーアドレスかどうかを判定.

    Args:
        ws_addr (str): WebSocketアドレス

    Returns:
        bool: 小智公式サーバーアドレスかどうか
    """
    return "api.tenclass.net" in ws_addr


def get_frame_duration() -> int:
    """デバイスのフレーム長を取得（最適化版：独立PyAudioインスタンスの作成を回避）

    返し値:
        int: フレーム長（ミリ秒）
    """
    try:
        # 公式サーバーかどうかをチェック
        ota_url = config.get_config("SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL")
        if not is_official_server(ota_url):
            return 60

        system = platform.system()

        if system == "Windows":
            # Windowsは通常、小さなバッファをサポート
            return 20
        elif system == "Linux":
            # Linuxは遅延を減らすためにやや大きなバッファが必要な場合がある（うまくいかない場合は60に変更）
            return 60
        elif system == "Darwin":  # macOS
            # macOSは通常良好なオーディオパフォーマンスを持つ
            return 20
        else:
            # その他のシステムは保守的な値を使用
            return 60

    except Exception:
        return 20  # 取得に失敗した場合、デフォルト値の20msを返す


class AudioConfig:
    """オーディオ設定クラス."""
    # 固定設定
    INPUT_SAMPLE_RATE = 16000  # 入力サンプリングレート16kHz
    # 出力サンプリングレート：公式サーバーは24kHz、その他は16kHzを使用
    _ota_url = config.get_config("SYSTEM_OPTIONS.NETWORK.OTA_VERSION_URL")
    OUTPUT_SAMPLE_RATE = 24000 if is_official_server(_ota_url) else 16000
    CHANNELS = 1

    # フレーム長を動的に取得
    FRAME_DURATION = get_frame_duration()

    # 異なるサンプリングレートに基づいてフレームサイズを計算
    INPUT_FRAME_SIZE = int(INPUT_SAMPLE_RATE * (FRAME_DURATION / 1000))
    # LinuxシステムはPCM出力を減らすために固定フレームサイズ、その他のシステムは動的計算
    OUTPUT_FRAME_SIZE = int(OUTPUT_SAMPLE_RATE * (FRAME_DURATION / 1000))
