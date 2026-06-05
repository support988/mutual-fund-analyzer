"""
Yahoo Finance Data Loader for RRG Charts
Fetches free OHLC data using the yfinance library
"""
import logging
from datetime import datetime, timedelta
from typing import Optional  # <-- Added missing import
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class YahooFinanceLoader:
    """
    A class to load Daily, Weekly, or Monthly timeframe data from Yahoo Finance.
    
    Parameters:
    :param config: Configuration dict (kept for compatibility, unused by yfinance)
    :type config: dict
    :param tf: 'daily', 'weekly', or 'monthly'
    :type tf: str
    :param end_date: End date up to which data must be returned
    :type end_date: Optional[datetime]
    :param period: Number of periods to return
    """
    
    def __init__(
        self,
        config: dict = None,
        tf: Optional[str] = "daily",
        end_date: Optional[datetime] = None,
        period: int = 160,
    ):
        self.closed = False
        self.tf = tf if tf else "daily"
        self.end_date = end_date if end_date else datetime.now()
        self.period = period
        logger.info(f"Initialized YahooFinanceLoader with timeframe: {self.tf}")

    def get(self, symbol: str, token: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Returns OHLC data for a symbol as a pandas DataFrame from Yahoo Finance.
        
        :param symbol: Instrument symbol formatted for Yahoo Finance (e.g., 'HDFCBANK.NS' or '^NSEI')
        :param token: Kept for compatibility with the main execution loop, ignored by Yahoo Finance.
        :return: DataFrame with OHLC data
        """
        try:
            # Calculate a generous buffer start date based on the period requested
            if self.tf == "daily":
                days_back = self.period + 50  
            elif self.tf == "weekly":
                days_back = (self.period + 15) * 7
            else:  # monthly
                days_back = (self.period + 12) * 30  
            
            start_date = self.end_date - timedelta(days=days_back)
            
            # Fetch historical data using yfinance
            df = yf.download(
                tickers=symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=self.end_date.strftime("%Y-%m-%d"),
                interval="1d",
                progress=False
            )
            
            if df.empty:
                logger.warning(f"No data returned from Yahoo Finance for {symbol}")
                return None
            
            # If yfinance returns multi-index columns, flatten them
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Ensure index name is set to 'Date'
            df.index.name = 'Date'
            df.sort_index(inplace=True)
            
            # Handle structures to match the specific float expectations of your app
            df_cleaned = pd.DataFrame({
                'Open': df['Open'].astype(float),
                'High': df['High'].astype(float),
                'Low': df['Low'].astype(float),
                'Close': df['Close'].astype(float),
                'Volume': df['Volume'].astype(float) if 'Volume' in df.columns else 0.0
            }, index=df.index)

            # Resample data if a higher timeframe is requested
            if self.tf == "weekly":
                # Resample to weekly candles ending on Friday
                df_weekly = df_cleaned.resample('W-FRI').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
                
                # Drop an incomplete trailing week if necessary
                if len(df_cleaned) > 0 and len(df_weekly) > 0:
                    last_trading_day = df_cleaned.index[-1].normalize()
                    last_weekly_date = df_weekly.index[-1].normalize()
                    if (last_weekly_date - last_trading_day).days > 2:
                        df_weekly = df_weekly.iloc[:-1]
                
                df_cleaned = df_weekly
                
            elif self.tf == "monthly":
                # Resample to monthly (month end)
                df_cleaned = df_cleaned.resample('M').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                }).dropna()

            # Slice data to contain only the exact historical length requested by the RRG algorithm
            if len(df_cleaned) > self.period:
                df_cleaned = df_cleaned.iloc[-self.period:]
            
            if len(df_cleaned) == 0:
                logger.warning(f"No data left after processing/resampling for {symbol}")
                return None
                
            return df_cleaned
            
        except Exception as e:
            logger.error(f"Error loading Yahoo Finance data for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
            
    def close(self):
        """No sessions to close for Yahoo Finance"""
        self.closed = True
        logger.info("YahooFinanceLoader terminated clean.")