import re
from pathlib import Path
from typing import List

import git

from app.core.config import settings

# Rozszerzenia plików do ingestii
SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".cpp", ".c", ".h",
    ".cs", ".rb", ".php", ".swift", ".kt",
    ".md", ".txt", ".yaml", ".yml", ".toml", ".sh",
    ".sql", ".r", ".scala", ".vue", ".svelte",
}

# Katalogi do pominięcia
IGNORED_DIRS = {
    "node_modules", "__pycache__", ".git", "vendor",
    "dist", "build", ".next", ".nuxt", "target",
    ".mypy_cache", ".pytest_cache", "venv", ".venv",
    "coverage", ".coverage", "htmlcov",
}

MAX_FILE_BYTES = 150_000  # 150 KB
CHUNK_SIZE = 1_200
CHUNK_OVERLAP = 150


def _repo_local_path(repo_url: str) -> Path:
    clean = repo_url.rstrip("/").replace(".git", "")
    # github.com/owner/repo → owner/repo
    match = re.search(r"github\.com[/:](.+)/(.+)", clean)
    if match:
        owner, name = match.group(1), match.group(2)
    else:
        parts = clean.split("/")
        owner, name = parts[-2], parts[-1]
    return Path(settings.repos_dir) / owner / name


def clone_or_update(repo_url: str) -> Path:
    """Klonuje lub aktualizuje repo lokalnie."""
    local = _repo_local_path(repo_url)

    # BUG FIX: sprawdzamy czy to rzeczywiście git repo, nie tylko czy katalog istnieje.
    # local.exists() może być True dla pustego katalogu, co spowodowałoby
    # InvalidGitRepositoryError przy git.Repo(local).
    is_git_repo = (local / ".git").exists()

    if is_git_repo:
        repo = git.Repo(local)
        origin = repo.remotes.origin
        origin.pull()
    else:
        # Usuń pusty katalog jeśli istnieje, żeby clone mógł go stworzyć
        if local.exists():
            import shutil
            shutil.rmtree(local)
        local.parent.mkdir(parents=True, exist_ok=True)

        clone_url = repo_url
        if settings.github_token:
            clone_url = repo_url.replace(
                "https://github.com",
                f"https://{settings.github_token}@github.com",
            )
        git.Repo.clone_from(clone_url, local)

    return local


def extract_files(repo_path: Path) -> List[dict]:
    """Wyodrębnia pliki z repozytorium do listy słowników."""
    files = []
    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        # Pomiń ignorowane katalogi
        rel_parts = file_path.relative_to(repo_path).parts
        if any(p in IGNORED_DIRS or p.startswith(".") for p in rel_parts):
            continue
        if file_path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                continue
            files.append(
                {
                    "path": str(file_path.relative_to(repo_path)),
                    "content": content,
                    "extension": file_path.suffix,
                }
            )
        except Exception:
            continue
    return files


def chunk_file(file_info: dict) -> tuple[List[str], List[dict]]:
    """Dzieli plik na fragmenty z metadanymi."""
    path = file_info["path"]
    content = file_info["content"]
    ext = file_info["extension"]
    header = f"# Plik: {path}\n\n"

    chunks = []
    metadatas = []

    if len(content) <= CHUNK_SIZE:
        chunks.append(header + content)
        metadatas.append({"path": path, "extension": ext, "chunk": 0})
    else:
        start = 0
        idx = 0
        while start < len(content):
            end = start + CHUNK_SIZE
            chunk_text = content[start:end]
            chunks.append(header + chunk_text)
            metadatas.append({"path": path, "extension": ext, "chunk": idx})
            start += CHUNK_SIZE - CHUNK_OVERLAP
            idx += 1

    return chunks, metadatas
