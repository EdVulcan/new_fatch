
import agent_tools
from risk_manager import calculate_position_size

def test_risk_logic():
    print("\n" + "="*60)
    print(" 🛡️  Risk Manager 核心逻辑单元测试")
    print("="*60)
    
    # 模拟场景 1: 正常黄金交易
    # 净值 100,000, 风险 1%, 金价 2150, 止损 2140 (间距 10)
    # 期望: units = (100,000 * 0.01) / 10 = 100
    u1 = calculate_position_size(100000, 0.01, 2140, 2150, "XAU_USD")
    print(f"📊 黄金测试 (1%风险): 计算单位={u1} | 预期=100")

    # 模拟场景 2: 触发杠杆保护 (止损极其窄的情况)
    # 净值 10,000, 风险 2%, 止损间距 0.1
    # 计算风险金 200 / 0.1 = 2000 单位
    # 名义价值 2000 * 2150 = 4,300,000
    # 20倍杠杆上限 = 10,000 * 20 = 200,000
    # 强制截断单位 = 200,000 / 2150 ≈ 93
    u2 = calculate_position_size(10000, 0.02, 2149.9, 2150, "XAU_USD")
    print(f"📊 杠杆保护测试: 计算单位={u2} | 预期应该被截断 (远小于 2000)")

    # 模拟场景 3: 外汇测试
    # 净值 50,000, 风险 1%, 止损间距 0.0050 (50 pips)
    # 期望: (50,000 * 0.01) / 0.0050 = 500 / 0.005 = 100,000
    u3 = calculate_position_size(50000, 0.01, 1.0850, 1.0900, "EUR_USD")
    print(f"📊 外汇测试 (1.09入场, 50点止损): 计算单位={u3} | 预期=100000")

def test_agent_tool_integration():
    print("\n" + "="*60)
    print(" 🛠️  Risk Manager & Report 整合连通性测试")
    print("="*60)
    try:
        # 1. 计算仓位 (包含保证金数据)
        risk_report = agent_tools.get_safe_position_size(
            risk_level=0.01,
            stop_loss_price=2140,
            entry_price=2150,
            instrument="XAU_USD"
        )
        print(f"📈 仓位计算详情: {risk_report}")
        
        # 2. 模拟生成作战报告
        report_details = {
            "action": "开多仓 (财务测试)",
            "instrument": "XAU_USD",
            "price": 2150.45,
            "units": risk_report['final_units'],
            "stop_loss": 2140.0,
            "take_profit": 2180.0,
            "technical_reason": "保证金指标压力测试报告。",
            "macro_context": "测试财务风险看板是否正确显示数据。",
            "confidence": "极高",
            **risk_report  # 解构注入财务字段
        }
        
        report_text = agent_tools.broadcast_trade_report(report_details)
        print(report_text)
        
    except Exception as e:
        print(f"❌ 整合测试失败: {e}")

if __name__ == "__main__":
    test_risk_logic()
    test_agent_tool_integration()
