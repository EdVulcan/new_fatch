"""
OpenClaw 3.0 Agent Tools
提供给大语言模型 (LLM) 量化智能体使用的标准化工具库。纯净的 Python 函数形态，依托 Google Style Docstring 规范以便充分被大模型所理解和调用。
"""

from kline_translator import generate_mock_klines, KlineTranslator
from strategy_sandbox import StrategySandbox
import logging

logger = logging.getLogger("AgentTools")

def get_current_market_semantics() -> str:
    """
    获取当前市场行情的自然语言语义描述。

    当需要分析当前市场走势、获取行情全局与微观状态、或者寻找新的交易灵感与形态特征时，必须首先调用此工具获取底层的自然语言数据支持。
    该工具有效地将冰冷抽象的量化形态数据（OHLCV），转换为一份带有明确结论与业务层面解读的研判提示文本。

    Returns:
        str: 行情分析战报。包含一段描述全局行情历史趋势（例如：震荡偏上整理）的文本；
             以及最近几根 K 线十分详尽的明细特征解析（例如：放量大阳线，长下影线探底针护盘，缩量十字星等），
             用于为 LLM 智能体提供精准的下一步操盘灵感。
    """
    # 获取 100 根虚拟 K 线的结构化行情数据
    df_history = generate_mock_klines(100)
    
    # 实例化数据翻译器总线
    translator = KlineTranslator()
    
    # 将标准DataFrame翻译成带有情绪指引和特征浓缩的提示词报告
    # 即便只有最近5根的精细快照，也能够借助第一句总趋势掌握大局观
    semantics_report = translator.translate_to_prompt(df_history, last_n=5)
    
    return semantics_report


def verify_strategy_code(strategy_code_str: str) -> dict:
    """
    在极速的仿真回测沙盒中安全验证交易策略代码的有效性与胜率表现。

    【🚨 严重警告】：严禁直接向主进程或交易路由器输出具有实盘操盘指令的代码段！
    任何基于行情数据获取、分析以及启发灵感后撰写的量化代码逻辑，在提出部署实盘之前，
    必须强制作为此沙盒验证 API 的参数进行全方位的回测与洗礼。

    传入本函数的参数必须是一段包含了主入口判定函数 `evaluate_signal` 的完整纯正且无污染的 Python 脚本。
    签名强制约定为： `def evaluate_signal(df_slice):` -> 根据滑动窗口数据片段返回 bool 值（True 代表在此刻开仓买入）。
    
    如果你写的代码导致异常报错、逻辑卡死或是无法通过裁判标准（胜率过低，盈亏比失衡），沙盒将会进行否决并指点你为何不通过；
    如果你通过了考验，你方可整理上报一份通过报告给系统管理员（人类指战员）。

    Args:
        strategy_code_str (str): 必须是一段携带了 `def evaluate_signal(df_slice):` 函数原型的极简化 Python 逻辑代码字符串。

    Returns:
        dict: 裁判评估委员会的评测回执结果字典，包含以下字段用于判断生死：
            - passed (bool): True 表示该策略击败了所有风控指标及格线，False 则被直接枪毙。
            - win_rate (float): 采用极速平移回测法在最近的历史数据片段中跑出的胜率指标（小数形式）。
            - trades (int): 该段逻辑一共触发了几笔交易。
            - pnl_ratio (float): 该策略在有效周期内的平均盈亏比率值。
            - reason (str): 通过（Perfect）或者被无情否决的具体理由说明（包含编译错误栈或者低劣胜率指标原因），可指引进一步迭代。
    """
    # 实例化自带严苛裁判体系的回测闭环虚拟沙盒
    # 配置: 最少成单不得小于3笔，胜率必须维持 45%+ 以及 1.0 的盈亏比基准线
    sandbox = StrategySandbox(min_trades=3, min_win_rate=0.45, min_pnl_ratio=1.0)
    
    # 使用新的一份独立100根环境数据做背靠背验证
    df_history = generate_mock_klines(100)
    
    try:
        # 使用隔离环境编译这段由野生大模型天马行空撰写的外来危险战略脚本
        # 严格限制作用域并试图抓取约定好的 `evaluate_signal` 对象
        # 如果连名字都写错了，它将抛出错误并在回执中教训提交者
        strategy_func = sandbox.load_strategy(strategy_code_str, func_name="evaluate_signal")
        
        # 将代码与环境历史数据交配滑动遍历（在此演示中：参考以往3根K线去决策，并严格锁仓持有2根K线后释放）
        test_results = sandbox.run_backtest(df_history, strategy_func, window_size=3, hold_bars=2)
        
        # 请裁判团下达处决书或准考证
        decision = sandbox.judge(test_results)
        return decision
        
    except Exception as e:
        # 如果代码逻辑跑挂了（语法错误、超出边界或是压根没有按照要求包装入参）
        # 返回标准的错误信息给回 LLM 使其作为反思和下一次重写的经验（Reflection Loop）
        logger.error(f"⚠️ 工具箱在代执行过程中捕获异常: {e}")
        return {
            'passed': False,
            'win_rate': 0.0,
            'trades': 0,
            'pnl_ratio': 0.0,
            'reason': f"代码注入沙盒执行时发生编译报错或运行时崩溃 (请仔细检查数据切片和索引边界): {str(e)}"
        }
