"""
OpenClaw 3.0 Agent Tools
提供给大语言模型 (LLM) 量化智能体使用的标准化工具库。纯净的 Python 函数形态，依托 Google Style Docstring 规范以便充分被大模型所理解和调用。

工具清单：
  1. get_current_market_semantics()    - 获取当前市场行情语义
  2. verify_strategy_code()           - 沙盒回测验证 (必须先调用此工具)
  3. execute_oanda_trade()            - 实盘下单 (仅限沙盒验证通过后)
  4. broadcast_trade_report()         - 广播作战报告
  5. get_performance_review()         - 读取历史盈亏，供自我反思与迭代
  6. get_safe_position_size()         - 仓位风险管理与保证金预警 (必须在下单前调用)
"""

from kline_translator import generate_mock_klines, KlineTranslator
from strategy_sandbox import StrategySandbox
from oanda_executor import (
    execute_oanda_trade as _oanda_execute,
    broadcast_trade_report as _broadcast,
    get_account_summary,
    get_recent_closed_trades
)
from risk_manager import calculate_position_size
import logging
from typing import Literal

logger = logging.getLogger("AgentTools")

def get_current_market_semantics() -> str:
    """
    获取当前市场行情的自然语言语义描述。
    Returns:
        str: 行情分析战报。
    """
    df_history = generate_mock_klines(100)
    translator = KlineTranslator()
    return translator.translate_to_prompt(df_history, last_n=5)


def verify_strategy_code(strategy_code_str: str) -> dict:
    """
    在极速的仿真回测沙盒中安全验证交易策略代码的有效性与胜率表现。
    """
    sandbox = StrategySandbox(min_trades=3, min_win_rate=0.45, min_pnl_ratio=1.0)
    df_history = generate_mock_klines(100)
    
    try:
        strategy_func = sandbox.load_strategy(strategy_code_str, func_name="evaluate_signal")
        test_results = sandbox.run_backtest(df_history, strategy_func, window_size=3, hold_bars=2)
        decision = sandbox.judge(test_results)
        return decision
    except Exception as e:
        logger.error(f"⚠️ 工具箱在代执行过程中捕获异常: {e}")
        return {
            'passed': False,
            'win_rate': 0.0,
            'trades': 0,
            'pnl_ratio': 0.0,
            'reason': f"代码注入沙盒执行时发生编译报错或运行时崩溃: {str(e)}"
        }


def execute_oanda_trade(
    instrument: str,
    units: int,
    side: Literal["buy", "sell"],
    sandbox_verdict: dict
) -> dict:
    """
    在 OANDA 模拟账户下达市价单。此函数是实盘操盘的最终入口。

    【🔒 强制安全门控】：此函数内嵌了沙盒验证通过检查，必须将 `verify_strategy_code` 的返回值
    原封不动地作为 `sandbox_verdict` 参数传入本函数。若沙盒未通过（passed=False），本函数将拒绝
    执行并立刻返回错误，防止 Agent 绕过验证直接上实盘。

    【⚖️ 仓位管理约束】：严禁私自猜测或固定下单数量。在此之前，必须先调用 `get_safe_position_size` 
    算出符合风险标准的 units，并按其结果进行交易。

    【🚨 流动性警告】：如果 `get_safe_position_size` 返回的 `margin_ratio` 超过 20%，
    系统将触发流动性预警。此时必须优先考虑账户存续，减小仓位或放弃交易。

    Args:
        instrument (str): 交易品种代码（如 'XAU_USD'）。
        units (int): 开仓数量。
        side (Literal["buy", "sell"]): 交易方向。
        sandbox_verdict (dict): `verify_strategy_code()` 的返回值。

    Returns:
        dict: OANDA 委托执行响应。
    """
    if not sandbox_verdict.get("passed", False):
        reason = sandbox_verdict.get("reason", "未通过沙盒验证")
        logger.error(f"🚫 实盘请求被门控拦截！沙盒裁决为否决：{reason}")
        return {
            "success": False,
            "order_id": None,
            "instrument": instrument,
            "units": 0,
            "price": 0.0,
            "timestamp": "",
            "error": f"[GATE_BLOCKED] 策略未通过沙盒验证，拒绝上实盘。原因：{reason}"
        }

    logger.info(f"✅ 安全门控通过（胜率: {sandbox_verdict.get('win_rate', 0):.1%}），准予下单 {instrument} {side.upper()} {units}")
    return _oanda_execute(instrument, units, side)


def broadcast_trade_report(action_details: dict) -> str:
    """
    将一笔交易事件格式化为极具可读性的 Markdown 风格"作战报告"，实时广播给指挥官。
    战报中包含财务风险看板，展示保证金占用、占比及强平风险垫。

    Args:
        action_details (dict): 包含 action, instrument, price, units 
                             以及字段 margin_used, margin_ratio, safety_buffer_pct。
    """
    return _broadcast(action_details)


def get_performance_review() -> dict:
    """
    读取 OANDA 模拟盘的历史盈亏记录，供 Agent 进行自我反思与策略迭代。
    """
    account = get_account_summary()
    recent_trades = get_recent_closed_trades(count=20)
    total_pnl = sum(t["realized_pnl"] for t in recent_trades)
    wins = [t for t in recent_trades if t["realized_pnl"] > 0]
    win_rate = len(wins) / len(recent_trades) if recent_trades else 0.0
    best = max(recent_trades, key=lambda t: t["realized_pnl"], default=None)
    worst = min(recent_trades, key=lambda t: t["realized_pnl"], default=None)

    return {
        "account": account,
        "recent_trades": recent_trades,
        "summary": {
            "total_trades": len(recent_trades),
            "total_pnl": round(total_pnl, 4),
            "win_rate": round(win_rate, 4),
            "best_trade": best,
            "worst_trade": worst
        }
    }


def get_safe_position_size(
    risk_level: float, 
    stop_loss_price: float, 
    entry_price: float, 
    instrument: str
) -> dict:
    """
    计算并在实战中推荐安全的下单数量 (Units) 与相关财务风险指标。

    【💡 核心流程】：在准备执行 `execute_oanda_trade` 下单之前，必须调用此工具。
    它会自动查询你当前的 OANDA 账户净值，并结合你指定的风险百分比和止损间距，
    算出符合 20 倍杠杆上限保护的安全头寸，并提供保证金预测。

    Args:
        risk_level (float): 愿意承担的风险比例 (如 0.01)。
        stop_loss_price (float): 预设止损价位。
        entry_price (float): 入场价。
        instrument (str): 品种代码。

    Returns:
        dict: 风险评估报告字典，包含：
            - final_units (int): 最终下注单位
            - margin_used (float): 保证金占用金额 (USD)
            - margin_ratio (float): 保证金占用比例 (0-1 之间)
            - notional_value (float): 名义总价值 (USD)
            - safety_buffer_pct (float): 止损空间百分比
            - leverage_used (float): 实际杠杆倍数
    """
    acc_summary = get_account_summary()
    equity = acc_summary.get("nav", 0)
    
    if equity <= 0:
        logger.error("❌ 账户净值为 0 或负数，无法计算仓位。")
        return {"final_units": 0, "margin_used": 0, "margin_ratio": 0}
        
    risk_metadata = calculate_position_size(
        equity=equity,
        risk_percent=risk_level,
        stop_loss_price=stop_loss_price,
        entry_price=entry_price,
        instrument=instrument
    )
    
    return risk_metadata
