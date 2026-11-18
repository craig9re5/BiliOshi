"""Generate Ed25519 release signing keys and build signed latest.json manifests."""

import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilioshi.runtime import APP_VERSION  # noqa: E402
from bilioshi.updater import (  # noqa: E402
    DEFAULT_REPO,
    RELEASE_PUBLIC_KEY,
    build_signed_manifest,
    ed25519_public_key,
    normalize_version,
    sha256_file,
    validate_manifest,
)

UPDATER_FILE = ROOT / "bilioshi" / "updater.py"


def _write_public_key(pub_hex: str) -> None:
    content = UPDATER_FILE.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^RELEASE_PUBLIC_KEY\s*=\s*"[0-9a-f]*"',
        f'RELEASE_PUBLIC_KEY = "{pub_hex}"',
        content,
        count=1,
        flags=re.M,
    )
    if count != 1:
        raise RuntimeError("Cannot locate RELEASE_PUBLIC_KEY in bilioshi/updater.py")
    UPDATER_FILE.write_text(updated, encoding="utf-8")


def cmd_generate_keypair(args) -> int:
    seed = os.urandom(32)
    seed_hex = seed.hex()
    pub_hex = ed25519_public_key(seed).hex()
    if args.save_private:
        out = Path(args.save_private).resolve()
        try:
            rel = out.relative_to(ROOT)
            if not rel.parts or rel.parts[0] not in ("build", "dist"):
                raise RuntimeError("Private key inside repository may only be saved under gitignored build/ or dist/")
        except ValueError:
            pass
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(seed_hex + "\n", encoding="utf-8")
        print(f"Saved private signing seed to: {out}")
    else:
        print(f"BILIOSHI_SIGNING_KEY={seed_hex}")
    print(f"RELEASE_PUBLIC_KEY={pub_hex}")
    if args.update_public:
        _write_public_key(pub_hex)
        print(f"Updated RELEASE_PUBLIC_KEY in {UPDATER_FILE.relative_to(ROOT)}")
    print("Configure the private seed in GitHub -> Settings -> Secrets and variables -> Actions -> BILIOSHI_SIGNING_KEY.")
    return 0


def cmd_manifest(args) -> int:
    exe = Path(args.exe).resolve()
    if not exe.is_file():
        raise RuntimeError(f"Executable not found: {exe}")
    version = normalize_version(args.version or APP_VERSION)
    if args.tag:
        tag_version = normalize_version(args.tag)
        if tag_version != version:
            raise RuntimeError(f"Tag {args.tag!r} does not match APP_VERSION {version!r}")
    tag = args.tag or f"v{version}"
    seed_hex = (os.environ.get(args.key_env) or "").strip()
    if not seed_hex:
        raise RuntimeError(
            f"Missing signing key in environment variable {args.key_env}. "
            "Run `python tools/release_update.py --generate-keypair --update-public` and add BILIOSHI_SIGNING_KEY to GitHub Actions Secrets."
        )
    derived_pub = ed25519_public_key(seed_hex).hex()
    expected_pub = (args.public_key or RELEASE_PUBLIC_KEY).strip().lower()
    if not expected_pub:
        raise RuntimeError("RELEASE_PUBLIC_KEY in bilioshi/updater.py is empty")
    if derived_pub != expected_pub:
        raise RuntimeError(
            f"{args.key_env} public key ({derived_pub[:12]}...) does not match RELEASE_PUBLIC_KEY ({expected_pub[:12]}...)"
        )
    exe_url = args.exe_url or f"https://github.com/{args.repo}/releases/download/{tag}/{exe.name}"
    manifest = build_signed_manifest(
        version=version,
        exe_url=exe_url,
        exe_sha256=sha256_file(exe),
        exe_size=exe.stat().st_size,
        signing_seed=seed_hex,
        notes=args.notes or "",
    )
    validate_manifest(manifest, public_key=expected_pub)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Signed release manifest: {output} (version={version}, sha256={manifest['exe_sha256'][:12]}...)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--generate-keypair", action="store_true", help="generate a new Ed25519 signing keypair")
    mode.add_argument("--manifest", action="store_true", help="sign and write latest.json for a built executable")
    parser.add_argument("--update-public", action="store_true", help="write generated public key into bilioshi/updater.py")
    parser.add_argument("--save-private", type=Path, help="save generated 64-hex private seed to a gitignored file")
    parser.add_argument("--exe", type=Path, help="path to built BiliOshi.exe")
    parser.add_argument("--output", type=Path, help="output path for latest.json")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="GitHub owner/repo")
    parser.add_argument("--tag", default="", help="Git release tag, e.g. v2026.11.18.1")
    parser.add_argument("--version", default="", help="override version (defaults to APP_VERSION)")
    parser.add_argument("--exe-url", default="", help="explicit HTTPS download URL for BiliOshi.exe")
    parser.add_argument("--notes", default="", help="short release summary")
    parser.add_argument("--key-env", default="BILIOSHI_SIGNING_KEY", help="environment variable holding 64-hex signing seed")
    parser.add_argument("--public-key", default="", help="override expected public key for testing")
    args = parser.parse_args()
    try:
        if args.generate_keypair:
            return cmd_generate_keypair(args)
        if not args.exe or not args.output:
            raise RuntimeError("--manifest requires --exe and --output")
        return cmd_manifest(args)
    except Exception as exc:
        sys.stderr.write(f"Release update tool failed: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
