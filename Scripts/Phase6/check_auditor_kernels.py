"""Check independent PN and accelerated-ray kernels against exact small cases."""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from audit_dataset import TriangleBVH, intersect
from audit_snapshot import area_weighted_normals, pn_position
from common import sha, write_new


def run():
    points = [[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]
    normals = area_weighted_normals(points, [[0, 1, 2]])
    smooth, linear = pn_position(points, normals, [.2, .3, .5], .012)
    assert max(abs(a-b) for a, b in zip(smooth, [.3, .5, 0.])) < 1e-12
    bent = [[0, 0, 1], [2**-.5, 0, 2**-.5], [0, 2**-.5, 2**-.5]]
    smooth, _ = pn_position(points, bent, [.2, .3, .5], .012)
    assert abs(math.dist(smooth, linear)-.012) < 1e-12
    for i, weights in enumerate(([1, 0, 0], [0, 1, 0], [0, 0, 1])):
        smooth, _ = pn_position(points, bent, weights, .012)
        assert math.dist(smooth, points[i]) < 1e-12
    random = np.random.default_rng(61023)
    triangles = random.uniform(-2, 2, (1200, 3, 3))
    triangles[1] = triangles[0]  # Coincident-face tie ordering is deterministic.
    tree = TriangleBVH(triangles)
    rays = [(random.uniform(-3, 3, 3), random.normal(size=3)) for _ in range(240)]
    rays += [(np.array(origin, dtype=float), np.array(direction, dtype=float))
             for origin in ((0, 0, 0), (-3, 0, 0), (3, 3, 3))
             for direction in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), (0, -1, 0), (0, 0, -1))]
    maximum = 0.; hits = misses = 0
    for origin, direction in rays:
        expected_index, expected_distance = intersect(origin, direction, triangles)
        index, distance = tree.intersect(origin, direction)
        if np.isfinite(expected_distance):
            assert index == expected_index
            maximum = max(maximum, abs(distance-expected_distance)); hits += 1
        else:
            assert not np.isfinite(distance); misses += 1
    assert maximum < 1e-12 and hits > 0 and misses > 0
    # A surface exactly on the near threshold is excluded by both paths.
    threshold_triangles = np.array([[[.15,-1,-1],[.15,1,-1],[.15,0,1]],
                                   [[.2,-1,-1],[.2,1,-1],[.2,0,1]]])
    o, d = np.zeros(3), np.array([1.,0.,0.])
    assert TriangleBVH(threshold_triangles).intersect(o,d) == intersect(o,d,threshold_triangles)
    return {'schema': 'endoforge.phase6.auditor-kernels.v1', 'passed': True,
            'checks': {'planar_pn_is_linear': True, 'pn_vertices_unchanged': True,
                       'pn_offset_exactly_bounded': True, 'bvh_equals_bruteforce': True,
                       'axis_parallel_and_near_threshold_rays': True},
            'random_seed': 61023, 'rays': len(rays)+1, 'triangles': len(triangles),
            'hits': hits, 'misses': misses, 'max_ray_distance_difference_cm': maximum,
            'kernel_sha256': {name: sha(Path(__file__).with_name(name))
                              for name in ('audit_snapshot.py','audit_dataset.py')}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(); write_new(args.output, report)
    print(json.dumps(report))
