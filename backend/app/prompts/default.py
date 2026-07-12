"""默认提示词 Provider — 标准提示词实现。

提供适用于大多数知识库助手场景的合理默认提示词策略。
可以通过依赖注入替换此提供者，而无需修改任何服务代码。
"""

from .base import BasePromptProvider


class DefaultPromptProvider(BasePromptProvider):
    """知识库 AI 助手的默认提示词提供者。

    实现系统使用的标准提示词模板。
    可以继承或替换此提供者以自定义提示词行为，
    无需修改 :mod:`chat_service` 或 API 层。

    用法::

        provider = DefaultPromptProvider()
        print(provider.system_prompt)
        rag_prompt = provider.build_rag_prompt(ctx, q)
        chat_prompt = provider.build_chat_prompt(msg)
    """

    # ------------------------------------------------------------------
    # BasePromptProvider 接口
    # ------------------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """返回知识库助手的默认系统提示词。

        返回值：
            定义助手角色和行为的简洁系统提示词字符串。
        """
        return "你是一名专业的知识库 AI 助手。请根据提供的资料准确、简洁地回答用户问题。"

    def build_rag_prompt(self, context: str, question: str) -> str:
        """构建 RAG 提示词，将回答限制在参考资料范围内。

        参数：
            context: 检索到的文档块（以单个字符串表示）。
            question: 用户的原始问题。

        返回值：
            格式化后的提示词字符串，指导 LLM 仅基于提供的上下文进行回答。
        """
        return (
            f"请仅根据以下参考知识回答问题。\n"
            f"\n"
            f"【参考知识】\n"
            f"{context}\n"
            f"\n"
            f"【用户问题】\n"
            f"{question}\n"
            f"\n"
            f"请仅根据参考知识回答。如果参考知识中没有相关信息，请明确说明'当前资料库中暂无相关信息'。"
        )

    def build_chat_prompt(self, message: str) -> str:
        """构建简单的通用聊天提示词。

        参数：
            message: 用户的聊天消息。

        返回值：
            包装用户消息的纯文本提示词字符串。
        """
        return f"【用户】\n{message}"