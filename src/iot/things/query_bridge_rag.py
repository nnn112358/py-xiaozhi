from src.iot.thing import Parameter, Thing, ValueType


def get_rag_result(qurey):
    """ライス都市管理システムの紹介.

    返し値:
        str: 紹介情報
    """
    print("クエリ:", qurey)
    introduction = "ここがあなたがクエリした関数で、コンテンツを返す場所です"
    return introduction


class QueryBridgeRAG(Thing):
    def __init__(self):
        super().__init__("クエリブリッジ", "ネットワーククエリ情報を取得し結果を保存")
        # クエリしたコンテンツを保存
        self.query_result = ""
        self.last_query = ""

        # プロパティを登録
        self.add_property("query_result", "現在のクエリ結果", lambda: self.query_result)
        self.add_property("last_query", "前回のクエリ内容", lambda: self.last_query)

        self._register_methods()

    def _register_methods(self):
        # 情報をクエリ
        self.add_method(
            "Query",
            "情報をクエリ",
            [Parameter("query", "クエリ内容", ValueType.STRING, True)],
            lambda params: self._query_info_and_store(params["query"].get_value()),
        )

        # クエリ結果を取得
        self.add_method(
            "GetQueryResult",
            "クエリ結果を取得",
            [],
            lambda params: {"result": self.query_result, "query": self.last_query},
        )

    def _query_info(self, query):
        """情報をクエリ.

        引数:
            query (str): クエリ内容

        返し値:
            str: クエリ結果
        """
        try:
            # ロジック層のRAGナレッジベースクエリを呼び出し
            result = get_rag_result(query)
            # ragクエリ

            # difyなどの他のネットワーク方式

            return result
        except Exception as e:
            print(f"情報クエリ失敗: {e}")
            return f"申し訳ありません、'{query}'のクエリ中にエラーが発生しました。"

    def _query_info_and_store(self, query):
        """情報をクエリして保存.

        引数:
            query (str): クエリ内容

        返し値:
            dict: 操作結果
        """
        try:
            # クエリ内容を記録
            self.last_query = query

            # 情報をクエリして保存
            self.query_result = self._query_info(query)

            return {"success": True, "message": "クエリ成功", "result": self.query_result}
        except Exception as e:
            return {"success": False, "message": f"クエリ失敗: {e}"}
