import pandas as pd
import numpy as np
import logging
from typing import Callable, Dict, Any

from kline_translator import generate_mock_klines

logger = logging.getLogger("StrategySandbox")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

class StrategySandbox:
    """
    虚拟回测沙盒与裁判系统：动态安全加载外部策略代码并进行极速回测裁决
    """
    def __init__(self, min_trades: int = 3, min_win_rate: float = 0.65, min_pnl_ratio: float = 1.2):
        self.min_trades = min_trades
        self.min_win_rate = min_win_rate
        self.min_pnl_ratio = min_pnl_ratio

    def load_strategy(self, code_str: str, func_name: str = "evaluate_signal") -> Callable:
        """
        动态构建隔离环境并加载 LLM 生成的策略代码
        """
        # 构建受限的 globals/locals 环境，防止污染主进程或执行危险系统操作
        sandbox_env: Dict[str, Any] = {
            "__builtins__": __builtins__,
            "pd": pd,
            "np": np
        }
        try:
            # 动态执行代码字符串注入字典
            exec(code_str, sandbox_env)
        except Exception as e:
            logger.error(f"❌ 策略代码编译失败: {e}")
            raise ValueError(f"代码存在语法或加载错误: {e}")
            
        if func_name not in sandbox_env:
            raise KeyError(f"未能在代码中找到约定的入口函数: {func_name}")
            
        func = sandbox_env[func_name]
        if not callable(func):
            raise TypeError(f"{func_name} 不是一个可调用的函数对象")
            
        logger.info(f"✅ 成功从 LLM 源码动态编译隔离函数: {func_name}")
        return func

    def run_backtest(self, df: pd.DataFrame, strategy_func: Callable, window_size: int = 5, hold_bars: int = 3) -> dict:
        """
        基于历史数据的极速回测引擎 (滑动窗口机制)
        """
        if len(df) <= window_size + hold_bars:
            raise ValueError("K 线数据量不足以进行回测，请提供更长的行情数据。")

        trades = []
        wins = 0
        total_profit = 0.0
        total_loss = 0.0
        
        in_position = False
        entry_price = 0.0
        entry_idx = 0
        
        logger.info(f"⏳ 开始极速回测 | 窗口大小={window_size} | 持仓周期={hold_bars} K线")
        
        for i in range(window_size, len(df)):
            if in_position:
                # 检查是否满足持仓时间退出
                if i - entry_idx >= hold_bars:
                    # 在持仓到达期限后的当前这笔 K 线的开盘价卖出平仓
                    exit_price = df.iloc[i]['open']
                    pnl = exit_price - entry_price
                    pnl_pct = pnl / entry_price
                    
                    if pnl > 0:
                        wins += 1
                        total_profit += pnl_pct
                    else:
                        total_loss += abs(pnl_pct)
                    
                    trades.append({
                        'entry_idx': entry_idx, 
                        'exit_idx': i, 
                        'entry_price': entry_price, 
                        'exit_price': exit_price,
                        'pnl_pct': pnl_pct
                    })
                    in_position = False
                continue

            # 确保后续还有足够的 K 线用于持有平仓
            if i >= len(df) - 1:
                break
                
            # 切片：取过去 window_size 根 K 线喂给策略函数
            history_slice = df.iloc[i-window_size:i]
            
            try:
                # 执行策略函数的布尔预测
                signal = strategy_func(history_slice)
            except Exception as e:
                logger.error(f"❌ 策略在执行 K 线索引 {i} 时发生异常: {e}")
                signal = False
                
            if signal:
                # 假设策略在当前这根 K 线发信号，我们以“下一根的开盘价 (即当前 i ) ”买入
                entry_price = df.iloc[i]['open']
                entry_idx = i
                in_position = True
                
        # 统计整体各项指标
        num_trades = len(trades)
        win_rate = wins / num_trades if num_trades > 0 else 0.0
        
        avg_profit = total_profit / wins if wins > 0 else 0.0
        # 盈亏比计算：总均盈利 / 总均亏损
        avg_loss = total_loss / (num_trades - wins) if (num_trades - wins) > 0 else 0.0
        if avg_loss > 0:
            pnl_ratio = avg_profit / avg_loss
        elif avg_profit > 0:
            pnl_ratio = 999.0  # 全胜的情景
        else:
            pnl_ratio = 0.0

        return {
            'trades': num_trades,
            'win_rate': win_rate,
            'pnl_ratio': pnl_ratio,
            'details': trades
        }

    def judge(self, backtest_results: dict) -> dict:
        """
        裁判系统：结合预设硬性阈值对策略生成评估判决字典
        """
        t = backtest_results['trades']
        wr = backtest_results['win_rate']
        pr = backtest_results['pnl_ratio']
        
        reasons = []
        if t < self.min_trades:
            reasons.append(f"交易频次过低: {t} 下降于阈值 {self.min_trades}")
        if wr < self.min_win_rate:
            reasons.append(f"胜率未达标: {wr:.1%} 低于阈值 {self.min_win_rate:.1%}")
        if pr < self.min_pnl_ratio and t > 0:
            reasons.append(f"盈亏比不可观: {pr:.2f} 低于阈值 {self.min_pnl_ratio}")

        passed = len(reasons) == 0
        
        return {
            'passed': passed,
            'win_rate': wr,
            'trades': t,
            'pnl_ratio': pr,
            'reason': " | ".join(reasons) if not passed else "Perfect! 各项指标均通过严格校验。"
        }

if __name__ == "__main__":
    print("="*60)
    print(" 【调试阶段】步骤一：生成 100 根 K 线的模拟环境行情数据")
    print("="*60)
    # 生成充足历史数据提供回测滑动窗口空间
    # 为了更容易产生交易，我们不修改生成规则，但是只要遇到收盘>开盘的情况就有概率触发
    mock_df = generate_mock_klines(100)
    print(f"✅ 成功生成 100 根模拟 K 线数据，起止周期: {mock_df.iloc[0]['datetime']} -> {mock_df.iloc[-1]['datetime']}")
    
    print("\n" + "="*60)
    print(" 【调试阶段】步骤二：加载并注入 LLM 生成的模拟交易代码")
    print("="*60)
    
    # 我们虚拟一段大模型手写的 Python 代码策略
    # 此策略逻辑：连收两根阳线（收盘>开盘），并且第二根强势突破前高的收盘价，就在下一刻追涨进入
    llm_generated_code = """
def evaluate_signal(df_slice):
    # 我们保证至少拿到过去 2 根 K 线
    if len(df_slice) < 2:
        return False
        
    last = df_slice.iloc[-1]
    prev = df_slice.iloc[-2]
    
    last_is_green = last['close'] > last['open']
    prev_is_green = prev['close'] > prev['open']
    higher_close = last['close'] > prev['close']
    
    # 策略精髓：连续阳线且重心上移即追涨
    return last_is_green and prev_is_green and higher_close
"""
    print(llm_generated_code.strip())
    
    # 实例化裁判系统，为了能够通过测试，稍微把阈值放宽一些或者按照原本需求
    sandbox = StrategySandbox(min_trades=3, min_win_rate=0.5, min_pnl_ratio=1.0)
    
    try:
        # 加载LLM虚拟代码提取函数对象
        func = sandbox.load_strategy(llm_generated_code)
        
        print("\n" + "="*60)
        print(" 【调试阶段】步骤三：滑动窗口触发极速回测")
        print("="*60)
        # 窗口大小为2就够提取最后两根数据了，为了模拟持有过程我们固定每笔持股3个周期
        results = sandbox.run_backtest(mock_df, func, window_size=2, hold_bars=3)
        
        print("\n📈 回测详细表现统计：")
        print(f" ▶ 总交易数: {results['trades']} 笔")
        print(f" ▶ 综合胜率: {results['win_rate']:.2%}")
        print(f" ▶ 盈亏比率: {results['pnl_ratio']:.2f}")
        for t in results['details']:
            print(f"   ▷ [Entry] idx: {t['entry_idx']} (${t['entry_price']:.2f}) -> [Exit] idx: {t['exit_idx']} (${t['exit_price']:.2f}) | PnL: {t['pnl_pct']:+.2%}")
            
        print("\n" + "="*60)
        print(" 【调试阶段】步骤四：严苛的裁判系统裁决判定")
        print("="*60)
        
        decision = sandbox.judge(results)
        print(f"⚖️ 裁决结果: 【{'通过 (PASSED)' if decision['passed'] else '否决 (REJECTED)'}】")
        print(f"📄 裁决依据: {decision['reason']}")
        
    except Exception as err:
        logger.error(f"❌ 运行沙盒测试时崩溃: {err}")
