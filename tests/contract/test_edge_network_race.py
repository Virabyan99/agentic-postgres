"""The edge's attach race (Session 42, D2558, D2563).

Two systemd units attach the shared edge proxy at boot -- a project's unit
(`ExecStartPost ... attach`, `... edge reconcile`) and the edge's own
(`ExecStartPost ... reconcile`). Each checks `is_attached`, finds it false, and
connects; the loser's `docker network connect` fails with Docker's *already
exists*, and before this repair it took that as failure (`die 9`) and systemd
took the project down -- beta-dev's unit at Session 41's boot.

The repair: every connect and disconnect goes through two helpers that, after
a failed call, read the network again and succeed when the wanted state holds.
Docker's texts are rig 42c's (Session 42 Run 1, Docker 29.5.2):
``endpoint with name <container> already exists in network <net>`` and
``container <id> is not connected to network <net>``.

The fake `docker` keeps its state in files: a lost race RECORDS the other
unit's work and THEN fails with Docker's text, which is the order the real
race has.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.p0]

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "bin" / "edge-network.sh"
EDGE = "apg-edge-traefik-1"
ALIAS = "apg-edge-proxy"

FAKE_DOCKER = r"""#!/usr/bin/env bash
# State: $FAKE_STATE/networks (one network per line, ":branch" suffix for a branch
# network) and $FAKE_STATE/attached (one "<network>" per line, alias implied).
# $FAKE_CONNECT / $FAKE_DISCONNECT: ok (default) | race | fail.
S="$FAKE_STATE"
touch "$S/attached"
case "$1 $2" in
  "ps --filter"|"ps -a") echo "apg-edge-traefik-1"; exit 0 ;;
esac
if [ "$1" = ps ]; then echo "apg-edge-traefik-1"; exit 0; fi
if [ "$1" = inspect ]; then
  format="$3"
  case "$format" in
    *'"Aliases"'*)
      net="$(printf '%s' "$format" | sed -E 's/.*Networks "([^"]+)".*/\1/')"
      grep -qx "$net" "$S/attached" && echo "[apg-edge-proxy]" && exit 0
      echo "<no value>"; exit 0 ;;
    *)
      printf '{'; sep=""
      while read -r n; do
        [ -n "$n" ] && printf '%s"%s":{}' "$sep" "$n" && sep=","
      done < "$S/attached"
      printf '}\n'; exit 0 ;;
  esac
fi
if [ "$1" = network ]; then
  case "$2" in
    inspect)
      net="${@: -1}"
      line="$(grep -E "^${net}(:branch)?$" "$S/networks")" \
        || { echo "Error: No such network: $net" >&2; exit 1; }
      case "$*" in
        *apg.branch.edge*) case "$line" in *:branch) echo true ;; *) echo "<no value>" ;; esac ;;
      esac
      exit 0 ;;
    ls)
      grep ':branch$' "$S/networks" | sed 's/:branch$//'; exit 0 ;;
    connect)
      net="${@: -2:1}"; container="${@: -1}"
      echo "connect $net" >> "$S/calls"
      case "${FAKE_CONNECT:-ok}" in
        race) grep -qx "$net" "$S/attached" || echo "$net" >> "$S/attached"
              echo "Error response from daemon: endpoint with name $container" \
                "already exists in network $net" >&2; exit 1 ;;
        fail) echo "Error response from daemon: network $net not found" >&2; exit 1 ;;
        *) echo "$net" >> "$S/attached"; exit 0 ;;
      esac ;;
    disconnect)
      net="$3"
      echo "disconnect $net" >> "$S/calls"
      case "${FAKE_DISCONNECT:-ok}" in
        race) grep -vx "$net" "$S/attached" > "$S/a.tmp"; mv "$S/a.tmp" "$S/attached"
              id=556b940283995faa73c7b4fb6d25779c46bb6d888a685d04db17999e9e58a622
              echo "Error response from daemon: container $id is not connected to network $net" >&2
              exit 1 ;;
        fail) echo "Error response from daemon: cannot disconnect: the daemon is shutting down" >&2
              exit 1 ;;
        *) grep -vx "$net" "$S/attached" > "$S/a.tmp"; mv "$S/a.tmp" "$S/attached"; exit 0 ;;
      esac ;;
  esac
fi
echo "fake docker: unhandled: $*" >&2
exit 99
"""


def _setup(
    tmp_path: Path,
    projects: tuple[str, ...],
    branches: tuple[str, ...] = (),
    attached: tuple[str, ...] = (),
) -> tuple[Path, Path, Path]:
    bin_dir, state, rendered = tmp_path / "bin", tmp_path / "state", tmp_path / "rendered"
    for directory in (bin_dir, state, rendered):
        directory.mkdir()
    (bin_dir / "docker").write_text(FAKE_DOCKER, encoding="utf-8")
    (bin_dir / "id").write_text("#!/bin/sh\necho 0\n", encoding="utf-8")
    for tool in ("docker", "id"):
        (bin_dir / tool).chmod(0o755)
    networks = []
    for key in projects:
        (rendered / key).mkdir()
        (rendered / key / "compose.env").write_text(
            f"EDGE_NETWORK_NAME=apg-{key}-edge\n", encoding="utf-8"
        )
        networks.append(f"apg-{key}-edge")
    networks += [f"{name}:branch" for name in branches]
    (state / "networks").write_text("".join(f"{n}\n" for n in networks), encoding="utf-8")
    (state / "attached").write_text("".join(f"{n}\n" for n in attached), encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    old = 'readonly PROJECT_RENDERED_ROOT="/var/lib/agentic-postgres/rendered"'
    assert script.count(old) == 1, old
    copy = tmp_path / "edge-network.sh"
    copy.write_text(
        script.replace(old, f'readonly PROJECT_RENDERED_ROOT="{rendered}"'), encoding="utf-8"
    )
    return copy, bin_dir, state


def _run(
    copy: Path,
    bin_dir: Path,
    state: Path,
    *arguments: str,
    connect: str = "ok",
    disconnect: str = "ok",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(copy), *arguments],
        capture_output=True, text=True, check=False,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "FAKE_STATE": str(state),
             "FAKE_CONNECT": connect, "FAKE_DISCONNECT": disconnect},
    )  # fmt: skip


def _attached(state: Path) -> set[str]:
    return {line for line in (state / "attached").read_text(encoding="utf-8").splitlines() if line}


def test_an_attach_lost_to_another_unit_succeeds(tmp_path: Path) -> None:
    """`attach`'s connect loses to another unit: the network is read again,
    the proxy IS attached with its alias, so the unit succeeds (D2558)."""
    copy, bin_dir, state = _setup(tmp_path, ("beta-dev",))
    done = _run(copy, bin_dir, state, "attach", "--project-key", "beta-dev", connect="race")
    assert done.returncode == 0, done.stderr
    assert "already attached by another unit" in done.stderr
    assert _attached(state) == {"apg-beta-dev-edge"}


def test_an_attach_network_lost_to_another_unit_succeeds(tmp_path: Path) -> None:
    """The same for a branch's network (`attach-network`, ADR 0271)."""
    copy, bin_dir, state = _setup(tmp_path, (), branches=("apg-slot3-prod_dev-edge",))
    done = _run(copy, bin_dir, state, "attach-network", "apg-slot3-prod_dev-edge", connect="race")
    assert done.returncode == 0, done.stderr
    assert "already attached by another unit" in done.stderr


def test_a_reconcile_lost_to_another_unit_succeeds(tmp_path: Path) -> None:
    """`reconcile` loses every connect -- two projects and a branch -- and
    succeeds: each network is attached by the time it reads again."""
    copy, bin_dir, state = _setup(
        tmp_path, ("alpha-dev", "beta-dev"), branches=("apg-slot3-prod_dev-edge",)
    )
    done = _run(copy, bin_dir, state, "reconcile", connect="race")
    assert done.returncode == 0, done.stderr
    assert _attached(state) == {
        "apg-alpha-dev-edge",
        "apg-beta-dev-edge",
        "apg-slot3-prod_dev-edge",
    }
    assert done.stderr.count("already attached by another unit") == 3, done.stderr


def test_a_detach_lost_to_another_unit_succeeds(tmp_path: Path) -> None:
    """`detach` and `detach-network` lose their disconnect to another unit:
    read again, not attached, done."""
    copy, bin_dir, state = _setup(tmp_path, ("beta-dev",), attached=("apg-beta-dev-edge",))
    done = _run(copy, bin_dir, state, "detach", "--project-key", "beta-dev", disconnect="race")
    assert done.returncode == 0, done.stderr
    assert "already detached by another unit" in done.stderr
    assert _attached(state) == set()
    branch_root = tmp_path / "branch"
    branch_root.mkdir()
    copy, bin_dir, state = _setup(
        branch_root,
        (),
        branches=("apg-slot3-prod_dev-edge",),
        attached=("apg-slot3-prod_dev-edge",),
    )
    done = _run(
        copy, bin_dir, state, "detach-network", "apg-slot3-prod_dev-edge", disconnect="race"
    )
    assert done.returncode == 0, done.stderr
    assert "already detached by another unit" in done.stderr


@pytest.mark.parametrize(
    ("arguments", "projects", "branches", "attached", "connect", "disconnect"),
    [
        (("attach", "--project-key", "beta-dev"), ("beta-dev",), (), (), "fail", "ok"),
        (
            ("attach-network", "apg-slot3-prod_dev-edge"),
            (),
            ("apg-slot3-prod_dev-edge",),
            (),
            "fail",
            "ok",
        ),
        (("reconcile",), ("beta-dev",), (), (), "fail", "ok"),
        (
            ("detach", "--project-key", "beta-dev"),
            ("beta-dev",),
            (),
            ("apg-beta-dev-edge",),
            "ok",
            "fail",
        ),
        (
            ("detach-network", "apg-slot3-prod_dev-edge"),
            (),
            ("apg-slot3-prod_dev-edge",),
            ("apg-slot3-prod_dev-edge",),
            "ok",
            "fail",
        ),
    ],
    ids=["attach", "attach-network", "reconcile", "detach", "detach-network"],
)
def test_any_other_failure_exits_nine(
    tmp_path: Path, arguments, projects, branches, attached, connect, disconnect
) -> None:  # type: ignore[no-untyped-def]
    """The control: a connect or disconnect that fails and leaves the wanted
    state NOT holding is still exit 9, naming Docker's text."""
    copy, bin_dir, state = _setup(tmp_path, projects, branches=branches, attached=attached)
    done = _run(copy, bin_dir, state, *arguments, connect=connect, disconnect=disconnect)
    assert done.returncode == 9, (done.returncode, done.stderr)
    assert "Error response from daemon" in done.stderr, done.stderr


def test_a_clean_attach_and_detach_say_nothing_of_another_unit(tmp_path: Path) -> None:
    """The ordinary path is unchanged: connect succeeds, no re-read line."""
    copy, bin_dir, state = _setup(tmp_path, ("beta-dev",))
    done = _run(copy, bin_dir, state, "attach", "--project-key", "beta-dev")
    assert done.returncode == 0, done.stderr
    assert "another unit" not in done.stderr
    assert _attached(state) == {"apg-beta-dev-edge"}
    done = _run(copy, bin_dir, state, "detach", "--project-key", "beta-dev")
    assert done.returncode == 0, done.stderr
    assert _attached(state) == set()


def _function_bodies(text: str, names: tuple[str, ...]) -> list[str]:
    """The text of each named shell function, `name() {` to the first `}` at column 0."""
    bodies = []
    for name in names:
        match = re.search(rf"^{name}\(\) \{{\n(.*?)^\}}", text, re.M | re.S)
        assert match, f"{name}() not found in {SCRIPT.name}"
        bodies.append(match.group(0))
    return bodies


def test_every_connect_goes_through_the_helper() -> None:
    """The class guard (D600): `docker network connect` and `docker network
    disconnect` appear in the script ONLY inside `connect_alias` and
    `disconnect_quiet` -- a new site that called Docker directly would bring
    the race back."""
    text = SCRIPT.read_text(encoding="utf-8")
    connect, disconnect = _function_bodies(text, ("connect_alias", "disconnect_quiet"))
    outside = text.replace(connect, "").replace(disconnect, "")
    code = [line for line in outside.splitlines() if not line.lstrip().startswith("#")]
    offenders = [line for line in code if re.search(r"docker network (dis)?connect\b", line)]
    assert offenders == [], offenders
    assert "docker network connect" in connect and "docker network disconnect" in disconnect
