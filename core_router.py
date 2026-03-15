import asyncio
import uuid
import time
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

# 配置日志规范
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("CoreRouter")

class Priority(IntEnum):
    """
    绝对优先级控制 (数字越小优先级越高)
    """
    P0_COMMAND = 0    # 用户高优指令（最高优先级，绝对插队）
    P1_TRADE = 1      # 实盘交易信号
    P2_AGENT = 2      # LLM 研判任务与反馈
    P3_HEARTBEAT = 3  # 底层系统心跳包（最低优先级）

@dataclass(order=True)
class Message:
    """
    统一消息结构
    order=True 配合 field(compare=False) 使得 PriorityQueue 仅按照 priority 排序，
    避免遇到相同优先级时去比较不支持比较的 payload 导致程序崩溃。
    """
    priority: Priority
    timestamp: float = field(compare=False, default_factory=time.time)
    id: str = field(compare=False, default_factory=lambda: str(uuid.uuid4()))
    topic: str = field(compare=False, default="")
    payload: Any = field(compare=False, default_factory=dict)

class CentralRouter:
    """
    中枢路由器：基于 asyncio.PriorityQueue 实现高并发环境下的绝对优先级调度
    """
    def __init__(self):
        self._queue = asyncio.PriorityQueue()
        self._running = False
        
        # 定义路由表（Topic 前缀映射到处理逻辑）
        self._routes = {
            "wechat.": self._handle_wechat,
            "quant.": self._handle_quant,
            "agent.": self._handle_agent,
            "system.": self._handle_heartbeat,
        }

    async def publish(self, message: Message):
        """
        供所有外部模块调用，向总线发布消息
        """
        await self._queue.put(message)
        logger.debug(f"📤 消息已发布 | 优先级: {message.priority.name} | Topic: {message.topic} | ID: {message.id}")

    async def start(self):
        """
        异步循环方法：持续从队列取出消息，并以无阻塞的方式路由处理
        """
        self._running = True
        logger.info("🚀 CentralRouter 中枢路由器已启动，正在监听消息队列...")
        
        while self._running:
            try:
                # 阻塞等待消息
                message = await self._queue.get()
                
                # 使用 create_task 以并发方式执行 handler，防止单个任务卡死整条路由队列
                asyncio.create_task(self._route_and_handle(message))
                
                # 标记该消息从队列中完成调度
                self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("🛑 CentralRouter 收到停止信号。")
                self._running = False
                break
            except Exception as e:
                logger.error(f"❌ 路由器主循环发生未捕获异常: {e}", exc_info=True)

    async def stop(self):
        """停止路由器"""
        self._running = False

    async def _route_and_handle(self, message: Message):
        """
        消息分发及执行包装器，内含超时控制与异常捕获
        """
        handler = self._get_handler(message.topic)
        if not handler:
            logger.warning(f"⚠️ 未找到合适路由，消息被丢弃 | Topic: {message.topic}")
            return
            
        try:
            # 增加超时控制：规定单个 Handler 避免无限挂起
            # 具体超时时间可以针对 Topic 或者优先级单独设定，这里设置默认值 5 秒
            timeout = 5.0
            await asyncio.wait_for(handler(message), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"⏳ 处理超时 (超过 {timeout}s) 强制中断 | Topic: {message.topic} | ID: {message.id}")
        except Exception as e:
            logger.error(f"💥 处理消息时发生业务异常 | Topic: {message.topic} | Error: {e}")

    def _get_handler(self, topic: str) -> Callable[[Message], Awaitable[None]]:
        """根据 Topic 前缀匹配正确的处理函数"""
        for prefix, handler in self._routes.items():
            if topic.startswith(prefix):
                return handler
        return None  # 默认无匹配

    # ===============================================
    # 模拟各类 Handler 处理函数
    # ===============================================
    async def _handle_wechat(self, message: Message):
        logger.info(f"🟢 [P0_COMMAND] 收到微信侧命令，立即执行指令: {message.payload}")
        await asyncio.sleep(0.1)  # 模拟执行耗时

    async def _handle_quant(self, message: Message):
        logger.info(f"📈 [P1_TRADE] 收到量化侧信号，执行实盘相关操盘手逻辑: {message.payload}")
        await asyncio.sleep(0.2)
        
    async def _handle_agent(self, message: Message):
        logger.info(f"🤖 [P2_AGENT] 收到 LLM 任务，转交智能体执行: {message.payload}")
        # 故意制造一个阻塞卡死的业务示例，测试容错控制
        if message.payload.get("will_block", False):
            logger.warning("Agent 任务模拟超时阻塞...")
            await asyncio.sleep(10.0) 
        else:
            await asyncio.sleep(0.5)

    async def _handle_heartbeat(self, message: Message):
        logger.info(f"💓 [P3_HEARTBEAT] 收到心跳包... 处理完毕。")
        await asyncio.sleep(0.01)

# ===============================================
# 测试代码
# ===============================================
async def test_router():
    router = CentralRouter()
    
    # 将 router.start() 放入后台 Task
    router_task = asyncio.create_task(router.start())
    # 等待一刹那确保日志顺畅
    await asyncio.sleep(0.1)
    
    logger.info("\n========== TEST 1: 测试绝对优先级插队特性 ==========")
    # 故意同时或者乱序推入一系列消息由于队列的特性会让 P0 率先出列
    messages_to_send = [
        Message(priority=Priority.P3_HEARTBEAT, topic="system.heartbeat", payload={"msg": "ping"}),
        Message(priority=Priority.P2_AGENT, topic="agent.analyze", payload={"symbol": "BTC", "will_block": False}),
        Message(priority=Priority.P1_TRADE, topic="quant.signal", payload={"action": "buy"}),
        Message(priority=Priority.P0_COMMAND, topic="wechat.private", payload={"command": "EMERGENCY_STOP"}),
    ]
    
    # 瞬间一股脑全塞进 Queue 里
    for msg in messages_to_send:
        await router.publish(msg)
        
    # 给系统一点时间去将塞入的消息消化并体现出处理日志
    await asyncio.sleep(1.0)
    
    logger.info("\n========== TEST 2: 测试并行处理与防卡死 (超时控制) ==========")
    # 推送一个会引起超时卡死的低优先级任务
    await router.publish(Message(
        priority=Priority.P2_AGENT, 
        topic="agent.research", 
        payload={"task": "Deep Analysis", "will_block": True}
    ))
    
    # 在刚才那个任务超时卡死时，我们再次推送一个高优的微信指令，测试是不是会阻塞整个路由
    await asyncio.sleep(0.1)
    await router.publish(Message(
        priority=Priority.P0_COMMAND, 
        topic="wechat.private", 
        payload={"command": "QUERY_STATUS"}
    ))
    
    # 顺便推送一个心跳包
    await router.publish(Message(
        priority=Priority.P3_HEARTBEAT, 
        topic="system.heartbeat", 
        payload={"msg": "ping"}
    ))

    # 等待防卡死的 Timeout (上边设置了 5 秒) 触发并打印错误日志
    await asyncio.sleep(6)
    
    logger.info("\n测试完成，向 Router 发送停止信号...")
    router_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(test_router())
    except KeyboardInterrupt:
        pass
