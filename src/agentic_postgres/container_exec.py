"""Every `docker exec` and every `compose run` this product performs (ADR 0218).

**No product child reads the terminal.** The class was measured on 2026-09-18
(rigs 30a2 and 30b2, Session 30 Run 2) and it is narrower than the shape the
runbooks had been guarding against:

| child reads stdin | `-i` | result under `sudo` with `use_pty` |
|---|---|---|
| no | no | completes |
| no | yes | completes |
| yes | no | completes |
| **yes** | **yes** | **stops** |

Neither `-i` alone nor a reading child alone stops anything, and `docker
compose run` allocates a pseudo-tty but does not itself read the terminal.
What stops is a child that reads stdin having been handed a terminal.

So the rule here is not a guard on the shape a human typed -- that was D972's
repair and it lived on one command out of fifteen. The rule is that **stdin is
closed unless input is supplied**, in which case stdin is a pipe carrying that
input and is never the terminal. A stopped process is one that read a terminal
it was not given; close the stdin and the mechanism is gone rather than
refused.

`-t` is never requested. The one exception in this product is the interactive
`apg dev psql`, which is gated on `sys.stdin.isatty()` and is a developer's
own terminal by design; it builds its argv with `exec_argv(tty=True)` and
hands it to `os.execvp`, never to `run`.
"""

from __future__ import annotations

import subprocess

__all__ = [
    "MIXED_TERMINAL_SHAPE_MESSAGE",
    "compose_run",
    "compose_run_argv",
    "exec_argv",
    "run",
]

#: The sentence `deploy.sh` has refused the mixed terminal shape with since
#: D972, minus the name of the flag it refuses it for. `bin/lib/tty-guard.sh`
#: prints the same words, and a test compares the two, so the shell library and
#: this module cannot drift apart.
MIXED_TERMINAL_SHAPE_MESSAGE = (
    "with stdin at a terminal and stdout or stderr redirected stops at the "
    "first docker exec -i under sudo (D972). Run it unredirected; the terminal "
    "is the log."
)


def exec_argv(
    container: str,
    *argv: str,
    user: str | None = None,
    env_file: str | None = None,
    input_given: bool = False,
    tty: bool = False,
) -> list[str]:
    """The argv for one `docker exec`, and the only place this product builds one.

    ``-i`` appears **exactly when** input will be fed. That is not a style
    preference: `-i` is what connects the child's stdin to this process's, so
    passing it without supplying input is what hands a child the terminal.

    ``tty=True`` is refused together with ``input_given``: a pseudo-terminal
    and a fed stdin are two different stdins, and a caller that wants both has
    not decided what it wants.
    """
    if tty and input_given:
        raise ValueError("a tty and a fed stdin are two different stdins; pass one or the other")
    command = ["docker", "exec"]
    if user is not None:
        command += ["-u", user]
    if env_file is not None:
        command += ["--env-file", env_file]
    if tty:
        command.append("-it")
    elif input_given:
        command.append("-i")
    command.append(container)
    command.extend(argv)
    return command


def run(
    container: str,
    *argv: str,
    input: str | bytes | None = None,
    user: str | None = None,
    env_file: str | None = None,
    timeout: float | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess:
    """One `docker exec`, with the terminal structurally out of reach.

    ``stdin`` is `DEVNULL` unless ``input`` is given, in which case
    `subprocess` supplies a pipe and ``-i`` is on the argv. There is no third
    case, and no argument that reaches an inherited stdin.

    Output is always captured. A caller that needs it uncaptured is
    interactive, and an interactive caller uses `exec_argv` with `os.execvp`.
    """
    return subprocess.run(  # noqa: S603
        exec_argv(
            container,
            *argv,
            user=user,
            env_file=env_file,
            input_given=input is not None,
        ),
        input=input,
        stdin=None if input is not None else subprocess.DEVNULL,
        capture_output=True,
        text=text,
        timeout=timeout,
        check=False,
    )


def compose_run_argv(compose_sh: str, rendered_dir: str, *rest: str) -> list[str]:
    """`bin/compose.sh <rendered> --runtime … run -T …`.

    ``-T`` goes immediately after the ``run`` token -- compose's *disable
    pseudo-tty allocation*. Rig 30b2 measured that compose does not itself read
    the terminal, so this is not what prevents the stop; `stdin=DEVNULL` in
    `compose_run` is. `-T` is here because a pseudo-tty this product never
    wants is one more way for a future child to find one.

    An argv with no ``run`` token is refused rather than passed through: it
    would mean the caller reached this function for something that does not
    start a container, and inserting ``-T`` into it would be a guess.
    """
    rest_list = list(rest)
    if "run" not in rest_list:
        raise ValueError(
            f"compose_run_argv builds a `run` invocation; {rest_list!r} names no run token"
        )
    index = rest_list.index("run")
    rest_list.insert(index + 1, "-T")
    return [compose_sh, rendered_dir, "--runtime", *rest_list]


def compose_run(
    compose_sh: str,
    rendered_dir: str,
    *rest: str,
    timeout: float | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess:
    """One `compose.sh … run`, stdin closed, output captured."""
    return subprocess.run(  # noqa: S603
        compose_run_argv(compose_sh, rendered_dir, *rest),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=text,
        timeout=timeout,
        check=False,
    )
