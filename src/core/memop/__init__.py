"""内存优化工具 — 对象池与容器管理。

参考 Cocos4 cocos/core/memop/ 模块：
- Pool<T>: 通用对象池，alloc/free 手动管理
- RecyclePool<T>: 每帧/每轮全量复用，reset() 清零
- ContainerManager: 定期缩减所有注册池的内存占用
"""
