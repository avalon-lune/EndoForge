"""Original smooth hepatic bed constrained by the accepted operative workspace.

The 31 attachment positions are hard equalities. Distributed Phase 6 height
samples guide the posterior fossa; they are softly fitted, not copied triangles.
The posterior field uses a C2 cubic radial basis. The original C1 anchor field
and continuous analytic macroform remain outside the neck blend. Neither this
construction nor its rest-state audit substitutes dynamic contact qualification.
"""
import numpy as np
import smooth_bed


class CubicField:
    def __init__(self, xy, z, fixed_count=31, regularization=.0002):
        self.center = xy.mean(0)
        self.scale = .025
        self.points = (xy - self.center) / self.scale
        radius = np.linalg.norm(self.points[:, None] - self.points[None], axis=2)
        kernel = radius ** 3
        # Exactly zero regularization at attachments keeps their values exact.
        kernel += np.diag(np.r_[np.zeros(fixed_count), np.full(len(xy) - fixed_count, regularization)])
        polynomial = np.column_stack([np.ones(len(xy)), self.points])
        matrix = np.block([[kernel, polynomial], [polynomial.T, np.zeros((3, 3))]])
        self.solution = np.linalg.solve(matrix, np.r_[z, np.zeros(3)])
        self.condition = float(np.linalg.cond(matrix))

    def __call__(self, xy):
        x = (xy - self.center) / self.scale
        radius = np.linalg.norm(x[:, None] - self.points[None], axis=2)
        return radius ** 3 @ self.solution[:-3] + np.column_stack([np.ones(len(x)), x]) @ self.solution[-3:]


def make_field(physical):
    anchors = np.asarray(physical['attachment_anchor_positions_m'])
    polygon = smooth_bed.hull(anchors[:, :2])
    baseline, _ = smooth_bed.fit_field(anchors, width=.024)
    old_height = smooth_bed.macro_mesh_height(physical['static_liver']['vertices_m'], physical['static_liver']['triangles'])
    xy = np.asarray([(x, y) for y in np.arange(-.029, .036, .002) for x in np.arange(-.021, .026, .002)])
    distance = smooth_bed.hull_distance(xy, polygon)
    near_anchor = np.linalg.norm(xy[:, None] - anchors[None, :, :2], axis=2).min(1)
    xy = xy[(near_anchor > .0007) & (distance < .016)]
    controls = np.column_stack([xy, old_height(xy) - .00015])
    points = np.vstack([anchors, controls])

    def weight(query):
        c = smooth_bed.macro_top(query)[1]
        return (1 - smooth_bed.quintic(smooth_bed.hull_distance(query, polygon) / .030)) * smooth_bed.quintic((c - .05) / .35)

    w = weight(points[:, :2])
    assert np.min(w) > .01
    residual = (points[:, 2] - smooth_bed.macro_top(points[:, :2])[0]) / w
    fit = CubicField(points[:, :2], residual)

    def evaluate(query):
        original = baseline(query)
        fitted = smooth_bed.macro_top(query)[0] + weight(query) * fit(query)
        blend = smooth_bed.quintic((query[:, 1] - .008) / .009)
        return original + blend * (fitted - original)

    metadata = {
        'basis': 'C2 cubic r^3 radial field plus linear polynomial; exact anchors and regularized non-anchor controls.',
        'control_count': len(controls), 'control_spacing_m': .002,
        'control_height_margin_m': .00015, 'regularization': .0002,
        'control_xy_bounds_m': [xy.min(0).tolist(), xy.max(0).tolist()],
        'field_collar_m': .030, 'baseline_collar_m': .024,
        'posterior_blend_start_y_m': .008, 'posterior_blend_width_m': .009,
        'source': 'Accepted Phase 6 operative height samples; macro rim/equator and bad lateral shoulder are not copied into the new collider.',
        'scope': 'Original engineering reconstruction. Full physical and visual requalification required; no clinical anatomical validation.'
    }
    return evaluate, fit, metadata
