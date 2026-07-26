import re
import math
from typing import List, Tuple, Dict

def tokenize(text: str) -> list[str]:
    tokens = re.split(r"[^\w-]+", text.lower())
    return [t for t in tokens if len(t) >= 2]

class BM25Index:
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.df: Dict[str, int] = {}
        self.doc_tf: Dict[str, Dict[str, int]] = {}
        self.doc_len: Dict[str, int] = {}
        self.avgdl: float = 0
        self.N: int = 0
        self.documents: Dict[str, str] = {}
        
    def add_documents(self, docs: list[tuple[str, str]]):
        for doc_id, content in docs:
            self.documents[doc_id] = content
            tokens = tokenize(content)
            
            self.doc_len[doc_id] = len(tokens)
            
            tf = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            self.doc_tf[doc_id] = tf
            
            for t in tf.keys():
                self.df[t] = self.df.get(t, 0) + 1
                
        self.N = len(self.documents)
        if self.N > 0:
            self.avgdl = sum(self.doc_len.values()) / self.N
            
    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)
        
    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        if self.N == 0:
            return []
            
        query_tokens = tokenize(query)
        scores = {doc_id: 0.0 for doc_id in self.documents.keys()}
        
        for term in query_tokens:
            idf = self._idf(term)
            if idf <= 0:
                continue
                
            for doc_id, tf_map in self.doc_tf.items():
                f = tf_map.get(term, 0)
                if f > 0:
                    dl = self.doc_len[doc_id]
                    len_norm = self.k1 * (1 - self.b + self.b * (dl / self.avgdl))
                    scores[doc_id] += idf * (f * (self.k1 + 1)) / (f + len_norm)
                    
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(doc_id, score) for doc_id, score in sorted_results[:top_k] if score > 0]
