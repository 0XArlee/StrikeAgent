"""The News Tower's data (phase 2 of the catalysts plan): headlines from free public feeds, classified by a
model (market, category, direction, impact), the price reaction measured on Strike after each one, and a reading per
market like the oil trader's panel (NET with a 6 h half-life, headlines the market rejected count 0.3x, a 60/40 blend
with the last 12 h of high impact, whipsaw, drivers), plus the official calendar and a scoreboard that says whether
the reading predicted anything.

Information for people in the city only: nothing here reaches the agents or changes what they trade (phase 1 measured
that no rule around the scheduled releases improves them, reports/event_study.md).

feeds -> store (sqlite) -> classify -> reaction -> score -> news.json, which the push loops send to the sites.
"""
