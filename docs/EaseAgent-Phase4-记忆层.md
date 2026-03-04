# Phase 4: 记忆层 (Memory Layer)

## 概述

记忆层让 EaseAgent 拥有"记忆"能力——记住员工的显式偏好、从日常行为中学习隐式偏好、在决策时检索相关记忆注入 Prompt，实现个性化服务。

## 架构

```
memory/
├── __init__.py           # MemorySystem 聚合类
├── explicit_store.py     # 显式偏好 (SQLite)
├── implicit_store.py     # 隐式偏好 (ChromaDB 向量)
├── context_memory.py     # 情境记忆 (ChromaDB 向量)
├── rag_retriever.py      # RAG 统一检索
└── preference_learner.py # 偏好学习器
```

### 三层记忆模型

| 层级 | 存储 | 数据来源 | 示例 |
|------|------|----------|------|
| **显式偏好** | SQLite `preferences` 表 | 员工主动设置 | "张三偏好色温4000K" |
| **隐式偏好** | ChromaDB `implicit_preferences` | Agent 观察 / LLM 记录 | "张三三次将空调从25调到23" |
| **情境记忆** | ChromaDB `context_memories` | Agent 决策追踪 | "张三开会时偏好冷光、安静" |

### 数据流

```
事件触发 → Agent OTAR 循环
                │
    ┌───────────┼───────────────────────┐
    │     OBSERVE 阶段                  │
    │     RAGRetriever.retrieve()       │
    │       ├── ExplicitStore (SQLite)  │
    │       ├── ImplicitStore (ChromaDB)│
    │       └── ContextMemory (ChromaDB)│
    │           ↓                       │
    │     三层记忆合并 → 注入 Prompt    │
    │                                   │
    │     THINK 阶段                    │
    │     LLM 决策（带记忆上下文）       │
    │                                   │
    │     ACT 阶段                      │
    │     ToolExecutor 执行             │
    │     update_preference_memory →    │
    │       ImplicitStore.add()         │
    │                                   │
    │     REFLECT 阶段                  │
    │     PreferenceLearner             │
    │       .learn_from_decision()      │
    │       → ContextMemory.add()       │
    └───────────────────────────────────┘
```

## 模块说明

### 1. ExplicitStore — 显式偏好存储

封装 SQLite `Preference` 表的服务层：

- `get_preferences(employee_id, context)` — 查询某员工偏好
- `set_preference(employee_id, category, key, value, context)` — 写入/更新偏好
- `get_all_for_employees(employee_ids)` — 批量查询多人偏好

### 2. ImplicitStore — 隐式偏好向量存储

ChromaDB collection `implicit_preferences`：

- `add(text, metadata)` — 写入一条隐式偏好向量
- `query(query_text, employee_id, n_results)` — 按语义检索
- metadata 包含：`employee_id`, `context`, `device_type`, `timestamp`, `learn_type`

### 3. ContextMemory — 情境记忆

ChromaDB collection `context_memories`：

- `add(text, metadata)` — 写入场景绑定的记忆
- `query(query_text, employee_id, scene_type, n_results)` — 按情境检索
- 与 ImplicitStore 的区别：强调场景类型（开会/独自办公/午休等）

### 4. RAGRetriever — RAG 统一检索

同时检索三层记忆并合并结果：

- `retrieve(employee_id, context_hint, n_results)` — 返回结构化偏好画像
- `retrieve_many(employee_ids, context_hint, n_results)` — 批量检索多人
- 输出格式化文本，可直接注入 Agent Prompt

### 5. PreferenceLearner — 偏好学习器

从 Agent 行为中自动学习：

- `learn_from_override(employee_id, device_type, agent_value, user_value, context)` — 用户手动覆盖 Agent 设置时学习
- `learn_from_decision(decision_data)` — 从决策日志中提取可学习信息

### 6. MemorySystem — 聚合门面

在 `memory/__init__.py` 中，`MemorySystem` 统一初始化所有子模块：

```python
memory_system = MemorySystem(
    db_session_factory=db_factory,
    chroma_client=chroma_client,
)
# 可用子模块：
# memory_system.explicit   — ExplicitStore
# memory_system.implicit   — ImplicitStore
# memory_system.context    — ContextMemory
# memory_system.retriever  — RAGRetriever
# memory_system.learner    — PreferenceLearner
```

## 集成点

### PromptBuilder

`_get_preferences()` 方法优先通过 `RAGRetriever.retrieve_many()` 获取三层记忆的综合偏好。当 RAGRetriever 不可用时，退回到直接查询 SQLite。

Prompt 中偏好展示格式：
```
员工偏好:
  张三: [显式] 色温=4000K, 亮度=80% | [学习] 三次将空调从25调到23 | [情境] 开会时偏好冷光
```

### ToolExecutor

`update_preference_memory` handler 从占位实现改为真正调用 `ImplicitStore.add()`，将 LLM 的偏好观察写入 ChromaDB 向量存储。

### AgentLoop

OTAR 的 Reflect 阶段新增 `_learn_from_decision()` 调用，将每次成功决策的工具调用模式记录到 ContextMemory，供后续决策参考。

### core/main.py

在 lifespan 中：
1. 在 Phase 3 之前初始化 `MemorySystem`
2. 将 `memory_system.implicit` 注入 `ToolExecutor`
3. 将 `memory_system.retriever` 注入 `PromptBuilder`
4. 将 `memory_system.learner` 注入 `EaseAgent`

## 降级策略

- ChromaDB 不可用时：ImplicitStore 和 ContextMemory 的 `add/query` 返回空结果，不影响系统运行
- RAGRetriever 失败时：PromptBuilder 自动退回到直接查询 SQLite 显式偏好
- 整个 MemorySystem 初始化失败时：Agent 仍然正常工作，只是没有记忆增强

## 依赖

- **SQLite**（已有）— 显式偏好存储
- **ChromaDB**（已有 Docker 服务）— 向量存储
- **chromadb** Python 客户端（已在 requirements.txt）

## 后续优化方向

- 向量记忆过期清理机制（定期删除过旧的隐式偏好）
- 偏好置信度衰减（时间越久权重越低）
- 用户反馈闭环（"这个设置你满意吗？"）
- 跨房间偏好泛化（会议室偏好迁移到其他会议室）
