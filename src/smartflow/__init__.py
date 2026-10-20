"""Smart Flow Agent.

Independent Python implementation of the Smart Flow Signals [EdgeCraft] indicator (Pine Script v6, see
``SmartFlowSignals.txt`` at the repository root, the immutable reference), its backtester and the Strike Finance
adapter. Layers never import upwards: ``core`` knows nothing about data sources, exchanges or the agent.
"""

ENGINE_VERSION = "1.0.0"  # bump on any change that can alter a signal or a trade
REFERENCE_SCRIPT = "SmartFlowSignals.txt"
REFERENCE_SHA256 = "8e493e64196698b258f24a7bf2c01a2a7f27cafa8c8f159b6ce36c770e0b768d"
