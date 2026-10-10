"""Repository Analyst."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from forgeflow.agents.base import Services
from forgeflow.repository.indexer import RepositoryIndex, analyze_repository
from forgeflow.schemas import CodeContext, RepositoryAnalysis, RepositorySummary
from forgeflow.telemetry import RunHandle

SYSTEM = (
    "You are the Repository Analyst in a software delivery system. Given a structural analysis of a "
    "repository (not its full source), describe its architecture, the most important modules, the coding "
    "conventions a contributor must follow and notable engineering risks. Be specific and concise. "
    "Only state what the analysis supports."
)


async def analyze(
    svc: Services, run: RunHandle, root: Path, repo_name: str
) -> tuple[RepositoryAnalysis, RepositorySummary, RepositoryIndex]:
    async with svc.recorder.tool_call(run, "repo.index", {"repository": repo_name}) as res:
        analysis, index = await asyncio.to_thread(analyze_repository, root)
        res["summary"] = f"{analysis.file_count} files, {len(index.chunks)} indexed chunks"
    compact = analysis.model_dump()
    compact["modules"] = [
        {"path": m.path, "symbols": m.symbols[:8], "imports": m.imports[:8]} for m in analysis.modules[:80]
    ]
    summary = await svc.llm.structured(
        RepositorySummary,
        purpose="summarize_repo",
        system=SYSTEM,
        prompt=f"Repository: {repo_name}\n\nStructural analysis (JSON):\n{json.dumps(compact)[:60_000]}",
        run=run,
        context={"analysis": analysis.model_dump(), "repo_name": repo_name},
    )
    return analysis, summary, index


async def retrieve(svc: Services, run: RunHandle, index: RepositoryIndex, query: str, k: int = 8) -> list[CodeContext]:
    async with svc.recorder.tool_call(run, "repo.search", {"query": query[:300], "k": k}) as res:
        hits = index.search(query, k)
        res["summary"] = ", ".join(h.path for h in hits) or "no matches"
    return hits


def memory_entries(analysis: RepositoryAnalysis, summary: RepositorySummary) -> dict[str, dict]:
    return {
        "architecture": {
            "summary": summary.architecture,
            "key_modules": summary.key_modules,
            "entrypoints": analysis.entrypoints,
            "docs": analysis.docs,
            "risks": summary.risks,
        },
        "conventions": {"items": sorted(set(summary.conventions + analysis.conventions))},
        "dependencies": {
            "frameworks": analysis.frameworks,
            "package_managers": analysis.package_managers,
            "import_graph": analysis.import_graph,
        },
        "test_structure": {
            "test_dirs": analysis.test_dirs,
            "test_files": analysis.test_files[:100],
            "verification_profile": analysis.verification_profile,
            "lint_profile": analysis.lint_profile,
        },
        "modules": {"modules": [m.model_dump() for m in analysis.modules[:200]]},
    }
