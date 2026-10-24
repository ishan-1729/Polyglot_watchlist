"""Forward-only request graph; operational recovery is managed by the service."""

from langgraph.graph import StateGraph, START, END
from watchlist.agent.nodes import make_nodes
from watchlist.agent.state import ReviewState


def build_graph(saver, ledger, retriever, failpoint=lambda stage: None):
    graph = StateGraph(ReviewState)
    for name, node in make_nodes(ledger, retriever, failpoint).items():
        graph.add_node(name, node)
    graph.add_edge(START, 'normalize')
    graph.add_conditional_edges('normalize', lambda s: 'explain' if s['error'] else 'retrieve_e5',
                               {'explain': 'explain', 'retrieve_e5': 'retrieve_e5'})
    path = ['retrieve_e5', 'format_candidates', 'prepare_review', 'human_review', 'explain', 'audit_record']
    for left, right in zip(path, path[1:]): graph.add_edge(left, right)
    graph.add_edge('audit_record', END)
    return graph.compile(checkpointer=saver)
