#!/usr/bin/env python3
"""
  python XSShield_Partitioner_minimal.py input.pdg.json -o parts.json \
      --theta_ast 120 --w_control 3.0 --w_data 1.0
"""

import json, argparse
import networkx as nx
import community as community_louvain  # python-louvain

MAX_DEPTH = 20

# --- I/O ---

def load_pdg(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- Graph build (paper) ---

def build_graph(pdg, w_control: float, w_data: float) -> nx.Graph:
    """Undirected weighted PDG. Control edges weigh more than data edges."""
    G = nx.Graph()
    for n in pdg.get('nodes', []):
        G.add_node(n['id'], **{
            'type': n.get('type'),
            'ast_size': n.get('ast_size', 0),
            'snippet': n.get('snippet', ''),
        })
    for e in pdg.get('edges', []):
        s, d = e.get('src'), e.get('dst')
        if s is None or d is None or s == d:
            continue
        et = e.get('type', 'data')
        w = w_control if et == 'control' else w_data
        if not (w == w) or w <= 0:
            continue
        if G.has_edge(s, d):
            G[s][d]['weight'] += w
        else:
            G.add_edge(s, d, weight=w)
    return G

# --- Partition (paper) ---

def ast_sum(G: nx.Graph) -> int:
    return sum(G.nodes[n].get('ast_size', 0) for n in G.nodes())


def louvain_split(G: nx.Graph):
    """One pass Louvain partition. Returns list of node sets.
    """
    parts = community_louvain.best_partition(G, weight='weight', resolution=1.0, random_state=0)
    comm = {}
    for n, c in parts.items():
        comm.setdefault(c, set()).add(n)
    return [set(ns) for ns in comm.values()]


def partition_recursive(G: nx.Graph, theta_ast: int, depth: int = 0):
    """Recursively apply Louvain until groups are under theta_ast or depth hits limit.
    """
    if depth >= MAX_DEPTH or G.number_of_nodes() <= 1:
        return [set(G.nodes())]

    total = ast_sum(G)
    if total <= theta_ast:
        return [set(G.nodes())]

    comms = louvain_split(G)
    if len(comms) <= 1:
        return [set(G.nodes())]

    out = []
    for nodes in comms:
        sub = G.subgraph(nodes)
        out.extend(partition_recursive(sub, theta_ast, depth + 1))
    return out

# --- Main ---

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdg_json')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--theta_ast', type=int, default=120)
    ap.add_argument('--w_control', type=float, default=3.0)
    ap.add_argument('--w_data', type=float, default=1.0)
    args = ap.parse_args()

    pdg = load_pdg(args.pdg_json)
    G = build_graph(pdg, args.w_control, args.w_data)

    parts_nodes = []
    for cc in nx.connected_components(G):
        sub = G.subgraph(cc)
        parts_nodes.extend(partition_recursive(sub, args.theta_ast, 0))

    out = []
    node_meta = {n['id']: n for n in pdg.get('nodes', [])}
    for i, ns in enumerate(parts_nodes):
        ns_list = sorted(ns)
        total_ast = sum(node_meta[n].get('ast_size', 0) for n in ns_list if n in node_meta)
        snippet = ' ; '.join((node_meta[n].get('snippet', '') or '')[:120] for n in ns_list if n in node_meta)
        out.append({
            'part_id': i,
            'nodes': ns_list,
            'ast_size': total_ast,
            'snippet': snippet,
        })

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    main()
