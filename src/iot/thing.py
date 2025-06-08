from typing import Any, Callable, Dict, List


class ValueType:
    """IoTデバイスのプロパティの値の型定義クラス.
    
    IoTデバイスのプロパティ値として使用可能な型を定数として定義します。
    これらの型は、デバイスの状態やメソッドパラメータの型チェックに使用されます。
    """
    BOOLEAN = "boolean"
    NUMBER = "number"
    STRING = "string"
    FLOAT = "float"


class Property:
    """IoTデバイスのプロパティを表現するクラス.
    
    IoTデバイスの状態を表すプロパティを定義します。
    各プロパティには名前、説明、値を取得するゲッター関数が含まれます。
    プロパティの型は、ゲッター関数の戻り値から自動的に推測されます。
    """
    
    def __init__(self, name: str, description: str, getter: Callable):
        """プロパティを初期化.
        
        Args:
            name: プロパティ名
            description: プロパティの説明
            getter: プロパティ値を取得するコールバック関数
        """
        self.name = name
        self.description = description
        self.getter = getter

        # ゲッター関数の戻り値の型を基にプロパティの型を自動判定
        test_value = getter()
        if isinstance(test_value, bool):
            self.type = ValueType.BOOLEAN
        elif isinstance(test_value, (int, float)):
            self.type = ValueType.NUMBER
        elif isinstance(test_value, str):
            self.type = ValueType.STRING
        else:
            raise TypeError(f"サポートされていないプロパティ型: {type(test_value)}")

    def get_descriptor_json(self) -> Dict:
        """プロパティの記述子をJSON形式で取得.
        
        Returns:
            Dict: プロパティの説明と型を含む辞書
        """
        return {"description": self.description, "type": self.type}

    def get_state_value(self):
        """プロパティの現在の値を取得.
        
        Returns:
            Any: プロパティの現在の値
        """
        return self.getter()


class Parameter:
    """IoTデバイスメソッドのパラメータを表現するクラス.
    
    IoTデバイスのメソッド呼び出しに使用されるパラメータを定義します。
    各パラメータには名前、説明、型、必須フラグが含まれます。
    """
    
    def __init__(self, name: str, description: str, type_: str, required: bool = True):
        """パラメータを初期化.
        
        Args:
            name: パラメータ名
            description: パラメータの説明
            type_: パラメータの型 (ValueType定数を使用)
            required: パラメータが必須かどうか
        """
        self.name = name
        self.description = description
        self.type = type_
        self.required = required
        self.value = None

    def get_descriptor_json(self) -> Dict:
        """パラメータの記述子をJSON形式で取得.
        
        Returns:
            Dict: パラメータの説明と型を含む辞書
        """
        return {"description": self.description, "type": self.type}

    def set_value(self, value: Any):
        """パラメータの値を設定.
        
        Args:
            value: 設定する値
        """
        self.value = value

    def get_value(self) -> Any:
        """パラメータの値を取得.
        
        Returns:
            Any: パラメータの現在の値
        """
        return self.value


class Method:
    """IoTデバイスのメソッドを表現するクラス.
    
    IoTデバイスが実行可能なメソッドを定義します。
    各メソッドには名前、説明、パラメータリスト、実行コールバック関数が含まれます。
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: List[Parameter],
        callback: Callable,
    ):
        """メソッドを初期化.
        
        Args:
            name: メソッド名
            description: メソッドの説明
            parameters: メソッドが受け取るパラメータのリスト
            callback: メソッド実行時に呼び出されるコールバック関数
        """
        self.name = name
        self.description = description
        self.parameters = {param.name: param for param in parameters}
        self.callback = callback

    def get_descriptor_json(self) -> Dict:
        """メソッドの記述子をJSON形式で取得.
        
        Returns:
            Dict: メソッドの説明とパラメータ情報を含む辞書
        """
        return {
            "description": self.description,
            "parameters": {
                name: param.get_descriptor_json()
                for name, param in self.parameters.items()
            },
        }

    def invoke(self, params: Dict[str, Any]) -> Any:
        """メソッドを実行.
        
        Args:
            params: メソッドに渡すパラメータの辞書
            
        Returns:
            Any: メソッド実行結果
            
        Raises:
            ValueError: 必須パラメータが不足している場合
        """
        # パラメータ値を設定
        for name, value in params.items():
            if name in self.parameters:
                self.parameters[name].set_value(value)

        # 必須パラメータの存在確認
        for name, param in self.parameters.items():
            if param.required and param.get_value() is None:
                raise ValueError(f"必須パラメータが不足: {name}")

        # コールバック関数を実行
        return self.callback(self.parameters)


class Thing:
    """IoTデバイスの基底クラス.
    
    IoTデバイスの基本的な機能を提供する抽象クラスです。
    プロパティ（状態）とメソッド（操作）を持ち、外部からの制御や状態確認が可能です。
    すべてのIoTデバイスはこのクラスを継承して実装されます。
    """
    
    def __init__(self, name: str, description: str):
        """IoTデバイスを初期化.
        
        Args:
            name: デバイス名
            description: デバイスの説明
        """
        self.name = name
        self.description = description
        self.properties = {}
        self.methods = {}

    def add_property(self, name: str, description: str, getter: Callable) -> None:
        """デバイスにプロパティを追加.
        
        Args:
            name: プロパティ名
            description: プロパティの説明
            getter: プロパティ値を取得するコールバック関数
        """
        self.properties[name] = Property(name, description, getter)

    def add_method(
        self,
        name: str,
        description: str,
        parameters: List[Parameter],
        callback: Callable,
    ) -> None:
        """デバイスにメソッドを追加.
        
        Args:
            name: メソッド名
            description: メソッドの説明
            parameters: メソッドパラメータのリスト
            callback: メソッド実行時のコールバック関数
        """
        self.methods[name] = Method(name, description, parameters, callback)

    def get_descriptor_json(self) -> Dict:
        """デバイスの完全な記述子をJSON形式で取得.
        
        Returns:
            Dict: デバイス名、説明、プロパティ、メソッドの情報を含む辞書
        """
        return {
            "name": self.name,
            "description": self.description,
            "properties": {
                name: prop.get_descriptor_json()
                for name, prop in self.properties.items()
            },
            "methods": {
                name: method.get_descriptor_json()
                for name, method in self.methods.items()
            },
        }

    def get_state_json(self) -> Dict:
        """デバイスの現在の状態をJSON形式で取得.
        
        Returns:
            Dict: デバイス名と全プロパティの現在値を含む辞書
        """
        return {
            "name": self.name,
            "state": {
                name: prop.get_state_value() for name, prop in self.properties.items()
            },
        }

    def invoke(self, command: Dict) -> Any:
        """デバイスのメソッドを実行.
        
        Args:
            command: 実行するメソッド名とパラメータを含むコマンド辞書
            
        Returns:
            Any: メソッド実行結果
            
        Raises:
            ValueError: 指定されたメソッドが存在しない場合
        """
        method_name = command.get("method")
        if method_name not in self.methods:
            raise ValueError(f"メソッドが存在しません: {method_name}")

        parameters = command.get("parameters", {})
        return self.methods[method_name].invoke(parameters)
