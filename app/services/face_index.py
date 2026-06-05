"""
FAISS Index Manager for fast face embedding search.

Manages an in-memory FAISS index that maps face embeddings to employee IDs.
Uses IndexFlatIP (Inner Product = cosine similarity for normalized vectors)
which is optimal for exact search with <1000 users.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Tuple, List, Dict

import faiss
import numpy as np

logger = logging.getLogger(__name__)

# Embedding dimension from ArcFace model
EMBEDDING_DIM = 512


class FaceIndexManager:
    """
    Manages FAISS index for fast nearest-neighbor face search.

    The index maps face embeddings to employee IDs.
    Multiple face encodings per employee are supported — each gets
    its own entry in the index, but they all map to the same employee_id.
    """

    def __init__(self, index_dir: str = "./data/faiss_index"):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.index_dir / "face_index.bin"
        self.mapping_path = self.index_dir / "id_mapping.npy"

        # FAISS index (Inner Product for cosine similarity on normalized vectors)
        self._index: Optional[faiss.IndexFlatIP] = None
        # Maps FAISS internal index → employee_id
        self._id_mapping: List[int] = []
        # Maps FAISS internal index → face_encoding DB id
        self._encoding_id_mapping: List[int] = []

        self._initialized = False

    def initialize(self):
        """Initialize or load existing index."""
        if self._initialized:
            return

        if self.index_path.exists() and self.mapping_path.exists():
            self._load_index()
        else:
            self._create_empty_index()

        self._initialized = True
        logger.info(
            f"FAISS index initialized with {self._index.ntotal} faces "
            f"({len(set(self._id_mapping))} unique employees)"
        )

    def _create_empty_index(self):
        """Create a new empty FAISS index."""
        self._index = faiss.IndexFlatIP(EMBEDDING_DIM)
        self._id_mapping = []
        self._encoding_id_mapping = []

    def _load_index(self):
        """Load index and mapping from disk."""
        try:
            self._index = faiss.read_index(str(self.index_path))
            data = np.load(str(self.mapping_path), allow_pickle=True).item()
            self._id_mapping = data.get("employee_ids", [])
            self._encoding_id_mapping = data.get("encoding_ids", [])
            logger.info(f"Loaded FAISS index from {self.index_path}")
        except Exception as e:
            logger.warning(f"Failed to load FAISS index: {e}. Creating new.")
            self._create_empty_index()

    def save_index(self):
        """Persist index and mapping to disk."""
        if self._index is None:
            return
        faiss.write_index(self._index, str(self.index_path))
        np.save(
            str(self.mapping_path),
            {
                "employee_ids": self._id_mapping,
                "encoding_ids": self._encoding_id_mapping,
            },
        )
        logger.info(f"Saved FAISS index ({self._index.ntotal} faces)")

    def build_index(self, embeddings_data: List[Dict]):
        """
        Rebuild the entire index from scratch.

        Args:
            embeddings_data: List of dicts with keys:
                - 'employee_id': int
                - 'encoding_id': int (DB id of face_encoding)
                - 'embedding': np.ndarray (512-dim normalized vector)
        """
        start = time.time()
        self._create_empty_index()

        if not embeddings_data:
            self.save_index()
            logger.info("Built empty FAISS index (no face data)")
            return

        vectors = []
        for data in embeddings_data:
            vectors.append(data["embedding"].astype(np.float32))
            self._id_mapping.append(data["employee_id"])
            self._encoding_id_mapping.append(data["encoding_id"])

        vectors_matrix = np.array(vectors, dtype=np.float32)
        # Normalize for cosine similarity
        faiss.normalize_L2(vectors_matrix)
        self._index.add(vectors_matrix)

        self.save_index()
        elapsed = time.time() - start
        logger.info(
            f"Built FAISS index with {len(embeddings_data)} faces "
            f"({len(set(self._id_mapping))} employees) in {elapsed:.3f}s"
        )

    def search(
        self,
        embedding: np.ndarray,
        threshold: float = 0.4,
        top_k: int = 1,
    ) -> List[Tuple[int, float]]:
        """
        Search for the nearest face in the index.

        Args:
            embedding: 512-dim query embedding.
            threshold: Minimum cosine similarity threshold.
                       For normalized vectors with IP index:
                       similarity > threshold = match.
            top_k: Number of nearest neighbors to return.

        Returns:
            List of (employee_id, similarity_score) tuples.
            Empty list if no match above threshold.
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        query = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(query)

        distances, indices = self._index.search(query, top_k)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:
                continue
            similarity = float(dist)
            if similarity >= threshold:
                employee_id = self._id_mapping[idx]
                results.append((employee_id, similarity))

        return results

    def add_face(
        self,
        employee_id: int,
        encoding_id: int,
        embedding: np.ndarray,
    ):
        """
        Add a single face to the index.

        Args:
            employee_id: Employee database ID.
            encoding_id: FaceEncoding database ID.
            embedding: 512-dim normalized embedding.
        """
        if self._index is None:
            self._create_empty_index()

        vector = embedding.astype(np.float32).reshape(1, -1)
        faiss.normalize_L2(vector)
        self._index.add(vector)
        self._id_mapping.append(employee_id)
        self._encoding_id_mapping.append(encoding_id)

        self.save_index()
        logger.debug(
            f"Added face for employee {employee_id} (total: {self._index.ntotal})"
        )

    def remove_employee_faces(self, employee_id: int):
        """
        Remove all faces for an employee by rebuilding the index.

        FAISS IndexFlat doesn't support removal, so we rebuild.
        This is fast enough for <1000 entries.
        """
        if self._index is None or self._index.ntotal == 0:
            return

        # Get all vectors
        all_vectors = faiss.rev_swig_ptr(
            self._index.get_xb(), self._index.ntotal * EMBEDDING_DIM
        ).reshape(self._index.ntotal, EMBEDDING_DIM).copy()

        # Filter out the employee
        keep_mask = [
            eid != employee_id for eid in self._id_mapping
        ]

        if not any(keep_mask):
            self._create_empty_index()
        else:
            new_vectors = all_vectors[keep_mask]
            new_emp_ids = [
                eid for eid, keep in zip(self._id_mapping, keep_mask) if keep
            ]
            new_enc_ids = [
                eid
                for eid, keep in zip(self._encoding_id_mapping, keep_mask)
                if keep
            ]

            self._create_empty_index()
            self._index.add(new_vectors)
            self._id_mapping = new_emp_ids
            self._encoding_id_mapping = new_enc_ids

        self.save_index()
        logger.info(f"Removed faces for employee {employee_id}")

    @property
    def total_faces(self) -> int:
        """Total number of face vectors in the index."""
        return self._index.ntotal if self._index else 0

    @property
    def total_employees(self) -> int:
        """Number of unique employees in the index."""
        return len(set(self._id_mapping))

    @property
    def is_initialized(self) -> bool:
        return self._initialized
