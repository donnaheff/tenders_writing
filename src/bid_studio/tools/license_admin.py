"""Vendor-side licence tool. Run on YOUR machine, never on a customer deployment.

    python -m bid_studio.tools.license_admin keygen --out license-private.pem
    python -m bid_studio.tools.license_admin issue --private-key license-private.pem \
        --licensee "Acme Ltd" --plan team --days 365
    python -m bid_studio.tools.license_admin inspect KEY --public-key PUBLIC_B64

The private key signs licence keys and must be kept secret and backed up; if it is lost you
cannot issue new keys, and if it leaks anyone can mint keys.
"""

import argparse
import os
import sys

from cryptography.hazmat.primitives import serialization

from bid_studio.services import licensing as lic


def _load_private(path: str):
    with open(path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def cmd_keygen(args) -> int:
    if os.path.exists(args.out) and not args.force:
        print(f"Refusing to overwrite {args.out} (use --force)", file=sys.stderr)
        return 1
    private, public_b64 = lic.generate_keypair()
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    print(f"Private key written to {args.out} (keep it secret, never commit it).")
    print("Set this on every deployment that should verify your keys:")
    print(f"LICENSE_PUBLIC_KEY={public_b64}")
    return 0


def cmd_issue(args) -> int:
    key = lic.issue(
        _load_private(args.private_key),
        licensee=args.licensee,
        plan=args.plan,
        days=None if args.perpetual else args.days,
        max_workspaces=args.workspaces,
        max_members=args.members,
    )
    print(key)
    return 0


def cmd_inspect(args) -> int:
    try:
        data = lic.parse(args.key, args.public_key)
    except lic.LicenseError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    for field, value in data.__dict__.items():
        print(f"{field}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="license_admin", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    kg = sub.add_parser("keygen", help="create a signing keypair")
    kg.add_argument("--out", required=True)
    kg.add_argument("--force", action="store_true")
    kg.set_defaults(fn=cmd_keygen)

    iss = sub.add_parser("issue", help="issue a licence key")
    iss.add_argument("--private-key", required=True)
    iss.add_argument("--licensee", required=True)
    iss.add_argument("--plan", required=True, choices=sorted(lic.PLANS))
    iss.add_argument("--days", type=int, default=365)
    iss.add_argument("--perpetual", action="store_true")
    iss.add_argument("--workspaces", type=int, help="override the plan's workspace limit")
    iss.add_argument("--members", type=int, help="override the plan's members-per-workspace limit")
    iss.set_defaults(fn=cmd_issue)

    ins = sub.add_parser("inspect", help="verify and show a key")
    ins.add_argument("key")
    ins.add_argument("--public-key", required=True)
    ins.set_defaults(fn=cmd_inspect)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
