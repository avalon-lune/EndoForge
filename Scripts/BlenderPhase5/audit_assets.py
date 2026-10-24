"""Independent structural audit for the authored Phase 5 asset contract."""
import hashlib
import json
import math
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'Assets/Phase5'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def mesh_check(v,f,closed=False):
    assert v and f
    assert all(len(p)==3 and all(math.isfinite(x) for x in p) for p in v)
    assert all(len(t)==3 and len(set(t))==3 and all(isinstance(i,int) and 0<=i<len(v) for i in t) for t in f)
    edge=Counter(tuple(sorted((a,b))) for t in f for a,b in zip(t,t[1:]+t[:1]))
    assert all(n<=2 for n in edge.values())
    if closed:assert all(n==2 for n in edge.values())
    neighbours={i:set() for i in range(len(v))}
    for a,b in edge:neighbours[a].add(b);neighbours[b].add(a)
    remaining=set(neighbours);components=0
    while remaining:
        components+=1;pending=[remaining.pop()]
        while pending:
            for neighbour in neighbours[pending.pop()]:
                if neighbour in remaining:remaining.remove(neighbour);pending.append(neighbour)
    if closed:assert components==1
    return {'vertices':len(v),'triangles':len(f),'boundary_edges':sum(n==1 for n in edge.values()),'connected_components':components,'closed_required':closed}


def png_check(path):
    b=path.read_bytes();assert b[:8]==b'\x89PNG\r\n\x1a\n'
    pos=8;payload=b'';width=height=None
    while pos<len(b):
        length=struct.unpack('>I',b[pos:pos+4])[0];kind=b[pos+4:pos+8];data=b[pos+8:pos+8+length]
        crc=struct.unpack('>I',b[pos+8+length:pos+12+length])[0]
        assert crc==zlib.crc32(kind+data)&0xffffffff
        if kind==b'IHDR':width,height=struct.unpack('>II',data[:8])
        if kind==b'IDAT':payload+=data
        pos+=length+12
        if kind==b'IEND':break
    decompressed=zlib.decompress(payload)
    assert width and height and len(decompressed)==height*(1+width*3)
    return {'width':width,'height':height,'sha256':sha(path)}


physics=json.loads((ASSETS/'physics-mesh.json').read_text(encoding='utf8'))
scene=json.loads((ASSETS/'scene.json').read_text(encoding='utf8'))
assert physics['model_id']==scene['model_id'] and physics['version']==scene['version']
assert physics['units']==scene['units']=='m'
report={'schema':'endoforge.asset-contract-check.v1','checks':{},'texture_files':{},'meshes':{}}
report['meshes']['Gallbladder']=mesh_check(physics['vertices_m'],physics['triangles'],True)
outer=scene['dynamic_surface'];assert outer['triangles']==physics['triangles']
assert outer['material_vertex_ids']==list(range(len(physics['vertices_m'])))
max_error=0
max_normal_error=0
for point,norm,visual in zip(physics['vertices_m'],physics['normals'],outer['vertices_m']):
    # Blender mathutils normalizes in float32; accept its representational error.
    max_normal_error=max(max_normal_error,abs(sum(c*c for c in norm)-1))
    assert max_normal_error<1e-6
    max_error=max(max_error,max(abs(point[k]+norm[k]*physics['thickness_m']/2-visual[k]) for k in range(3)))
assert max_error<=1e-12
report['checks']['outer_wall_binding_error_m']=max_error
report['checks']['max_normal_squared_length_error']=max_normal_error
ids=[100]+[o['id'] for o in scene['static_objects']];assert len(set(ids))==len(ids)
for obj in scene['static_objects']:
    report['meshes'][obj['name']]=mesh_check(obj['vertices_m'],obj['triangles'],obj['id'] in (200,400,401))
    assert len(obj['uvs'])==len(obj['vertices_m'])
    if obj['id']==200:
        assert obj['vertices_m']==physics['static_liver']['vertices_m']
        assert obj['triangles']==physics['static_liver']['triangles']
for mat in scene['material_sets'].values():
    for key in ('base_color_texture','normal_texture','roughness_texture'):
        rel=mat[key];path=(ASSETS/rel).resolve();assert path.is_relative_to(ASSETS.resolve())
        report['texture_files'][rel]=png_check(path)
bridge=scene['attachment_bridge']
assert bridge['surface_material_vertex_ids']==physics['attachment_vertex_ids']
assert bridge['anchors_m']==physics['attachment_anchor_positions_m']
assert bridge['anchor_bindings']==physics['attachment_anchor_bindings']
anchor_errors=[]
for position,binding in zip(physics['attachment_anchor_positions_m'],physics['attachment_anchor_bindings']):
    f=physics['static_liver']['triangles'][binding['triangle_id']]
    bary=binding['barycentric'];assert len(bary)==3 and min(bary)>=0 and abs(sum(bary)-1)<1e-12
    reconstructed=[sum(bary[j]*physics['static_liver']['vertices_m'][f[j]][k] for j in range(3)) for k in range(3)]
    anchor_errors.append(math.sqrt(sum((a-b)**2 for a,b in zip(position,reconstructed))))
assert len(anchor_errors)==31 and max(anchor_errors)<=1e-8
report['checks']['max_anchor_binding_reconstruction_error_m']=max(anchor_errors)
assert bridge['boundary_edges']
assert all(a in physics['attachment_vertex_ids'] and b in physics['attachment_vertex_ids'] for a,b in bridge['boundary_edges'])
blend_verification=json.loads((ASSETS/'blend-verification.json').read_text(encoding='utf8'))
assert blend_verification['passed'] and blend_verification['native_reopen']
assert blend_verification['blend_sha256']==sha(ASSETS/'EndoForge_Anatomy.blend')
report['checks'].update({'matching_static_liver_collision_mesh':True,'unique_object_ids':True,'textures_crc_and_full_decompression':True,'attachment_boundary_binding':True,'editable_blend_exists':True})
report['physics_sha256']=sha(ASSETS/'physics-mesh.json');report['scene_sha256']=sha(ASSETS/'scene.json');report['blend_sha256']=sha(ASSETS/'EndoForge_Anatomy.blend')
report['passed']=True
(ASSETS/'asset-contract-check.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'passed':True,'texture_count':len(report['texture_files']),'objects':len(ids),'report':str(ASSETS/'asset-contract-check.json')}))
