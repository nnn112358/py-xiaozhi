import threading

from openai import OpenAI


class ImageAnalyzer:
    _instance = None
    _lock = threading.Lock()
    client = None

    def __init__(self):
        self.model = None

    def __new__(cls):
        """シングルトンパターンを保証する."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init(
        self,
        api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        models="qwen-omni-turbo",
    ):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        self.models = models

    @classmethod
    def get_instance(cls):
        """カメラマネージャーインスタンスを取得（スレッドセーフ）"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def analyze_image(
        self, base64_image, prompt="画像に描かれているのはどのような光景ですか、ユーザーが目の不自由な方である可能性があるため詳細に説明してください"
    ) -> str:
        """画像を分析して結果を返す."""
        completion = self.client.chat.completions.create(
            model=self.models,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant.",  # リストではなく文字列を直接使用
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            modalities=["text"],
            stream=True,
            stream_options={"include_usage": True},
        )
        mesag = ""
        for chunk in completion:
            if chunk.choices:
                mesag += chunk.choices[0].delta.content
            else:
                pass
        return mesag
