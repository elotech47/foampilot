"""Tutorial index searcher.

Two-stage search:
1. Hard filter — eliminate cases with wrong solver type or missing physics.
2. Rank — score by solver match (40%), physics overlap (30%), keyword/semantic (30%).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from foampilot.index.builder import TutorialEntry

log = structlog.get_logger(__name__)

# Default weight configuration
_W_SOLVER = 0.40
_W_PHYSICS = 0.30
_W_KEYWORD = 0.20
_W_SEMANTIC = 0.10


@dataclass
class SearchResult:
    """A single search result with its relevance score."""

    entry: TutorialEntry
    score: float
    match_reasons: list[str]


class TutorialSearcher:
    """Searches the tutorial index for cases matching a query.

    Args:
        index_dir: Directory containing tutorial index JSON files.
        version: OpenFOAM version to search (e.g., "11").
    """

    def __init__(
        self,
        index_dir: Path | None = None,
        version: str = "11",
    ) -> None:
        self._index_dir = index_dir or (Path(__file__).parent / "data")
        self._version = version
        self._entries: list[TutorialEntry] | None = None
        self._embeddings: list[list[float]] | None = None

    # ── Index loading ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load the index from disk (lazy, called once)."""
        if self._entries is not None:
            return

        index_path = self._index_dir / f"tutorial_index_v{self._version}.json"
        log.info(
            "loading_index",
            path=str(index_path),
            version=self._version,
            exists=index_path.exists(),
        )

        if not index_path.exists():
            log.warning(
                "index_file_not_found",
                path=str(index_path),
                hint="Run: python scripts/build_index.py --version "
                     f"{self._version} --tutorials-path <path>",
            )
            self._entries = []
            return

        size_kb = round(index_path.stat().st_size / 1024, 1)
        log.debug("index_file_found", path=str(index_path), size_kb=size_kb)

        raw = json.loads(index_path.read_text())
        self._entries = [TutorialEntry(**item) for item in raw]
        log.info(
            "index_loaded",
            entry_count=len(self._entries),
            version=self._version,
            size_kb=size_kb,
        )

        # ── Optional: load semantic embeddings ──────────────────────────────
        emb_path = self._index_dir / f"tutorial_embeddings_v{self._version}.npy"
        log.debug("checking_for_embeddings", path=str(emb_path), exists=emb_path.exists())
        if emb_path.exists():
            log.info("loading_embeddings", path=str(emb_path))
            try:
                import numpy as np
                arr = np.load(emb_path)
                self._embeddings = arr.tolist()
                dims = arr.shape[1] if arr.ndim == 2 else "unknown"
                log.info(
                    "embeddings_loaded",
                    count=len(self._embeddings),
                    dimensions=dims,
                    path=str(emb_path),
                )
            except Exception as exc:
                log.warning(
                    "embeddings_load_failed",
                    path=str(emb_path),
                    error=str(exc),
                )
        else:
            log.info(
                "embeddings_not_available",
                reason="no embeddings file found — semantic search disabled",
                hint="Run build_index.py with --embeddings to enable semantic search",
            )

    # ── Public search API ──────────────────────────────────────────────────────

    def search(
        self,
        solver: str | None = None,
        physics_tags: list[str] | None = None,
        keywords: list[str] | None = None,
        query_text: str | None = None,
        top_n: int = 5,
        require_mesh_type: str | None = None,
    ) -> list[SearchResult]:
        """Search the tutorial index.

        Args:
            solver: Required solver binary name (e.g., "simpleFoam").
            physics_tags: Required physics tags (e.g., ["incompressible", "turbulent"]).
            keywords: Free-text keywords to match against case paths and descriptions.
            query_text: Full natural language query for semantic search.
            top_n: Maximum number of results to return.
            require_mesh_type: If set, only return cases with this mesh type.

        Returns:
            List of SearchResult objects ranked by descending score.
        """
        log.info(
            "search_called",
            solver=solver,
            physics_tags=physics_tags,
            keywords=keywords,
            query_text=query_text,
            top_n=top_n,
            require_mesh_type=require_mesh_type,
        )

        self._load()

        if not self._entries:
            log.warning("search_aborted", reason="index is empty")
            return []

        log.info("search_pool_size", total_entries=len(self._entries))

        # ── Stage 1: Hard filter ─────────────────────────────────────────────
        log.info(
            "filter_start",
            criteria={
                "solver": solver,
                "physics_tags": physics_tags,
                "require_mesh_type": require_mesh_type,
            },
        )
        candidates = self._hard_filter(solver, physics_tags, require_mesh_type)
        log.info(
            "filter_complete",
            candidates=len(candidates),
            filtered_out=len(self._entries) - len(candidates),
        )

        if not candidates:
            log.warning(
                "no_candidates_after_filter",
                solver=solver,
                physics_tags=physics_tags,
                require_mesh_type=require_mesh_type,
                hint="Relaxing filter criteria automatically",
            )
            # Relax: drop solver constraint, keep physics tags
            if solver and (physics_tags or require_mesh_type):
                log.info("search_relax_solver", dropped="solver", keeping="physics_tags")
                candidates = self._hard_filter(None, physics_tags, require_mesh_type)

            # Relax further: drop physics tags too, keep mesh type
            if not candidates and physics_tags:
                log.info("search_relax_physics", dropped="physics_tags", keeping="mesh_type")
                candidates = self._hard_filter(None, None, require_mesh_type)

            # Last resort: drop all constraints
            if not candidates:
                log.info("search_relax_all", dropped="all_constraints")
                candidates = self._hard_filter(None, None, None)

            if not candidates:
                log.warning("search_empty_index", reason="index has no entries")
                return []

            log.info(
                "search_relaxed_candidates",
                candidates=len(candidates),
                original_solver=solver,
                original_physics=physics_tags,
            )

        # ── Stage 2: Query embedding (semantic search) ───────────────────────
        query_embedding = None
        if query_text:
            if self._embeddings:
                log.info("computing_query_embedding", query_text=query_text)
                from foampilot.index.embeddings import embed_text
                query_embedding = embed_text(query_text)
                if query_embedding:
                    log.info(
                        "query_embedding_computed",
                        dimensions=len(query_embedding),
                    )
                else:
                    log.warning("query_embedding_failed", reason="embed_text returned None")
            else:
                log.info(
                    "semantic_search_skipped",
                    reason="no embeddings loaded — keyword search only",
                )

        # ── Stage 3: Score and rank all candidates ───────────────────────────
        log.info("scoring_candidates", count=len(candidates))
        scored = []
        for idx, entry in candidates:
            score, reasons = self._score(
                entry,
                solver=solver,
                physics_tags=physics_tags or [],
                keywords=keywords or [],
                query_embedding=query_embedding,
                entry_embedding=(
                    self._embeddings[idx]
                    if self._embeddings and idx < len(self._embeddings)
                    else None
                ),
            )
            scored.append(SearchResult(entry=entry, score=score, match_reasons=reasons))

        scored.sort(key=lambda r: r.score, reverse=True)
        results = scored[:top_n]

        log.info(
            "search_complete",
            results_returned=len(results),
            top_results=[
                {"path": r.entry.path, "score": round(r.score, 3), "reasons": r.match_reasons}
                for r in results
            ],
        )
        return results

    # ── Hard filter ────────────────────────────────────────────────────────────

    def _hard_filter(
        self,
        solver: str | None,
        physics_tags: list[str] | None,
        require_mesh_type: str | None,
    ) -> list[tuple[int, TutorialEntry]]:
        """Return (original_index, entry) pairs that pass mandatory filters."""
        result = []
        solver_filtered = 0
        physics_filtered = 0
        mesh_filtered = 0

        for idx, entry in enumerate(self._entries or []):
            # Solver must match if specified
            if solver and entry.solver != solver:
                solver_filtered += 1
                log.debug(
                    "filter_rejected_solver",
                    case=entry.path,
                    required=solver,
                    actual=entry.solver,
                )
                continue

            # All required physics tags must be present
            if physics_tags:
                missing = [t for t in physics_tags if t not in entry.physics_tags]
                if missing:
                    physics_filtered += 1
                    log.debug(
                        "filter_rejected_physics",
                        case=entry.path,
                        missing_tags=missing,
                        entry_tags=entry.physics_tags,
                    )
                    continue

            # Mesh type filter
            if require_mesh_type and entry.mesh_type != require_mesh_type:
                mesh_filtered += 1
                log.debug(
                    "filter_rejected_mesh_type",
                    case=entry.path,
                    required=require_mesh_type,
                    actual=entry.mesh_type,
                )
                continue

            result.append((idx, entry))

        log.debug(
            "filter_breakdown",
            total=len(self._entries or []),
            passed=len(result),
            rejected_by_solver=solver_filtered,
            rejected_by_physics=physics_filtered,
            rejected_by_mesh_type=mesh_filtered,
        )
        return result

    # ── Scoring ────────────────────────────────────────────────────────────────

    def _score(
        self,
        entry: TutorialEntry,
        solver: str | None,
        physics_tags: list[str],
        keywords: list[str],
        query_embedding: list[float] | None,
        entry_embedding: list[float] | None,
    ) -> tuple[float, list[str]]:
        """Compute a relevance score [0..1] for a candidate entry."""
        reasons: list[str] = []
        total = 0.0

        # Solver match (40%)
        if solver and entry.solver == solver:
            solver_score = _W_SOLVER
            reasons.append(f"solver match: {solver}")
        elif not solver:
            solver_score = _W_SOLVER * 0.5  # neutral if no solver required
        else:
            solver_score = 0.0
        total += solver_score

        # Physics tag overlap (30%)
        if physics_tags:
            overlap = sum(1 for t in physics_tags if t in entry.physics_tags)
            tag_score = (_W_PHYSICS * overlap) / len(physics_tags)
            total += tag_score
            if overlap:
                reasons.append(f"physics overlap: {overlap}/{len(physics_tags)}")
        else:
            tag_score = _W_PHYSICS * 0.5
            total += tag_score

        # Keyword match (20%)
        if keywords:
            searchable = (
                entry.path + " " + entry.description + " " +
                " ".join(entry.physics_tags)
            ).lower()
            matched_kws = [kw for kw in keywords if kw.lower() in searchable]
            kw_score = (_W_KEYWORD * len(matched_kws)) / len(keywords)
            total += kw_score
            if matched_kws:
                reasons.append(f"keyword match: {matched_kws}")
        else:
            kw_score = _W_KEYWORD * 0.5
            total += kw_score

        # Semantic similarity (10%)
        if query_embedding and entry_embedding:
            from foampilot.index.embeddings import cosine_similarity
            sim = cosine_similarity(query_embedding, entry_embedding)
            sem_score = _W_SEMANTIC * max(0.0, sim)
            total += sem_score
            reasons.append(f"semantic similarity: {sim:.3f}")
        else:
            sem_score = _W_SEMANTIC * 0.5
            total += sem_score

        score = min(total, 1.0)

        log.debug(
            "entry_scored",
            case=entry.path,
            solver_score=round(solver_score, 3),
            physics_score=round(tag_score, 3),
            keyword_score=round(kw_score, 3),
            semantic_score=round(sem_score, 3),
            total=round(score, 3),
            reasons=reasons,
        )
        return score, reasons
