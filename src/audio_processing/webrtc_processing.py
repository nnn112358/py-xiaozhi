"""WebRTCオーディオ処理モジュール。

このモジュールはWebRTC APMライブラリのエコーキャンセル(AEC)、ノイズ抑制(NS)等の
オーディオ処理機能を提供します。
webrtc_aec_demo.pyから抽出し、リアルタイム処理モジュールとして最適化されました。

主要機能:
1. エコーキャンセル(AEC) - スピーカー出力がマイク入力に与える干渉を除去
2. ノイズ抑制(NS) - 環境ノイズを減少
3. ゲイン制御(AGC) - オーディオゲインを自動調整
4. ハイパスフィルタ - 低周波ノイズを除去

使用例:
    processor = WebRTCProcessor()
    processed_audio = processor.process_capture_stream(input_audio, reference_audio)
"""

import ctypes
import os
import threading
from ctypes import POINTER, Structure, byref, c_bool, c_float, c_int, c_short, c_void_p

import numpy as np

from src.utils.logging_config import get_logger
from src.utils.path_resolver import find_resource

logger = get_logger(__name__)


# DLLファイルの絶対パスを取得
def get_webrtc_dll_path():
    """WebRTC APMライブラリのパスを取得します。
    
    Returns:
        str: WebRTC APMライブラリのファイルパス
    """
    dll_path = find_resource("libs/webrtc_apm/win/x86_64/libwebrtc_apm.dll")
    if dll_path:
        return str(dll_path)

    # フォールバック手段: 元のロジックを使用
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    fallback_path = os.path.join(
        project_root, "libs", "webrtc_apm", "win", "x86_64", "libwebrtc_apm.dll"
    )
    logger.warning(f"WebRTCライブラリが見つからないため、フォールバックパスを使用します: {fallback_path}")
    return fallback_path


# WebRTC APMライブラリをロード
try:
    dll_path = get_webrtc_dll_path()
    apm_lib = ctypes.CDLL(dll_path)
    logger.info(f"WebRTC APMライブラリのロードに成功しました: {dll_path}")
except Exception as e:
    logger.error(f"WebRTC APMライブラリのロードに失敗しました: {e}")
    apm_lib = None


# 列挙型を定義
class DownmixMethod(ctypes.c_int):
    AverageChannels = 0
    UseFirstChannel = 1


class NoiseSuppressionLevel(ctypes.c_int):
    Low = 0
    Moderate = 1
    High = 2
    VeryHigh = 3


class GainControllerMode(ctypes.c_int):
    AdaptiveAnalog = 0
    AdaptiveDigital = 1
    FixedDigital = 2


class ClippingPredictorMode(ctypes.c_int):
    ClippingEventPrediction = 0
    AdaptiveStepClippingPeakPrediction = 1
    FixedStepClippingPeakPrediction = 2


# 構造体を定義
class Pipeline(Structure):
    _fields_ = [
        ("MaximumInternalProcessingRate", c_int),
        ("MultiChannelRender", c_bool),
        ("MultiChannelCapture", c_bool),
        ("CaptureDownmixMethod", c_int),
    ]


class PreAmplifier(Structure):
    _fields_ = [("Enabled", c_bool), ("FixedGainFactor", c_float)]


class AnalogMicGainEmulation(Structure):
    _fields_ = [("Enabled", c_bool), ("InitialLevel", c_int)]


class CaptureLevelAdjustment(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("PreGainFactor", c_float),
        ("PostGainFactor", c_float),
        ("MicGainEmulation", AnalogMicGainEmulation),
    ]


class HighPassFilter(Structure):
    _fields_ = [("Enabled", c_bool), ("ApplyInFullBand", c_bool)]


class EchoCanceller(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("MobileMode", c_bool),
        ("ExportLinearAecOutput", c_bool),
        ("EnforceHighPassFiltering", c_bool),
    ]


class NoiseSuppression(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("NoiseLevel", c_int),
        ("AnalyzeLinearAecOutputWhenAvailable", c_bool),
    ]


class TransientSuppression(Structure):
    _fields_ = [("Enabled", c_bool)]


class ClippingPredictor(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("PredictorMode", c_int),
        ("WindowLength", c_int),
        ("ReferenceWindowLength", c_int),
        ("ReferenceWindowDelay", c_int),
        ("ClippingThreshold", c_float),
        ("CrestFactorMargin", c_float),
        ("UsePredictedStep", c_bool),
    ]


class AnalogGainController(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("StartupMinVolume", c_int),
        ("ClippedLevelMin", c_int),
        ("EnableDigitalAdaptive", c_bool),
        ("ClippedLevelStep", c_int),
        ("ClippedRatioThreshold", c_float),
        ("ClippedWaitFrames", c_int),
        ("Predictor", ClippingPredictor),
    ]


class GainController1(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("ControllerMode", c_int),
        ("TargetLevelDbfs", c_int),
        ("CompressionGainDb", c_int),
        ("EnableLimiter", c_bool),
        ("AnalogController", AnalogGainController),
    ]


class InputVolumeController(Structure):
    _fields_ = [("Enabled", c_bool)]


class AdaptiveDigital(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("HeadroomDb", c_float),
        ("MaxGainDb", c_float),
        ("InitialGainDb", c_float),
        ("MaxGainChangeDbPerSecond", c_float),
        ("MaxOutputNoiseLevelDbfs", c_float),
    ]


class FixedDigital(Structure):
    _fields_ = [("GainDb", c_float)]


class GainController2(Structure):
    _fields_ = [
        ("Enabled", c_bool),
        ("VolumeController", InputVolumeController),
        ("AdaptiveController", AdaptiveDigital),
        ("FixedController", FixedDigital),
    ]


class Config(Structure):
    _fields_ = [
        ("PipelineConfig", Pipeline),
        ("PreAmp", PreAmplifier),
        ("LevelAdjustment", CaptureLevelAdjustment),
        ("HighPass", HighPassFilter),
        ("Echo", EchoCanceller),
        ("NoiseSuppress", NoiseSuppression),
        ("TransientSuppress", TransientSuppression),
        ("GainControl1", GainController1),
        ("GainControl2", GainController2),
    ]


# DLL関数プロトタイプを定義
if apm_lib:
    apm_lib.WebRTC_APM_Create.restype = c_void_p
    apm_lib.WebRTC_APM_Create.argtypes = []

    apm_lib.WebRTC_APM_Destroy.restype = None
    apm_lib.WebRTC_APM_Destroy.argtypes = [c_void_p]

    apm_lib.WebRTC_APM_CreateStreamConfig.restype = c_void_p
    apm_lib.WebRTC_APM_CreateStreamConfig.argtypes = [c_int, c_int]

    apm_lib.WebRTC_APM_DestroyStreamConfig.restype = None
    apm_lib.WebRTC_APM_DestroyStreamConfig.argtypes = [c_void_p]

    apm_lib.WebRTC_APM_ApplyConfig.restype = c_int
    apm_lib.WebRTC_APM_ApplyConfig.argtypes = [c_void_p, POINTER(Config)]

    apm_lib.WebRTC_APM_ProcessReverseStream.restype = c_int
    apm_lib.WebRTC_APM_ProcessReverseStream.argtypes = [
        c_void_p,
        POINTER(c_short),
        c_void_p,
        c_void_p,
        POINTER(c_short),
    ]

    apm_lib.WebRTC_APM_ProcessStream.restype = c_int
    apm_lib.WebRTC_APM_ProcessStream.argtypes = [
        c_void_p,
        POINTER(c_short),
        c_void_p,
        c_void_p,
        POINTER(c_short),
    ]

    apm_lib.WebRTC_APM_SetStreamDelayMs.restype = None
    apm_lib.WebRTC_APM_SetStreamDelayMs.argtypes = [c_void_p, c_int]


def create_optimized_apm_config():
    """最適化されたWebRTC APM設定を作成します。リアルタイムオーディオ処理用に最適化。
    
    Returns:
        Config: 最適化された設定構造体
    """
    config = Config()

    # パイプライン設定 - 16kHzで最適化
    config.PipelineConfig.MaximumInternalProcessingRate = 16000
    config.PipelineConfig.MultiChannelRender = False
    config.PipelineConfig.MultiChannelCapture = False
    config.PipelineConfig.CaptureDownmixMethod = DownmixMethod.AverageChannels

    # プリアンプ - 歪みを減らすために無効
    config.PreAmp.Enabled = False
    config.PreAmp.FixedGainFactor = 1.0

    # レベル調整 - シンプル設定
    config.LevelAdjustment.Enabled = False
    config.LevelAdjustment.PreGainFactor = 1.0
    config.LevelAdjustment.PostGainFactor = 1.0
    config.LevelAdjustment.MicGainEmulation.Enabled = False
    config.LevelAdjustment.MicGainEmulation.InitialLevel = 100

    # ハイパスフィルタ - 低周波ノイズ除去のため有効
    config.HighPass.Enabled = True
    config.HighPass.ApplyInFullBand = True

    # エコーキャンセル - コア機能
    config.Echo.Enabled = True
    config.Echo.MobileMode = False
    config.Echo.ExportLinearAecOutput = False
    config.Echo.EnforceHighPassFiltering = True

    # ノイズ抑制 - 中程度の強度
    config.NoiseSuppress.Enabled = True
    config.NoiseSuppress.NoiseLevel = NoiseSuppressionLevel.Moderate
    config.NoiseSuppress.AnalyzeLinearAecOutputWhenAvailable = True

    # 過渡抑制 - 音声を保護するため無効
    config.TransientSuppress.Enabled = False

    # ゲイン制御1 - 適応デジタルゲインを有効
    config.GainControl1.Enabled = True
    config.GainControl1.ControllerMode = GainControllerMode.AdaptiveDigital
    config.GainControl1.TargetLevelDbfs = 3
    config.GainControl1.CompressionGainDb = 9
    config.GainControl1.EnableLimiter = True

    # アナログゲインコントローラ - 無効
    config.GainControl1.AnalogController.Enabled = False
    config.GainControl1.AnalogController.StartupMinVolume = 0
    config.GainControl1.AnalogController.ClippedLevelMin = 70
    config.GainControl1.AnalogController.EnableDigitalAdaptive = False
    config.GainControl1.AnalogController.ClippedLevelStep = 15
    config.GainControl1.AnalogController.ClippedRatioThreshold = 0.1
    config.GainControl1.AnalogController.ClippedWaitFrames = 300

    # クリッピング予測器 - 無効
    predictor = config.GainControl1.AnalogController.Predictor
    predictor.Enabled = False
    predictor.PredictorMode = ClippingPredictorMode.ClippingEventPrediction
    predictor.WindowLength = 5
    predictor.ReferenceWindowLength = 5
    predictor.ReferenceWindowDelay = 5
    predictor.ClippingThreshold = -1.0
    predictor.CrestFactorMargin = 3.0
    predictor.UsePredictedStep = True

    # ゲイン制御2 - 競合を避けるため無効
    config.GainControl2.Enabled = False
    config.GainControl2.VolumeController.Enabled = False
    config.GainControl2.AdaptiveController.Enabled = False
    config.GainControl2.AdaptiveController.HeadroomDb = 5.0
    config.GainControl2.AdaptiveController.MaxGainDb = 30.0
    config.GainControl2.AdaptiveController.InitialGainDb = 15.0
    config.GainControl2.AdaptiveController.MaxGainChangeDbPerSecond = 6.0
    config.GainControl2.AdaptiveController.MaxOutputNoiseLevelDbfs = -50.0
    config.GainControl2.FixedController.GainDb = 0.0

    return config


class WebRTCProcessor:
    """WebRTCベースのオーディオプロセッサ。
    
    リアルタイムエコーキャンセルとオーディオ拡張機能を提供します。
    WebRTC APMライブラリを使用して、マイク入力からエコーを除去し、
    ノイズを抑制し、ゲインを最適化します。
    """

    def __init__(self, sample_rate=16000, channels=1, frame_size=160):
        """WebRTCプロセッサを初期化します。

        Args:
            sample_rate (int): サンプリングレート、デフォルト16000Hz
            channels (int): チャンネル数、デフォルト1（モノラル）
            frame_size (int): フレームサイズ、デフォルト160サンプル（10ms @ 16kHz）
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = frame_size

        # WebRTC APMインスタンス
        self.apm = None
        self.stream_config = None
        self.config = None

        # スレッドセーフティ用ロック
        self._lock = threading.Lock()

        # 初期化状態
        self._initialized = False

        # 参照信号バッファ（エコーキャンセル用）
        self._reference_buffer = []
        self._reference_lock = threading.Lock()

        # WebRTC APMを初期化
        self._initialize()

    def _initialize(self):
        """WebRTC APMを初期化します。
        
        Returns:
            bool: 初期化が成功した場合True
        """
        if not apm_lib:
            logger.error("WebRTC APMライブラリがロードされていないため、プロセッサを初期化できません")
            return False

        try:
            with self._lock:
                # APMインスタンスを作成
                self.apm = apm_lib.WebRTC_APM_Create()
                if not self.apm:
                    logger.error("WebRTC APMインスタンスの作成に失敗しました")
                    return False

                # ストリーム設定を作成
                self.stream_config = apm_lib.WebRTC_APM_CreateStreamConfig(
                    self.sample_rate, self.channels
                )
                if not self.stream_config:
                    logger.error("WebRTCストリーム設定の作成に失敗しました")
                    return False

                # 設定を適用
                self.config = create_optimized_apm_config()
                result = apm_lib.WebRTC_APM_ApplyConfig(self.apm, byref(self.config))
                if result != 0:
                    logger.warning(f"WebRTC設定の適用に失敗しました、エラーコード: {result}")

                # 遅延を設定
                apm_lib.WebRTC_APM_SetStreamDelayMs(self.apm, 50)

                self._initialized = True
                logger.info("WebRTCプロセッサの初期化が成功しました")
                return True

        except Exception as e:
            logger.error(f"WebRTCプロセッサの初期化に失敗しました: {e}")
            return False

    def process_capture_stream(self, input_data, reference_data=None):
        """キャプチャストリーム（マイク入力）を処理します。

        WebRTC APMを使用して、マイク入力からエコー、ノイズ、ゲインを処理します。
        参照データが提供された場合、エコーキャンセルの精度が向上します。

        Args:
            input_data (bytes): 入力オーディオデータ
            reference_data (bytes, optional): 参照オーディオデータ

        Returns:
            bytes: 処理済みオーディオデータ、失敗時は元データを返す
        """
        if not self._initialized or not self.apm:
            logger.warning("WebRTCプロセッサが未初期化のため、元データを返します")
            return input_data

        try:
            with self._lock:
                # 入力データをnumpy配列に変換
                input_array = np.frombuffer(input_data, dtype=np.int16)

                # データ長を確認
                if len(input_array) != self.frame_size:
                    logger.warning(
                        f"入力データ長が不一致です。期待値{self.frame_size}、実際{len(input_array)}"
                    )
                    return input_data

                # 入力ポインタを作成
                input_ptr = input_array.ctypes.data_as(POINTER(c_short))

                # 出力バッファを作成
                output_array = np.zeros(self.frame_size, dtype=np.int16)
                output_ptr = output_array.ctypes.data_as(POINTER(c_short))

                # 参照信号を処理（提供された場合）
                if reference_data:
                    self._process_reference_stream(reference_data)

                # キャプチャストリームを処理
                result = apm_lib.WebRTC_APM_ProcessStream(
                    self.apm,
                    input_ptr,
                    self.stream_config,
                    self.stream_config,
                    output_ptr,
                )

                if result != 0:
                    logger.debug(f"WebRTC処理警告、エラーコード: {result}")
                    # 警告があっても処理済みデータを返す

                return output_array.tobytes()

        except Exception as e:
            logger.error(f"キャプチャストリームの処理に失敗しました: {e}")
            return input_data

    def _process_reference_stream(self, reference_data):
        """参照ストリーム（スピーカー出力）を処理します。

        エコーキャンセルの精度を向上させるために、スピーカーからの
        出力音声を参照信号として処理します。

        Args:
            reference_data (bytes): 参照オーディオデータ
        """
        try:
            # 参照データをnumpy配列に変換
            ref_array = np.frombuffer(reference_data, dtype=np.int16)

            # データ長を確認
            if len(ref_array) != self.frame_size:
                # 長さが不一致の場合、正しい長さに調整
                if len(ref_array) > self.frame_size:
                    ref_array = ref_array[: self.frame_size]
                else:
                    # ゼロパディング
                    padded = np.zeros(self.frame_size, dtype=np.int16)
                    padded[: len(ref_array)] = ref_array
                    ref_array = padded

            # 参照信号ポインタを作成
            ref_ptr = ref_array.ctypes.data_as(POINTER(c_short))

            # 参照出力バッファを作成（使用しないが必要）
            ref_output_array = np.zeros(self.frame_size, dtype=np.int16)
            ref_output_ptr = ref_output_array.ctypes.data_as(POINTER(c_short))

            # 参照ストリームを処理
            result = apm_lib.WebRTC_APM_ProcessReverseStream(
                self.apm,
                ref_ptr,
                self.stream_config,
                self.stream_config,
                ref_output_ptr,
            )

            if result != 0:
                logger.debug(f"参照ストリーム処理警告、エラーコード: {result}")

        except Exception as e:
            logger.error(f"参照ストリームの処理に失敗しました: {e}")

    def add_reference_data(self, reference_data):
        """参照データをバッファに追加します。

        Args:
            reference_data (bytes): 参照オーディオデータ
        """
        with self._reference_lock:
            self._reference_buffer.append(reference_data)
            # バッファサイズを適正に保つ（約1秒のデータ）
            max_buffer_size = self.sample_rate // self.frame_size
            if len(self._reference_buffer) > max_buffer_size:
                self._reference_buffer = self._reference_buffer[-max_buffer_size:]

    def get_reference_data(self):
        """最古の参照データを取得し、削除します。

        Returns:
            bytes or None: 参照オーディオデータ、バッファが空の場合None
        """
        with self._reference_lock:
            if self._reference_buffer:
                return self._reference_buffer.pop(0)
            return None

    def close(self):
        """WebRTCプロセッサを閉じ、リソースを解放します。"""
        if not self._initialized:
            return

        try:
            with self._lock:
                # 参照バッファをクリア
                with self._reference_lock:
                    self._reference_buffer.clear()

                # ストリーム設定を破棄
                if self.stream_config:
                    apm_lib.WebRTC_APM_DestroyStreamConfig(self.stream_config)
                    self.stream_config = None

                # APMインスタンスを破棄
                if self.apm:
                    apm_lib.WebRTC_APM_Destroy(self.apm)
                    self.apm = None

                self._initialized = False
                logger.info("WebRTCプロセッサを閉じました")

        except Exception as e:
            logger.error(f"WebRTCプロセッサの終了に失敗しました: {e}")

    def __del__(self):
        """デストラクタ、リソースの解放を保証します。"""
        self.close()
