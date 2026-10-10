"""Static repository analysis and lexical retrieval.

The analyst never sends a whole repository to a model. It builds a structural summary
(languages, frameworks, modules, imports, tests, docs) with parsers and heuristics,
and serves focused code excerpts through a BM25 index over line windows. Semantic
embeddings are intentionally not used: for the repository sizes ForgeFlow targets,
identifier-aware BM25 retrieves the right files and is deterministic and free.
"""

from __future__ import annotations

import ast
import json
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from forgeflow.schemas import CodeContext, ModuleSummary, RepositoryAnalysis
from forgeflow.workspace.manager import IGNORED_DIRS

LANGUAGES = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".swift": "Swift",
    ".sql": "SQL",
    ".sh": "Shell",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
    ".html": "HTML",
    ".css": "CSS",
}
CODE_LANGUAGES = {
    "Python",
    "TypeScript",
    "JavaScript",
    "Go",
    "Rust",
    "Java",
    "Kotlin",
    "Ruby",
    "PHP",
    "C#",
    "C",
    "C++",
    "Swift",
}
FRAMEWORK_MARKERS = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "starlette": "Starlette",
    "pydantic": "Pydantic",
    "sqlalchemy": "SQLAlchemy",
    "langgraph": "LangGraph",
    "langchain": "LangChain",
    "pytest": "pytest",
    "react": "React",
    "next": "Next.js",
    "express": "Express",
    "vue": "Vue",
    "svelte": "Svelte",
    "jest": "Jest",
    "vitest": "Vitest",
    "gin-gonic": "Gin",
}
MAX_FILES = 5000
MAX_INDEX_BYTES = 200_000
WINDOW = 40

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for word in _TOKEN.findall(text):
        parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", word) or [word]
        out.extend(p.lower() for p in parts if len(p) > 1)
        if len(parts) > 1:
            out.append(word.lower())
    return out


@dataclass
class _Chunk:
    path: str
    start: int
    end: int
    text: str
    tf: Counter[str] = field(default_factory=Counter)
    length: int = 0


class RepositoryIndex:
    """BM25 over overlapping line windows. Paths are weighted by repeating path tokens."""

    def __init__(self) -> None:
        self.chunks: list[_Chunk] = []
        self.df: Counter[str] = Counter()

    def add(self, path: str, text: str) -> None:
        lines = text.splitlines()
        step = WINDOW // 2
        for start in range(0, max(len(lines), 1), step):
            window = lines[start : start + WINDOW]
            if not window and start > 0:
                break
            body = "\n".join(window)
            tokens = tokenize(body) + tokenize(path.replace("/", " ")) * 3
            chunk = _Chunk(
                path=path, start=start + 1, end=start + len(window), text=body, tf=Counter(tokens), length=len(tokens)
            )
            self.chunks.append(chunk)
            self.df.update(set(tokens))
            if start + WINDOW >= len(lines):
                break

    def search(self, query: str, k: int = 8, k1: float = 1.4, b: float = 0.75) -> list[CodeContext]:
        q = set(tokenize(query))
        if not q or not self.chunks:
            return []
        n = len(self.chunks)
        avg = sum(c.length for c in self.chunks) / n
        scored = []
        for c in self.chunks:
            score = 0.0
            for t in q:
                f = c.tf.get(t)
                if not f:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * c.length / avg))
            if score > 0:
                scored.append((score, c))
        scored.sort(key=lambda sc: -sc[0])
        seen: set[str] = set()
        results = []
        for score, c in scored:
            if c.path in seen:  # one excerpt per file keeps context diverse
                continue
            seen.add(c.path)
            results.append(
                CodeContext(path=c.path, start_line=c.start, end_line=c.end, score=round(score, 3), content=c.text)
            )
            if len(results) >= k:
                break
        return results


def iter_files(root: Path) -> list[str]:
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if (d not in IGNORED_DIRS and not d.startswith(".")) or d == ".github")
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if p.is_symlink():
                continue
            files.append(str(p.relative_to(root)))
            if len(files) >= MAX_FILES:
                return files
    return files


def _read(root: Path, rel: str) -> str | None:
    p = root / rel
    try:
        if p.stat().st_size > MAX_INDEX_BYTES:
            return None
        data = p.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode(errors="replace")


def _python_module(rel: str, text: str) -> ModuleSummary:
    symbols: list[str] = []
    imports: list[str] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ModuleSummary(path=rel, language="Python", lines=text.count("\n") + 1)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(("." * node.level) + node.module)
    return ModuleSummary(
        path=rel, language="Python", symbols=symbols[:50], imports=imports[:50], lines=text.count("\n") + 1
    )


_JS_IMPORT = re.compile(r"""(?:import\s.*?from\s+|require\()\s*['"]([^'"]+)['"]""")
_JS_EXPORT = re.compile(r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|interface|type)\s+(\w+)")


def _js_module(rel: str, text: str, language: str) -> ModuleSummary:
    return ModuleSummary(
        path=rel,
        language=language,
        symbols=_JS_EXPORT.findall(text)[:50],
        imports=_JS_IMPORT.findall(text)[:50],
        lines=text.count("\n") + 1,
    )


def _is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return bool(
        re.match(r"test_.*\.py$", name)
        or name.endswith("_test.py")
        or name.endswith("_test.go")
        or re.search(r"\.(test|spec)\.[jt]sx?$", name)
    )


def analyze_repository(root: Path) -> tuple[RepositoryAnalysis, RepositoryIndex]:
    files = iter_files(root)
    languages: Counter[str] = Counter()
    modules: list[ModuleSummary] = []
    index = RepositoryIndex()
    total_lines = 0
    texts: dict[str, str] = {}
    for rel in files:
        lang = LANGUAGES.get(Path(rel).suffix.lower())
        if lang:
            languages[lang] += 1
        text = _read(root, rel)
        if text is None:
            continue
        total_lines += text.count("\n") + 1
        if (
            lang in CODE_LANGUAGES
            or lang in ("Markdown", "TOML", "YAML", "JSON")
            or Path(rel).name in ("Dockerfile", "Makefile")
        ):
            index.add(rel, text)
        if lang == "Python":
            modules.append(_python_module(rel, text))
            texts[rel] = text
        elif lang in ("TypeScript", "JavaScript"):
            modules.append(_js_module(rel, text, lang))
            texts[rel] = text

    root_files = [f for f in files if "/" not in f]
    manifest_text = "\n".join(
        (_read(root, f) or "")
        for f in files
        if Path(f).name in ("pyproject.toml", "requirements.txt", "package.json", "go.mod", "setup.py", "setup.cfg")
    ).lower()
    imported = " ".join(i.lower() for m in modules for i in m.imports)
    frameworks = sorted(
        {
            name
            for marker, name in FRAMEWORK_MARKERS.items()
            if re.search(rf"(^|[^a-z]){re.escape(marker)}([^a-z]|$)", manifest_text + " " + imported)
        }
    )

    package_managers = []
    if "pyproject.toml" in root_files:
        package_managers.append("uv" if "uv.lock" in root_files else "poetry" if "poetry.lock" in root_files else "pip")
    elif "requirements.txt" in root_files:
        package_managers.append("pip")
    if "package.json" in root_files:
        package_managers.append(
            "pnpm" if "pnpm-lock.yaml" in root_files else "yarn" if "yarn.lock" in root_files else "npm"
        )
    if "go.mod" in root_files:
        package_managers.append("go")

    test_files = [f for f in files if _is_test(f)]
    test_dirs = sorted(
        {f.split("/")[0] for f in files if f.split("/")[0] in ("tests", "test", "__tests__", "spec")}
        | {str(Path(f).parent) for f in test_files if str(Path(f).parent) != "."}
    )
    docs = [
        f
        for f in files
        if f.lower().endswith(".md") and ("/" not in f or f.lower().startswith("docs/") or "architecture" in f.lower())
    ][:30]

    entrypoints = []
    for rel, text in texts.items():
        name = rel.rsplit("/", 1)[-1]
        if (
            name
            in (
                "main.py",
                "app.py",
                "manage.py",
                "wsgi.py",
                "asgi.py",
                "index.ts",
                "index.js",
                "server.ts",
                "server.js",
            )
            or re.search(r"=\s*(FastAPI|Flask)\(", text)
            or '__name__ == "__main__"' in text
        ):
            entrypoints.append(rel)
    entrypoints.extend(f for f in files if re.match(r"cmd/[^/]+/main\.go$", f))

    # Internal import graph for Python modules.
    by_module = {
        m.path[:-3].replace("/", ".").removesuffix(".__init__"): m.path for m in modules if m.path.endswith(".py")
    }
    graph: dict[str, list[str]] = defaultdict(list)
    for m in modules:
        for imp in m.imports:
            target = by_module.get(imp.lstrip("."))
            if target and target != m.path:
                graph[m.path].append(target)

    verification: list[list[str]] = []
    lint: list[list[str]] = []
    if languages.get("Python"):
        if test_files or "pytest" in frameworks:
            verification.append(["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"])
        lint.append(["python", "-m", "compileall", "-q", "."])
        if "ruff.toml" in root_files or "[tool.ruff" in manifest_text:
            lint.append(["python", "-m", "ruff", "check", "."])
    if "package.json" in root_files:
        try:
            scripts = json.loads(_read(root, "package.json") or "{}").get("scripts", {})
        except json.JSONDecodeError:
            scripts = {}
        if "test" in scripts:
            verification.append(["npm", "test", "--", "--watch=false"])
        if "lint" in scripts:
            lint.append(["npm", "run", "lint"])
        if "typecheck" in scripts:
            lint.append(["npm", "run", "typecheck"])
    if "go.mod" in root_files:
        verification.append(["go", "test", "./..."])
        lint.append(["go", "vet", "./..."])

    analysis = RepositoryAnalysis(
        root_files=root_files[:100],
        languages=dict(languages.most_common()),
        frameworks=frameworks,
        package_managers=package_managers,
        test_dirs=test_dirs[:20],
        test_files=test_files[:200],
        docs=docs,
        entrypoints=sorted(set(entrypoints))[:20],
        modules=sorted(modules, key=lambda m: m.path)[:400],
        import_graph={k: sorted(set(v)) for k, v in sorted(graph.items())},
        verification_profile=verification,
        lint_profile=lint,
        file_count=len(files),
        total_lines=total_lines,
        conventions=_conventions(texts, files),
    )
    return analysis, index


def _conventions(texts: dict[str, str], files: list[str]) -> list[str]:
    out = []
    py = {k: v for k, v in texts.items() if k.endswith(".py")}
    if py:
        funcs = annotated = 0
        for text in py.values():
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    funcs += 1
                    annotated += node.returns is not None
        if funcs:
            out.append(f"Python return annotations on {round(100 * annotated / funcs)}% of functions")
        if any(f.endswith("conftest.py") for f in files):
            out.append("pytest fixtures shared through conftest.py")
        if any("BaseModel" in t for t in py.values()):
            out.append("Pydantic models for request/response validation")
        if any("from __future__ import annotations" in t for t in py.values()):
            out.append("Postponed annotations (from __future__ import annotations)")
        quotes = Counter(
            "double" if '"' in line else "single"
            for t in py.values()
            for line in t.splitlines()
            if ("'" in line) != ('"' in line)
        )
        if quotes:
            out.append(f"Prefers {quotes.most_common(1)[0][0]}-quoted strings")
    if any(f.endswith((".ts", ".tsx")) for f in files):
        out.append("TypeScript sources")
    return out
