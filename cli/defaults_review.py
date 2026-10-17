"""Conservative, opt-in review of explicitly loaded incoming defaults."""
from copy import deepcopy
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from uuid import uuid4

from flowtoml import loads, read_toml
from fsutil import current_project_root
from paths import USER_OVERLAY_DIR


def merge(base, overlay):
    result = deepcopy(base)
    for key, value in overlay.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def remove(config, path):
    result = deepcopy(config)
    current = result
    for key in path[:-1]:
        current = current[key]
    del current[path[-1]]
    return result


def value_at(config, path):
    for key in path:
        if not isinstance(config, dict) or key not in config:
            return None
        config = config[key]
    return config


# Settings whose mere presence changes behavior, independent of value — an
# explicit provider_order, even one that only restates the incoming default,
# suppresses openhands_policy.py's role-specific hosted_preferences routing.
# A plain `local != incoming` comparison can never see this: the values match,
# so nothing looks like an override. Authoritative defaults must still offer
# to remove it, since keeping a redundant pin keeps masking role preferences
# the install/update never intended to override.
MASKING_PATHS = {("provider_selection", "provider_order")}


class DefaultsReviewEngine:
    def compare(self, defaults, overrides, path=(), *, scope="user", higher=None):
        differences = []
        for key, local in overrides.items():
            if key not in defaults:
                continue
            setting = (*path, key)
            incoming = defaults[key]
            if isinstance(local, dict) and isinstance(incoming, dict):
                differences.extend(self.compare(incoming, local, setting, scope=scope, higher=higher))
            elif local != incoming or setting in MASKING_PATHS:
                inherited = incoming
                for part in reversed(setting):
                    inherited = {part: inherited}
                differences.append({"path": list(setting), "scope": scope, "local": local,
                    "incoming": incoming, "effective_after_removal": value_at(merge(inherited, higher or {}), setting)})
        return differences


def edit_toml(original, paths):
    """Delete recognized spans, then prove the complete semantic delta."""
    text = original.decode("utf-8")
    before = loads(text)
    expected = deepcopy(before)
    paths = {tuple(path) for path in paths}
    for path in paths:
        expected = remove(expected, path)
    lines = text.splitlines(keepends=True)
    table = ()
    spans = {path: [] for path in paths}
    catalog = ("provider_candidates",) in paths
    candidate_ids = []
    if catalog:
        entries = before.get('provider_candidates', [])
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError('provider_candidates must be an array of tables')
        candidate_ids = [entry.get('candidate_id') for entry in entries]
        if any(not isinstance(identifier, str) or not identifier for identifier in candidate_ids):
            raise ValueError('candidate entries require unique IDs')
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        header = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]\s*(?:#.*)?", stripped)
        array = re.fullmatch(r"\[\[([A-Za-z0-9_.-]+)\]\]\s*(?:#.*)?", stripped)
        if header or array:
            table = tuple((header or array)[1].split("."))
            if array and catalog and table == ("provider_candidates",):
                spans[("provider_candidates",)].append(index)
            continue
        assignment = re.match(r"([A-Za-z0-9_-]+)\s*=", stripped)
        if not assignment:
            if stripped.startswith("["):
                table = ("__unsupported__",)
            continue
        path = (*table, assignment[1])
        if catalog and table == ("provider_candidates",):
            loads(stripped)
            spans[("provider_candidates",)].append(index)
        elif path in paths:
            loads(stripped)
            spans[path].append(index)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate candidate IDs; edit manually")
    for path, indexes in spans.items():
        if not indexes or (path != ("provider_candidates",) and len(indexes) != 1):
            raise ValueError(f"unsupported or ambiguous assignment: {'.'.join(path)}; edit manually")
    deleted = {index for indexes in spans.values() for index in indexes}
    result = "".join(preserve_comment(line) if index in deleted else line for index, line in enumerate(lines)).encode()
    if loads(result.decode()) != expected:
        raise ValueError("edit changes unrelated TOML or cannot expose inheritance; edit manually")
    return result


def preserve_comment(line):
    quote = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
        elif character == '\\' and quote == '"':
            escaped = True
        elif quote:
            if character == quote:
                quote = None
        elif character in {'"', "'"}:
            quote = character
        elif character == '#':
            return line[:len(line) - len(line.lstrip())] + line[index:]
    return ''


def remove_candidate(original, candidate_id):
    entries = loads(original.decode()).get('provider_candidates', [])
    matches = [entry for entry in entries if entry.get('candidate_id') == candidate_id]
    if len(matches) != 1 or len(entries) != 1:
        raise ValueError('partial candidate reset cannot expose inherited array defaults; adopt the complete catalog explicitly')
    return edit_toml(original, [('provider_candidates',)])


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    descriptor, name = tempfile.mkstemp(prefix=".flow-review-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def apply_changes(changes, backup_dir, *, validate=lambda changes: None):
    for path, original, replacement in changes:
        if path.is_symlink() or path.read_bytes() != original:
            raise ValueError(f"source changed or is a symlink: {path}")
        loads(replacement.decode())
    validate(changes)
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_dir.chmod(0o700)
    receipt = {"state": "prepared", "files": []}
    for index, (path, original, replacement) in enumerate(changes):
        backup = backup_dir / f"{index}.toml"
        backup.write_bytes(original)
        backup.chmod(0o600)
        if backup.read_bytes() != original:
            raise ValueError(f'backup verification failed: {backup}')
        receipt["files"].append({"path": str(path.resolve()), "backup": str(backup.resolve()),
            "before": digest(original), "after": digest(replacement)})
    receipt_path = backup_dir / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2))
    try:
        for (path, original, replacement), entry in zip(changes, receipt["files"]):
            if path.is_symlink() or digest(path.read_bytes()) != entry["before"]:
                raise ValueError(f"source changed: {path}")
            atomic_write(path, replacement)
        receipt["state"] = "applied"
        receipt_path.write_text(json.dumps(receipt, indent=2))
    except BaseException:
        recover(receipt_path)
        raise
    return receipt_path


def recover(receipt_path):
    receipt = json.loads(receipt_path.read_text())
    errors = []
    for entry in reversed(receipt["files"]):
        path = Path(entry["path"])
        try:
            current = digest(path.read_bytes())
            if current == entry["before"]:
                continue
            if path.is_symlink() or current != entry["after"]:
                raise ValueError("subsequent edit preserved")
            original = Path(entry["backup"]).read_bytes()
            if digest(original) != entry["before"]:
                raise ValueError("backup hash mismatch")
            atomic_write(path, original)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}")
    receipt.update(state="partial-recovery" if errors else "restored", recovery_errors=errors)
    receipt_path.write_text(json.dumps(receipt, indent=2))
    if errors:
        raise ValueError(f"partial recovery; see {receipt_path}: " + "; ".join(errors))


def runtime_defaults(manifest, overlay):
    from model_policy import runtime_policy_for_agent
    roles = manifest.get('agents', [])
    defaults = {'workspace': {'confirmation': 'SDK default (NeverConfirm)'}, 'profiles': {}, 'roles': {}}
    if not isinstance(overlay.get('profiles', {}), dict) or not isinstance(overlay.get('roles', {}), dict):
        raise ValueError('runtime profiles and roles must be tables')
    for name, profile in overlay.get('profiles', {}).items():
        if not isinstance(profile, dict):
            raise ValueError(f'runtime profile {name} must be a table')
        kind = profile.get('kind', name)
        if kind in {'claude', 'codex'}:
            defaults['profiles'][name] = {'permission_requests': 'stock-openhands',
                'model': {role['name']: runtime_policy_for_agent(manifest, kind, role).get('model') for role in roles}}
    for name, options in overlay.get('roles', {}).items():
        if not isinstance(options, dict):
            raise ValueError(f'runtime role {name} must be a table')
        if 'profile' in options:
            defaults['roles'][name] = {'profile': 'eligible SDK provider roster; role-only calls follow inherited routing policy'}
    def is_routing_pin(name):
        # A default_profile/stage profile pin is a behavior override whether
        # it names a native (claude/codex) profile or a local one — nothing
        # about the built-in default behavior needs any such pin at all. Only
        # the profile *definitions* in overlay['profiles'] (base_url, model,
        # context) stay scoped to native kinds above: a local profile's own
        # fields are machine connection data, not routing, and must not be
        # offered for reset here.
        return bool(name)
    if is_routing_pin(overlay.get('default_profile')):
        defaults['default_profile'] = 'no global pin; implementation inherits the Ollama coordinator; other stages require a selected profile'
    for stage, options in overlay.get('stages', {}).items():
        if is_routing_pin(options.get('profile')):
            defaults.setdefault('stages', {})[stage] = {'profile': 'ollama' if stage == 'implement' else 'inherited global profile or explicit selection required'}
    return defaults


def validate_effective(incoming, loaded, changes):
    from provider_selection import merge_selection_policy, select_candidate
    replacements = {path: loads(replacement.decode()) for path, _, replacement in changes}
    for _, path, original, _ in loaded:
        if path.is_symlink() or path.read_bytes() != original:
            raise ValueError(f'scope changed since review: {path}')
    documents = {(scope, path.name): replacements.get(path, config) for scope, path, _, config in loaded}
    user = documents.get(('user', 'flow.toml'), {})
    for scope in {name for name, _, _, _ in loaded}:
        project = documents.get((scope, 'flow.toml'), {}) if scope != 'user' else {}
        policy = merge_selection_policy(incoming.get('provider_selection', {}), user.get('provider_selection'), project.get('provider_selection'))
        effective = merge(merge(incoming, user), project)
        catalog = effective.get('provider_candidates', [])
        select_candidate({'operation': 'edit'}, policy, catalog,
            [{'candidate_id': candidate.get('candidate_id'), 'state': 'ready'} for candidate in catalog])
        runtime = documents.get(('user', 'runtime.toml'), {})
        if scope != 'user':
            runtime = merge(runtime, documents.get((scope, 'runtime.toml'), {}))
        if runtime.get('workspace', {}).get('confirmation') not in {None, 'always'}:
            raise ValueError('invalid effective workspace confirmation')
        for profile in runtime.get('profiles', {}).values():
            if profile.get('permission_requests') not in {None, 'interactive', 'stock-openhands'}:
                raise ValueError('invalid effective native permission policy')
    validate_runtime_documents(loaded, changes)


def validate_runtime_documents(loaded, changes):
    from openhands_config import load_config, select
    replacements = {path: replacement for path, _, replacement in changes}
    with tempfile.TemporaryDirectory(prefix='flow-review-validation-') as temporary:
        root = Path(temporary)
        user = root / 'user'
        user.mkdir()
        projects = {}
        for scope, path, original, _ in loaded:
            if scope == 'user':
                directory = user
            else:
                if scope not in projects:
                    projects[scope] = root / str(len(projects))
                directory = projects[scope] / '.flow'
                directory.mkdir(parents=True, exist_ok=True)
            (directory / path.name).write_bytes(replacements.get(path, original))
        for project in [root / 'user-scope', *projects.values()]:
            config = load_config(project, user)
            for profile in config.get('profiles', {}):
                select(project, 'implement', 'lead-developer', profile, config=config, user_overlay=user)
            for role, options in config.get('roles', {}).items():
                if 'profile' in options:
                    select(project, 'implement', role, options['profile'], config=config, user_overlay=user)


def configure_parser(parser):
    parser.add_argument("--incoming", type=Path, default=Path(__file__).resolve().parents[1] / "scaffolds/default/flow.toml")
    parser.add_argument("--user-overlay", type=Path, default=USER_OVERLAY_DIR)
    parser.add_argument("--project", type=Path, action="append", default=[])
    parser.add_argument("--auto-project", action="store_true",
        help="also review the project the working directory sits inside, exactly like "
             "`flow install`/`flow update` do automatically; excludes flow's own ~/.flow. "
             "Used by install-flow.sh, which has no Python-side caller to fold this scope "
             "in for it; `--project` keeps adding further explicit scopes on top either way.")
    parser.add_argument("--check", action="store_true", help="report pending differences only; never read stdin or write")
    parser.add_argument("--recover", type=Path)
    return parser


def main(argv=None):
    return run(configure_parser(argparse.ArgumentParser(description=__doc__)).parse_args(argv))


def run(args):
    """Authoritative install defaults: remove conflicting overrides by default.

    Every setting that still differs from (or masks, see MASKING_PATHS) the
    incoming default is removed so the scope inherits it, with no interactive
    Keep/Adopt question and no distinction between a tty and a script. `--check`
    is the only way to preview without writing; recovery from the backup this
    run writes is the explicit opt-out for any single run's result.
    """
    if args.recover:
        recover(args.recover)
        return 0
    incoming = read_toml(args.incoming)
    projects = list(args.project)
    if args.auto_project:
        root = current_project_root()
        if root is not None and not any(project.resolve() == root for project in projects):
            projects.insert(0, root)
    scopes = [("user", args.user_overlay)]
    scopes.extend((str(project.resolve()), project / ".flow") for project in projects)
    loaded = []
    seen = set()
    incomplete = False
    for scope, path in [(scope, directory / filename) for scope, directory in scopes for filename in ('flow.toml', 'runtime.toml')]:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        try:
            original = path.read_bytes()
            loaded.append((scope, path, original, loads(original.decode())))
        except FileNotFoundError:
            # No override file for this scope: the overwhelmingly common,
            # benign case (runtime.toml is optional; many projects have no
            # local overrides at all). Not a reset failure.
            print(f"Skipped {scope}: {path}: no override file to review")
        except (OSError, ValueError) as exc:
            # The file exists but could not be read or parsed. Reporting
            # this as a plain "Skipped" line while still returning success
            # would claim a complete reset when part of it never happened.
            print(f"Skipped {scope}: {path}: {exc}")
            incomplete = True
    users = {path.name: config for scope, path, _, config in loaded if scope == 'user'}
    changes = []
    for scope, path, original, config in loaded:
        user = users.get(path.name, {})
        base = incoming if path.name == 'flow.toml' else runtime_defaults(incoming, merge(user, config))
        defaults = base if scope == "user" else merge(base, user)
        differences = DefaultsReviewEngine().compare(base, config, scope=scope)
        chosen = []
        for difference in differences:
            difference['file'] = str(path)
            difference['incoming'] = value_at(base, difference['path'])
            if path.name == 'flow.toml' and difference['path'][:1] == ['provider_selection']:
                # provider_selection fields have real merge semantics —
                # allowlists intersect, disables union, ceilings take the
                # minimum, lower layers only reorder — that a generic
                # recursive-replacement preview cannot reproduce once a
                # field with those semantics becomes reviewable here.
                from provider_selection import merge_selection_policy
                framework_policy = base.get('provider_selection', {})
                remaining = remove(config, difference['path']).get('provider_selection', {})
                layers = ((framework_policy, remaining) if scope == 'user'
                    else (framework_policy, user.get('provider_selection', {}), remaining))
                policy = merge_selection_policy(*layers)
                difference['effective_after_removal'] = value_at({'provider_selection': policy}, difference['path'])
            else:
                difference['effective_after_removal'] = value_at(defaults, difference['path'])
            try:
                edit_toml(original, [difference['path']])
            except (ValueError, KeyError, TypeError) as exc:
                difference['adoption_unavailable'] = str(exc)
                incomplete = True
            if scope == "user":
                difference["selected_projects_after_removal"] = {name: value_at(merge(merge(base, remove(user, difference["path"])), project_config), difference["path"])
                    for name, project_path, _, project_config in loaded if name != "user" and project_path.name == path.name}
            print(json.dumps(difference, sort_keys=True, default=str))
            if not args.check and 'adoption_unavailable' not in difference:
                chosen.append(difference["path"])
        if chosen:
            replacement = edit_toml(original, chosen)
            changes.append((path, original, replacement))
            if scope == 'user':
                users[path.name] = loads(replacement.decode())
    if changes:
        backup = args.user_overlay / "defaults-review" / uuid4().hex
        print(f"Applied; recovery receipt: {apply_changes(changes, backup, validate=lambda changes: validate_effective(incoming, loaded, changes))}")
    if incomplete:
        print("Defaults review incomplete: a scope could not be read/parsed, or a setting could not be "
              "safely removed (see adoption_unavailable above); not a successful complete reset.")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f"Defaults review failed: {error}", file=sys.stderr)
        sys.exit(1)
