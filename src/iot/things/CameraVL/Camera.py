import asyncio
import base64
import logging
import threading

import cv2

from src.application import Application
from src.constants.constants import DeviceState
from src.iot.thing import Thing
from src.iot.things.CameraVL import VL

logger = logging.getLogger("Camera")


class Camera(Thing):
    def __init__(self):
        super().__init__("Camera", "カメラ管理")
        self.app = None
        """カメラマネージャーを初期化."""
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        # 設定を読み込み
        self.cap = None
        self.is_running = False
        self.camera_thread = None
        self.result = ""
        from src.utils.config_manager import ConfigManager

        self.config = ConfigManager.get_instance()
        # カメラコントローラー
        VL.ImageAnalyzer.get_instance().init(
            self.config.get_config("CAMERA.VLapi_key"),
            self.config.get_config("CAMERA.Loacl_VL_url"),
            self.config.get_config("CAMERA.models"),
        )
        self.VL = VL.ImageAnalyzer.get_instance()

        self.add_property_and_method()  # デバイスメソッドと状態プロパティを定義

    def add_property_and_method(self):
        # プロパティを定義
        self.add_property("power", "カメラが開いているか", lambda: self.is_running)
        self.add_property("result", "認識した画面の内容", lambda: self.result)
        # メソッドを定義
        self.add_method(
            "start_camera", "カメラを開く", [], lambda params: self.start_camera()
        )

        self.add_method(
            "stop_camera", "カメラを閉じる", [], lambda params: self.stop_camera()
        )

        self.add_method(
            "capture_frame_to_base64",
            "画面を認識",
            [],
            lambda params: self.capture_frame_to_base64(),
        )

    def _camera_loop(self):
        """カメラスレッドのメインループ."""
        camera_index = self.config.get_config("CAMERA.camera_index")
        self.cap = cv2.VideoCapture(camera_index)

        if not self.cap.isOpened():
            logger.error("カメラを開けません")
            return

        # カメラパラメータを設定
        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH, self.config.get_config("CAMERA.frame_width")
        )
        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT, self.config.get_config("CAMERA.frame_height")
        )
        self.cap.set(cv2.CAP_PROP_FPS, self.config.get_config("CAMERA.fps"))

        self.is_running = True
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                logger.error("画面を読み取れません")
                break

            # 画面を表示
            cv2.imshow("Camera", frame)

            # 'q'キーを押して終了
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.is_running = False

        # カメラを解放してウィンドウを閉じる
        self.cap.release()
        cv2.destroyAllWindows()

    def start_camera(self):
        """カメラスレッドを開始."""
        if self.camera_thread is not None and self.camera_thread.is_alive():
            logger.warning("カメラスレッドは既に実行中です")
            return

        self.camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
        self.camera_thread.start()
        logger.info("カメラスレッドが開始されました")
        return {"status": "success", "message": "カメラスレッドが開かれました"}

    def capture_frame_to_base64(self):
        """現在の画面をキャプチャしてBase64エンコードに変換."""
        if not self.cap or not self.cap.isOpened():
            logger.error("カメラが開いていません")
            return None

        ret, frame = self.cap.read()
        if not ret:
            logger.error("画面を読み取れません")
            return None

        # フレームをJPEG形式に変換
        _, buffer = cv2.imencode(".jpg", frame)

        # JPEG画像をBase64エンコードに変換
        frame_base64 = base64.b64encode(buffer).decode("utf-8")
        self.result = str(self.VL.analyze_image(frame_base64))
        # アプリケーションインスタンスを取得
        self.app = Application.get_instance()
        logger.info("画面が認識されました")
        self.app.set_device_state(DeviceState.LISTENING)
        asyncio.create_task(self.app.protocol.send_wake_word_detected("認識結果を報告"))
        return {"status": "success", "message": "認識成功", "result": self.result}

    def stop_camera(self):
        """カメラスレッドを停止."""
        self.is_running = False
        if self.camera_thread is not None:
            self.camera_thread.join()  # スレッド終了を待機
            self.camera_thread = None
            logger.info("カメラスレッドが停止されました")
            return {"status": "success", "message": "カメラスレッドが停止されました"}
