
import logging
import agent_tools
from oanda_executor import broadcast_trade_report

logging.basicConfig(level=logging.INFO)

def test_connectivity():
    print("\n" + "="*60)
    print(" 🔍 OANDA 连通性与账户快照测试")
    print("="*60)
    try:
        review = agent_tools.get_performance_review()
        acc = review['account']
        print(f"✅ 成功连接 OANDA！")
        print(f"💰 账户余额: {acc['balance']}")
        print(f"📈 账户净值: {acc['nav']}")
        print(f"📦 当前持仓: {acc['open_trade_count']} 笔")
    except Exception as e:
        print(f"❌ OANDA 连接失败: {e}")

def test_sandbox_gate():
    print("\n" + "="*60)
    print(" 🛡️  安全门控拦截测试 (模拟未通过验证的调用)")
    print("="*60)
    # 模拟一个失败的沙盒裁决
    failed_verdict = {"passed": False, "reason": "胜率过低 (30%)，不符合实盘上线标准"}
    
    result = agent_tools.execute_oanda_trade(
        instrument="XAU_USD",
        units=1,
        side="buy",
        sandbox_verdict=failed_verdict
    )
    
    if not result['success'] and "[GATE_BLOCKED]" in str(result['error']):
        print(f"✅ 拦截成功！门控正常识别并阻止了非法实盘请求。")
        print(f"🚫 拦截反馈: {result['error']}")
    else:
        print(f"❌ 警告：门控未能正确拦截异常请求！")

def test_report_broadcast():
    print("\n" + "="*60)
    print(" 📡 作战报告广播测试")
    print("="*60)
    details = {
        "action": "开多仓 (测试)",
        "instrument": "XAU_USD",
        "price": 2150.45,
        "units": 10,
        "stop_loss": 2140.0,
        "take_profit": 2180.0,
        "technical_reason": "小时线级别放量大阳线突破，站稳支撑位。",
        "macro_context": "市场避险情绪升温，黄金作为避险资产受资金关注。",
        "confidence": "极高 (测试用例)"
    }
    broadcast_trade_report(details)

if __name__ == "__main__":
    test_connectivity()
    test_sandbox_gate()
    test_report_broadcast()
