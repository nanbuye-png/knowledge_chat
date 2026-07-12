"""基础提示词 Provider — 提示词管理的抽象接口。

定义了所有提示词提供者必须实现的契约。
提示词提供者负责构建系统提示词、RAG 提示词和通用聊天提示词。
"""

from abc import ABC, abstractmethod


class BasePromptProvider(ABC):
    """所有提示词提供者的抽象基类。

    提示词提供者封装了发送给 LLM 的提示词构建逻辑。
    不同的提供者可以提供不同的系统提示词（如严格的知识库助手 vs 创意写作机器人），
    而系统的其他部分保持不变。

    每个具体的提示词提供者 **必须** 实现：

    - :attr:`system_prompt` — 发送给 LLM 的系统级指令
    - :meth:`build_rag_prompt` — 构建检索增强提示词
    - :meth:`build_chat_prompt` — 构建通用聊天提示词
    """

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """返回发送给 LLM 的系统级提示词。

        此提示词通常作为以 ``"system"`` 角色发送的第一条消息，
        定义了助手的角色、行为约束和回复风格。

        返回值：
            包含系统提示词的字符串。
        """
        ...

    @abstractmethod
    def build_rag_prompt(self, context: str, question: str) -> str:
        """构建 RAG（检索增强生成）提示词。

        将检索到的文档上下文与用户问题组合为一条提示词，
        指导 LLM 根据提供的内容进行回答。

        参数：
            context: 检索到的文档块（以单个字符串表示）。
            question: 用户的原始问题。

        返回值：
            可直接发送给 LLM 的完整提示词字符串。
        """
        ...

    @abstractmethod
    def build_chat_prompt(self, message: str) -> str:
        """构建通用聊天提示词。

        将用户消息包装为无文档上下文的自由对话格式。
        根据不同提供者可能包含额外指令（如回复语言、语气等）。

        参数：
            message: 用户的聊天消息。

        返回值：
            可直接发送给 LLM 的提示词字符串。
        """
        ...