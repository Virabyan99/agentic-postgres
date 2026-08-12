#!/usr/bin/env python
"""Derive the verification-only JWKS from the bootstrap signing key.

ADR 0051 says PostgREST receives a JWKS **derived** from the private key rather
than a stored public copy: one value, one derivation, and nothing that can drift
from the key it claims to describe. This is that derivation.

**Public material, and stored as such.** The output is a modulus, an exponent, an
algorithm and an RFC 7638 thumbprint -- everything a verifier is entitled to hold
and nothing that can sign. It is written world-readable on purpose: a 0400 file
would imply a confidentiality this content does not have, and the next reader
would have to work out whether that was meaningful. The *private* key it comes
from stays 0400 root in the root plane, which is what makes "no service holds
it" a filesystem fact (ADR 0054).

**The public half is derived first, and only that is read.** The obvious
spelling -- `openssl rsa -in <private> -noout -text` -- prints `privateExponent`,
`prime1`, `prime2` and the coefficient. Measured, with a control proving the
search finds them when they are present. `-noout` suppresses the *re-encoded
key*, not the text dump, and a comment claiming otherwise is how private key
material ends up in a captured stdout, a traceback or a log.

So this runs `-pubout` first and reads the modulus and exponent from the public
key over a pipe. The second invocation never sees a private parameter, and
`test_the_derivation_never_reads_private_material` asserts the spelling rather
than the intention. `src/agentic_postgres/jwt_keys.py` builds the JWK from those
two numbers and states that it never runs a subprocess and never touches a key
file; the subprocess is here.

Exit codes (runbook section 2 convention):
  0  the JWKS was written, or was already current
  2  invalid operator input
  3  missing local prerequisite, or not root
  5  the deployed state or the signing key is unusable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agentic_postgres import jwt_keys, secrets_contract
from agentic_postgres.secret_generation import SECRET_ROOT

#: The root-plane file the signing key is materialized into (ADR 0054, 0055).
SIGNING_KEY_FILE = "bootstrap_jwt_signing_key.pem"

#: Where the rendered JWKS lands, and the name PostgREST is configured to read.
#: The container path is project-neutral, which is why `compose.yaml` can carry
#: `PGRST_JWT_SECRET` while the host path stays in the per-project override.
JWKS_FILENAME = "jwks.json"

#: World-readable. See the module docstring: this is public verification
#: material, and the container reads it as uid 65532.
JWKS_MODE = 0o444

#: `openssl rsa -noout -text` prints this line for the public exponent.
_EXPONENT = re.compile(r"^\s*(?:publicExponent|Exponent):\s*(\d+)\s*\(0x[0-9a-fA-F]+\)\s*$")


class JwksError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def signing_key_path(project_key: str, generation: str) -> Path:
    path = (
        SECRET_ROOT
        / project_key
        / "generations"
        / generation
        / secrets_contract.ROOT_PLANE_DIRECTORY
        / SIGNING_KEY_FILE
    )
    if not path.is_file():
        raise JwksError(
            5,
            f"no signing key at {path}. The bootstrap issuer's key is materialized into "
            "the root plane by the deploy; a project deployed before session 5 has none.",
        )
    return path


def _run(command: list[str], *, stdin: bytes | None = None) -> bytes:
    """Run one openssl invocation.

    `stderr` is deliberately not echoed on failure: openssl names the key's path
    and, on some failures, prints material from it.
    """
    result = subprocess.run(command, input=stdin, capture_output=True, check=False, timeout=60)
    if result.returncode != 0:
        raise JwksError(5, f"openssl failed: {' '.join(command[:4])}")
    return result.stdout


def public_key_pem(key_path: Path) -> bytes:
    """The public half of the signing key, in memory.

    Derived rather than stored. ADR 0051's "one stored value and one derivation"
    is the reason there is no public PEM anywhere on disk to go stale against the
    private one.
    """
    return _run(["openssl", "rsa", "-in", str(key_path), "-pubout"])


def read_public_parameters(key_path: Path) -> tuple[str, int]:
    """The modulus and the public exponent, from the public key only.

    Both invocations take the public PEM on **stdin**, so no private parameter
    is ever in this process's memory and no temporary file holds one.

    Reading the exponent from `-text` is unavoidable -- openssl has no
    `-exponent` flag -- so the line is matched against an anchored pattern and a
    miss is an error rather than a default of 65537. A default would be a guess
    wearing the shape of a measurement, and it would be right for every key this
    project generates, which is exactly what would keep it from being noticed.

    The label differs between the two paths: a private key prints
    `publicExponent: 65537 (0x10001)` and a public one prints
    `Exponent: 65537 (0x10001)`. Both are accepted, measured rather than assumed,
    with a `-3` key as the control that the number is read rather than defaulted.
    """
    public = public_key_pem(key_path)

    modulus = _run(["openssl", "rsa", "-pubin", "-noout", "-modulus"], stdin=public)
    modulus_text = modulus.decode("ascii", "replace").strip()

    described = _run(["openssl", "rsa", "-pubin", "-noout", "-text"], stdin=public)
    for line in described.decode("ascii", "replace").splitlines():
        matched = _EXPONENT.match(line)
        if matched:
            return modulus_text, int(matched.group(1))

    raise JwksError(
        5,
        "openssl printed no public exponent line for this key. The JWKS is not written "
        "from a default: 65537 is what every key this project generates uses, and "
        "assuming it here would publish an exponent nobody read.",
    )


def build(project_key: str, generation: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the JWKS and the single public JWK it contains."""
    modulus, exponent = read_public_parameters(signing_key_path(project_key, generation))
    jwk = jwt_keys.public_jwk(modulus_hex=modulus, exponent=exponent)
    # One key. A rotation publishes two and is Run 10's; `build_jwks` enforces
    # the ceiling and every other rule, so nothing about that is restated here.
    return jwt_keys.build_jwks([jwk]), jwk


def write(document: dict[str, Any], destination: Path) -> bool:
    """Write the JWKS if it differs. Returns whether anything changed.

    Byte-compared rather than rewritten unconditionally: the file's mtime is the
    only signal a reader has that a rotation happened, and a deploy that rewrote
    an identical file on every run would destroy it.
    """
    payload = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if destination.is_file() and destination.read_bytes() == payload:
        destination.chmod(JWKS_MODE)
        return False

    # Written beside the target and renamed, so a container starting during the
    # write never opens a partial key set.
    staging = destination.with_suffix(".json.staging")
    staging.write_bytes(payload)
    staging.chmod(JWKS_MODE)
    staging.replace(destination)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="render-jwks",
        description="Derive the verification-only JWKS from the bootstrap signing key.",
        allow_abbrev=False,
    )
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--generation", required=True, metavar="ID")
    parser.add_argument("--rendered-dir", required=True, type=Path, metavar="DIR")

    arguments = parser.parse_args(argv)

    try:
        if os.geteuid() != 0:
            raise JwksError(
                3,
                "must run as root: the bootstrap signing key is 0400 owned by root, "
                "which is what makes 'no service holds it' a filesystem fact.",
            )
        if not arguments.rendered_dir.is_dir():
            raise JwksError(2, f"no rendered directory at {arguments.rendered_dir}")

        document, jwk = build(arguments.project_key, arguments.generation)
        destination = arguments.rendered_dir / JWKS_FILENAME
        changed = write(document, destination)
    except JwksError as error:
        print(f"render-jwks: {error}", file=sys.stderr)
        return error.code

    verb = "wrote" if changed else "confirmed"
    print(f"render-jwks: {verb} {destination} ({JWKS_MODE:04o}), kid {jwk['kid']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
