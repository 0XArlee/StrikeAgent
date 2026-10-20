"""
@pyne

Independent re-translation of SmartFlowSignals.txt (lines 72-168: signal section, default inputs) into PyneCore's
Pine-compatible Python, written from the Pine source, NOT from smartflow/core. Run with PyneCore (TradingView-
validated runtime) and compare its plots bar by bar with the engine: `verify_pyne/compare.py`.
Proprietary (c) EdgeCraft - keep private.
"""
from pynecore.lib import *
from pynecore.types import *


@script.indicator("Smart Flow Signals verify", overlay=False)
def main():
    lookN = 20
    rangeMin = 1.0
    bodyMin = 0.6
    volMin = 1.5
    htfSwing = 5
    emaFastN = 100
    emaSlowN = 200

    atr: Series[float] = lib.ta.atr(14)

    def structure():
        ph = lib.ta.pivothigh(lib.high, htfSwing, htfSwing)
        pl = lib.ta.pivotlow(lib.low, htfSwing, htfSwing)
        lastH: Persistent[float] = na
        lastL: Persistent[float] = na
        trd: Persistent[int] = 0
        if not lib.na(ph):
            lastH = ph
        if not lib.na(pl):
            lastL = pl
        if not lib.na(lastH) and lib.close > lastH:
            trd = 1
            lastH = na
        if not lib.na(lastL) and lib.close < lastL:
            trd = -1
            lastL = na
        return trd

    def closedTrend():
        s: Series[int] = structure()
        return s[1]

    htfTrend: Series[int] = lib.request.security(lib.syminfo.tickerid, "240", closedTrend(),
                                                 lookahead=lib.barmerge.lookahead_on)

    hiS: Series[float] = lib.ta.highest(lib.high, lookN)
    loS: Series[float] = lib.ta.lowest(lib.low, lookN)
    hiN = hiS[1]
    loN = loS[1]

    hasVol: Persistent[bool] = False
    if not lib.na(lib.volume) and lib.volume > 0:
        hasVol = True
    vol: Series[float] = lib.volume if hasVol else na
    volAv = lib.ta.sma(vol, 20)

    emaF = lib.ta.ema(lib.close, emaFastN)
    emaS = lib.ta.ema(lib.close, emaSlowN)
    emaTrend = 1 if emaF > emaS else (-1 if emaF < emaS else 0)

    mfSrc: Series[float] = lib.hlc3
    mfRaw = mfSrc * vol
    mfPos = lib.math.sum(mfRaw if mfSrc >= mfSrc[1] else 0.0, 14)
    mfNeg = lib.math.sum(mfRaw if mfSrc < mfSrc[1] else 0.0, 14)
    mfi = 100 - 100 / (1 + mfPos / mfNeg) if mfNeg != 0 else 100.0
    mfMult = ((lib.close - lib.low) - (lib.high - lib.close)) / (lib.high - lib.low) if lib.high != lib.low else 0.0
    volAv21 = lib.ta.sma(vol, 21)
    mfvAv21 = lib.ta.sma(mfMult * vol, 21)
    cmf = mfvAv21 / volAv21 if volAv21 != 0 else 0.0
    volW = lib.math.log((vol / volAv21 if volAv21 != 0 else 1.0) + 1)
    mfEma = lib.ta.ema(mfSrc, 10)
    mfDev = lib.ta.ema(lib.math.abs(mfSrc - mfEma), 10)
    mfCi = (mfSrc - mfEma) / (0.015 * mfDev) * (1 + volW * 0.5) if mfDev != 0 else 0.0
    flow: Series[float] = lib.ta.ema(mfCi, 21) * 0.5 + cmf * 100 * 0.3 + (mfi - 50) * 1.2 * 0.2

    rng = lib.high - lib.low
    body = lib.math.abs(lib.close - lib.open)
    disp = not lib.na(atr) and rng >= rangeMin * atr and body >= bodyMin * rng
    volOk = volMin == 0 or lib.na(vol) or (not lib.na(volAv) and vol >= volMin * volAv)
    relVol = na if (lib.na(volAv) or volAv == 0) else vol / volAv
    rawBuy = disp and lib.close > lib.open and not lib.na(hiN) and lib.close > hiN
    rawSell = disp and lib.close < lib.open and not lib.na(loN) and lib.close < loN
    stUp = htfTrend == 1
    stDn = htfTrend == -1
    sigRaw = ((1 if (rawBuy and stUp) else (-1 if (rawSell and stDn) else 0))
              if (lib.barstate.isconfirmed and volOk) else 0)

    lib.plot.plot(sigRaw, "Signal")
    lib.plot.plot(htfTrend, "HTF trend")
    lib.plot.plot(relVol, "Relative volume")
    lib.plot.plot(flow, "Money flow")
    lib.plot.plot(emaTrend, "EMA trend")
    lib.plot.plot(emaF, "Fast EMA")
    lib.plot.plot(emaS, "Slow EMA")
