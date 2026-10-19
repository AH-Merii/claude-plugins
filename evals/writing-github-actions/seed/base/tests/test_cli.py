import io
import sys

from wordstat.cli import main


def test_prints_counts_tab_separated(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("x y x"))
    assert main(["1"]) == 0
    assert capsys.readouterr().out == "2\tx\n"
