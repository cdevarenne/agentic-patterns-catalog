from agentic_patterns_catalog import cli


def test_help_lists_subcommands(capsys) -> None:
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "catalog" in out


def test_unknown_subcommand_is_usage_error() -> None:
    assert cli.main(["does-not-exist"]) == 2
