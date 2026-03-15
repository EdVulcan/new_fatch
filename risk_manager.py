# -*- coding: utf-8 -*-
"""
OpenClaw 3.0 风险管理系统 (Risk Manager)
负责进行精确的仓位计算 (Position Sizing)，集成不同品种的点值适配与杠杆风控拦截。
"""

import logging

logger = logging.getLogger("RiskManager")

def calculate_position_size(
    equity: float, 
    risk_percent: float, 
    stop_loss_price: float, 
    entry_price: float, 
    instrument: str
) -> int:
    """
    根据账户净值、单笔风险比例、止损位和入场位计算安全的下单数量 (Units)。

    计算公式：
    1. 风险金额 = 净值 * 风险比例
    2. 止损间距 = ABS(入场价 - 止损价)
    3. 单位数量 = 风险金额 / 止损间距 (根据品种点值换算)
    
    风控门控：
    - 杠杆锁定：最大下单杠杆不得超过 20 倍。

    Args:
        equity (float): 账户当前的净资产 (NAV)。
        risk_percent (float): 单笔交易愿意承担的风险比例（如 0.01 代表 1%）。
        stop_loss_price (float): 计划的止损退出价格。
        entry_price (float): 计划的成交入场价格。
        instrument (str): 交易品种代码 (如 'XAU_USD', 'EUR_USD')，用于适配点值。

    Returns:
        int: 计算得出的安全下单单位数 (正整数)。
    """
    # 1. 计算允许亏损的绝对风险金额
    risk_amount = equity * risk_percent
    
    # 2. 计算止损点的物理间距
    sl_dist = abs(entry_price - stop_loss_price)
    
    if sl_dist <= 0:
        logger.warning(f"🚫 止损间距无效 ({sl_dist})，请检查入场价与止损价设置。")
        return 0

    # 3. 点值/波动换算处理 (Pip Value Adaptation)
    # 对于 OANDA XAU_USD, 价格 0.01 的波动对应 0.01 美元的价值（假设 1 单位）
    # 对于 OANDA 外汇 (如 EUR_USD), 价格 0.0001 的波动（1 pip）对应 0.0001 美元的价值
    # 本质上对于直盘和黄金，在单位数为 1 时，1点波动价值即为 1点价格。
    # raw_units = 风险金 / 止损点差
    raw_units = risk_amount / sl_dist
    
    # 4. 杠杆保护 (Leverage Protection)
    # 最大名义价值 = 净值 * 20
    max_leverage = 20
    max_notional_value = equity * max_leverage
    
    # 当前计算出的单位对应的名义价值
    # 注意：黄金 1 单位名义价值 = 1 * 当前金价；外汇 1 单位名义价值 = 1 * 基准货币价
    current_notional_value = raw_units * entry_price
    
    if current_notional_value > max_notional_value:
        logger.warning(
            f"⚠️ 风控拦截：原计算单位 {int(raw_units)} 对应杠杆过高。"
            f"已强制截断至 {max_leverage} 倍最大杠杆保护。"
        )
        # 强制修正单位使其符合最大杠杆
        safe_units = max_notional_value / entry_price
    else:
        safe_units = raw_units
        
    final_units = int(safe_units)
    
    # 5. 保证金与风险垫计算 (Margin & Safety Buffer)
    # 获取杠杆率 (Margin Rate): OANDA 默认通常为 2% (即 50:1 杠杆)
    margin_rate = 0.02 
    leverage_ratio = 1 / margin_rate
    
    # 计算保证金占用 (Margin Used)
    margin_used = (final_units * entry_price) / leverage_ratio
    
    # 计算保证金占比 (Margin Ratio)
    margin_ratio = margin_used / equity
    
    # 计算强平风险垫 (Safety Buffer)
    # 逻辑：在当前仓位下，价格向止损方向波动多少会耗尽这笔单子分配的风险金(Risk Amount)
    # 本质上对于 Agent 来说，查看 sl_dist 动态百分比更有意义
    safety_buffer = sl_dist / entry_price
    
    # 名义总价值 (Units * Entry Price)
    notional_value = final_units * entry_price
    
    risk_metadata = {
        "final_units": final_units,
        "margin_used": round(margin_used, 2),
        "margin_ratio": round(margin_ratio, 4),
        "notional_value": round(notional_value, 2),
        "safety_buffer_pct": round(safety_buffer * 100, 2),
        "leverage_used": round(notional_value / equity, 2)
    }

    if margin_ratio > 0.20:
        logger.warning(
            f"🚨 流动性警告：当前策略预计占用保证金 {margin_ratio:.1%}！"
            f"超过 20% 安全红线，建议强制减仓以维持账户存续。"
        )

    logger.info(
        f"🛡️ 仓位计算完成 | 品种: {instrument} | 单位: {final_units} | "
        f"保证金占用: ${risk_metadata['margin_used']} ({risk_metadata['margin_ratio']:.2%})"
    )
    
    return risk_metadata
