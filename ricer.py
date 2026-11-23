"""ricer: apply or remove ~/.dotfiles.

Entry prefixes:
  name      plain: staged into .ricer/build/, destination is a symlink to it
  !!name    copied straight into the destination
  !!!name   destination is a symlink straight to the repo source

Destination roots:
  home/           -> $HOME
  <name>/         -> $XDG_CONFIG_HOME/<name>
  any package with a .ricer_out file -> the absolute path written in it
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent
RICER_DIR = REPO / ".ricer"
STATE_FILE = RICER_DIR / "state.json"
ACTIONS_FILE = RICER_DIR / "actions.json"
BUILD_DIR = RICER_DIR / "build"
HOME = Path.home()
XDG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
COPY_PREFIX = "!!"
DIRECT_PREFIX = "!!!"
OUT_MARKER = ".ricer_out"
SKIP = {".git", "ricer.py", "README.md"}
BACKUP_SUFFIX = ".backup"


# ---------- helpers ----------

def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_hash(path):
    """One hash for a whole tree: relative paths and contents, in sorted order."""
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(path)).encode())
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
    return h.hexdigest()


def content_hash(path):
    return dir_hash(path) if path.is_dir() else file_sha(path)


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save_state(state):
    RICER_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_action(entry):
    entry["time"] = datetime.datetime.now().isoformat(timespec="seconds")
    log = load_json(ACTIONS_FILE, [])
    log.append(entry)
    RICER_DIR.mkdir(parents=True, exist_ok=True)
    ACTIONS_FILE.write_text(json.dumps(log, indent=2))


def remove_path(p):
    if p.is_symlink() or p.is_file():
        p.unlink()
    elif p.is_dir():
        shutil.rmtree(p)


def dest_kind(p):
    if p.is_symlink():
        return "symlink"
    if p.is_dir():
        return "dir"
    if p.is_file():
        return "file"
    return None


def matches(tgt, rec):
    """True if the existing target is exactly what rec describes."""
    mode = rec["mode"]
    if mode in ("link", "dirlink"):
        return tgt.is_symlink() and os.readlink(tgt) == rec["src"]
    if mode == "copy":
        return tgt.is_file() and not tgt.is_symlink() and file_sha(tgt) == rec["hash"]
    if mode == "copytree":
        return tgt.is_dir() and not tgt.is_symlink() and dir_hash(tgt) == rec["hash"]
    return False


def write_rec(tgt, rec):
    tgt.parent.mkdir(parents=True, exist_ok=True)
    mode = rec["mode"]
    if mode in ("link", "dirlink"):
        tgt.symlink_to(rec["src"], target_is_directory=mode == "dirlink")
    elif mode == "copytree":
        shutil.copytree(rec["src"], tgt)
    else:
        shutil.copy2(rec["src"], tgt)


def ask(prompt, choices):
    while True:
        ans = input(f"{prompt} [{'/'.join(choices)}] ").strip().lower()
        if ans in choices:
            return ans


# ---------- 1. scan sources ----------

def package_root(pkg):
    """Destination root for a package: its .ricer_out path, or the default."""
    marker = pkg / OUT_MARKER
    if marker.is_file():
        raw = marker.read_text().strip()
        if not raw:
            raise SystemExit(f"{marker}: empty; put an absolute path in it")
        out = Path(raw).expanduser()
        if not out.is_absolute():
            raise SystemExit(f"{marker}: path must be absolute or start with ~")
        return out
    return HOME if pkg.name == "home" else XDG / pkg.name


def _strip(name):
    """Return (level, bare_name). Level 0 plain, 1 '!!', 2 '!!!'."""
    if name.startswith(DIRECT_PREFIX):
        return 2, name[len(DIRECT_PREFIX):]
    if name.startswith(COPY_PREFIX):
        return 1, name[len(COPY_PREFIX):]
    return 0, name


def _rec(level, src, rel, pkg):
    if level == 2:  # !!!: symlink straight to the repo
        return {"mode": "dirlink" if src.is_dir() else "link", "src": str(src)}
    if level == 1:  # !!: real copy written straight into the destination
        return {"mode": "copytree" if src.is_dir() else "copy",
                "src": str(src), "hash": content_hash(src)}
    # plain file: staged in the build area, destination links to it
    return {"mode": "stage", "src": str(src),
            "build": str(BUILD_DIR / pkg.name / rel)}


def _walk(pkg, cur, root, want):
    for entry in sorted(cur.iterdir()):
        if entry.name == OUT_MARKER and cur == pkg:
            continue  # the marker configures ricer, it is not deployed
        level, bare = _strip(entry.name)
        rel = entry.relative_to(pkg).with_name(bare)
        if entry.is_dir() and level == 0:
            _walk(pkg, entry, root, want)  # plain dirs are walked file by file
        elif entry.is_file() or entry.is_dir():
            want[str(root / rel)] = _rec(level, entry, rel, pkg)


def desired_state():
    want = {}
    for pkg in sorted(REPO.iterdir()):
        if not pkg.is_dir() or pkg.name in SKIP or pkg.name.startswith("."):
            continue
        _walk(pkg, pkg, package_root(pkg), want)
    return want


# ---------- 2. stage ----------

def stage(want, dry_run):
    """Rebuild .ricer/build/ from plain entries and point their targets at it."""
    if not dry_run and BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)  # the build area is disposable
    for tgt_s, rec in list(want.items()):
        if rec["mode"] != "stage":
            continue
        build = Path(rec["build"])
        if not dry_run:
            build.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(rec["src"], build)
        want[tgt_s] = {"mode": "link", "src": rec["build"]}


# ---------- 3. plan ----------

def plan(want, old):
    actions = []
    for t, rec in want.items():
        tgt = Path(t)
        if matches(tgt, rec):
            actions.append({"op": "noop", "tgt": t, "rec": rec})
        elif dest_kind(tgt) is None:
            actions.append({"op": "create", "tgt": t, "rec": rec})
        elif t in old and matches(tgt, old[t]):
            actions.append({"op": "update", "tgt": t, "rec": rec})
        else:
            actions.append({"op": "conflict", "tgt": t, "rec": rec,
                            "kind": dest_kind(tgt)})

    for t, rec in old.items():
        if t in want:
            continue
        tgt = Path(t)
        if matches(tgt, rec):
            actions.append({"op": "remove", "tgt": t, "rec": rec})
        elif dest_kind(tgt) is not None:
            actions.append({"op": "conflict", "tgt": t, "rec": None,
                            "kind": dest_kind(tgt), "stale": True})
    return actions


# ---------- 4. resolve conflicts ----------

def resolve(actions, policy):
    for a in actions:
        if a["op"] != "conflict":
            continue
        what = f"{a['kind']} at {a['tgt']}"
        if a.get("stale"):
            what += " (no longer in repo)"
        choice = policy or ask(f"Conflict: {what}.", ["delete", "backup", "skip"])
        if choice == "skip":
            a["op"] = "skip"
        elif choice == "delete":
            a["op"] = "replace" if a["rec"] else "remove"
        else:
            a["op"] = "backup"
    return actions


# ---------- 5. execute ----------

def execute(actions):
    for a in actions:
        op, rec = a["op"], a["rec"]
        if op in ("noop", "skip"):
            continue
        tgt = Path(a["tgt"])
        print(f"{op:8} {tgt}")
        entry = {"op": op, "tgt": a["tgt"]}
        if op == "create":
            write_rec(tgt, rec)
        elif op in ("update", "replace"):
            remove_path(tgt)
            write_rec(tgt, rec)
        elif op == "remove":
            remove_path(tgt)
        elif op == "backup":
            backup = tgt.with_name(tgt.name + BACKUP_SUFFIX)
            if backup.exists() or backup.is_symlink():
                remove_path(backup)
            tgt.rename(backup)
            entry["backup"] = str(backup)
            if rec:
                write_rec(tgt, rec)
        if rec:
            entry["mode"], entry["src"] = rec["mode"], rec["src"]
        log_action(entry)


# ---------- commands ----------

def apply(args):
    old = load_json(STATE_FILE, {})
    want = desired_state()
    stage(want, dry_run=args.dry_run)
    actions = plan(want, old)

    if args.dry_run:
        for a in actions:
            print(f"{a['op']:8} {a['tgt']}")
        return

    actions = resolve(actions, args.policy)
    execute(actions)

    # Snapshot what ricer now owns. Skipped targets keep their old record,
    # so they are still tracked and will be asked about again.
    state = dict(want)
    for a in actions:
        if a["op"] == "skip":
            if a["tgt"] in old:
                state[a["tgt"]] = old[a["tgt"]]
            else:
                state.pop(a["tgt"], None)
    save_state(state)


def remove_all(args):
    """Delete every target ricer previously wrote, unless it has been edited."""
    old = load_json(STATE_FILE, {})
    remaining = {}
    for t, rec in old.items():
        tgt = Path(t)
        if matches(tgt, rec):
            print(f"remove   {tgt}")
            if not args.dry_run:
                remove_path(tgt)
                log_action({"op": "remove", "tgt": t, "mode": rec["mode"],
                            "src": rec["src"]})
        elif dest_kind(tgt) is not None:
            print(f"keep     {tgt} (edited since ricer wrote it)")
            remaining[t] = rec
    if not args.dry_run:
        if BUILD_DIR.exists():
            shutil.rmtree(BUILD_DIR)
        save_state(remaining)


def main():
    p = argparse.ArgumentParser(description="Apply or remove ~/.dotfiles")
    p.add_argument("action", nargs="?", default="apply",
                   choices=["apply", "remove"],
                   help="apply (default) reconciles the system; "
                        "remove deletes everything ricer previously wrote")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="show the plan, change nothing")
    p.add_argument("--policy", choices=["delete", "backup", "skip"],
                   help="answer every conflict the same way (apply only)")
    args = p.parse_args()

    if args.action == "remove":
        remove_all(args)
    else:
        apply(args)


if __name__ == "__main__":
    main()
