"""Geometric dihedral metrics; never substitutes rendered visual review."""
import numpy as np

def geometric_angles(vertices, faces):
    p = np.asarray(vertices); f = np.asarray(faces, dtype=np.int32)
    n = np.cross(p[f[:, 1]] - p[f[:, 0]], p[f[:, 2]] - p[f[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-15)
    edge = {}
    for i, face in enumerate(f):
        for a, b in zip(face, np.roll(face, -1)):
            edge.setdefault(tuple(sorted((int(a), int(b)))), []).append(i)
    values = []
    for (a, b), adjacent in edge.items():
        if len(adjacent) == 2:
            angle = float(np.degrees(np.arccos(np.clip(np.dot(n[adjacent[0]], n[adjacent[1]]), -1, 1))))
            values.append((angle, a, b, adjacent))
    values.sort(reverse=True, key=lambda x: x[0])
    angles = np.asarray([x[0] for x in values])
    return {'vertices': len(p), 'triangles': len(f), 'edges_above_30deg': int(sum(angles > 30)),
            'edges_above_60deg': int(sum(angles > 60)), 'maximum_deg': float(angles.max()),
            'p95_deg': float(np.percentile(angles, 95)),
            'largest_edges': [{'angle_deg': x[0], 'vertices': [x[1], x[2]], 'midpoint_m': ((p[x[1]] + p[x[2]]) / 2).tolist(),
                               'length_m': float(np.linalg.norm(p[x[1]] - p[x[2]]))} for x in values[:20]]}

