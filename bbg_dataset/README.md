# Bloomberg HSI dataset (pulled 17–18 Sep 2026, HKUST library terminal)

Personal research use only — do not redistribute raw data (Bloomberg licence).

| File | Rows | What |
|---|---|---|
| prices_daily.parquet / .csv | 217k | 95 HSI members × 2016-01-04..2026-09-18: close (adj), volume, tri (total-return index), mktcap |
| fundamentals_semiannual.* | 1,943 | per stock per H1/FY: revenue, net_income, eps, bvps, cfo, total_debt, roe, shares_out + **announce_date** (point-in-time key; `announce_date_est=True` = fallback period_end+90d) |
| earnings_dates.csv | 9,870 | every announcement date + fiscal period per stock |
| dividends.csv | 3,417 | declared/ex/pay dates, amount, freq, type |
| macro_series.* / macro_wide.csv | 104k | 47 series: HK/US/CN rates, FX, commodities, global indices, VHSI, VIX, monthly macro |
| static_snapshot.csv | 95 | name, GICS sector, mktcap, shares, PE, PB, div yield, ISIN (as of 18 Sep 2026) |
| members_HSI.csv | 95 | current HSI constituents |

Caveats: universe = *today's* HSI members (survivorship bias; historical weights sheet failed, re-pull next session). Fundamentals are semi-annual. Some series have gaps (#N/A) where the field does not apply.

Scripts: `build_dataset.py` (xlsx → parquet), `factor_test.py` (momentum/value quintile test).
