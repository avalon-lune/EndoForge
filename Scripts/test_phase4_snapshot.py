"""Positive and adversarial checks for the independent snapshot auditor.

These synthetic fixtures exercise the auditor, not the UE renderer or solver.
Real frozen snapshots are checked separately during package acceptance.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from verify_phase4_snapshot import audit_snapshot


def fixture():
    physical = [[.1, -.05, -.05], [.1, .05, -.05], [.1, 0, .05]]
    weights = [[i/20, j/20, 1-(i+j)/20] for i in range(1, 5) for j in range(1, 5)]
    rendered = [[100*sum(physical[k][a]*w[k] for k in range(3)) for a in range(3)] for w in weights]
    return {
        'phase': 4,
        'native_state': {
            'protocol': 4, 'type': 'state', 'healthy': True, 'safety_stops': 0,
            'state_id': 1, 'simulation_id': 1, 'frame': 1, 'reset_id': 1,
            'topology_revision': 1, 'time': 1/30, 'specimen': 'flat',
            'vertices': physical, 'triangles': [[0, 1, 2]],
            'node_ids': [0, 1, 2], 'material_node_ids': [0, 1, 2], 'parent_node_ids': [-1, -1, -1],
        },
        'render_vertices_cm': rendered,
        'render_triangles': [0, 1, 2],
        'render_bindings': [{'nodes': [0, 1, 2], 'weights': w} for w in weights],
        'camera': {
            'position_cm': [0, 0, 0], 'forward': [1, 0, 0], 'right': [0, 1, 0], 'up': [0, 0, 1],
            'viewport': [800, 800], 'view_rect': [0, 0, 800, 800], 'horizontal_fov_deg': 90,
            'fx_px': 400, 'fy_px': 400, 'cx_px': 400, 'cy_px': 400,
            'view_projection_matrix': [[0, 0, 0, 1], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 0]],
        },
        'projected_samples': [{'render_index': i, 'pixel': [400+400*y/x, 400-400*z/x]} for i, (x, y, z) in enumerate(rendered)],
    }


class SnapshotAuditTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='endoforge-snapshot-audit-')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'snapshot.json'

    def audit(self, data):
        self.path.write_text(json.dumps(data), encoding='utf-8')
        return audit_snapshot(self.path)

    def test_consistent_geometry_and_camera_pass(self):
        result = self.audit(fixture())
        self.assertTrue(result['passed'])
        self.assertLess(result['max_projection_error_px'], 1e-9)
        self.assertEqual(result['visible_projection_samples'], 16)

    def test_reject_corrupt_state_geometry_identity_projection_and_camera(self):
        def mutation(key):
            data = fixture()
            if key == 'geometry': data['render_vertices_cm'][0][0] += .1
            if key == 'pixel': data['projected_samples'][0]['pixel'][0] += 5
            if key == 'identity': data['native_state']['node_ids'][1] = 0
            if key == 'protected': data['native_state']['safety_stops'] = 1
            if key == 'nonfinite': data['native_state']['vertices'][0][0] = float('nan')
            if key == 'topology': data['render_bindings'][0]['nodes'] = [0, 0, 2]
            if key == 'sample': data['projected_samples'][1] = copy.deepcopy(data['projected_samples'][0])
            if key == 'intrinsics': data['camera']['fx_px'] += 10
            if key == 'extrinsics': data['camera']['position_cm'][1] += 1
            if key == 'parent': data['native_state']['parent_node_ids'][0] = -2
            return data
        for key in ('geometry', 'pixel', 'identity', 'protected', 'nonfinite', 'topology', 'sample', 'intrinsics', 'extrinsics', 'parent'):
            with self.subTest(corruption=key), self.assertRaises(ValueError):
                self.audit(mutation(key))

    def test_reject_screenshot_path_escape(self):
        data = fixture()
        data['screenshot'] = '../outside.png'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.audit(data)


if __name__ == '__main__':
    unittest.main()
