from stock_dashboard.engine.config_loader import Config

_SP500 = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","BRK-B","LLY","AVGO",
    "JPM","TSLA","UNH","V","XOM","MA","JNJ","PG","HD","COST","MRK","ABBV",
    "CVX","CRM","BAC","NFLX","KO","PEP","TMO","WMT","ACN","MCD","CSCO","ABT",
    "LIN","ADBE","AMD","TXN","DHR","PM","NEE","CMCSA","WFC","RTX","IBM","INTC",
    "QCOM","AMGN","CAT","NOW","GE","HON","SPGI","ISRG","SYK","BKNG","GS","MS",
    "T","VRTX","PANW","AMAT","UNP","DE","AXP","LOW","BLK","SCHW","MDT","ADI",
    "TJX","CI","ELV","MMM","ZTS","MO","DUK","SO","C","USB","BMY","BSX","CB",
    "SHW","REGN","ICE","AON","HCA","MDLZ","ITW","PLD","COP","EOG","SLB","PSX",
    "VLO","MPC","OXY","HAL","DVN","FCX","NEM","APD","LMT","GD","BA","NOC",
    "TDG","WM","RSG","CTAS","FAST","CME","CBOE","MCO","MSCI","FIS","FISV",
    "PYPL","DIS","PH","EMR","ROK","ETN","AWK","AEE","WEC","EXC","AEP","D",
    "CVS","MCK","HUM","CNC","PFE","GILD","BIIB","ILMN","IQV","DXCM",
    "AMT","CCI","EQIX","PSA","SPG","O","NKE","LULU","STZ","MNST","KDP","KHC",
    "GIS","TSN","NTAP","JKHY",
]

_NDX100 = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","ASML",
    "COST","NFLX","AMD","ADBE","QCOM","INTU","AMAT","ISRG","TXN","BKNG",
    "CMCSA","PANW","SBUX","VRTX","LRCX","KLAC","MDLZ","SNPS","CDNS","REGN",
    "MAR","MELI","CTAS","ABNB","CSX","FTNT","ORLY","PCAR","MRNA","CRWD",
    "ROP","MNST","PAYX","WDAY","ROST","ODFL","CPRT","MCHP","FAST","IDXX",
    "DXCM","BIIB","AEP","CTSH","DLTR","EXC","XEL","ALGN","ENPH","ZS",
    "DDOG","TEAM","MDB","SNOW","NET","TTD","ROKU","ETSY","UBER","DASH","COIN",
    "PDD","JD","BIDU","LI","NIO",
]

def get_universe(cfg: Config) -> list[str]:
    tickers: set[str] = set()
    if cfg.universe.get("include_sp500", True):
        tickers.update(_SP500)
    if cfg.universe.get("include_ndx100", True):
        tickers.update(_NDX100)
    tickers.update(cfg.universe.get("extra_tickers", []))
    return sorted(tickers)
