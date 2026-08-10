"""Idempotent starter question bank (15 Java + 10 Agent questions)."""

from __future__ import annotations

try:
    from .db import get_db, init_db, insert_question
except ImportError:  # Allows: python backend/seed.py
    from db import get_db, init_db, insert_question


SEED_QUESTIONS = [
    {
        "category": "八股",
        "topic": "并发",
        "question": "Java 内存模型中的 happens-before 是什么？volatile 能保证什么？",
        "answer": "happens-before 是判断跨线程操作可见性和有序性的规则。若 A happens-before B，则 A 的结果对 B 可见且 A 先于 B 排序。volatile 写 happens-before 后续对同一变量的读，因此它保证可见性，并通过内存屏障限制相关重排序；单次读写具有原子性，但复合操作如 i++ 仍不具备原子性。",
        "keypoints": ["happens-before 定义", "volatile 可见性", "volatile 有序性/内存屏障", "复合操作不保证原子性"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "并发",
        "question": "synchronized 的锁升级过程是什么？它和 ReentrantLock 如何选择？",
        "answer": "现代 JVM 会依据竞争情况使用轻量级锁、重量级锁等状态以降低无竞争开销，具体实现随 JDK 版本变化。synchronized 语法简单、异常时自动释放并由 JVM 优化；ReentrantLock 支持可中断、超时、公平锁和多个 Condition。一般先选 synchronized，需要高级能力时再选 Lock。",
        "keypoints": ["无竞争到竞争的锁状态变化", "synchronized 自动释放", "ReentrantLock 可中断/超时", "公平锁与 Condition", "按需求选择"],
        "difficulty": 4,
    },
    {
        "category": "八股",
        "topic": "并发",
        "question": "ThreadPoolExecutor 的核心参数和任务提交流程是什么？",
        "answer": "核心参数包括 corePoolSize、maximumPoolSize、keepAliveTime、workQueue、threadFactory 和 rejectionHandler。提交时先创建核心线程，再尝试入队；队列满后再创建非核心线程；达到最大线程数后执行拒绝策略。队列类型会显著改变参数的实际效果。",
        "keypoints": ["七个核心参数", "核心线程优先", "随后任务入队", "队列满再扩线程", "最大线程后拒绝", "队列选择影响行为"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "并发",
        "question": "AQS 的核心设计是什么？公平锁和非公平锁有何区别？",
        "answer": "AQS 用一个 volatile state 表示同步状态，并用 CLH 风格的双向等待队列管理竞争线程。子类通过 tryAcquire/tryRelease 定义独占或共享语义。公平锁通常先检查队列前驱，按排队顺序获取；非公平锁允许新线程直接 CAS 抢锁，吞吐通常更高但可能饥饿。",
        "keypoints": ["volatile state", "CAS 更新状态", "FIFO/CLH 等待队列", "模板方法", "公平性与吞吐权衡"],
        "difficulty": 4,
    },
    {
        "category": "八股",
        "topic": "并发",
        "question": "使用 CompletableFuture 时常见的线程池和异常处理陷阱有哪些？",
        "answer": "未指定执行器的异步阶段默认使用 commonPool，不适合混入阻塞任务。应按业务隔离线程池，限制队列并设置拒绝和监控。异常要通过 exceptionally、handle 或 whenComplete 明确处理；组合多个任务时要注意超时、取消传播以及 join 对当前线程的阻塞。",
        "keypoints": ["默认 commonPool", "阻塞任务需隔离", "异常链显式处理", "超时与取消", "join/get 可能阻塞"],
        "difficulty": 4,
    },
    {
        "category": "八股",
        "topic": "集合",
        "question": "HashMap 在 JDK 8 中的 put 和扩容流程是什么？",
        "answer": "HashMap 先扰动 hash，再用 (n-1)&hash 定位桶。空桶直接放入；碰撞时遍历链表或红黑树并更新/追加。链表达到阈值且数组容量足够时树化。元素数超过 threshold 后容量通常翻倍，节点依据旧容量对应的 hash 位拆分到原位置或原位置+oldCap。",
        "keypoints": ["hash 扰动与定位", "链表/红黑树处理碰撞", "树化条件", "负载因子与 threshold", "扩容高位拆分"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "集合",
        "question": "ConcurrentHashMap 在 JDK 8 中如何保证线程安全？",
        "answer": "JDK 8 不再使用 Segment，主要通过 volatile 可见性、CAS 和桶头 synchronized 协作。初始化、空桶插入等路径使用 CAS；桶内冲突更新锁住桶头；扩容时多个线程可通过 transfer 协助迁移。读操作大多无锁，但其迭代器只提供弱一致性。",
        "keypoints": ["CAS + synchronized", "锁粒度为桶", "volatile 可见性", "多线程协助扩容", "读大多无锁/弱一致迭代"],
        "difficulty": 4,
    },
    {
        "category": "八股",
        "topic": "JVM",
        "question": "JVM 运行时数据区如何划分？哪些区域是线程私有的？",
        "answer": "程序计数器、Java 虚拟机栈和本地方法栈通常线程私有；堆和方法区是线程共享的。栈帧包含局部变量表、操作数栈、动态链接和返回信息。对象主要位于堆，类元数据在 HotSpot 的 Metaspace。直接内存不属于规范定义的数据区，但也可能导致内存溢出。",
        "keypoints": ["程序计数器", "虚拟机栈/本地方法栈", "堆", "方法区与 Metaspace", "线程私有和共享", "直接内存"],
        "difficulty": 2,
    },
    {
        "category": "八股",
        "topic": "JVM",
        "question": "什么对象可以作为 GC Roots？可达性分析为什么能解决循环引用？",
        "answer": "常见 GC Roots 包括栈帧中的引用、静态字段引用、JNI 引用、活动线程及 JVM 内部引用。可达性分析从 Roots 沿引用图遍历，无法到达的对象才可能回收。两个对象即便相互引用，只要整体不可从任何 Root 到达，仍会被判为不可达，因此不受引用计数的循环问题影响。",
        "keypoints": ["栈中引用", "静态/JNI 引用", "活动线程等 JVM Roots", "从 Roots 遍历引用图", "循环引用仍可回收"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "JVM",
        "question": "G1 垃圾收集器的 Region、Remembered Set 和 Mixed GC 分别做什么？",
        "answer": "G1 将堆划成等大小 Region，逻辑上组合成年轻代和老年代。Remembered Set 记录跨 Region 引用，避免扫描整个堆。并发标记识别老年代存活情况后，Mixed GC 会同时回收年轻 Region 和收益较高的老年代 Region。G1 根据停顿目标选择回收集合，但停顿时间不是硬实时保证。",
        "keypoints": ["Region 化堆", "Remembered Set 跨区引用", "并发标记", "Mixed GC", "按收益选择回收集合", "停顿目标非硬保证"],
        "difficulty": 4,
    },
    {
        "category": "八股",
        "topic": "JVM",
        "question": "类加载过程有哪些阶段？双亲委派模型解决了什么问题？",
        "answer": "类生命周期主要经过加载、验证、准备、解析、初始化等阶段。双亲委派要求加载请求优先交给父加载器，父加载器无法完成时子加载器再尝试，从而让核心类由稳定的加载器加载，避免重复和伪造。SPI、应用服务器隔离和热部署等场景会有受控的打破或扩展。",
        "keypoints": ["加载", "验证/准备/解析", "初始化", "父加载器优先", "避免核心类重复和篡改", "SPI 等例外"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "Java基础",
        "question": "String.intern()、字符串常量池和 new String() 的关系是什么？",
        "answer": "字符串字面量会复用常量池中的规范实例。new String(...) 会在堆上创建新的 String 对象，因此引用通常不同但 equals 内容相等。intern() 返回常量池中该内容的规范引用；若池中没有，具体放入或引用哪个对象的细节与 JDK 实现和写法有关，不应把引用相等作为业务逻辑。",
        "keypoints": ["字面量进入/复用常量池", "new 创建新对象", "equals 与 == 区别", "intern 返回规范引用", "实现细节与版本相关"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "Spring",
        "question": "Spring Bean 从实例化到可用经历哪些关键生命周期步骤？",
        "answer": "容器先实例化 Bean 并注入属性，然后执行 Aware 回调、BeanPostProcessor 的初始化前处理、@PostConstruct/InitializingBean/自定义 init，最后执行初始化后处理，其中 AOP 代理常在后处理器阶段创建。容器关闭时调用 @PreDestroy、DisposableBean 或自定义 destroy。",
        "keypoints": ["实例化与依赖注入", "Aware 回调", "BeanPostProcessor 前后处理", "初始化回调", "AOP 代理时机", "销毁回调"],
        "difficulty": 4,
    },
    {
        "category": "八股",
        "topic": "Spring",
        "question": "@Transactional 在哪些常见情况下会失效？",
        "answer": "常见原因包括同类方法自调用绕过代理、方法不可被当前代理机制覆盖、对象不是 Spring Bean、异常被吞掉、抛出的异常不符合默认回滚规则、传播行为或数据源配置不正确。排查时先确认调用是否经过代理，再检查异常、事务管理器和最终 SQL 连接。",
        "keypoints": ["自调用绕过代理", "非 Spring 管理对象", "代理无法拦截的方法", "异常被捕获或不匹配回滚规则", "事务管理器/数据源", "传播行为"],
        "difficulty": 3,
    },
    {
        "category": "八股",
        "topic": "Spring",
        "question": "Spring 如何处理循环依赖？为什么构造器循环依赖通常无法解决？",
        "answer": "单例 setter/字段注入的循环依赖可借助三级缓存暴露早期对象引用，并在需要时提供早期代理。构造器注入要求创建 A 时先完整得到 B，而创建 B 又先需要 A，此时尚无可暴露实例，因此形成死结。prototype Bean 也不走单例缓存方案。最佳实践仍是重构依赖关系。",
        "keypoints": ["单例三级缓存", "早期对象引用", "早期 AOP 代理", "构造器依赖无实例可暴露", "prototype 不支持", "优先重构"],
        "difficulty": 4,
    },
    {
        "category": "agent",
        "topic": "RAG",
        "question": "一个完整的 RAG 系统从文档到答案通常包含哪些环节？",
        "answer": "离线侧包括解析清洗、切分、元数据处理、向量化和索引；在线侧包括查询改写、召回、过滤/融合、重排、上下文组装和生成。生产系统还要做权限过滤、引用溯源、缓存、评测与观测。每一阶段都应有可独立度量的质量指标。",
        "keypoints": ["文档解析与切分", "Embedding 与索引", "查询改写/召回", "过滤与重排", "上下文组装与生成", "权限/引用/观测"],
        "difficulty": 2,
    },
    {
        "category": "agent",
        "topic": "RAG",
        "question": "Chunk 应该如何切分？chunk size 和 overlap 的主要权衡是什么？",
        "answer": "应优先尊重标题、段落、代码块等语义边界，再结合模型上下文和查询粒度确定大小。过小会丢上下文并增加索引项，过大会稀释语义、降低精确召回并消耗 token。overlap 可缓解边界信息丢失，但会增加存储和结果重复。应通过真实查询集评测，而非只凭经验设置。",
        "keypoints": ["优先语义边界", "过小丢上下文", "过大稀释召回", "overlap 缓解边界问题", "成本与重复", "用评测集调参"],
        "difficulty": 3,
    },
    {
        "category": "agent",
        "topic": "RAG",
        "question": "向量召回、关键词召回和 reranker 如何组合？",
        "answer": "向量检索擅长语义相似，BM25 等关键词检索擅长专有词和精确匹配，常用混合召回提高候选覆盖率，再用 RRF 或分数归一化融合。cross-encoder reranker 对候选进行更精细的相关性判断，但延迟和成本更高，所以通常只重排较小的 top-k。",
        "keypoints": ["向量语义召回", "BM25 精确词匹配", "混合召回", "RRF/分数融合", "reranker 精排", "top-k 与延迟权衡"],
        "difficulty": 3,
    },
    {
        "category": "agent",
        "topic": "可靠性",
        "question": "如何系统性降低大模型幻觉，而不只是修改 Prompt？",
        "answer": "先限定可回答范围，并用 RAG 或工具提供可验证事实；要求引用证据并在证据不足时拒答。对关键输出使用结构化约束、规则或第二模型校验，必要时让确定性系统执行最终动作。再用事实性评测集、线上抽检和反馈闭环定位幻觉来源。",
        "keypoints": ["限定范围与拒答", "RAG/工具提供事实", "引用与可追溯", "结构化约束和校验", "关键动作交给确定性系统", "离线在线评测"],
        "difficulty": 3,
    },
    {
        "category": "agent",
        "topic": "工具调用",
        "question": "Function Calling/Tool Calling 的完整执行循环是什么？",
        "answer": "应用向模型提供工具 schema 和上下文；模型返回工具名及结构化参数；应用必须校验参数、鉴权并执行工具；再把工具结果作为消息交回模型，直到得到最终回答或达到步数限制。生产环境还需处理幂等、超时、重试、并发、危险操作确认和审计。",
        "keypoints": ["声明工具 schema", "模型选择工具并给参数", "参数校验与鉴权", "应用执行后回传结果", "循环与步数限制", "幂等/超时/审计"],
        "difficulty": 3,
    },
    {
        "category": "agent",
        "topic": "记忆",
        "question": "Agent 的短期记忆和长期记忆应如何设计？",
        "answer": "短期记忆服务于当前任务，可保留最近消息、工具结果和压缩摘要，并受上下文窗口约束。长期记忆保存跨会话有价值的事实、偏好或经验，通常需要结构化存储或向量检索。写入前要判断价值、去重和权限，读取时按当前任务检索，且要支持过期、纠错和用户删除。",
        "keypoints": ["短期上下文/摘要", "长期持久化检索", "选择性写入", "按任务相关性读取", "去重与权限", "过期纠错删除"],
        "difficulty": 3,
    },
    {
        "category": "agent",
        "topic": "推理规划",
        "question": "ReAct 模式解决了什么问题？它有哪些工程风险？",
        "answer": "ReAct 让模型在推理、选择行动、观察工具结果之间循环，从而把外部事实和操作纳入决策。工程风险包括无限循环、错误累积、token 与延迟膨胀、敏感思维过程暴露以及执行危险动作。应设置步骤/预算限制、状态机、工具权限、终止条件和完整轨迹观测。",
        "keypoints": ["推理-行动-观察循环", "利用外部工具反馈", "循环/错误累积风险", "成本和延迟", "步骤与预算限制", "权限和轨迹观测"],
        "difficulty": 3,
    },
    {
        "category": "agent",
        "topic": "多Agent",
        "question": "什么时候值得使用多 Agent，而不是一个 Agent 加多个工具？",
        "answer": "当任务可明确分解、不同子任务需要独立上下文或专业策略，且并行收益能覆盖协调成本时，多 Agent 才有价值。简单串行工具调用通常单 Agent 更稳定。多 Agent 要解决任务分配、共享状态、冲突合并、失败恢复、预算和可观测性，否则只是增加延迟与不确定性。",
        "keypoints": ["可分解/可并行任务", "独立专业上下文", "协调成本", "简单任务优先单 Agent", "共享状态与冲突合并", "失败恢复和预算"],
        "difficulty": 4,
    },
    {
        "category": "agent",
        "topic": "安全",
        "question": "Prompt Injection 是什么？RAG/Agent 系统如何防御？",
        "answer": "Prompt Injection 是不可信输入试图覆盖系统指令或诱导模型泄密、越权调用工具。防御要把网页/文档视为数据而非指令，分隔并标注来源；工具层做最小权限、参数校验和高风险确认；敏感信息不进入模型可见上下文；输出继续做策略检查。不能只靠一段反注入 Prompt。",
        "keypoints": ["不可信内容操纵模型", "数据与指令隔离", "最小工具权限", "参数校验和人工确认", "敏感信息隔离", "分层防御"],
        "difficulty": 4,
    },
    {
        "category": "agent",
        "topic": "评测",
        "question": "如何评测一个 Agent 系统，而不是只看最终回答好不好？",
        "answer": "应同时衡量任务成功率、答案正确性、工具选择和参数正确率、步骤效率、延迟、成本、安全违规以及失败恢复。建立覆盖典型与对抗场景的版本化数据集，保存完整轨迹，使用规则、人工和 LLM judge 组合评测，并定期校准 judge。线上结合抽样审查、用户反馈和分阶段指标定位退化。",
        "keypoints": ["任务成功率", "工具调用正确性", "步骤/延迟/成本", "安全与恢复", "版本化评测集", "轨迹级评测", "线上反馈与监控"],
        "difficulty": 4,
    },
]


def seed_database() -> int:
    """Insert missing starter questions and return the number added."""

    init_db()
    inserted = 0
    for item in SEED_QUESTIONS:
        with get_db() as conn:
            exists = conn.execute(
                "SELECT 1 FROM questions WHERE question = ? LIMIT 1",
                (item["question"],),
            ).fetchone()
        if exists:
            continue
        insert_question(source="内置题库", **item)
        inserted += 1
    return inserted


if __name__ == "__main__":
    added = seed_database()
    print(f"Seed complete: added {added} question(s), total starter set {len(SEED_QUESTIONS)}.")


__all__ = ["SEED_QUESTIONS", "seed_database"]
