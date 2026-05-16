"""Chart rendering."""

from trading_bot.render.charts import render_market_chart
from trading_bot.render.theme import DARK_THEME, apply_dark_theme

__all__ = ["DARK_THEME", "apply_dark_theme", "render_market_chart"]
