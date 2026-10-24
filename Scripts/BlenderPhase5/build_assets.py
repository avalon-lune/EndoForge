"""Author original EndoForge anatomy assets; all dimensions are in metres.

References guide composition only. This script never imports third-party mesh or
image data. Geometry, UVs and material source are reproducible and editable.
"""
import argparse
import hashlib
import json
import math
import random
import struct
import sys
import zlib
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

P = math.pi
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Assets" / "Phase5"


def oriented(vertices, faces):
    volume = sum(Vector(vertices[a]).dot(Vector(vertices[b]).cross(Vector(vertices[c]))) for a,b,c in faces) / 6
    return faces if volume > 0 else [[a,c,b] for a,b,c in faces]


def radial_mesh(fn, rings=12, sides=24):
    verts = [fn(0, 0)]
    uvs = [[0.5, 0.0]]
    for j in range(1, rings):
        for k in range(sides):
            verts.append(fn(P*j/rings, 2*P*k/sides))
            uvs.append([k/sides,j/rings])
    end = len(verts)
    verts.append(fn(P,0)); uvs.append([0.5,1.0])
    def ix(j,k): return 1+(j-1)*sides+k%sides
    faces = []
    for k in range(sides): faces.append([0,ix(1,k),ix(1,k+1)])
    for j in range(1,rings-1):
        for k in range(sides):
            a,b,c,d=ix(j,k),ix(j,k+1),ix(j+1,k),ix(j+1,k+1)
            faces.extend([[a,c,d],[a,d,b]])
    for k in range(sides): faces.append([ix(rings-1,k),end,ix(rings-1,k+1)])
    return verts,oriented(verts,faces),uvs


def gallbladder(theta, phi):
    t=(1-math.cos(theta))*0.5
    radial=math.sin(theta)
    xcenter=0.0035*t*t
    y=-0.035+0.060*t
    zcenter=0.022+0.004*t
    rx=0.018*radial*(1-0.63*t)
    rz=0.012*radial*(1-0.35*t)
    return [xcenter+rx*math.cos(phi),y,zcenter+rz*math.sin(phi)]


def liver(theta,phi):
    # One continuous asymmetric wedge-like organ, with a broad right lobe,
    # tapered left lobe, inferior rim and a gentle gallbladder-bed depression.
    s=math.sin(theta); c=math.cos(theta)
    ux=s*math.cos(phi); uy=s*math.sin(phi)
    x=0.010+0.104*ux
    y=0.052+0.079*uy*(1-0.17*ux)
    breadth=1-0.23*max(-ux,0)
    z=-0.018+0.040*c*breadth
    if c>0:
        bed=math.exp(-((x-0.002)/0.024)**2-((y-0.012)/0.035)**2)
        z-=0.006*bed
        z+=0.0024*math.sin(3*phi+0.4)*s*s
    z-=0.007*max(-uy,0)*s
    return [x,y,z]


def normals(vertices,faces):
    result=[Vector((0,0,0)) for _ in vertices]
    for a,b,c in faces:
        n=(Vector(vertices[b])-Vector(vertices[a])).cross(Vector(vertices[c])-Vector(vertices[a]))
        for i in (a,b,c): result[i]+=n
    return [list(v.normalized()) for v in result]


def topology(vertices,faces):
    edges={}; used=set(); zero=0
    for face in faces:
        used.update(face)
        a,b,c=map(lambda i:Vector(vertices[i]),face)
        zero+=(b-a).cross(c-a).length<1e-12
        for a,b in zip(face,face[1:]+face[:1]):
            key=tuple(sorted((a,b))); edges[key]=edges.get(key,0)+1
    return {"vertices":len(vertices),"triangles":len(faces),
            "boundary_edges":sum(v==1 for v in edges.values()),
            "nonmanifold_edges":sum(v>2 for v in edges.values()),
            "degenerate_triangles":zero,"unused_vertices":len(vertices)-len(used),
            "bounds_m":[[min(v[i] for v in vertices),max(v[i] for v in vertices)] for i in range(3)]}


def make_object(name, vertices, faces, uvs=None, mat=None):
    mesh=bpy.data.meshes.new(name+"_Mesh")
    mesh.from_pydata(vertices,[],faces); mesh.update()
    ob=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(ob)
    if mat: mesh.materials.append(mat)
    for f in mesh.polygons: f.use_smooth=True
    if uvs:
        layer=mesh.uv_layers.new(name="MaterialUV")
        for poly in mesh.polygons:
            coords=[list(uvs[i]) for i in poly.vertices]
            if max(c[0] for c in coords)-min(c[0] for c in coords)>.5:
                coords=[[u+1 if u<.5 else u,v] for u,v in coords]
            for li,uv in zip(poly.loop_indices,coords): layer.data[li].uv=uv
    return ob


def export_physics():
    OUT.mkdir(parents=True,exist_ok=True)
    verts,faces,uvs=radial_mesh(gallbladder)
    ns=normals(verts,faces)
    lv,lf,lu=radial_mesh(liver,16,32)
    fixed=[i for i,v in enumerate(verts) if v[1]>.0245]
    attachment=[i for i,v in enumerate(verts) if -.006<=v[1]<=.020 and ns[i][2]<-.55]
    anchors=[[verts[i][0],verts[i][1],verts[i][2]-.003] for i in attachment]
    data={"schema":"endoforge.anatomy-mesh.v1","model_id":"endoforge-gallbladder-v1",
          "version":1,"units":"m","vertices_m":verts,"triangles":faces,"normals":ns,
          "uvs":uvs,"thickness_m":.0011,"fixed_vertex_ids":fixed,
          "attachment_vertex_ids":attachment,"attachment_anchor_positions_m":anchors,
          "static_liver":{"vertices_m":lv,"triangles":lf},
          "grasp_targets_m":[[-.005,-.032,.022],[.005,-.032,.022]],
          "home_tips_m":[[-.011,-.048,.022],[.011,-.048,.022]],
          "provenance":"Original analytic mesh authored for EndoForge in Blender. Teacher-provided assets are references, not copied geometry.",
          "clinical_material_validated":False}
    # The current deliverable includes a locally conforming continuous hepatic
    # bed. Explicit physics regeneration must reproduce v2, not the old floating
    # endpoint prototype. Import is delayed to keep the shared helpers usable.
    sys.path.insert(0,str(Path(__file__).parent))
    from build_hepatic_bed import create as create_hepatic_bed
    data=create_hepatic_bed(data)
    (OUT/"physics-mesh.json").write_text(json.dumps(data,separators=(",",":")),encoding="utf8")
    (OUT/"geometry-audit.json").write_text(json.dumps({"gallbladder_middle_surface":topology(verts,faces),"liver":topology(data['static_liver']['vertices_m'],data['static_liver']['triangles']),"fixed_vertex_count":len(fixed),"attachment_vertex_count":len(attachment),"thickness_m":.0011},indent=2),encoding="utf8")
    print("PHASE5_PHYSICS_ASSET",str(OUT/"physics-mesh.json"),flush=True)
    return data


def write_png(path, rgb):
    a=np.clip(rgb*255,0,255).astype(np.uint8)
    height,width,_=a.shape
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    scan=b''.join(b'\x00'+a[y].tobytes() for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan,6))+chunk(b'IEND',b''))


def noise_image(size,grid,seed):
    rng=np.random.default_rng(seed)
    coarse=rng.random((grid+1,grid+1))
    yy,xx=np.mgrid[0:size,0:size].astype(np.float64)
    xx*=grid/size; yy*=grid/size
    ix=xx.astype(int); iy=yy.astype(int); tx=xx-ix; ty=yy-iy
    tx=tx*tx*(3-2*tx); ty=ty*ty*(3-2*ty)
    return ((1-tx)*(1-ty)*coarse[iy,ix]+tx*(1-ty)*coarse[iy,ix+1]+(1-tx)*ty*coarse[iy+1,ix]+tx*ty*coarse[iy+1,ix+1])


def stroke(mask,p0,p1,width):
    size=mask.shape[0]
    x0,y0=np.array(p0)*size; x1,y1=np.array(p1)*size
    radius=max(.7,width*size)
    loX=max(0,int(min(x0,x1)-radius*3)); hiX=min(size,int(max(x0,x1)+radius*3)+1)
    loY=max(0,int(min(y0,y1)-radius*3)); hiY=min(size,int(max(y0,y1)+radius*3)+1)
    if loX>=hiX or loY>=hiY:return
    yy,xx=np.mgrid[loY:hiY,loX:hiX]
    dx,dy=x1-x0,y1-y0
    t=np.clip(((xx-x0)*dx+(yy-y0)*dy)/(dx*dx+dy*dy+1e-10),0,1)
    d2=(xx-x0-t*dx)**2+(yy-y0-t*dy)**2
    alpha=np.exp(-d2/(radius*radius))
    mask[loY:hiY,loX:hiX]=np.maximum(mask[loY:hiY,loX:hiX],alpha)


def tissue_textures(name,color,seed,vessel_strength=.35,roughness=.3):
    size=1024
    folder=OUT/'textures'; folder.mkdir(exist_ok=True)
    n0=noise_image(size,5,seed); n1=noise_image(size,28,seed+1); n2=noise_image(size,110,seed+2)
    rng=random.Random(seed)
    vessels=np.zeros((size,size))
    for j in range(7):
        start=(rng.uniform(.05,.95),rng.uniform(.10,.85))
        pts=[start]
        direction=rng.choice([-1,1])
        for step in range(7):
            pts.append((pts[-1][0]+direction*rng.uniform(.008,.025),pts[-1][1]+rng.uniform(.012,.032)))
        for i in range(len(pts)-1):
            stroke(vessels,pts[i],pts[i+1],.0014*(1-i/10))
            if i in (1,3,5):
                p=pts[i]
                for sub in range(5):
                    q=(p[0]-direction*rng.uniform(.012,.027),p[1]+rng.uniform(.003,.016))
                    stroke(vessels,p,q,.00065*(1-sub/7));p=q
    variation=(n0-.5)*.11+(n1-.5)*.04+(n2-.5)*.018
    if name=='HepaticCapsule':
        # Capsule has fine mottling; low-frequency cloudy patches looked like
        # painted camouflage on the large support organ in the first preview.
        variation=(n0-.5)*.030+(n1-.5)*.025+(n2-.5)*.014
    rgb=np.array(color)[None,None,:]+variation[:,:,None]*np.array([1,.88,.66])[None,None,:]
    if name=='GallbladderSerosa':
        grey=np.array([.38,.39,.34])
        patch=np.clip((n0-.35)*.75,0,.42)[:,:,None]
        rgb=rgb*(1-patch)+grey[None,None,:]*patch
    vein=np.array([.29,.105,.13])
    opacity=vessels[:,:,None]*vessel_strength
    rgb=rgb*(1-opacity)+vein[None,None,:]*opacity
    rough=np.clip(roughness+(n1-.5)*.08+(n2-.5)*.035,.16,.48)
    h=(n1*.4+n2*.6)
    gy,gx=np.gradient(h)
    nm=np.stack([-gx*2,-gy*2,np.ones_like(h)],axis=-1)
    nm/=np.linalg.norm(nm,axis=-1,keepdims=True)
    paths={"base_color_texture":f'textures/{name}_base.png',"roughness_texture":f'textures/{name}_roughness.png',"normal_texture":f'textures/{name}_normal.png'}
    write_png(OUT/paths['base_color_texture'],rgb)
    write_png(OUT/paths['roughness_texture'],np.repeat(rough[:,:,None],3,axis=2))
    write_png(OUT/paths['normal_texture'],nm*.5+.5)
    return paths


def tissue_material(name,color,roughness,seed,vessel_strength=.35):
    paths=tissue_textures(name,color,seed,vessel_strength,roughness)
    m=bpy.data.materials.new(name); m.use_nodes=True
    n=m.node_tree.nodes; link=m.node_tree.links
    p=n.get('Principled BSDF')
    p.inputs['Roughness'].default_value=roughness
    p.inputs['Metallic'].default_value=0
    p.inputs['IOR'].default_value=1.38
    if 'Subsurface Weight' in p.inputs:p.inputs['Subsurface Weight'].default_value=.06
    if 'Subsurface Radius' in p.inputs:p.inputs['Subsurface Radius'].default_value=(.0012,.00065,.00035)
    if 'Coat Weight' in p.inputs:p.inputs['Coat Weight'].default_value=.18
    if 'Coat Roughness' in p.inputs:p.inputs['Coat Roughness'].default_value=.17
    for field,target in [('base_color_texture','Base Color'),('roughness_texture','Roughness')]:
        node=n.new('ShaderNodeTexImage'); node.image=bpy.data.images.load(str(OUT/paths[field]))
        node.label=field;node.image.filepath='//'+paths[field]
        if field!='base_color_texture':node.image.colorspace_settings.name='Non-Color'
        link.new(node.outputs['Color'],p.inputs[target])
    node=n.new('ShaderNodeTexImage');node.image=bpy.data.images.load(str(OUT/paths['normal_texture']))
    node.image.colorspace_settings.name='Non-Color';node.image.filepath='//'+paths['normal_texture']
    normal=n.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.3
    link.new(node.outputs['Color'],normal.inputs['Color']);link.new(normal.outputs['Normal'],p.inputs['Normal'])
    descriptor={'name':name,'base_color':color,'roughness':roughness,'metallic':0,'subsurface_weight':.06,'ior':1.38,'coat_weight':.18,**paths}
    return m,descriptor


def grid_mesh(fn,nx,ny):
    vertices=[];uvs=[];faces=[]
    for j in range(ny+1):
        for i in range(nx+1):
            u,v=i/nx,j/ny;vertices.append(fn(u,v));uvs.append([u,v])
    for j in range(ny):
        for i in range(nx):
            a=i+j*(nx+1);b=a+1;c=a+nx+1;d=c+1
            faces.extend([[a,b,d],[a,d,c]])
    return vertices,faces,uvs


def tube_mesh(points,radius,sides=10):
    pts=[Vector(p) for p in points];verts=[];uvs=[];faces=[]
    for i,p in enumerate(pts):
        axis=(pts[min(i+1,len(pts)-1)]-pts[max(i-1,0)]).normalized()
        u=axis.cross(Vector((0,0,1)))
        if u.length<.01:u=axis.cross(Vector((0,1,0)))
        u.normalize();v=axis.cross(u).normalized()
        for k in range(sides):
            theta=2*P*k/sides
            verts.append(list(p+radius*(u*math.cos(theta)+v*math.sin(theta))))
            uvs.append([k/sides,i/(len(pts)-1)])
    for i in range(len(pts)-1):
        for k in range(sides):
            a=i*sides+k;b=i*sides+(k+1)%sides;c=a+sides;d=b+sides
            faces.extend([[a,b,d],[a,d,c]])
    for i,rev in [(0,True),(len(pts)-1,False)]:
        center=len(verts);verts.append(list(pts[i]));uvs.append([.5,.5])
        for k in range(sides):
            a=i*sides+k;b=i*sides+(k+1)%sides
            faces.append([center,b,a] if rev else [center,a,b])
    return verts,oriented(verts,faces),uvs


def main_scene(data,render=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    scene.render.engine='CYCLES';scene.cycles.samples=48;scene.cycles.use_denoising=True
    scene.render.resolution_x=1280;scene.render.resolution_y=960;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.render.film_transparent=False
    scene.world=bpy.data.worlds.new('AbdominalAmbient');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.12,.055,.04,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.055
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=-.45
    materials={}
    for name,color,rough,seed,vessel in [
        ('GallbladderSerosa',[.48,.47,.32],.31,52,.66),
        ('HepaticCapsule',[.30,.105,.085],.32,35,.18),
        ('PeritonealLining',[.43,.20,.18],.32,113,.4),
        ('OmentalFat',[.69,.46,.16],.39,119,.45),
        ('HepaticBedConnective',[.63,.46,.33],.34,128,.18),
        ('BiliaryDuct',[.64,.58,.36],.35,28,.12),
        ('ArterialLandmark',[.48,.11,.10],.3,25,.03)]:
        materials[name]=tissue_material(name,color,rough,seed,vessel)
    output={'schema':'endoforge.anatomy-scene.v1','model_id':data['model_id'],'version':data['version'],'units':'m',
            'static_objects':[],'camera':{'position_m':[.006,-.085,.067],'target_m':[.003,-.006,.021],'fov_degrees':58},
            'clinical_anatomy_review':'pending teacher/clinician review','physics_mesh':'physics-mesh.json'}
    def add_static(name,object_id,geo,material_name,collision=False,description=''):
        verts,faces,uvs=geo;mat,desc=materials[material_name]
        obj=make_object(name,verts,faces,uvs,mat)
        obj['object_id']=object_id;obj['role']=description;obj['physics_collision']=collision
        output['static_objects'].append({'name':name,'id':object_id,'vertices_m':verts,'triangles':faces,'uvs':uvs,'material':desc,'collision':collision,'description':description})
        return obj
    outer=(np.array(data['vertices_m'])+np.array(data['normals'])*data['thickness_m']*.5).tolist()
    gb=make_object('Gallbladder_Wall_Outer',outer,data['triangles'],data['uvs'],materials['GallbladderSerosa'][0])
    gb['object_id']=100;gb['physics_model']=data['model_id'];gb['wall_thickness_m']=data['thickness_m']
    for name,ids in [('HepaticBedAttachment',data['attachment_vertex_ids']),('NeckConstraint',data['fixed_vertex_ids'])]:
        group=gb.vertex_groups.new(name=name);group.add(ids,1,'REPLACE')
    sub=gb.modifiers.new('EditableDisplaySubdivision','SUBSURF');sub.levels=2;sub.render_levels=2
    inner=(np.array(data['vertices_m'])-np.array(data['normals'])*data['thickness_m']*.5).tolist()
    inner_obj=make_object('Gallbladder_Wall_Inner',inner,[[c,b,a] for a,b,c in data['triangles']],data['uvs'],materials['GallbladderSerosa'][0])
    inner_obj.hide_render=True;inner_obj.hide_set(True);inner_obj['role']='Inspectable inner wall; outer render is opaque.'
    output['dynamic_surface']={'name':gb.name,'id':100,'vertices_m':outer,'triangles':data['triangles'],'uvs':data['uvs'],'material':materials['GallbladderSerosa'][1],
                               'material_vertex_ids':list(range(len(outer))),'binding':'outer physical layer of matching material vertex; no independent render displacement'}
    lv=data['static_liver']['vertices_m'];lf=data['static_liver']['triangles']
    lu=[[.5+math.atan2(v[1]-.052,v[0]-.01)/(2*P),.5+math.asin(max(-1,min(1,(v[2]+.018)/.04)))/P] for v in lv]
    liver_obj=add_static('Liver_HepaticSupport',200,(lv,lf,lu),'HepaticCapsule',True,'Fixed organ support with a continuous refined hepatic bed; contact mesh is this same geometry.')
    if data.get('attachment_anchor_bindings'):
        liver_anchor_ids=sorted({lf[b['triangle_id']][int(np.argmax(b['barycentric']))] for b in data['attachment_anchor_bindings']})
        group=liver_obj.vertex_groups.new(name='HepaticBedAnchorVertices');group.add(liver_anchor_ids,1,'REPLACE')
        ap=dict(zip(data['attachment_vertex_ids'],data['attachment_anchor_positions_m']))
        bed_tri=np.asarray([[ap[i] for i in f] for f in data['triangles'] if all(i in ap for i in f)])
        bed_ids=[]
        for i,p in enumerate(lv):
            e=bed_tri[:,1,:2]-bed_tri[:,0,:2];f=bed_tri[:,2,:2]-bed_tri[:,0,:2];q=np.asarray(p[:2])-bed_tri[:,0,:2]
            det=e[:,0]*f[:,1]-e[:,1]*f[:,0]
            u=(q[:,0]*f[:,1]-q[:,1]*f[:,0])/det;v=(e[:,0]*q[:,1]-e[:,1]*q[:,0])/det
            weights=np.stack([1-u-v,u,v],axis=1)
            on=(np.all(weights>=-1e-7,axis=1))&(np.abs(np.einsum('ij,ij->i',weights,bed_tri[:,:,2])-p[2])<1e-8)
            if np.any(on):bed_ids.append(i)
        group=liver_obj.vertex_groups.new(name='HepaticBedLocalSurface');group.add(bed_ids,1,'REPLACE')
        liver_obj['anchor_bindings_json']=json.dumps(data['attachment_anchor_bindings'])
        output['static_objects'][-1]['semantic_regions']={'hepatic_bed_vertex_ids':bed_ids,'anchor_vertex_ids':liver_anchor_ids}
    # Local posterior cavity, deliberately open towards the laparoscope.
    def cavity(u,v):
        az=P*u;lat=-P*.47+P*.89*v
        return [.164*math.cos(lat)*math.cos(az),.018+.150*math.cos(lat)*math.sin(az),.008+.102*math.sin(lat)]
    cv,cf,cu=grid_mesh(cavity,64,32)
    cf=[[c,b,a] for a,b,c in cf]
    add_static('LocalPeritonealCavity',300,(cv,cf,cu),'PeritonealLining',False,'Open local cavity reference surface; its camera-side boundary is intentional.')
    def lower_wall(u,v):
        x=(u-.5)*.31;y=-.105+v*.25
        return [x,y,-.061+.027*(x/.155)**2+.018*((y-.02)/.14)**2]
    add_static('InferiorCavitySurface',301,grid_mesh(lower_wall,48,32),'PeritonealLining',False,'Lower local cavity background, outside tested manipulation envelope.')
    def fat(u,v):
        x=(u-.5)*.25;y=-.091+v*.040+.007*math.sin(2*P*u)
        wave=.0022*(math.sin(u*P*13+v*P*2)**2)+.0018*(math.sin(v*P*4-u*P*3)**2)
        z=-.009+wave+.008*v+.004*math.sin(u*P*3)**2
        return [x,y,z]
    add_static('AnteriorOmentalFold',310,grid_mesh(fat,100,25),'OmentalFat',False,'Original lobulated local fat/omentum sheet; intentional thin-sheet boundary.')
    def side_fat(u,v):
        # A continuous surrounding skirt extends beyond the camera crop. A
        # rectangular floating patch previously left an implausible cut edge.
        x=-.16+u*.32;y=-.13+v*.29
        z=-.036+.019*(x/.17)**2+.006*((y-.03)/.15)**2
        z+=.0007*math.sin(u*P*8+v*P*2)**2+.0006*math.sin(v*P*7)**2
        return [x,y,z]
    add_static('LateralOmentalFold',311,grid_mesh(side_fat,90,80),'OmentalFat',False,'Continuous surrounding omental skirt outside the active gallbladder wall.')
    duct_pts=[]
    for i in range(25):
        t=i/24;duct_pts.append([.0035+.019*t+.002*math.sin(P*t),.025+.034*t,.026-.014*t+.002*math.sin(P*t)])
    add_static('CysticDuctLandmark',400,tube_mesh(duct_pts,.00145,14),'BiliaryDuct',False,'Anatomical orientation landmark; no duct cutting or fluid simulation.')
    artery_pts=[[p[0]+.003,p[1]+.003,p[2]+.001] for p in duct_pts]
    add_static('CysticArteryLandmark',401,tube_mesh(artery_pts,.00055,10),'ArterialLandmark',False,'Provisional arterial landmark pending anatomical review.')
    # Display-only reference bed strips explicitly linked to material vertex IDs.
    bedverts=[];bedfaces=[];beduv=[]
    ids=data['attachment_vertex_ids'];anchors=data['attachment_anchor_positions_m']
    anchor_by_id=dict(zip(ids,anchors))
    for face in data['triangles']:
        if all(i in anchor_by_id for i in face):
            start=len(bedverts)
            for i in face:bedverts.append(anchor_by_id[i]);beduv.append(data['uvs'][i])
            bedfaces.append([start,start+1,start+2])
    # In v2 the bed is part of the hepatic collision mesh. Do not overlay a
    # coplanar detached reference patch: it would z-fight and imply a false island.
    if bedfaces and data['version']<2:add_static('HepaticBedReference',210,(bedverts,bedfaces,beduv),'HepaticBedConnective',False,'Legacy fixed attachment endpoint reference.')
    output['attachment_material']=materials['HepaticBedConnective'][1]
    bed_edges={}
    for face in data['triangles']:
        if all(i in anchor_by_id for i in face):
            for a,b in zip(face,face[1:]+face[:1]):
                key=tuple(sorted((a,b)));bed_edges[key]=bed_edges.get(key,0)+1
    output['attachment_bridge']={'surface_material_vertex_ids':ids,'anchors_m':anchors,
                                 'boundary_edges':[list(edge) for edge,count in bed_edges.items() if count==1],
                                 'material':materials['HepaticBedConnective'][1],
                                 'anchor_bindings':data.get('attachment_anchor_bindings',[]),
                                 'binding':'Each boundary edge joins current OUTER wall material vertices to its two fixed anchor positions on the actual hepatic collision triangles.'}
    output['material_sets']={name:desc for name,(_,desc) in materials.items()}
    output['grasp_targets_m']=data['grasp_targets_m'];output['home_tips_m']=data['home_tips_m']
    output['appearance_notes']=['No lighting/highlights baked into base color.','Normal maps describe shading detail, not geometry truth.','Blender preview subdivision is editable; UE runtime must use its recorded physical binding.']
    output['orientation']={'x':'lateral (simulation axis, not a patient DICOM axis)','y':'fundus to neck; tools enter from negative Y','z':'up from hepatic support','scope':'local gallbladder working field; not a complete abdomen'}
    output['anatomical_landmarks']=[
        {'name':'Gallbladder fundus','position_m':data['vertices_m'][0],'object_id':100},
        {'name':'Gallbladder neck','position_m':data['vertices_m'][-1],'object_id':100},
        {'name':'Liver bed attachment region','position_m':np.asarray(anchors).mean(axis=0).tolist(),'object_id':200},
        {'name':'Cystic duct landmark','position_m':duct_pts[12],'object_id':400},
        {'name':'Provisional cystic arterial landmark','position_m':artery_pts[12],'object_id':401}]
    (OUT/'scene.json').write_text(json.dumps(output,separators=(',',':')),encoding='utf8')
    camd=bpy.data.cameras.new('LaparoscopePreview');cam=bpy.data.objects.new('LaparoscopePreview',camd);scene.collection.objects.link(cam)
    cam.location=output['camera']['position_m'];target=Vector(output['camera']['target_m']);cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();camd.angle=math.radians(output['camera']['fov_degrees']);camd.clip_start=.0005;camd.clip_end=1;scene.camera=cam
    for name,offset,power,size,color in [('ScopeKey',(-.008,-.005,.002),.55,.007,(1,.85,.73)),('ScopeFill',(.009,.002,-.001),.22,.009,(.83,.9,1))]:
        ld=bpy.data.lights.new(name,'AREA');ld.energy=power;ld.shape='DISK';ld.size=size;ld.color=color
        light=bpy.data.objects.new(name,ld);scene.collection.objects.link(light);light.location=cam.location+Vector(offset);light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
    # A neutral overhead light only assists the inspection preview, recorded as such.
    ld=bpy.data.lights.new('InspectionBounce','AREA');ld.energy=.08;ld.size=.12
    lo=bpy.data.objects.new('InspectionBounce',ld);scene.collection.objects.link(lo);lo.location=(0,.06,.12)
    lo.rotation_euler=(Vector((0,.02,0))-lo.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.view_layer.objects.active=gb;gb.select_set(True)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA'
    scene['asset_provenance']='Original code-generated geometry and textures. Teacher references reviewed visually, no copied mesh or photographic texels.'
    scene['medical_validation']='Provisional engineering anatomy pending clinician review.'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'EndoForge_Anatomy.blend'))
    if render:
        scene.render.filepath=str(OUT/'anatomy-preview.png');bpy.ops.render.render(write_still=True)
    audit={'schema':'endoforge.asset-audit.v1','blender_version':bpy.app.version_string,'model_id':data['model_id'],
           'gallbladder_middle_surface':topology(data['vertices_m'],data['triangles']),
           'static_objects':{o['name']:topology(o['vertices_m'],o['triangles']) for o in output['static_objects']},
           'original_geometry':True,'original_textures':True,'medical_review':'pending',
           'runtime_scene_json':str(OUT/'scene.json'),'source_blend':str(OUT/'EndoForge_Anatomy.blend')}
    (OUT/'geometry-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    print('PHASE5_ASSETS_COMPLETE',json.dumps({'static_objects':len(output['static_objects']),'path':str(OUT),'rendered':render}),flush=True)


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    if '--rebuild-physics' in args or not (OUT/'physics-mesh.json').exists():data=export_physics()
    else:data=json.loads((OUT/'physics-mesh.json').read_text(encoding='utf8'))
    if '--physics-only' not in args:main_scene(data,'--no-render' not in args)
