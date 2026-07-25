from dataclasses import dataclass
from typing import List, Optional, Any
import networkx as nx

@dataclass
class SearchResult:
    chunk_id: str
    score: float
    file_path: str
    symbol_name: str
    snippet: str
    source: str

class HybridSearch:
    def __init__(self, bm25_index: Any, vector_store: Any, graph: Optional[nx.DiGraph] = None):
        self.bm25_index = bm25_index
        self.vector_store = vector_store
        self.graph = graph

    def search(self, query: str, mode: str = "auto", top_k: int = 10, query_vector: Optional[List[float]] = None) -> list[SearchResult]:
        if mode == "auto":
            if query_vector is not None:
                mode = "hybrid"
            else:
                mode = "bm25"
                
        results = []
        
        if mode == "bm25":
            bm25_res = self.bm25_index.search(query, top_k=top_k)
            for doc_id, score in bm25_res:
                results.append(SearchResult(
                    chunk_id=doc_id, score=score, file_path="", symbol_name="", snippet="", source="bm25"
                ))
                
        elif mode == "semantic":
            if query_vector is None:
                raise ValueError("query_vector must be provided for semantic search")
            vec_res = self.vector_store.search(query_vector, top_k=top_k)
            for res in vec_res:
                results.append(SearchResult(
                    chunk_id=res["id"], score=res["score"], 
                    file_path=res["metadata"].get("file_path", ""), 
                    symbol_name=res["metadata"].get("symbol_name", ""), 
                    snippet=res["metadata"].get("snippet", ""), 
                    source="semantic"
                ))
                
        elif mode == "hybrid":
            if query_vector is None:
                raise ValueError("query_vector must be provided for hybrid search")
                
            bm25_res = self.bm25_index.search(query, top_k=top_k*2)
            vec_res = self.vector_store.search(query_vector, top_k=top_k*2)
            
            k_rrf = 60
            scores = {}
            metadata_map = {}
            
            for rank, (doc_id, score) in enumerate(bm25_res):
                scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k_rrf + rank + 1)
                metadata_map[doc_id] = {"source": "bm25"}
                
            for rank, res in enumerate(vec_res):
                doc_id = res["id"]
                scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k_rrf + rank + 1)
                metadata_map[doc_id] = res["metadata"]
                metadata_map[doc_id]["source"] = "hybrid" if metadata_map[doc_id].get("source") else "semantic"
                
            sorted_fusion = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            
            for doc_id, score in sorted_fusion[:top_k]:
                meta = metadata_map.get(doc_id, {})
                results.append(SearchResult(
                    chunk_id=doc_id, score=score, 
                    file_path=meta.get("file_path", ""), 
                    symbol_name=meta.get("symbol_name", ""), 
                    snippet=meta.get("snippet", ""), 
                    source=meta.get("source", "hybrid")
                ))
                
        if self.graph is not None:
            for result in results:
                node = result.symbol_name
                if node in self.graph:
                    neighbors = set(self.graph.successors(node)) | set(self.graph.predecessors(node))
                    result_symbols = {r.symbol_name for r in results}
                    overlap = neighbors.intersection(result_symbols)
                    if overlap:
                        result.score *= (1.0 + 0.1 * len(overlap))
                        
            results.sort(key=lambda x: x.score, reverse=True)
                
        return results[:top_k]
