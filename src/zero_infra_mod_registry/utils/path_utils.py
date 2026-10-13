from __future__ import annotations

import os
from typing import List


def repo_to_index_entry(repo: str) -> str:
    """
    An index entry is just $org/$repoName, which happens to be the last 2 pieces 
    of a github repo url. This converts repo urls to index entries.
    
    Args:
        repo: Repository URL or path
        
    Returns:
        Index entry in the format "org/repo"
    """
    # split on / or \, recombine with /
    repo = repo.replace("\\", "/")
    repo = repo.strip().rstrip("/")
    return "/".join(repo.split("/")[-2:])
