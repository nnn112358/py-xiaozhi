"""
仮想ランプデバイス

IoTシステムでの照明制御をシミュレートする仮想ランプデバイスです。
オン/オフの基本的な制御機能を提供し、テストやデモンストレーションに使用できます。
"""
from src.iot.thing import Thing


class Lamp(Thing):
    """仮想ランプデバイスクラス.
    
    照明のオン/オフ制御を行う仮想IoTデバイスです。
    電源状態の取得、ランプのオン/オフ操作を提供します。
    実際のハードウェアを使用せずに照明制御機能をテストできます。
    
    Attributes:
        power (bool): ランプの電源状態（True=オン、False=オフ）
    """
    
    def __init__(self):
        """仮想ランプデバイスを初期化."""
        super().__init__("Lamp", "テスト用の仮想ランプ")
        self.power = False

        print("[仮想デバイス] ランプデバイスの初期化が完了しました")

        # プロパティを定義
        self.add_property("power", "ランプの電源状態", lambda: self.power)

        # メソッドを定義
        self.add_method("TurnOn", "ランプをオンにする", [], lambda params: self._turn_on())

        self.add_method("TurnOff", "ランプをオフにする", [], lambda params: self._turn_off())

    def _turn_on(self):
        """ランプをオンにする内部メソッド.
        
        Returns:
            dict: 操作結果を含む辞書
        """
        self.power = True
        print("[仮想デバイス] ランプがオンになりました")
        return {"status": "success", "message": "ランプがオンになりました"}

    def _turn_off(self):
        """ランプをオフにする内部メソッド.
        
        Returns:
            dict: 操作結果を含む辞書
        """
        self.power = False
        print("[仮想デバイス] ランプがオフになりました")
        return {"status": "success", "message": "ランプがオフになりました"}
