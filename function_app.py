import azure.functions as func
import logging
import json
import os
from datetime import datetime
import yfinance as yf
from openai import AzureOpenAI

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

STOCKS = ["AAPL", "TSLA", "NVDA", "MSFT", "GOOGL"]


def get_stock_data(symbol: str) -> dict:
    stock = yf.Ticker(symbol)
    info = stock.info

    hist = stock.history(period="3mo")
    current_price = round(hist['Close'].iloc[-1], 2)
    price_1mo_ago = hist['Close'].iloc[-22] if len(hist) >= 22 else hist['Close'].iloc[0]
    price_change_1mo = round(((current_price - price_1mo_ago) / price_1mo_ago) * 100, 2)

    try:
        news = stock.news[:5] if stock.news else []
        news_titles = [n.get('content', {}).get('title', '') if isinstance(n.get('content'), dict) else n.get('title', '') for n in news]
    except Exception:
        news_titles = []

    try:
        recs = stock.recommendations
        latest_recs = recs.tail(5).to_dict('records') if recs is not None and not recs.empty else []
    except Exception:
        latest_recs = []

    return {
        "symbol": symbol,
        "company_name": info.get('longName', symbol),
        "current_price": current_price,
        "price_change_1mo_pct": price_change_1mo,
        "market_cap": info.get('marketCap', 'N/A'),
        "pe_ratio": info.get('trailingPE', 'N/A'),
        "forward_pe": info.get('forwardPE', 'N/A'),
        "revenue_growth": info.get('revenueGrowth', 'N/A'),
        "profit_margins": info.get('profitMargins', 'N/A'),
        "analyst_target_price": info.get('targetMeanPrice', 'N/A'),
        "recommendation_mean": info.get('recommendationMean', 'N/A'),
        "recent_news": news_titles,
        "analyst_recommendations": latest_recs,
    }


def analyze_with_gpt(stocks_data: list) -> str:
    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2025-04-01-preview",
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
    )

    stocks_json = json.dumps(stocks_data, ensure_ascii=False, indent=2, default=str)

    prompt = f"""你是一位專業的美股分析師。請根據以下股票數據進行分析並給出投資建議。

股票數據：
{stocks_json}

請針對每支股票提供：
1. 投資建議（買入 / 持有 / 賣出）
2. 主要優勢（2-3點）
3. 主要風險（2-3點）
4. 目標價格預估
5. 綜合評分（1-10分）

最後提供整體市場觀察與優先推薦順序。
請以繁體中文回答，格式清晰易讀。"""

    response = client.chat.completions.create(
        model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-pro"),
        messages=[
            {"role": "system", "content": "你是一位擁有20年經驗的美股分析師，擅長技術分析、基本面分析、財報解讀與市場情緒判斷。"},
            {"role": "user", "content": prompt}
        ],
        max_tokens=4000,
        temperature=0.3
    )

    return response.choices[0].message.content


@app.route(route="analyze")
def analyze(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Stock analysis triggered")

    try:
        stocks_data = []
        for symbol in STOCKS:
            logging.info(f"Fetching data for {symbol}")
            stocks_data.append(get_stock_data(symbol))

        logging.info("Sending to GPT for analysis...")
        analysis = analyze_with_gpt(stocks_data)

        result = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "stocks_analyzed": STOCKS,
            "analysis": analysis
        }

        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )
