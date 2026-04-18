"""Parse GitHub issue/PR URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GitHubURL:
    owner: str
    repo: str
    issue_number: str


_ISSUE_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)"
)


def parse_github_issue_url(url: str) -> GitHubURL:
    m = _ISSUE_RE.search(url)
    if not m:
        raise ValueError(
            f"Invalid GitHub issue URL: {url}\n"
            "Expected: https://github.com/owner/repo/issues/123"
        )
    return GitHubURL(
        owner=m.group("owner"),
        repo=m.group("repo"),
        issue_number=m.group("number"),
    )
