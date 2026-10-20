"""Explicit trade lifecycle. A signal is not an order, an accepted order is not a position, a bracket is not a
protection until its stop leg is seen on the exchange. Illegal transitions raise instead of being papered over."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class S(str, Enum):
    SIGNAL_DETECTED = "signal_detected"
    SIGNAL_VALIDATED = "signal_validated"
    REJECTED_BY_RISK = "rejected_by_risk"
    ORDER_PREPARED = "order_prepared"
    PENDING_AUTHORIZATION = "pending_authorization"
    ORDER_SENT = "order_sent"
    PARTIALLY_FILLED = "partially_filled"
    POSITION_OPEN = "position_open"           # filled, protection not yet confirmed
    PROTECTED = "protected"                   # stop (and target) confirmed resting on the exchange
    EXIT_REQUESTED = "exit_requested"
    POSITION_CLOSED = "position_closed"
    CANCELLED = "cancelled"                   # entry never filled / authorization refused / expired
    ERROR = "error"                           # unknown state: no new orders for this market until reconciled
    RECONCILIATION_PENDING = "reconciliation_pending"


TERMINAL = {S.REJECTED_BY_RISK, S.POSITION_CLOSED, S.CANCELLED}

ALLOWED: dict[S, set[S]] = {
    S.SIGNAL_DETECTED: {S.SIGNAL_VALIDATED, S.REJECTED_BY_RISK, S.CANCELLED},
    S.SIGNAL_VALIDATED: {S.ORDER_PREPARED, S.REJECTED_BY_RISK, S.CANCELLED},
    S.ORDER_PREPARED: {S.PENDING_AUTHORIZATION, S.ORDER_SENT, S.CANCELLED},
    S.PENDING_AUTHORIZATION: {S.ORDER_SENT, S.CANCELLED},
    S.ORDER_SENT: {S.PARTIALLY_FILLED, S.POSITION_OPEN, S.PROTECTED, S.CANCELLED, S.ERROR, S.RECONCILIATION_PENDING},
    S.PARTIALLY_FILLED: {S.POSITION_OPEN, S.PROTECTED, S.ERROR, S.RECONCILIATION_PENDING, S.EXIT_REQUESTED},
    S.POSITION_OPEN: {S.PROTECTED, S.EXIT_REQUESTED, S.POSITION_CLOSED, S.ERROR, S.RECONCILIATION_PENDING},
    S.PROTECTED: {S.EXIT_REQUESTED, S.POSITION_CLOSED, S.ERROR, S.RECONCILIATION_PENDING},
    S.EXIT_REQUESTED: {S.POSITION_CLOSED, S.PROTECTED, S.ERROR, S.RECONCILIATION_PENDING},
    S.ERROR: {S.RECONCILIATION_PENDING},
    S.RECONCILIATION_PENDING: {S.POSITION_OPEN, S.PROTECTED, S.POSITION_CLOSED, S.CANCELLED, S.ERROR},
}


class IllegalTransition(RuntimeError):
    pass


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    dir: int
    signal_time: int
    state: S = S.SIGNAL_DETECTED
    history: list[tuple[float, str, str]] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def to(self, new: S, why: str = "") -> None:
        if new == self.state:
            return
        if new not in ALLOWED.get(self.state, set()):
            raise IllegalTransition(f"{self.trade_id}: {self.state.value} -> {new.value} not allowed ({why})")
        self.history.append((time.time(), f"{self.state.value}->{new.value}", why))
        self.state = new

    @property
    def active(self) -> bool:
        return self.state not in TERMINAL

    def to_dict(self) -> dict:
        return {"trade_id": self.trade_id, "symbol": self.symbol, "dir": self.dir, "signal_time": self.signal_time,
                "state": self.state.value, "history": self.history, "data": self.data}

    @classmethod
    def from_dict(cls, d: dict) -> "TradeRecord":
        t = cls(d["trade_id"], d["symbol"], d["dir"], d["signal_time"], S(d["state"]))
        t.history = [tuple(h) for h in d.get("history", [])]
        t.data = d.get("data", {})
        return t
