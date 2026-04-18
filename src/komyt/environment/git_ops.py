"""Git operations — clone, branch, commit, push."""

from __future__ import annotations

import logging
from pathlib import Path

import git

logger = logging.getLogger(__name__)


class GitOperations:
    """Manages git operations on a local repository."""

    def __init__(self, repo_path: Path) -> None:
        self._path = repo_path
        self._repo: git.Repo | None = None

    @property
    def repo(self) -> git.Repo:
        if self._repo is None:
            self._repo = git.Repo(self._path)
        return self._repo

    @staticmethod
    def clone(url: str, target: Path, branch: str = "main", token: str = "") -> GitOperations:
        logger.info("Cloning %s into %s (branch=%s)", url, target, branch)
        clone_url = _inject_token(url, token) if token else url
        git.Repo.clone_from(clone_url, str(target), branch=branch)
        ops = GitOperations(target)
        ops._repo = git.Repo(target)
        return ops

    def create_branch(self, branch_name: str) -> None:
        if branch_name in [ref.name for ref in self.repo.branches]:  # type: ignore[union-attr]
            logger.info("Branch %s already exists, switching to it", branch_name)
            self.repo.git.checkout(branch_name)
        else:
            logger.info("Creating and switching to branch %s", branch_name)
            self.repo.git.checkout("-b", branch_name)

    def current_branch(self) -> str:
        return self.repo.active_branch.name

    def commit(self, message: str, add_all: bool = True) -> str | None:
        if add_all:
            self.repo.git.add("-A")

        if not self.repo.is_dirty(index=True):
            logger.info("Nothing to commit")
            return None

        self.repo.index.commit(message)
        sha = self.repo.head.commit.hexsha
        logger.info("Committed: %s (%s)", message, sha[:8])
        return sha

    def push(self, remote: str = "origin", branch: str | None = None) -> None:
        branch = branch or self.current_branch()
        logger.info("Pushing %s to %s", branch, remote)
        self.repo.git.push(remote, branch, "--set-upstream")

    def has_changes(self) -> bool:
        return self.repo.is_dirty(untracked_files=True)

    def get_diff_summary(self) -> str:
        return self.repo.git.diff("--stat")  # type: ignore[no-any-return]

    def get_log(self, max_count: int = 10) -> list[str]:
        return [
            f"{c.hexsha[:8]} {c.summary}"
            for c in self.repo.iter_commits(max_count=max_count)
        ]

    def rebase_on(self, base_branch: str) -> None:
        logger.info("Rebasing on %s", base_branch)
        self.repo.git.rebase(base_branch)

    def read_file(self, relative_path: str) -> str | None:
        full = self._path / relative_path
        if full.exists():
            return full.read_text(encoding="utf-8", errors="ignore")
        return None


def _inject_token(url: str, token: str) -> str:
    if token and "github.com" in url and "@" not in url:
        return url.replace("https://github.com", f"https://x-access-token:{token}@github.com")
    return url
