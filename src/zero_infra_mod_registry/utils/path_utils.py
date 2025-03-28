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
    repo = repo.strip().rstrip(os.path.sep)
    return os.path.sep.join(repo.split(os.path.sep)[-2:])
