from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import numpy as np

class VectorStore(ABC):
    @abstractmethod
    def add(self, id: str, vector: List[float], metadata: Dict[str, Any]):
        pass

    @abstractmethod
    def search(self, query_vector: List[float], top_k: int) -> list:
        pass

    @abstractmethod
    def delete(self, id: str):
        pass

    @abstractmethod
    def count(self) -> int:
        pass


class LanceDBStore(VectorStore):
    def __init__(self, uri: str, table_name: str = "vectors"):
        try:
            import lancedb
        except ImportError:
            raise ImportError("lancedb is required for LanceDBStore")
            
        self.uri = uri
        self.table_name = table_name
        self.db = lancedb.connect(uri)
        self.table = None
        
        if table_name in self.db.table_names():
            self.table = self.db.open_table(table_name)
            
    def _ensure_table(self, dim: int):
        import pyarrow as pa
        if self.table is None:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
                pa.field("metadata", pa.string())
            ])
            self.table = self.db.create_table(self.table_name, schema=schema)
            
    def add(self, id: str, vector: List[float], metadata: Dict[str, Any]):
        import json
        self._ensure_table(len(vector))
        data = [{
            "id": id,
            "vector": vector,
            "metadata": json.dumps(metadata)
        }]
        self.table.add(data)

    def search(self, query_vector: List[float], top_k: int) -> list:
        import json
        if self.table is None:
            return []
        
        results = self.table.search(query_vector).limit(top_k).to_list()
        formatted_results = []
        for r in results:
            formatted_results.append({
                "id": r["id"],
                "score": 1.0 - r.get("_distance", 0.0),
                "metadata": json.loads(r["metadata"])
            })
        return formatted_results

    def delete(self, id: str):
        if self.table is not None:
            self.table.delete(f"id = '{id}'")

    def count(self) -> int:
        if self.table is None:
            return 0
        return len(self.table)


class InMemoryStore(VectorStore):
    def __init__(self):
        self.vectors = {}
        self.metadata = {}

    def add(self, id: str, vector: List[float], metadata: Dict[str, Any]):
        self.vectors[id] = np.array(vector)
        self.metadata[id] = metadata

    def search(self, query_vector: List[float], top_k: int) -> list:
        if not self.vectors:
            return []
            
        q_vec = np.array(query_vector)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
            
        scores = []
        for v_id, vec in self.vectors.items():
            v_norm = np.linalg.norm(vec)
            if v_norm == 0:
                score = 0
            else:
                score = np.dot(q_vec, vec) / (q_norm * v_norm)
            scores.append((v_id, float(score)))
            
        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for v_id, score in scores[:top_k]:
            results.append({
                "id": v_id,
                "score": score,
                "metadata": self.metadata[v_id]
            })
        return results

    def delete(self, id: str):
        self.vectors.pop(id, None)
        self.metadata.pop(id, None)

    def count(self) -> int:
        return len(self.vectors)


def create_vector_store(backend: str, **kwargs) -> VectorStore:
    if backend == "lancedb":
        return LanceDBStore(kwargs.get("uri", "./lancedb"), kwargs.get("table_name", "vectors"))
    elif backend == "memory":
        return InMemoryStore()
    else:
        raise ValueError(f"Unknown backend: {backend}")
