"""向后兼容垫片：``AgensProvider`` 已更名为 ``AgnesProvider``。

历史拼写（``agens``）只是因为字母顺序写反，厂商品牌名是 **Agnes**，
规范实现现在位于 :mod:`app.services.llm.agnes_provider`。

保留本模块是为了不打断历史引用，例如::

    from app.services.llm.agens_provider import AgensProvider   # 旧写法，仍可用

新代码请统一从 :mod:`app.services.llm.agnes_provider` 导入
:class:`~app.services.llm.agnes_provider.AgnesProvider`。
"""
from .agnes_provider import AgnesProvider

# 旧类名（历史拼写）保留为同一对象的别名，`isinstance` / `issubclass` 判定不受影响
AgensProvider = AgnesProvider

__all__ = ["AgnesProvider", "AgensProvider"]
