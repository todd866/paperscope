"""Cluster a corpus's embedding vectors and write to audit.sqlite.

Default is k-means with k=20. Vectors are L2-normalised so Euclidean distance
is monotone with cosine distance (centroid-nearest = cosine-nearest).

The cluster_run_id (e.g., 'kmeans-20-2026-05-16') tags every cluster and
cluster_assignment row so multiple k-values can coexist for comparison.

Usage:
    from paperscope.systematic_review.methodological_audit.cluster import cluster_corpus
    cluster_corpus(
        db_path="audit.sqlite",
        embeddings_parquet="embeddings/corpus.parquet",  # columns: pmid, embedding
        k=20,
        seed=42,
    )

The parquet must have at least 'pmid' (string) and 'embedding' (list of float).
Any embedder works; Gemini Embedding 2 (3072D matryoshka) is the reference
implementation but OpenAI, sentence-transformers, etc. are equivalent.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path


def _load_vectors(parquet_path: str | Path):
    import numpy as np
    try:
        import pyarrow.parquet as pq
    except ImportError as e:
        raise RuntimeError(
            "methodological-audit clustering requires pyarrow: pip install pyarrow"
        ) from e
    table = pq.read_table(parquet_path)
    pmids = table.column("pmid").to_pylist()
    embs = table.column("embedding").to_pylist()
    X = np.asarray(embs, dtype=np.float32)
    return pmids, X


def _l2_normalise(X):
    import numpy as np
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return X / norms


def _kmeans(X, k: int, seed: int = 42, n_init: int = 10):
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=k, n_init=n_init, random_state=seed, max_iter=300, verbose=0)
    labels = km.fit_predict(X)
    return labels, km.cluster_centers_


def cluster_corpus(
    *,
    db_path: str | Path,
    embeddings_parquet: str | Path,
    k: int = 20,
    seed: int = 42,
    n_init: int = 10,
    tag: str = "",
) -> str:
    """Cluster the corpus and write to audit.sqlite. Returns the cluster_run_id."""
    import numpy as np

    pmids, X = _load_vectors(embeddings_parquet)
    X_norm = _l2_normalise(X)

    t0 = time.time()
    labels, centroids = _kmeans(X_norm, k=k, seed=seed, n_init=n_init)
    elapsed = time.time() - t0

    # Distance to centroid = 1 - cosine similarity (since vectors are L2-normalised)
    centroid_norms = np.linalg.norm(centroids, axis=1, keepdims=True)
    centroid_norms[centroid_norms == 0] = 1.0
    centroids_n = centroids / centroid_norms
    sims = np.einsum("nd,nd->n", X_norm, centroids_n[labels])
    distances = 1.0 - sims

    today = datetime.now().strftime("%Y-%m-%d")
    suffix = f"-{tag}" if tag else ""
    cluster_run_id = f"kmeans-{k}-{today}{suffix}"

    con = sqlite3.connect(db_path)
    cur = con.cursor()
    # Idempotent re-write of this cluster_run_id
    cur.execute("DELETE FROM cluster_assignments WHERE cluster_run_id = ?", (cluster_run_id,))
    cur.execute("DELETE FROM clusters WHERE cluster_run_id = ?", (cluster_run_id,))

    # Per-cluster header rows (with centroid_pmid = closest paper)
    cluster_ids = sorted(set(int(l) for l in labels))
    for cid in cluster_ids:
        mask = labels == cid
        n_papers = int(mask.sum())
        idxs = np.where(mask)[0]
        dists_in = distances[idxs]
        nearest_idx = idxs[int(np.argmin(dists_in))]
        centroid_pmid = pmids[nearest_idx]
        cur.execute(
            """INSERT INTO clusters
               (cluster_run_id, cluster_id, cluster_name, cluster_description,
                n_papers, centroid_pmid)
               VALUES (?, ?, NULL, NULL, ?, ?)""",
            (cluster_run_id, cid, n_papers, centroid_pmid),
        )

    rows = [
        (cluster_run_id, pmids[i], int(labels[i]), float(distances[i]))
        for i in range(len(pmids))
    ]
    cur.executemany(
        """INSERT INTO cluster_assignments
           (cluster_run_id, pmid, cluster_id, distance_to_centroid)
           VALUES (?, ?, ?, ?)""",
        rows,
    )
    con.commit()
    con.close()

    return cluster_run_id
