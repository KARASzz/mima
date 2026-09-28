import pytest
from crypto.trajectory_gui import collect_trajectory


def test_collect_trajectory_signature():
    """collect_trajectory 必须返回 list[tuple[float, float]]。"""
    import inspect
    sig = inspect.signature(collect_trajectory)
    assert sig.return_annotation == "list[tuple[float, float]]"


def test_collect_trajectory_can_be_mocked(monkeypatch):
    """可用 mock 跳过 GUI 调用，验证函数可调用。"""
    monkeypatch.setattr("matplotlib.pyplot.show", lambda *a, **kw: None)
    monkeypatch.setattr("matplotlib.pyplot.ginput", lambda *a, **kw: [(0.0, 0.0)] * 20)
    traj = collect_trajectory()
    assert len(traj) >= 10