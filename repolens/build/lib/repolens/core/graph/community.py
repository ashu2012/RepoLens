import networkx as nx
import logging

logger = logging.getLogger(__name__)

class CommunityDetector:
    def detect(self, graph: nx.DiGraph) -> dict[str, int]:
        undirected_graph = graph.to_undirected()
        communities_map = {}
        
        try:
            from graspologic.partition import leiden
            communities = leiden(undirected_graph)
            communities_map = communities
        except ImportError:
            logger.info("graspologic not found, falling back to networkx greedy_modularity_communities")
            from networkx.algorithms.community import greedy_modularity_communities
            communities = greedy_modularity_communities(undirected_graph)
            for i, comm in enumerate(communities):
                for node in comm:
                    communities_map[node] = i
                    
        for node, comm_id in communities_map.items():
            if node in graph:
                graph.nodes[node]["community"] = comm_id
                
        return communities_map
