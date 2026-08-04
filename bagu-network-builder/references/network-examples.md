# 知识网络示例

收录从单个知识点出发、延伸到完整知识网络的参考示例。建网时参考其组织方式（ASCII 网络图 + 延伸路径说明），但**不要照抄**--要根据当前知识点真实关联来织网。

每个示例展示"理解->串联->建网"中的**第三层（建网）**完整产出，供格式和组织方式参考。

---

## 示例 1：从 synchronized 出发的知识网络

```
                        synchronized
                             |
            +----------------+----------------+
            |                |                |
        原理层            演进层            对比层
            |                |                |
     OS mutex 原语      JDK6 锁升级      ReentrantLock(AQS)
            |                |                |
   用户态/内核态切换    偏向锁(JDK15废弃)   CLH 队列
            |                |                |
   Java 一对一         轻量级锁(CAS)     LockSupport.park
   线程模型                |                |
            |          自适应自旋      Unsafe.park(native)
            |                |
            |          ┌─────┴──────┐
            |          |            |
            v          v            v
   Java 21 虚拟线程   CAS 原理    内存可见性
   (协程,用户态调度)  (无锁编程)    (volatile)
                          |            |
                     CAS 的ABA问题   JMM/happens-before
                          |
                     Atomic 类家族
                     (AtomicInteger等)
```

**延伸路径**：

- **路径1（向原理层）**：synchronized 重量级锁 -> OS mutex -> 用户态/内核态切换 -> Java 一对一线程模型 -> 为什么虚拟线程要出现（绕开一对一映射，用户态调度）-> 协程/Go goroutine 对比
- **路径2（向演进层）**：早期重量级锁 -> JDK 6 锁升级（偏向/轻量/自适应自旋）-> 偏向锁为什么 JDK 15 废弃（CAS 便宜了，维护成本不划算）-> 锁的未来趋势（乐观化、轻量化）
- **路径3（向对比层）**：synchronized -> ReentrantLock(AQS) -> AQS 的 CLH 队列 -> LockSupport -> CAS -> CAS 的 ABA 问题 -> Atomic 类 -> volatile/JMM

**为什么这样织网**：synchronized 是 Java 并发的核心入口，它的"为什么重"指向 OS 层，它的"怎么优化"指向 JVM 演进，它的"替代方案"指向 AQS 体系。三条路径各自独立又相互交织（CAS 同时出现在演进层和对比层），这就是网状结构。

---

## 示例 2：从分布式锁出发的知识网络

```
                        分布式锁
                            |
           +----------------+----------------+
           |                |                |
       实现方案          关联组件         一致性问题
           |                |                |
    +------+------+    +----+----+     Redis 单点问题
    |             |    |         |           |
  Redis实现   Zookeeper  Redis   ZK       -> Redlock
  (SETNX)    (临时节点)   |         |      (多节点投票)
    |             |        |         |
  过期时间     Watch机制  数据结构  ZAB协议
  +续期                  |         |
  (看门狗)               v         v
                  哈希/List/Set  ZK集群
                  /  ZSet           选举
                       |
                  +----+----+
                  |         |
              跳表实现   内存淘汰
                        机制
                  |         |
              数据结构   -> 操作系统
              (链表/哈希)  内存页面置换
                            算法(LRU/LFU)
```

**延伸路径**：

- **路径1（向实现方案）**：分布式锁 -> Redis 实现（SETNX+过期+看门狗续期）-> Redisson 看门狗机制 -> Zookeeper 实现（临时节点+Watch）-> 两者区别（Redis 重性能/AP，ZK 重一致/CP）-> CAP 定理
- **路径2（向 Redis 数据结构）**：分布式锁用到 Redis -> Redis 数据结构 -> ZSet（跳表实现）-> 跳表 vs 平衡树 -> 哈希表 -> 内存淘汰机制（LRU/LFU）-> OS 内存页面置换算法（同一个 LRU 思想）
- **路径3（向一致性）**：分布式锁单点问题 -> Redlock（多节点投票）-> 网络分区下的锁安全性（Martin Kleppmann 质疑 Redlock）-> 分布式一致性（Paxos/Raft）-> CAP

**为什么这样织网**：分布式锁是一个"枢纽"知识点--它上接分布式一致性理论，下接具体中间件（Redis/ZK），横向连数据结构和算法。从这一个点能展开到计算机体系结构的多个层面，这正是"知识网络"的价值：一个点通向多个域。

---

## 示例 3：从 Spring IOC 出发的知识网络

```
                        Spring IOC
                            |
           +----------------+----------------+
           |                |                |
        原理层            关联机制          演进层
           |                |                |
      反射机制          依赖注入(DI)      XML配置->注解
           |                |                |
   Class.forName      Bean生命周期      @ComponentScan
   Method.invoke            |            @Autowired
                    +-------+-------+         |
                    |               |    Spring Boot
               三级缓存        AOP(动态代理)   (自动装配)
               (循环依赖)            |
                              JDK动态代理
                              vs CGLIB
                                    |
                              代理模式(设计模式)
```

**延伸路径**：

- **路径1（向原理层）**：Spring IOC -> 反射机制 -> Class.forName / Method.invoke -> Java 反射的性能 -> 反射的应用场景（框架、序列化、ORM）
- **路径2（向关联机制）**：IOC -> DI 依赖注入 -> Bean 生命周期 -> 三级缓存解决循环依赖 -> AOP（动态代理）-> JDK 动态代理 vs CGLIB -> 代理模式（设计模式家族）
- **路径3（向演进层）**：XML 配置 -> 注解配置（@ComponentScan/@Autowired）-> Spring Boot 自动装配 -> Spring Boot Starter 机制

**为什么这样织网**：Spring 是后端框架的核心，IOC 是 Spring 的核心。它的"怎么实现"指向 Java 反射，它的"怎么解决循环依赖"指向三级缓存和对象引用，它的"AOP"指向设计模式。从 IOC 出发能串到反射、设计模式、框架演进三条线。
