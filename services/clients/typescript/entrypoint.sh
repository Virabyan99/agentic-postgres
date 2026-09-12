#!/bin/sh
#
# Typecheck the generated client mounted at /work, and optionally run its smoke.
#
#   (no argument)  tsc --noEmit over /work/tsconfig.json. Exit 0 means the
#                  generated package compiles under the settings it ships with.
#   smoke          the above, then `node smoke.ts` against a live deployment,
#                  whose URLs and token arrive in the environment.
#
# **The compiler is addressed by its path in THIS image, never through `npx`**
# (D1225). `npx tsc` resolves from the current directory first and, finding
# nothing, will FETCH the package from the registry -- so a proof that ran it
# would reach the network at test time, silently, and pass for the wrong
# reason on a machine that happened to be online. The point of a hash-locked
# toolchain image is that the check is offline; `npx` gives that away in one
# word.
#
# **/work is read-only and nothing here writes to it.** The generated client
# has no node_modules of its own -- it declares no runtime dependency at all --
# so `@types/node` is supplied from this image with --typeRoots rather than by
# installing anything into the directory under test. A toolchain that wrote a
# node_modules into the checkout it was handed would dirty the tree it was
# asked to check, and the dirt would land in a developer's `git status`.

set -eu

TSC=/app/node_modules/.bin/tsc
TYPE_ROOTS=/app/node_modules/@types

if [ ! -x "${TSC}" ]; then
    printf 'client-typescript: %s is not executable; the image did not build\n' "${TSC}" >&2
    exit 3
fi
if [ ! -d /work ]; then
    printf 'client-typescript: nothing is mounted at /work\n' >&2
    exit 2
fi

# **"I cannot read it" is a THIRD answer, not "it is not there"** (D1228, ADR
# 0195). This image runs as 65532, and a directory mounted at 0700 from another
# uid is not absent -- it is unreadable, and every `[ -f ... ]` below is false
# for both reasons. Reported as absence it sends the reader to regenerate a
# client that is already sitting right there, which is the wrong turn ADR 0195
# was written after. Measured: a 0700 mount answered "tsconfig.json is not
# there" until this clause existed.
if [ ! -r /work ] || [ ! -x /work ]; then
    printf 'client-typescript: /work is mounted but this image cannot read it (it runs as %s).\n' \
        "$(id -u):$(id -g)" >&2
    printf 'client-typescript: the directory needs to be readable by that uid -- 0755 on the\n' >&2
    printf 'client-typescript: directory and 0644 on its files. This is NOT "no client here".\n' >&2
    exit 3
fi

if [ ! -f /work/tsconfig.json ]; then
    printf 'client-typescript: /work/tsconfig.json is not there, so there is no generated client to check\n' >&2
    exit 2
fi

cd /work
"${TSC}" -p tsconfig.json --noEmit --typeRoots "${TYPE_ROOTS}"
status=$?
if [ "${status}" -ne 0 ]; then
    exit "${status}"
fi

if [ "${1:-}" = "smoke" ]; then
    if [ ! -f /work/smoke.ts ]; then
        printf 'client-typescript: /work/smoke.ts is not there\n' >&2
        exit 2
    fi
    # The client runs as itself, on the pinned Node, with no flag: this version
    # strips types unflagged (D1204, measured in rig 23b). Its output is one
    # JSON line per step and never a token.
    exec node /work/smoke.ts
fi

printf 'client-typescript: %s typechecks\n' "${PWD}"
