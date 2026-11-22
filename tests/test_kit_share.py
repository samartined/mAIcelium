"""`mai kit share`: a new skills repo with skills taken from another repo.

Why this file exists: giving someone a few of your skills must give them everything
those skills need to work (their hooks, the hooks those hooks rely on, the skills those
hooks serve, the vendor notice and license), and nothing else: not the files git does not
track, not the skills you keep, not a trace of you.
"""
import json
import os
import subprocess
import sys

import pytest

from _lib.layer_kit import generator

# The engine needs fcntl and symlinks, so the tests that run it exist only on Linux and
# macOS. They are left undefined elsewhere rather than skipped: CI allows no skipped test.
ENGINE_RUNS_HERE = os.name == "posix"


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def skill(source, relative, body="body\n"):
    write(os.path.join(source, "skills", relative, "SKILL.md"),
          "---\nname: %s\ndescription: d\n---\n%s" % (os.path.basename(relative), body))


def hook(source, name, script, skills, needs=(), events=("PreToolUse",), rules=()):
    hooks_dir = os.path.join(source, "claude", "hooks")
    write(os.path.join(hooks_dir, script), "import sys\nsys.exit(0)\n")
    test = "test_" + script
    write(os.path.join(hooks_dir, test), "print('ok')\n")
    registry_path = os.path.join(hooks_dir, "registry.json")
    hooks_path = os.path.join(hooks_dir, "hooks.json")
    registry = json.load(open(registry_path)) if os.path.exists(registry_path) else {}
    wiring = json.load(open(hooks_path)) if os.path.exists(hooks_path) else {"hooks": {}}
    registry[name] = {"script": script, "test": test, "skills": list(skills), "needs": list(needs),
                      "rules": list(rules), "origin": "repo"}
    for event in events:
        wiring["hooks"].setdefault(event, []).append({"matcher": "Bash", "hooks": [{
            "type": "command", "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/run.py" %s' % name, "timeout": 10}]})
    write(registry_path, json.dumps(registry))
    write(hooks_path, json.dumps(wiring))


@pytest.fixture
def source(tmp_path, monkeypatch):
    """Someone's skills repo, with hooks that serve some skills and rely on others."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Grace Hopper\n\temail = grace@private.example\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = str(tmp_path / "graces-private-skills")
    skill(root, "_common/plain")
    skill(root, "_common/keeper")
    skill(root, "_domains/ops/guarded")
    skill(root, "_domains/ops/base")
    skill(root, "_domains/ops/combo")
    skill(root, "_common/vendored")
    write(os.path.join(root, "skills/_common/vendored/VENDOR.md"), "Upstream: example/vendored v1\n")
    write(os.path.join(root, "skills/_common/vendored/LICENSE"), "MIT License\n")
    write(os.path.join(root, "rules/_domains/ops/guard-rule.mdc"), "---\nalwaysApply: true\n---\nrule\n")
    write(os.path.join(root, "rules/_domains/ops/other-rule.mdc"), "---\nalwaysApply: true\n---\nother\n")
    hook(root, "guard", "guard.py", ["_domains/ops/guarded"], rules=["_domains/ops/guard-rule.mdc"])
    hook(root, "base", "base.py", ["_domains/ops/base"])
    hook(root, "combo", "combo.py", ["_domains/ops/combo"], needs=["base"], events=("PreToolUse", "PostToolUse"))
    git("init", "-q", "-b", "main", cwd=root)
    git("add", "-A", cwd=root)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "init", cwd=root)
    write(os.path.join(root, "skills/_common/plain/notes.local"), "untracked scratch\n")
    return root


def create(tmp_path, source, *relatives, allow=()):
    destination = str(tmp_path / "acme-skills")
    report = generator.create(destination, name="acme-skills", owner="Ada",
                              with_skills=[os.path.join(source, "skills", r) for r in relatives], allow=allow)
    return destination, report


def registry(destination):
    return json.load(open(os.path.join(destination, "claude/hooks/registry.json")))


def wired(destination):
    names = set()
    for groups in json.load(open(os.path.join(destination, "claude/hooks/hooks.json")))["hooks"].values():
        for group in groups:
            names.update(h["command"].split()[-1] for h in group["hooks"])
    return names


def test_a_plain_skill_comes_alone_and_only_with_its_tracked_files(tmp_path, source):
    destination, _ = create(tmp_path, source, "_common/plain")
    assert os.listdir(os.path.join(destination, "skills/_common/plain")) == ["SKILL.md"]
    assert set(registry(destination)) == {"session-start"}
    assert not os.path.exists(os.path.join(destination, "skills/_common/keeper"))


def test_a_skill_brings_its_hook_its_test_and_its_wiring(tmp_path, source):
    destination, _ = create(tmp_path, source, "_domains/ops/guarded")
    assert registry(destination)["guard"]["origin"] == "repo"
    assert os.path.isfile(os.path.join(destination, "claude/hooks/guard.py"))
    assert os.path.isfile(os.path.join(destination, "claude/hooks/test_guard.py"))
    assert wired(destination) == {"session-start", "guard"}


def test_a_hook_brings_the_rules_it_reads_and_no_other(tmp_path, source):
    destination, _ = create(tmp_path, source, "_domains/ops/guarded")
    assert os.listdir(os.path.join(destination, "rules/_domains/ops")) == ["guard-rule.mdc"]


def test_a_hook_brings_the_hooks_it_needs_and_the_skills_they_serve(tmp_path, source):
    destination, report = create(tmp_path, source, "_domains/ops/combo")
    assert set(registry(destination)) == {"session-start", "combo", "base"}
    assert os.path.isfile(os.path.join(destination, "skills/_domains/ops/base/SKILL.md"))
    assert "_domains/ops/base" in report["added"]


def test_a_vendored_skill_keeps_its_notice_and_license(tmp_path, source):
    destination, _ = create(tmp_path, source, "_common/vendored")
    folder = os.path.join(destination, "skills/_common/vendored")
    assert sorted(os.listdir(folder)) == ["LICENSE", "SKILL.md", "VENDOR.md"]


def test_a_domain_folder_that_is_also_a_skill_is_not_a_trace(tmp_path, source):
    skill(source, "_domains/ops")
    git("add", "-A", cwd=source)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "domain skill", cwd=source)
    destination, _ = create(tmp_path, source, "_domains/ops/guarded")
    assert os.path.isdir(os.path.join(destination, "skills/_domains/ops/guarded"))


def test_a_skill_naming_one_that_stays_behind_is_refused_and_nothing_is_left(tmp_path, source):
    write(os.path.join(source, "skills/_common/plain/SKILL.md"),
          "---\nname: plain\ndescription: d\n---\nPair it with `keeper`.\n")
    with pytest.raises(generator.LayerError) as refusal:
        create(tmp_path, source, "_common/plain")
    assert "skills/_common/plain/SKILL.md:5: keeper" in str(refusal.value)
    assert not os.path.exists(tmp_path / "acme-skills")


def test_a_skill_carrying_the_builders_name_is_refused_unless_allowed(tmp_path, source):
    write(os.path.join(source, "skills/_common/plain/SKILL.md"),
          "---\nname: plain\ndescription: d\n---\nWritten by Grace Hopper.\n")
    with pytest.raises(generator.LayerError):
        create(tmp_path, source, "_common/plain")
    destination, _ = create(tmp_path, source, "_common/plain", allow=["Grace Hopper"])
    assert os.path.isdir(destination)


def test_a_skill_git_does_not_track_is_refused(tmp_path, source):
    skill(source, "_common/draft")
    with pytest.raises(generator.LayerError) as refusal:
        create(tmp_path, source, "_common/draft")
    assert "commit" in str(refusal.value)
    assert not os.path.exists(tmp_path / "acme-skills")


def test_a_folder_that_is_not_a_skill_is_refused(tmp_path, source):
    with pytest.raises(generator.LayerError):
        create(tmp_path, source, "_domains/ops")


if ENGINE_RUNS_HERE:
    def test_the_new_repo_keeps_its_invariants(tmp_path, source):
        destination, _ = create(tmp_path, source, "_domains/ops/combo", "_domains/ops/guarded")
        completed = subprocess.run([sys.executable, os.path.join(destination, "claude/tests/test_repo_invariants.py")],
                                   capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr


def share(tmp_path, source, only=(), allow=()):
    skills, rules = generator.select(source, only=only)
    destination = str(tmp_path / "acme-skills")
    generator.create(destination, name="acme-skills", owner="Ada", with_skills=skills, with_rules=rules, allow=allow)
    return destination


def listing(root, folder):
    found = []
    for current, _, names in os.walk(os.path.join(root, folder)):
        found += [os.path.relpath(os.path.join(current, name), root) for name in names
                  if name != ".gitkeep" and not os.path.basename(current).startswith(".")]
    return sorted(path.replace(os.sep, "/") for path in found)


def test_a_domain_that_is_also_a_skill_brings_itself_and_everything_inside(tmp_path, source):
    skill(source, "_domains/ops")
    git("add", "-A", cwd=source)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "domain skill", cwd=source)
    skills, _ = generator.select(source, only=["ops"])
    root = os.path.realpath(os.path.join(source, "skills"))
    assert [os.path.relpath(path, root).replace(os.sep, "/") for path in skills] == [
        "_domains/ops", "_domains/ops/base", "_domains/ops/combo", "_domains/ops/guarded"]


def test_a_domain_brings_its_skills_and_its_rules_in_the_same_layout(tmp_path, source):
    destination = share(tmp_path, source, only=["ops"])
    assert listing(destination, "rules") == ["rules/_domains/ops/guard-rule.mdc", "rules/_domains/ops/other-rule.mdc"]
    assert [path for path in listing(destination, "skills") if path.endswith("SKILL.md")] == [
        "skills/_domains/ops/base/SKILL.md", "skills/_domains/ops/combo/SKILL.md", "skills/_domains/ops/guarded/SKILL.md"]


def test_without_only_the_whole_repo_is_shared(tmp_path, source):
    destination = share(tmp_path, source)
    skills = [path for path in listing(destination, "skills") if path.endswith("SKILL.md")]
    assert "skills/_common/keeper/SKILL.md" in skills and "skills/_domains/ops/base/SKILL.md" in skills
    assert "rules/_domains/ops/other-rule.mdc" in listing(destination, "rules")


def test_only_takes_a_single_skill_or_rule_by_name(tmp_path, source):
    destination = share(tmp_path, source, only=["plain", "other-rule"])
    assert listing(destination, "rules") == ["rules/_domains/ops/other-rule.mdc"]
    assert [path for path in listing(destination, "skills") if path.endswith("SKILL.md")] == [
        "skills/_common/plain/SKILL.md"]


def test_an_unknown_name_is_refused(tmp_path, source):
    with pytest.raises(generator.LayerError) as refusal:
        generator.select(source, only=["nothing-called-this"])
    assert "nothing-called-this" in str(refusal.value)


def test_a_skill_naming_a_rule_left_behind_is_refused(tmp_path, source):
    write(os.path.join(source, "skills/_common/plain/SKILL.md"),
          "---\nname: plain\ndescription: d\n---\nFollow `other-rule.mdc`.\n")
    git("add", "-A", cwd=source)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "mention", cwd=source)
    with pytest.raises(generator.LayerError) as refusal:
        share(tmp_path, source, only=["plain"])
    assert "other-rule.mdc" in str(refusal.value)
    destination = share(tmp_path, source, only=["plain", "other-rule"])
    assert os.path.isfile(os.path.join(destination, "rules/_domains/ops/other-rule.mdc"))


def test_except_leaves_out_a_skill_or_a_rule_of_what_is_shared(tmp_path, source):
    skills, rules = generator.select(source, only=["ops"], exclude=["guarded", "other-rule"])
    names = sorted(os.path.basename(path) for path in skills + rules)
    assert names == ["base", "combo", "guard-rule.mdc"]


def test_except_with_an_unknown_name_is_refused(tmp_path, source):
    with pytest.raises(generator.LayerError) as refusal:
        generator.select(source, only=["ops"], exclude=["not-there"])
    assert "not-there" in str(refusal.value)


def test_the_builders_own_name_is_a_trace_even_when_they_are_the_owner(tmp_path, source):
    write(os.path.join(source, "skills/_common/plain/SKILL.md"),
          "---\nname: plain\ndescription: d\n---\nWritten by Grace Hopper.\n")
    git("add", "-A", cwd=source)
    git("-c", "commit.gpgsign=false", "commit", "-q", "-m", "signed", cwd=source)
    with pytest.raises(generator.LayerError):
        generator.create(str(tmp_path / "kit"), name="kit", owner="Grace Hopper",
                         with_skills=[os.path.join(source, "skills/_common/plain")])
    assert not os.path.exists(tmp_path / "kit")
