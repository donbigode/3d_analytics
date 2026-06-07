"""Trend radar domain: scoring + source adapters.

Pure (scoring) and adapter (sources/) layers. Adapters do I/O but isolate it so
the scheduler can plug them in; tests monkeypatch them.
"""
