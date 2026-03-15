import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_mock_klines(n=20) -> pd.DataFrame:
    """
    生成一段包含最近 n 根 K 线的模拟 Pandas DataFrame
    包含字段：datetime, open, high, low, close, volume
    """
    base_time = datetime.now() - timedelta(days=n)
    
    data = []
    current_price = 100.0
    
    # 固定随机种子以保证每次运行测试效果一致，可自行注释掉以观察真实随机
    np.random.seed(42)
    
    for i in range(n):
        dt = base_time + timedelta(days=i)
        
        # 增加一些随机波动
        open_p = current_price + np.random.normal(0, 0.5)
        close_p = open_p + np.random.normal(0, 1)
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 1.0))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 1.0))
        volume = int(np.random.uniform(2000, 5000))
        
        # 针对最后5根K线，故意制造特定的经典形态，方便语义测试
        idx_from_end = n - i
        
        if idx_from_end == 3: # 倒数第三根：缩量十字星
            open_p = current_price
            close_p = current_price + 0.02
            high_p = current_price + 1.0
            low_p = current_price - 0.8
            volume = 800
        elif idx_from_end == 2: # 倒数第二根：长下影线探底针
            open_p = current_price
            close_p = current_price + 0.5
            high_p = close_p + 0.5
            low_p = current_price - 6.0 # 长长下影线
            volume = 4500
        elif idx_from_end == 1: # 最后一根：放量大阳线
            open_p = current_price
            close_p = current_price * 1.06 # 单日大涨6%
            high_p = close_p * 1.01
            low_p = open_p * 0.99
            volume = 12000
            
        # 修正一下上下限，防止某些随机情况下 high 测算出错
        high_p = max(high_p, open_p, close_p)
        low_p = min(low_p, open_p, close_p)
            
        data.append({
            "datetime": dt.strftime("%Y-%m-%d"),
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": volume
        })
        current_price = close_p
        
    df = pd.DataFrame(data)
    return df

class KlineTranslator:
    """
    K 线数据语义翻译器：将标准的 OHLCV 数据框架转换为大语言模型易懂的自然语言。
    """
    def __init__(self):
        pass

    def _analyze_single_kline(self, row: pd.Series, avg_volume: float) -> str:
        """
        分析单根 K 线形态特征并输出简单的标签组合文本
        """
        o, h, l, c, v = row['open'], row['high'], row['low'], row['close'], row['volume']
        
        # 基础计算
        body = c - o
        body_abs = abs(body)
        total_range = h - l if h - l > 0 else 0.0001
        
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        
        # 特征量化
        body_ratio = body_abs / total_range
        upper_ratio = upper_shadow / total_range
        lower_ratio = lower_shadow / total_range
        
        amplitude = total_range / o # 振幅
        
        # —— 形态判断逻辑 ——
        morphology = []
        
        # 1. 实体与涨跌判断
        if amplitude < 0.01 and body_ratio <= 0.2:
            morphology.append("十字星")
        elif body > 0:
            if body_ratio > 0.6 and amplitude > 0.03:
                morphology.append("大阳线")
            elif body_ratio > 0.4:
                morphology.append("阳线")
            else:
                morphology.append("小阳线")
        else:
            if body_ratio > 0.6 and amplitude > 0.03:
                morphology.append("大阴线")
            elif body_ratio > 0.4:
                morphology.append("阴线")
            else:
                morphology.append("小阴线")
                
        # 2. 影线特征
        if lower_ratio > 0.55 and lower_ratio > body_ratio * 1.5:
            morphology.append("长下影线(探底针)")
        if upper_ratio > 0.55 and upper_ratio > body_ratio * 1.5:
            morphology.append("长上影线(避雷针)")
            
        # 3. 成交量特征
        if v > avg_volume * 1.8:
            vol_desc = "放量"
        elif v < avg_volume * 0.6:
            vol_desc = "缩量"
        else:
            vol_desc = "平量"
            
        return f"{vol_desc}{'+'.join(morphology)}"

    def _calculate_trend(self, df: pd.DataFrame) -> str:
        """
        全区段（通常是最近20根）的趋势计算
        """
        if len(df) < 2:
            return "数据不足无法判断"
            
        first_close = df.iloc[0]['close']
        last_close = df.iloc[-1]['close']
        
        high_max = df['high'].max()
        low_min = df['low'].min()
        
        price_change_ratio = (last_close - first_close) / first_close
        
        if price_change_ratio > 0.08:
            return f"显著上涨趋势 (区间涨幅: {price_change_ratio:.2%})"
        elif price_change_ratio < -0.08:
            return f"显著下跌趋势 (区间跌幅: {price_change_ratio:.2%})"
        else:
            if (high_max - low_min) / first_close > 0.15:
                return "宽幅震荡"
            else:
                if price_change_ratio > 0:
                    return "震荡偏上整理"
                else:
                    return "震荡偏下整理"

    def translate_to_prompt(self, df: pd.DataFrame, last_n: int = 5) -> str:
        """
        核心方法：提取最后 N 根 K 线，结合全局上下文，输出清洗的 prompt 文本
        """
        if df.empty:
            return "【提示警告】暂无K线数据。"
            
        trend_desc = self._calculate_trend(df)
        
        # 截取近 N 根
        recent_df = df.tail(last_n)
        
        # 计算全局平均成交量，提供给单根K线判断放缩量
        avg_vol = df['volume'].mean()
        
        kline_descriptions = []
        for i in range(len(recent_df)):
            idx_from_end = len(recent_df) - i # 计算这根是倒数第几根
            row = recent_df.iloc[i]
            
            # 获取基础形态
            desc = self._analyze_single_kline(row, avg_vol)
            
            # 业务增强提示：基于提取的关键形态打点标签，帮助 LLM 从金融角度抓重点
            interpretation = ""
            if "长下影线" in desc:
                interpretation = "，长下影线说明下方存在多头强力护盘与支撑"
            if "长上影线" in desc:
                interpretation = "，长上影线说明上方抛压较重"
            if "大阳线" in desc and "放量" in desc:
                interpretation = "，放量大涨，实体饱满，多头资金强力突破前高"
            if "大阴线" in desc and ("放量" in desc or "阴线" in desc):
                interpretation = "，空头宣泄，跌势凶狠"
            if "十字星" in desc and "缩量" in desc:
                interpretation = "，市场分歧缩小步入观望期，可能面临方向选择"
                
            kline_descriptions.append(
                f"K线-{idx_from_end} [{row['datetime']} / 收盘价 {row['close']}]: 为{desc}{interpretation}"
            )
            
        prompt = (
            f"【全局趋势】近 {len(df)} 根K线总体处于{trend_desc}状态。\n"
            f"【近期形态】最后 {len(recent_df)} 根 K 线的明细特征如下：\n"
        )
        for doc in kline_descriptions:
            prompt += f"- {doc}\n"
            
        return prompt

if __name__ == "__main__":
    print("="*60)
    print(" 步骤一：生成拟合 20 根 K 线的 Mock DataFrame")
    print("="*60)
    mock_df = generate_mock_klines(20)
    print(mock_df.tail(6).to_string(index=False)) # 打印最近几根给开发者核对
    
    print("\n" + "="*60)
    print(" 步骤二：交由 K 线数据语义翻译器处理并输出 LLM 专属 Prompt")
    print("="*60)
    translator = KlineTranslator()
    
    # 提取全局和近5根K线形态
    prompt_text = translator.translate_to_prompt(mock_df, last_n=5)
    print(prompt_text)
