import json, math, pathlib, tempfile, unittest
import audit_phase4_collision_geometry as audit

class CollisionGeometryAuditTests(unittest.TestCase):
    def pose(self,center=(0,0,0)):
        return {'center_m':list(center),'axis':[1,0,0],'side':[0,1,0],'normal':[0,0,1]}
    def test_triangle_interior_crosses_when_all_nodes_are_outside(self):
        v=[[-2,-2,0],[2,-2,0],[0,2,0]];tools=[{'jaw_poses':[self.pose()]}]
        node,surface,_=audit.geometry_depth(v,[[0,1,2]],tools,[1,1,.2])
        self.assertEqual(node,0);self.assertAlmostEqual(surface,.2,places=5)
    def test_tangent_and_clear_are_not_penetration(self):
        for z in (.2,.3):
            _,surface,_=audit.geometry_depth([[-2,-2,z],[2,-2,z],[0,2,z]],[[0,1,2]],[{'jaw_poses':[self.pose()]}],[1,1,.2])
            self.assertLess(surface,1e-10)
    def test_transformed_obb_matches_axis_aligned(self):
        # Rotation around world Z, plus translation. The test is not axis-aligned.
        a=.73;c=math.cos(a);s=math.sin(a);center=[3,-2,7]
        transform=lambda p:[center[0]+c*p[0]-s*p[1],center[1]+s*p[0]+c*p[1],center[2]+p[2]]
        vertices=list(map(transform,[[-2,-2,0],[2,-2,0],[0,2,0]]));pose={'center_m':center,'axis':[c,s,0],'side':[-s,c,0],'normal':[0,0,1]}
        node,surface,_=audit.geometry_depth(vertices,[[0,1,2]],[{'jaw_poses':[pose]}],[1,1,.2])
        self.assertEqual(node,0);self.assertAlmostEqual(surface,.2,places=5)
    def test_sweep_catches_clear_endpoints(self):
        vertices=[[-2,-2,0],[2,-2,0],[0,2,0]];triangles=[[0,1,2]];half=[1,1,.2]
        before={'vertices':vertices,'tools':[{'jaw_poses':[self.pose((0,0,-1))]}]};after={'vertices':vertices,'tools':[{'jaw_poses':[self.pose((0,0,1))]}]}
        self.assertEqual(audit.geometry_depth(vertices,triangles,before['tools'],half)[1],0)
        self.assertEqual(audit.geometry_depth(vertices,triangles,after['tools'],half)[1],0)
        v,t=audit.interpolate_frame(before,after,.5)
        self.assertAlmostEqual(audit.geometry_depth(v,triangles,t,half)[1],.2,places=5)
    def test_bad_frame_basis_rejected(self):
        p=self.pose();p['side']=[1,0,0]
        with self.assertRaisesRegex(ValueError,'Nonorthogonal'):audit.validate_pose(p)
        p=self.pose();p['normal']=[0,0,-1]
        with self.assertRaisesRegex(ValueError,'handedness'):audit.validate_pose(p)
    def test_raw_missing_frame_and_nan_are_rejected(self):
        mesh={'type':'mesh','case_id':'fixture','triangles':[[0,1,2]],'rest_vertices':[[0,0,0],[1,0,0],[0,1,0]],'jaw_half_extents_m':[.00725,.00125,.0007],'dt_s':1/30}
        base={'type':'collision_frame','frame':-1,'step_index':0,'time_s':0,'phase':'initial','vertices':[[0,0,3],[1,0,3],[0,1,3]],'tools':[{'jaw_poses':[self.pose()]},{'jaw_poses':[self.pose()]}],'actual_tip_m':[0,0,0],'healthy':True,'safety_stops':0,'min_tet_volume_ratio':1,'min_triangle_area_ratio':1,'surface_depth_m':0}
        for corruption in ('missing','nan','header_nan','wrong_jaw_size'):
            frame=json.loads(json.dumps(base));header=json.loads(json.dumps(mesh))
            if corruption=='missing':frame['step_index']=2
            elif corruption=='nan':frame['vertices'][0][0]=float('nan')
            elif corruption=='header_nan':header['rest_vertices'][0][0]=float('nan')
            else:header['jaw_half_extents_m'][2]*=.1
            with tempfile.TemporaryDirectory() as directory:
                path=pathlib.Path(directory)/'fixture.jsonl';path.write_text(json.dumps(header)+'\n'+json.dumps(frame)+'\n',encoding='utf-8')
                with self.assertRaises(ValueError):audit.audit_trajectory(path)

if __name__=='__main__':unittest.main()
