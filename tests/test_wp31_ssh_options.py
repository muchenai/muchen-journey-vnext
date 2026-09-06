from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_canary_ssh_sessions_use_keepalive_options() -> None:
    workflow = (ROOT / ".github/workflows/wp15-wartime-production.yml").read_text(
        encoding="utf-8"
    )
    workflow = workflow[
        workflow.index("  greenfield_canary:\n") : workflow.index("  operate:\n")
    ]
    blocks: list[str] = []
    current: list[str] = []
    collecting = False
    for line in workflow.splitlines():
        if "opts=(" in line:
            current = [line]
            collecting = True
            if "UserKnownHostsFile" in line:
                blocks.append("\n".join(current))
                current = []
                collecting = False
            continue
        if collecting:
            current.append(line)
            if "UserKnownHostsFile" in line:
                blocks.append("\n".join(current))
                current = []
                collecting = False

    assert blocks
    required = (
        "-o ServerAliveInterval=15",
        "-o ServerAliveCountMax=4",
        "-o TCPKeepAlive=yes",
    )
    for block in blocks:
        for option in required:
            assert option in block, option
