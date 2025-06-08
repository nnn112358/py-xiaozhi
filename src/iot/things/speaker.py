from src.application import Application
from src.iot.thing import Parameter, Thing, ValueType


class Speaker(Thing):
    def __init__(self):
        super().__init__("Speaker", "現在のAIロボットのスピーカー")

        # 現在のディスプレイインスタンスの音量を初期値として取得
        try:
            app = Application.get_instance()
            self.volume = app.display.current_volume
        except Exception:
            # 取得に失敗した場合、デフォルト値を使用
            self.volume = 100  # デフォルト音量

        # プロパティを定義
        self.add_property("volume", "現在の音量値", lambda: self.volume)

        # メソッドを定義
        self.add_method(
            "SetVolume",
            "音量を設定",
            [Parameter("volume", "0から100の間の整数", ValueType.NUMBER, True)],
            lambda params: self._set_volume(params["volume"].get_value()),
        )

    def _set_volume(self, volume):
        if 0 <= volume <= 100:
            self.volume = volume
            try:
                app = Application.get_instance()
                app.display.update_volume(volume)
                return {"success": True, "message": f"音量を{volume}に設定しました"}
            except Exception as e:
                print(f"音量設定失敗: {e}")
                return {"success": False, "message": f"音量設定失敗: {e}"}
        else:
            raise ValueError("音量は0-100の間でなければなりません")
