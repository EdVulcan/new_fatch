"""
OpenClaw 3.0 OANDA 交易执行器
通过 oandapyV20 REST 客户端对接 OANDA 模拟/实盘账户，提供市价单下单与历史交易记录读取能力。
所有凭证通过环境变量注入，严禁硬编码。
"""

import os
import logging
from datetime import datetime, timezone
from typing import Literal

from dotenv import load_dotenv
import oandapyV20
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.trades as trades
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.transactions as transactions

load_dotenv()

logger = logging.getLogger("OandaExecutor")


def _get_client() -> tuple[oandapyV20.API, str]:
    """
    构建并返回已鉴权的 OANDA API 客户端与 Account ID。
    凭证来源于 .env 文件或系统环境变量。

    Returns:
        tuple: (api_client, account_id)

    Raises:
        EnvironmentError: 如果必要的环境变量未设置。
    """
    account_id = os.getenv("OANDA_ACCOUNT_ID")
    access_token = os.getenv("OANDA_ACCESS_TOKEN")
    environment = os.getenv("OANDA_ENVIRONMENT", "practice")  # 默认模拟盘

    if not account_id or not access_token:
        raise EnvironmentError(
            "❌ 环境变量 OANDA_ACCOUNT_ID 或 OANDA_ACCESS_TOKEN 未配置！"
            "请在项目根目录创建 .env 文件并填入凭证。"
        )

    client = oandapyV20.API(access_token=access_token, environment=environment)
    return client, account_id


def execute_oanda_trade(
    instrument: str,
    units: int,
    side: Literal["buy", "sell"]
) -> dict:
    """
    在 OANDA 模拟账户下达市价单。

    【🚨 强制前置条件】：此函数只能在 `verify_strategy_code` 沙盒验证通过（passed=True）后才可调用。
    严禁跳过沙盒验证直接喂入交易指令，任何绕过此规则的行为均属违规操作。

    Args:
        instrument (str): 交易品种代码，遵循 OANDA 规范（如 'XAU_USD', 'EUR_USD', 'GBP_JPY'）。
        units (int): 开仓数量，正整数。最终方向由 `side` 参数统一控制，无需手动设置正负。
                     单位因品种而异（如 XAU_USD 单位为盎司）。
        side (Literal["buy", "sell"]): 交易方向。
            - "buy"：做多开仓。
            - "sell"：做空开仓（units 将自动转换为负数）。

    Returns:
        dict: OANDA API 的标准化响应回执，包含以下核心字段：
            - success (bool): True 表示订单成功被 OANDA 接受，False 表示失败。
            - order_id (str): OANDA 分配的交易单号（可用于后续平仓/查询）。
            - instrument (str): 下单品种。
            - units (int): 实际下单数量（含正负方向）。
            - price (float): 实际成交价格。
            - timestamp (str): 服务器时间戳（ISO8601格式）。
            - error (str | None): 如果失败，包含 OANDA 返回的原始错误信息。

    Example:
        >>> result = execute_oanda_trade('XAU_USD', 1, 'buy')
        >>> if result['success']:
        ...     print(f"成交价：{result['price']}")
    """
    client, account_id = _get_client()

    # 根据方向确定 units 的正负号
    final_units = units if side == "buy" else -units

    order_body = {
        "order": {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(final_units),
            "timeInForce": "FOK",      # Fill-Or-Kill: 无法立刻全部成交则整单撤销
            "positionFill": "DEFAULT"
        }
    }

    try:
        r = orders.OrderCreate(account_id, data=order_body)
        response = client.request(r)

        fill = response.get("orderFillTransaction", {})
        price = float(fill.get("price", 0))
        order_id = fill.get("tradeOpened", {}).get("tradeID", fill.get("id", "N/A"))
        timestamp = fill.get("time", datetime.now(timezone.utc).isoformat())

        logger.info(
            f"✅ 市价单成交 | {instrument} {side.upper()} {final_units} | "
            f"价格: {price} | 单号: {order_id}"
        )

        return {
            "success": True,
            "order_id": order_id,
            "instrument": instrument,
            "units": final_units,
            "price": price,
            "timestamp": timestamp,
            "error": None
        }

    except oandapyV20.exceptions.V20Error as e:
        logger.error(f"❌ OANDA API 执行失败 | {instrument} | 错误: {e}")
        return {
            "success": False,
            "order_id": None,
            "instrument": instrument,
            "units": final_units,
            "price": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }


def broadcast_trade_report(action_details: dict) -> str:
    """
    将一笔交易行为格式化为极具可读性的"作战报告"，实时广播给指挥官。

    每一次开仓或平仓事件发生后，必须立刻调用此工具生成并输出战报。
    战报内容涵盖技术面逻辑支撑、宏观情绪描述、关键价位和风控参数，
    是 Agent 向人类指战员汇报决策链条的标准通信协议。

    Args:
        action_details (dict): 本次交易的完整细节字典，建议包含如下字段（所有字段均为可选，有值则自动填入）：
            - action (str): 动作类型，如 "开多仓", "开空仓", "平仓止盈", "平仓止损"。
            - instrument (str): 品种代码，如 "XAU_USD"。
            - price (float): 执行价格（开/平仓价）。
            - units (int): 开仓数量。
            - stop_loss (float): 止损价格参考位。
            - take_profit (float): 目标止盈价格参考位。
            - technical_reason (str): 技术面核心判断依据（例如："放量大阳线突破颈线，RSI 尚未超买"）。
            - macro_context (str): 当前宏观/情绪背景（例如："美元流动性宽松，黄金避险需求升温"）。
            - confidence (str): 对此次决策的置信度描述，如 "高 (沙盒胜率 65%+)"。

    Returns:
        str: 一份格式化的 Markdown 风格的作战报告文本，可直接打印至控制台或推送至通讯频道。
    """
    # ── Windows 编码冲突修复 ──
    # 强制将标准输出切换为 UTF-8，防止在 CMD/PowerShell 打印 Emoji 时触发 GBK 编码报错
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    action = action_details.get("action", "未知操作")
    instrument = action_details.get("instrument", "未知品种")
    price = action_details.get("price", 0.0)
    units = action_details.get("units", 0)
    sl = action_details.get("stop_loss", "未设置")
    tp = action_details.get("take_profit", "未设置")
    tech_reason = action_details.get("technical_reason", "暂无技术面分析")
    macro_ctx = action_details.get("macro_context", "暂无宏观情绪参考")
    confidence = action_details.get("confidence", "待评估")
    
    # 财务风险看板数据
    margin_used = action_details.get("margin_used", 0.0)
    margin_ratio = action_details.get("margin_ratio", 0.0)
    notional = action_details.get("notional_value", 0.0)
    safety_buffer = action_details.get("safety_buffer_pct", "N/A")

    report = f"""
╔══════════════════════════════════════════════════════════════╗
║         🚨 OpenClaw 3.0 — 实盘作战报告                      ║
╠══════════════════════════════════════════════════════════════╣
  📅 时间戳      : {now}
  🎯 操作指令    : {action}
  📊 交易品种    : {instrument}
  💰 执行价格    : {price}
  📦 开仓数量    : {units}
  🏢 名义价值    : ${notional:,.2f}
  🔬 置信度评级  : {confidence}
╠══════════════════════════════════════════════════════════════╣
  💵 保证金占用  : ${margin_used:,.2f}
  📈 保证金占比  : {margin_ratio * 100:.2f}%
  🚧 强平风险垫  : {safety_buffer}% (价格波动空间)
╠══════════════════════════════════════════════════════════════╣
  🛡️  止损参考位  : {sl}
  🎯 止盈目标位  : {tp}
╠══════════════════════════════════════════════════════════════╣
  📐 技术面逻辑支撑:
     {tech_reason}
  🌍 宏观情绪背景:
     {macro_ctx}
╚══════════════════════════════════════════════════════════════╝
"""
    print(report)
    logger.info(f"📡 作战报告已广播 | 操作: {action} | 品种: {instrument}")
    return report


def get_account_summary() -> dict:
    """
    查询当前模拟账户的基本信息，包括账户余额、未实现盈亏和总净值。

    Returns:
        dict: 包含账户摘要的字典，关键字段：
            - balance (float): 当前账户资金余额。
            - unrealized_pnl (float): 当前持仓的未实现盈亏。
            - nav (float): 账户净值 (Net Asset Value)。
            - open_trade_count (int): 当前持仓笔数。
    """
    client, account_id = _get_client()
    r = accounts.AccountSummary(account_id)
    resp = client.request(r)
    acc = resp.get("account", {})
    return {
        "balance": float(acc.get("balance", 0)),
        "unrealized_pnl": float(acc.get("unrealizedPL", 0)),
        "nav": float(acc.get("NAV", 0)),
        "open_trade_count": int(acc.get("openTradeCount", 0))
    }


def get_recent_closed_trades(count: int = 20) -> list[dict]:
    """
    从 OANDA 获取最近已平仓的历史交易记录，供 Agent 自我反思与策略迭代使用。

    Args:
        count (int): 获取最近多少笔交易记录，默认 20 笔，上限 500。

    Returns:
        list[dict]: 交易记录列表，每条包含：
            - trade_id (str): 交易单号。
            - instrument (str): 品种。
            - open_price (float): 开仓价。
            - close_price (float): 平仓价。
            - units (int): 数量（正=多，负=空）。
            - realized_pnl (float): 已实现盈亏（正=盈利，负=亏损）。
            - open_time (str): 开仓时间。
            - close_time (str): 平仓时间。
    """
    client, account_id = _get_client()
    
    params = {"state": "CLOSED", "count": min(count, 500)}
    r = trades.TradesList(account_id, params=params)
    resp = client.request(r)

    result = []
    for t in resp.get("trades", []):
        result.append({
            "trade_id": t.get("id"),
            "instrument": t.get("instrument"),
            "open_price": float(t.get("price", 0)),
            "close_price": float(t.get("averageClosePrice", 0)),
            "units": int(float(t.get("initialUnits", 0))),
            "realized_pnl": float(t.get("realizedPL", 0)),
            "open_time": t.get("openTime", ""),
            "close_time": t.get("closeTime", "")
        })
    return result
