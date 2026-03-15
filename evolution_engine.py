import asyncio
import logging
import re
from typing import Dict, Any

from kline_translator import generate_mock_klines
from strategy_sandbox import StrategySandbox
from core_router import Priority, Message

logger = logging.getLogger("EvolutionEngine")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s', datefmt='%H:%M:%S')

async def mock_llm_generate_strategy(prompt: str) -> str:
    """
    模拟 LLM 根据 K 线语义提示词，进行逻辑思考并生成 Python 代码
    """
    logger.info("🧠 [THINK] LLM 正在基于市场行情进行深度思考与编码...")
    await asyncio.sleep(1.5)  # 模拟网络调用延迟
    
    # 我们故意返回一段稍微复杂点、能体现逻辑的代码，并且一定能通过预设门槛
    # 逻辑：价格在 5 根 K 线内出现缩量震荡且重心上移破前高，这与刚刚 Translator 的 mock 数据呼应
    code_response = '''
```python
def evaluate_signal(df_slice):
    if len(df_slice) < 3:
        return False
        
    last = df_slice.iloc[-1]
    prev1 = df_slice.iloc[-2]
    prev2 = df_slice.iloc[-3]
    
    # 寻找阳线突破，同时要求近期低点抬高 (探底针护盘有效)
    is_breakout = last['close'] > prev1['high'] and last['close'] > last['open']
    lows_rising = prev1['low'] >= prev2['low']
    
    return is_breakout and lows_rising
```
'''
    return code_response

class EvolutionEngine:
    """
    OpenClaw 3.0 自动进化引擎：发现、编码、回测、实盘 上线闭环体系
    """
    def __init__(self):
        # 实例化轻量级回测沙盒及裁判标准
        self.sandbox = StrategySandbox(min_trades=3, min_win_rate=0.45, min_pnl_ratio=1.0)
        
    def _extract_code(self, llm_response: str) -> str:
        """简单的由 Markdown 代码块提取核心代码"""
        match = re.search(r"```python(.*?)```", llm_response, re.DOTALL)
        if match:
            return match.group(1).strip()
        return llm_response.strip()

    async def run_evolution_cycle(self):
        """
        完整的一轮进化周期：观察 -> 思考 -> 验证 -> 决策
        """
        print("\n" + "="*70)
        print(" 🧬 [EVOLUTION CYCLE] 初始化自治进化循环引擎...")
        print("="*70)
        
        # 步骤 A（观察） - 模拟获取并翻译当前市场行情
        print("\n👁️  步骤 A [Observe]: 正在观测市场并生成全局上下文语义...")
        await asyncio.sleep(0.5)
        mock_prompt = "【全局趋势】近 100 根K线总体处于震荡偏上整理状态...\n【近期形态】最后 5 根 K 线特征: K线-1 为放量大阳线，实体饱满突破前高。K线-2 为长下影线探底针..."
        print(f"📊 观测完毕，行情语义已提取: [ {mock_prompt[:45]}... ]")

        # 步骤 B（思考） - 委托给 LLM 撰写能对付这段行情的策略代码
        print("\n🤖 步骤 B [Think]: 将语义上下文输入大模型引擎，请求量化逻辑编码...")
        llm_reply = await mock_llm_generate_strategy(mock_prompt)
        raw_code = self._extract_code(llm_reply)
        print("📝 LLM 编码完成！提取到的核心判定函数如下：")
        for line in raw_code.split('\n'):
            print("   ▍", line)

        # 步骤 C（验证） - 加载到沙盒中进行历史极速回测验证
        print("\n🔬 步骤 C [Verify]: 正在将新鲜策略送入回测沙盒中提纯验证...")
        await asyncio.sleep(0.5)
        try:
            strategy_func = self.sandbox.load_strategy(raw_code)
            # 生成 100 根数据做背靠背验证测试
            df_history = generate_mock_klines(100) 
            
            # 使用沙盒运行回测
            results = self.sandbox.run_backtest(df_history, strategy_func, window_size=3, hold_bars=2)
            decision = self.sandbox.judge(results)
            
            print(f"📈 回测出表 -> 交易数: {results['trades']} 笔 | 胜率: {results['win_rate']:.1%} | 盈亏比: {results['pnl_ratio']:.2f}")
            print(f"⚖️ 裁判决议: {'通过 (PASSED) ✅' if decision['passed'] else '否决 (REJECTED) ❌'} | 理由: {decision['reason']}")
            
        except Exception as e:
            logger.error(f"验证阶段崩溃: {e}")
            decision = {'passed': False}

        # 步骤 D（决策） - 决定是否推送到实盘路由器总线
        print("\n🎯 步骤 D [Decide]: 最终进化决策环节...")
        await asyncio.sleep(0.5)
        if decision['passed']:
            # 拟态生成中枢消息结构
            msg = Message(
                priority=Priority.P0_COMMAND,
                topic="system.evolution.upgrade",
                payload={"strategy_code": raw_code, "metrics": {"win_rate": results['win_rate'], "trades": results['trades']}}
            )
            print("🚨 [URGENT] ===============================================")
            print(f"🚨 [P0_COMMAND] 报告指挥官：Agent 发现新形态并以 {results['win_rate']:.1%} 胜率通过沙盒回测！请求实盘加载！")
            print(f"🚨 [Router Message Hook] -> Topic: {msg.topic} | Priority: {msg.priority.name} | ID: {msg.id}")
            print("🚨 [URGENT] ===============================================")
        else:
            print("♻️ 策略未达标：将被遗弃，收集本次失败经验，准备下一次突变进化...")

        print("\n🏁 进化循环生命周期 [观察 -> 写代码 -> 回测 -> 汇报] 执行完毕。")

if __name__ == "__main__":
    engine = EvolutionEngine()
    try:
        asyncio.run(engine.run_evolution_cycle())
    except KeyboardInterrupt:
        print("\n进化过程中断。")
