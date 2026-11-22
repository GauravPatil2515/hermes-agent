"""Managed-worker delegation interrupt tests (#158919).

When a managed worker receives a stop frame or the owner process disconnects (EOF/OSError),
in-flight background subagent delegations must receive interrupt signals so they do not
become orphan processes running indefinitely in the worker process tree.
"""
import threading
from types import SimpleNamespace
import pytest


def test_worker_controls_stop_interrupts_async_delegations(monkeypatch):
    from agent.managed_worker import WorkerControls
    import tools.async_delegation as ad

    interrupted = []
    monkeypatch.setattr(ad, "interrupt_all", lambda reason="": (interrupted.append(reason), 1)[1])

    controls = WorkerControls.__new__(WorkerControls)
    controls.stopped = threading.Event()
    controls.agent = None
    controls.lock = threading.Lock()
    controls.clarifications = {}

    controls.stop()
    assert controls.stopped.is_set()
    assert interrupted == ["stop"]


def test_worker_controls_owner_disconnect_interrupts_async_delegations(monkeypatch):
    from agent import managed_worker as mw
    import tools.async_delegation as ad

    interrupted = []
    monkeypatch.setattr(ad, "interrupt_all", lambda reason="": (interrupted.append(reason), 1)[1])
    drained = []
    monkeypatch.setattr(mw, "_drain_background_delegations", lambda budget: drained.append(budget))
    monkeypatch.setattr(mw, "_die_with_owner", lambda: None)

    controls = mw.WorkerControls.__new__(mw.WorkerControls)
    controls.stopped = threading.Event()
    controls.agent = None
    controls.lock = threading.Lock()
    controls.clarifications = {}
    controls.finish = threading.Event()

    def raise_eof(_buf):
        raise EOFError("pipe closed by owner")

    monkeypatch.setattr(mw, "read_frame", raise_eof)

    controls.read()
    assert controls.stopped.is_set()
    assert controls.finish.is_set()
    assert "stop" in interrupted
    assert "owner exit" in interrupted
    assert len(drained) == 1
