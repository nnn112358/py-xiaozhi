"""
IoTデバイス管理モジュール

IoTデバイス（Thing）の登録、状態管理、メソッド実行を一元管理するクラスを提供します。
シングルトンパターンを使用してアプリケーション全体で単一のインスタンスを共有します。
"""
import json
import logging
from typing import Any, Dict, Optional, Tuple

from src.iot.thing import Thing


class ThingManager:
    """IoTデバイス管理クラス.
    
    システム内のすべてのIoTデバイスを管理し、デバイスの状態取得、
    メソッド実行、状態変化の検出などの機能を提供します。
    シングルトンパターンで実装され、アプリケーション全体で単一のインスタンスを使用します。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        """ThingManagerのシングルトンインスタンスを取得.
        
        Returns:
            ThingManager: ThingManagerのインスタンス
        """
        if cls._instance is None:
            cls._instance = ThingManager()
        return cls._instance

    def __init__(self):
        """ThingManagerを初期化."""
        self.things = []
        self.last_states = {}  # 状態キャッシュ辞書、前回の状態を保存

    def add_thing(self, thing: Thing) -> None:
        """IoTデバイスを管理対象に追加.
        
        Args:
            thing: 追加するIoTデバイス
        """
        self.things.append(thing)

    def get_descriptors_json(self) -> str:
        """すべてのデバイスの記述子をJSON形式で取得.
        
        Returns:
            str: すべてのデバイスの記述子を含むJSON文字列
        """
        descriptors = [thing.get_descriptor_json() for thing in self.things]
        return json.dumps(descriptors)

    def get_states_json(self, delta=False) -> Tuple[bool, str]:
        """すべてのデバイスの状態JSONを取得.

        Args:
            delta: 変化した部分のみを返すかどうか。Trueの場合は変化した部分のみ返す

        Returns:
            Tuple[bool, str]: 状態変化があったかどうかのブール値とJSON文字列のタプル
        """
        if not delta:
            self.last_states.clear()

        changed = False
        states = []

        for thing in self.things:
            state_json = thing.get_state_json()

            if delta:
                # 状態が変化したかチェック
                is_same = (
                    thing.name in self.last_states
                    and self.last_states[thing.name] == state_json
                )
                if is_same:
                    continue
                changed = True
                self.last_states[thing.name] = state_json

            # state_jsonが既に辞書オブジェクトかチェック
            if isinstance(state_json, dict):
                states.append(state_json)
            else:
                states.append(json.loads(state_json))  # JSON文字列を辞書に変換

        return changed, json.dumps(states)

    def get_states_json_str(self) -> str:
        """旧コードとの互換性のため、元のメソッド名と戻り値の型を保持."""
        _, json_str = self.get_states_json(delta=False)
        return json_str

    def invoke(self, command: Dict) -> Optional[Any]:
        """デバイスメソッドを呼び出し.

        Args:
            command: nameとmethodなどの情報を含むコマンド辞書

        Returns:
            Optional[Any]: デバイスが見つかって呼び出しに成功した場合は結果を返す。そうでなければ例外をスロー
            
        Raises:
            ValueError: 指定されたデバイスが存在しない場合
        """
        thing_name = command.get("name")
        for thing in self.things:
            if thing.name == thing_name:
                return thing.invoke(command)

        # エラーログを記録
        logging.error(f"デバイスが存在しません: {thing_name}")
        raise ValueError(f"デバイスが存在しません: {thing_name}")
