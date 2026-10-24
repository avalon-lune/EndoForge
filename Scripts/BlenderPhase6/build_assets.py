"""Original Phase 6 visual assets, preserving the Phase 5 physical contract.

Run: blender -b --python Scripts/BlenderPhase6/build_assets.py -- --no-render
The render surface is a bounded point-normal patch, NOT independent displacement.
All high-frequency color/roughness/normal textures are original mathematical data.
"""
import copy
import hashlib
import json
import math
import random
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Scripts'/'BlenderPhase5'))
import build_assets as base
OUT=ROOT/'Assets'/'Phase6'
base.OUT=OUT
PI=math.pi
CAP=.00012
MATERIAL_PARAMETERS=[
    ('GallbladderSerosa',[.405,.423,.345],.285,652,.57,4096),
    ('HepaticCapsule',[.285,.133,.157],.265,635,.14,4096),
    ('PeritonealLining',[.415,.293,.306],.315,613,.43,2048),
    ('OmentalFat',[.59,.445,.295],.325,619,.33,2048),
    ('HepaticBedConnective',[.51,.395,.367],.305,628,.29,2048),
    ('BiliaryDuct',[.485,.440,.345],.295,638,.23,2048),
    ('ArterialLandmark',[.345,.115,.142],.275,625,.09,2048)]
NORMAL_STRENGTH={'GallbladderSerosa':.085,'HepaticCapsule':.075,
                 'PeritonealLining':.08,'OmentalFat':.11}


def periodic_noise(size,grid,seed):
    """Original smooth colour field, continuous across cylindrical U seams."""
    rng=np.random.default_rng(seed)
    coarse=rng.random((grid+1,grid+1),dtype=np.float32);coarse[:,-1]=coarse[:,0]
    x=np.arange(size,dtype=np.float32)*grid/size
    ix=x.astype(np.int32);t=x-ix;t=t*t*(3-2*t)
    return ((1-t[None,:])*(1-t[:,None])*coarse[ix[:,None],ix[None,:]]+
            t[None,:]*(1-t[:,None])*coarse[ix[:,None],ix[None,:]+1]+
            (1-t[None,:])*t[:,None]*coarse[ix[:,None]+1,ix[None,:]]+
            t[None,:]*t[:,None]*coarse[ix[:,None]+1,ix[None,:]+1])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pn_surface(vertices,faces,uvs,subdivision=8,locked=None):
    """Cubic PN triangle with a Euclidean bound from its physical triangle.

    Identical shared edge normals/weights yield identical edge positions. The
    cap is applied after computing the PN offset, so it holds for every state
    when the runtime recomputes this patch using current simulation positions.
    """
    p=np.asarray(vertices,dtype=float);f=np.asarray(faces,dtype=np.int32)
    ns=np.asarray(base.normals(vertices,faces));uv=np.asarray(uvs)
    out=[];norm=[];tex=[];tris=[];src=[];weights=[];offsets=[]
    lock=np.zeros(len(p),dtype=bool) if locked is None else np.asarray(locked,dtype=bool)
    for tid,(a,b,c) in enumerate(f):
        pp=p[[a,b,c]];nn=ns[[a,b,c]];tu=uv[[a,b,c]].copy()
        if np.ptp(tu[:,0])>.5:tu[tu[:,0]<.5,0]+=1
        def edge(i,j):return (2*pp[i]+pp[j]-np.dot(pp[j]-pp[i],nn[i])*nn[i])/3
        e01,e10,e12,e21,e20,e02=[edge(i,j) for i,j in [(0,1),(1,0),(1,2),(2,1),(2,0),(0,2)]]
        center=(e01+e10+e12+e21+e20+e02)/6
        center=center+(center-pp.mean(axis=0))*.5
        idx={}
        for j in range(subdivision+1):
            for k in range(subdivision+1-j):
                u=1-(j+k)/subdivision;v=j/subdivision;w=k/subdivision
                bary=np.array([u,v,w]);linear=bary@pp
                curved=pp[0]*u**3+pp[1]*v**3+pp[2]*w**3+3*(e01*u*u*v+e10*u*v*v+e12*v*v*w+e21*v*w*w+e20*u*w*w+e02*u*u*w)+6*center*u*v*w
                delta=curved-linear;d=float(np.linalg.norm(delta))
                if d>CAP:delta*=CAP/d
                # A continuous shared-edge mask avoids cracks at the border of
                # the frozen bed. Every triangle with three locked vertices is
                # exactly physical; the 8mm safety neighborhood encloses the bed.
                delta*=float(bary@(~lock[[a,b,c]]))
                idx[(j,k)]=len(out);out.append((linear+delta).tolist())
                n=bary@nn;n/=max(np.linalg.norm(n),1e-15);norm.append(n.tolist())
                tex.append((bary@tu).tolist());src.append(tid);weights.append(bary.tolist());offsets.append(float(np.linalg.norm(delta)))
        for j in range(subdivision):
            for k in range(subdivision-j):
                tris.append([idx[j,k],idx[j+1,k],idx[j,k+1]])
                if j+k<subdivision-1:tris.append([idx[j+1,k],idx[j+1,k+1],idx[j,k+1]])
    return {'vertices_m':out,'triangles':tris,'uvs':tex,'normals':norm,
            'source_triangle_ids':src,'barycentrics':weights,'subdivision':subdivision,
            'method':'bounded_pn_triangle','max_offset_m':CAP,
            'measured_max_offset_m':max(offsets),'locked_source_vertex_ids':np.flatnonzero(lock).tolist()}


def vessel_mask(size,seed,amount=10,width_scale=1.0,neck_flow=False):
    """Tapered branching vessels with inherited directions, no image pixels.

    Several calibres remain visible at the operative camera distance. A parent
    and its child share a tangent before diverging, avoiding disconnected hairs.
    """
    rng=random.Random(seed);mask=np.zeros((size,size),dtype=np.float32)
    def stroke(a,b,width,strength):
        x0,y0=np.asarray(a)*size;x1,y1=np.asarray(b)*size
        physical_radius=width*size
        # Approximate pixel filtering keeps tiny branches continuous without
        # turning every terminal twig into an equally thick opaque line.
        radius=math.sqrt(physical_radius*physical_radius+.6*.6)
        strength*=min(1.,physical_radius/.6)
        xlo=max(0,int(min(x0,x1)-radius*3));xhi=min(size,int(max(x0,x1)+radius*3)+1)
        ylo=max(0,int(min(y0,y1)-radius*3));yhi=min(size,int(max(y0,y1)+radius*3)+1)
        if xlo>=xhi or ylo>=yhi:return
        yy,xx=np.mgrid[ylo:yhi,xlo:xhi]
        dx,dy=x1-x0,y1-y0;t=np.clip(((xx-x0)*dx+(yy-y0)*dy)/(dx*dx+dy*dy+1e-12),0,1)
        d2=(xx-x0-t*dx)**2+(yy-y0-t*dy)**2
        local=np.exp(-d2/(radius*radius))*strength
        mask[ylo:yhi,xlo:xhi]=np.maximum(mask[ylo:yhi,xlo:xhi],local)
    def branch(x,y,angle,length,width,depth):
        points=[];angles=[];steps=max(12,int(length*180));phase=rng.random()*PI*2
        for i in range(steps+1):
            t=i/steps;aa=angle+.23*math.sin(t*3.4+phase)+.09*math.sin(t*8+phase)
            if i:x+=math.cos(aa)*length/steps;y+=math.sin(aa)*length/steps
            points.append((x,y));angles.append(aa)
        for i in range(steps):
            # Wrap along U, matching the organ's cylindrical UV seam.
            for shift in (-1,0,1):
                a=(points[i][0]+shift,points[i][1]);b=(points[i+1][0]+shift,points[i+1][1])
                stroke(a,b,width*(1-.82*i/steps),min(1.,(1-i/steps)*4))
        if depth:
            for t in (rng.uniform(.18,.30),rng.uniform(.40,.58),rng.uniform(.67,.81)):
                i=int(t*steps);px,py=points[i]
                branch(px,py,angles[i]+rng.choice((-1,1))*rng.uniform(.35,.85),length*rng.uniform(.24,.44),width*.46,depth-1)
    for i in range(amount):
        if neck_flow:
            branch((i+.4+rng.random()*.2)/amount,-.015,rng.uniform(1.15,1.95),
                   rng.uniform(.68,1.02),rng.uniform(.0009,.00145)*width_scale,2)
        else:
            # Some paths enter from outside the map so the visible region does
            # not read as repeated isolated branch stamps.
            branch(rng.uniform(-.1,1.1),rng.uniform(-.1,1.0),rng.uniform(-PI,PI),
                   rng.uniform(.24,.46),rng.uniform(.0008,.00145)*width_scale,2)
    return mask


def textures(name,color,seed,roughness,vessel_strength,size=2048):
    folder=OUT/'textures';folder.mkdir(parents=True,exist_ok=True)
    n0=periodic_noise(size,6,seed);n1=periodic_noise(size,28,seed+1)
    n2=periodic_noise(size,160,seed+2);n3=periodic_noise(size,11,seed+3)
    vessels=vessel_mask(size,seed,5 if name=='GallbladderSerosa' else 15 if name=='PeritonealLining' else 9,
                        neck_flow=name=='GallbladderSerosa')
    variation=(n1-.5)*.025+(n2-.5)*.009
    rgb=np.broadcast_to(np.asarray(color,dtype=np.float32),(size,size,3)).copy()
    rgb+=variation[:,:,None]*np.array([1,.83,.78],dtype=np.float32)
    def mix(target,weight):
        nonlocal rgb
        alpha=np.clip(weight,0,1).astype(np.float32)[:,:,None]
        rgb=rgb*(1-alpha)+np.asarray(target,dtype=np.float32)*alpha
    if name=='GallbladderSerosa':
        # Grey-olive serosa, irregular ivory connective patches and subtle pink
        # vascular regions. These are albedo variations, never baked shading.
        mix([.515,.495,.420],np.clip((n0-.22)*1.25,0,.70))
        mix([.455,.332,.330],np.clip((n3-.48)*1.45,0,.34))
        mix([.290,.355,.315],np.clip((.43-n0)*1.2,0,.26))
        # Image top corresponds to Blender V=1 (the authored neck region).
        row=np.arange(size,dtype=np.float32)/max(size-1,1)
        neck=np.clip((.28-row)/.28,0,1)[:,None]*(.28+.30*n3)
        mix([.50,.365,.345],neck)
    elif name=='HepaticCapsule':
        mix([.385,.220,.245],np.clip((n0-.25)*.85,0,.42))
        mix([.230,.115,.146],np.clip((.57-n3)*.78,0,.30))
        # Fine translucent capsule markings, separate from dark capillaries.
        membrane=vessel_mask(size,seed+83,16,.40)
        mix([.55,.405,.405],membrane*.09)
        del membrane
    elif name=='PeritonealLining':
        mix([.495,.395,.345],np.clip((n0-.25)*1.1,0,.55))
        mix([.355,.255,.310],np.clip((n3-.35)*.8,0,.40))
    elif name=='OmentalFat':
        mix([.685,.545,.365],np.clip((n0-.3)*.85,0,.45))
        mix([.525,.355,.315],np.clip((n3-.50)*.75,0,.25))
    if name=='OmentalFat':
        septa=np.clip((np.abs(n1-.5)-.17)*.12,0,.025)
        rgb+=septa[:,:,None]*np.array([.55,.43,.35],dtype=np.float32)
    # A broad, low-opacity fringe beneath fine vessel cores creates a buried
    # appearance rather than opaque painted wires. No shadow/highlight texels.
    fringe=np.sqrt(vessels)
    mix([.48,.265,.285],fringe*vessel_strength*.13)
    mix([.26,.105,.145],vessels*vessel_strength)
    paths={'base_color_texture':f'textures/{name}_base.png','roughness_texture':f'textures/{name}_roughness.png','normal_texture':f'textures/{name}_normal.png'}
    base.write_png(OUT/paths['base_color_texture'],rgb)
    del rgb,vessels,fringe,n0,n3
    # 4K color / 2K roughness+normals. Spatial normal amplitude is intentionally
    # low; it adds shading detail and does not claim extra physical geometry.
    if size==4096:n1=n1[::2,::2];n2=n2[::2,::2]
    rough=np.clip(roughness+(n1-.5)*.055+(n2-.5)*.018,.20,.41)
    # The old high-frequency-dominant map read as pebbled rubber at close range.
    # Keep fine serosal relief subtle and independent of the geometric labels.
    height=n1*.72+n2*.28;gy,gx=np.gradient(height)
    nm=np.stack([-gx*2.0,-gy*2.0,np.ones_like(height)],axis=-1);nm/=np.linalg.norm(nm,axis=-1,keepdims=True)
    base.write_png(OUT/paths['roughness_texture'],np.repeat(rough[:,:,None],3,axis=2))
    base.write_png(OUT/paths['normal_texture'],nm*.5+.5)
    return paths


def material(name,color,roughness,seed,vessels,size):
    paths={key:f'textures/{name}_{suffix}.png' for key,suffix in [('base_color_texture','base'),('roughness_texture','roughness'),('normal_texture','normal')]}
    if '--reuse-textures' not in sys.argv or not all((OUT/path).exists() for path in paths.values()):
        paths=textures(name,color,seed,roughness,vessels,size)
    mat=bpy.data.materials.get(name) or bpy.data.materials.new(name);mat.use_nodes=True
    # The hepatic-bed material is used by UE's dynamic attachment bridge, not a
    # standalone Blender mesh. Keep its editable nodes across repeated saves.
    mat.use_fake_user=True
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;p=nodes.get('Principled BSDF')
    # Materials-only updates replace image nodes without altering object data.
    for node in list(nodes):
        if node.type in ('TEX_IMAGE','NORMAL_MAP'):nodes.remove(node)
    p.inputs['Roughness'].default_value=roughness;p.inputs['IOR'].default_value=1.38
    p.inputs['Subsurface Weight'].default_value=.07
    p.inputs['Subsurface Radius'].default_value=(.0012,.0006,.0003)
    # Match the actual UE single-lobe wet surface. No Blender-only coat is used.
    p.inputs['Coat Weight'].default_value=0
    for key,target in [('base_color_texture','Base Color'),('roughness_texture','Roughness')]:
        t=nodes.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(OUT/paths[key]));t.image.filepath='//'+paths[key]
        if key!='base_color_texture':t.image.colorspace_settings.name='Non-Color'
        links.new(t.outputs['Color'],p.inputs[target])
    t=nodes.new('ShaderNodeTexImage');t.image=bpy.data.images.load(str(OUT/paths['normal_texture']));t.image.filepath='//'+paths['normal_texture'];t.image.colorspace_settings.name='Non-Color'
    normal_strength=NORMAL_STRENGTH.get(name,.09)
    nm=nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=normal_strength
    links.new(t.outputs['Color'],nm.inputs['Color']);links.new(nm.outputs['Normal'],p.inputs['Normal'])
    desc={'name':name,'base_color':color,'roughness':roughness,'metallic':0,'specular':.32,
          'subsurface_color':[.29,.12,.13] if name!='GallbladderSerosa' else [.30,.21,.185],
          'subsurface_opacity':.95,'subsurface_weight':.07,'ior':1.38,'normal_strength':normal_strength,
          'wet_surface_model':'opaque single microfacet lobe; low roughness plus subsurface shading, no unimplemented clear-coat claim',
          'base_texture_resolution':size,'aux_texture_resolution':2048,'ue_material':'/Game/Materials/M_AnatomyPhase6',**paths}
    return mat,desc


def fbx(obj,object_id):
    """Export authored coordinates in cm; Unreal import disables axis conversion.

    Legacy UE FBX always mirrors Y in FFbxDataConverter::ConvertPos even with
    scene-axis conversion disabled. Export (100X,-100Y,100Z) and reverse faces;
    set global_scale .01 to cancel Blender's implicit x100 FBX node scale.
    The final UE coordinate mapping is Xue=100Xbl,Yue=100Ybl,Zue=100Zbl.
    Importer vertex comparison is required before accepting UE integration.
    """
    directory=OUT/'meshes';directory.mkdir(exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    dup=obj.copy();dup.data=obj.data.copy();bpy.context.collection.objects.link(dup)
    dup.name=f'SM_{object_id}';dup.data.materials.clear()
    # Preserve the actual source shading normals before applying handedness.
    sn=np.zeros((len(obj.data.vertices),3))
    for loop,n in zip(obj.data.loops,obj.data.corner_normals):sn[loop.vertex_index]+=np.asarray(n.vector)
    sn/=np.maximum(np.linalg.norm(sn,axis=1,keepdims=True),1e-15)
    for v in dup.data.vertices:v.co.x*=100;v.co.y*=-100;v.co.z*=100
    dup.data.flip_normals()
    sn[:,1]*=-1;dup.data.normals_split_custom_set_from_vertices(sn.tolist())
    dup.select_set(True);bpy.context.view_layer.objects.active=dup
    path=directory/f'SM_{object_id}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'MESH'},
        global_scale=.01,apply_unit_scale=False,apply_scale_options='FBX_SCALE_NONE',
        axis_forward='-Y',axis_up='Z',use_space_transform=False,bake_space_transform=False,
        use_mesh_modifiers=False,mesh_smooth_type='FACE',use_tspace=True,add_leaf_bones=False,
        bake_anim=False,path_mode='AUTO')
    mesh=dup.data;bpy.data.objects.remove(dup,do_unlink=True);bpy.data.meshes.remove(mesh)
    return {'static_mesh_asset':f'/Game/Phase6/Meshes/SM_{object_id}.SM_{object_id}',
            'fbx_file':f'meshes/SM_{object_id}.fbx','fbx_units':'cm',
            'fbx_mapping':'raw vertices = (100X,-100Y,100Z), reversed triangle winding; identity node scale; legacy UE FBX Y mirror restores JSON XYZ centimetres. Scene/unit conversion disabled.'}


def main(render=False):
    OUT.mkdir(parents=True,exist_ok=True)
    src=ROOT/'Assets'/'Phase5'/'physics-mesh.json'
    shutil.copyfile(src,OUT/'physics-mesh.json')
    data=json.loads(src.read_text(encoding='utf8'))
    old=json.loads((ROOT/'Assets'/'Phase5'/'scene.json').read_text(encoding='utf8'))
    scene_data=copy.deepcopy(old);scene_data['phase']=6
    scene_data['asset_revision']='phase6-visual-v2-materials';scene_data['static_objects']=[]
    scene_data['camera']={'position_m':[.009,-.122,.088],'target_m':[.003,-.003,.019],'fov_degrees':64}
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.preferences.filepaths.save_version=0
    s=bpy.context.scene;s.unit_settings.system='METRIC';s.unit_settings.scale_length=1
    s.render.engine='CYCLES';s.cycles.samples=64;s.cycles.use_denoising=True
    s.render.resolution_x=1600;s.render.resolution_y=1200;s.render.resolution_percentage=100
    s.render.image_settings.file_format='PNG';s.render.image_settings.color_mode='RGB'
    s.world=bpy.data.worlds.new('Phase6AbdominalEnvironment');s.world.use_nodes=True
    s.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.08,.035,.025,1)
    s.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.035
    s.view_settings.view_transform='AgX';s.view_settings.exposure=-.1
    mats={}
    for args in MATERIAL_PARAMETERS:
        mats[args[0]]=material(*args);print('PHASE6_TEXTURE_READY',args[0],flush=True)
    scene_data['material_sets']={name:desc for name,(_,desc) in mats.items()}
    scene_data['dynamic_surface']['material']=mats['GallbladderSerosa'][1]
    scene_data['attachment_material']=mats['HepaticBedConnective'][1]
    scene_data['attachment_bridge']['material']=mats['HepaticBedConnective'][1]
    d=scene_data['dynamic_surface'];dyn=pn_surface(d['vertices_m'],d['triangles'],d['uvs'],8)
    scene_data['dynamic_display']={**dyn,'id':100,'binding':'Recompute bounded PN on every accepted physical boundary state; exported GPU geometry uses exactly this surface.'}
    gb=base.make_object('Gallbladder_HighPrecision_Display',dyn['vertices_m'],dyn['triangles'],dyn['uvs'],mats['GallbladderSerosa'][0])
    gb.data.normals_split_custom_set_from_vertices(dyn['normals'])
    gb['object_id']=100;gb['physical_visual_max_offset_m']=CAP
    proxy=base.make_object('Gallbladder_Physics_Proxy',d['vertices_m'],d['triangles'],d['uvs'])
    proxy.hide_render=True;proxy.hide_set(True);proxy['role']='Unmodified Phase 5 physical wall reference'
    for name,ids in [('HepaticBedAttachment',data['attachment_vertex_ids']),('NeckConstraint',data['fixed_vertex_ids'])]:
        group=proxy.vertex_groups.new(name=name);group.add(ids,1,'REPLACE')
    objects=[]
    def add(name,oid,geo,matname,description,source=None,display=None):
        v,f,uv=geo;ob=base.make_object(name,v,f,uv,mats[matname][0]);ob['object_id']=oid;ob['role']=description
        if display:
            ob.data.normals_split_custom_set_from_vertices(display['normals'])
            locked_ids=set(display.get('locked_source_vertex_ids',[]))
            if locked_ids and source:
                frozen=[i for i,t in enumerate(display['source_triangle_ids']) if all(v in locked_ids for v in source['triangles'][t])]
                if frozen:ob.vertex_groups.new(name='HepaticBedLockedDisplay').add(frozen,1,'REPLACE')
        item=copy.deepcopy(source) if source else {'name':name,'id':oid,'vertices_m':v,'triangles':f,'uvs':uv,'collision':False,'description':description}
        item['material']=mats[matname][1]
        if display:item['display_mesh']=display
        item.update(fbx(ob,oid));scene_data['static_objects'].append(item);objects.append(ob)
        return item
    liver=next(o for o in old['static_objects'] if o['id']==200)
    # Preserve the entire local hepatic bed plus a safety neighborhood, including
    # adjacent triangles. The actual collision topology remains byte-equivalent.
    verts=np.asarray(liver['vertices_m']);anchors=np.asarray(data['attachment_anchor_positions_m'])
    locked=np.min(np.linalg.norm(verts[:,None,:]-anchors[None,:,:],axis=2),axis=1)<.008
    ld=pn_surface(liver['vertices_m'],liver['triangles'],liver['uvs'],4,locked)
    add('Liver_HighPrecision_Capsule',200,(ld['vertices_m'],ld['triangles'],ld['uvs']),'HepaticCapsule','Detailed bounded surface; all bed-neighborhood triangles remain exactly physical.',liver,ld)
    def cavity(u,v):
        az=PI*u;lat=-PI*.46+PI*.87*v
        fold=.0011*math.sin(9*az+2*math.sin(lat*3))+.00065*math.sin(17*lat+az*4)
        return [(.19+fold)*math.cos(lat)*math.cos(az),.029+(.18+fold)*math.cos(lat)*math.sin(az),.003+(.119+fold)*math.sin(lat)]
    v,f,uv=base.grid_mesh(cavity,192,96)
    add('LocalPeritonealCavity',300,(v,[[c,b,a] for a,b,c in f],uv),'PeritonealLining','Expanded local posterior cavity with actual small serosal folds, outside the working envelope.')
    def lower(u,v):
        x=(u-.5)*.38;y=-.15+v*.35
        z=-.066+.023*(x/.19)**2+.014*((y-.03)/.17)**2
        z+=.0007*math.sin(22*PI*u+2*math.sin(5*PI*v))+.0004*math.sin(18*PI*v)
        return [x,y,z]
    add('InferiorCavitySurface',301,base.grid_mesh(lower,160,112),'PeritonealLining','Expanded lower cavity with fine folds; no fictitious contact response.')
    def fat(u,v):
        x=(u-.5)*.35;y=-.15+v*.32
        z=-.043+.018*(x/.175)**2+.006*((y-.03)/.16)**2
        a=math.sin(29*PI*u+1.9*math.sin(8*PI*v))**2;b=math.sin(25*PI*v+1.2*math.sin(9*PI*u))**2
        z+=.0015*a*b+.0006*math.sin(9*PI*u+3*PI*v)**2
        return [x,y,z]
    add('LobulatedOmentalSkirt',311,base.grid_mesh(fat,240,176),'OmentalFat','Continuous original lobulated fat layer extending out of crop; authored geometric lobules.')
    def anterior(u,v):
        x=(u-.5)*.30;y=-.112+v*.045+.006*math.sin(2*PI*u)
        z=-.019+.009*v+.004*math.sin(3*PI*u)**2
        z+=.0018*math.sin(22*PI*u+3*PI*v)**2*math.sin(12*PI*v+4*PI*u)**2
        return [x,y,z]
    add('AnteriorOmentalFold',310,base.grid_mesh(anterior,200,64),'OmentalFat','Detailed anterior omentum below the instrument entry corridor.')
    for oid,name,radius,mat,shift in [(400,'CysticDuctLandmark',.00145,'BiliaryDuct',0),(401,'CysticArteryLandmark',.00055,'ArterialLandmark',.003)]:
        pts=[]
        for i in range(97):
            t=i/96;pts.append([.0035+.019*t+.002*math.sin(PI*t)+shift,.025+.034*t+shift,.026-.014*t+.002*math.sin(PI*t)+(shift/3)])
        add(name,oid,base.tube_mesh(pts,radius,32),mat,'Orientation landmark, no duct/artery physical simulation; clinical review pending.')
    scene_data['appearance_notes']=['Original 4K hero-color and 2K auxiliary maps; no photographic texels or baked highlights.',
        'Blender and UE share the same detailed exported geometry; no Blender-only subdivision modifier.',
        'Dynamic display uses bounded PN with <=0.12mm offset from the accepted physical boundary.',
        'Static liver bed neighborhood is unchanged; other liver patches are bounded by 0.12mm.',
        'Static FBX in explicit cm; importer must verify correspondence before acceptance.',
        'Normal maps change shading normals only; dataset geometric normals remain explicit geometry normals.']
    (OUT/'scene.json').write_text(json.dumps(scene_data,separators=(',',':')),encoding='utf8')
    camd=bpy.data.cameras.new('Phase6LaparoscopePreview');cam=bpy.data.objects.new(camd.name,camd);s.collection.objects.link(cam)
    cam.location=scene_data['camera']['position_m'];target=Vector(scene_data['camera']['target_m'])
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();camd.angle=math.radians(64);camd.clip_start=.0005;camd.clip_end=2;s.camera=cam
    for name,off,power,size,col in [('ScopeKey',(-.004,-.003,.002),.72,.0045,(1,.89,.80)),('ScopeFill',(.004,0,0),.18,.006,(.91,.95,1))]:
        light=bpy.data.lights.new(name,'AREA');light.energy=power;light.shape='DISK';light.size=size;light.color=col
        ob=bpy.data.objects.new(name,light);s.collection.objects.link(ob);ob.location=cam.location+Vector(off);ob.rotation_euler=(target-ob.location).to_track_quat('-Z','Y').to_euler()
    s['provenance']='Original procedural anatomy and texture authoring. Reference inspection only. No teacher mesh or photographic pixels imported.'
    s['clinical_validation']='Provisional local engineering anatomy; physician review pending.'
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'EndoForge_Anatomy.blend'))
    audit={'schema':'endoforge.phase6.asset-audit.v1','passed':True,'blender_version':bpy.app.version_string,
           'physics_mesh_sha256':sha(src),'copied_physics_sha256':sha(OUT/'physics-mesh.json'),
           'physics_unchanged':src.read_bytes()==(OUT/'physics-mesh.json').read_bytes(),
           'dynamic_display':{'vertices':len(dyn['vertices_m']),'triangles':len(dyn['triangles']),'max_offset_m':dyn['measured_max_offset_m'],'cap_m':CAP},
           'liver_display':{'vertices':len(ld['vertices_m']),'triangles':len(ld['triangles']),'max_offset_m':ld['measured_max_offset_m'],'locked_source_vertices':int(locked.sum())},
           'objects':{o['name']:base.topology(o.get('display_mesh',o)['vertices_m'],o.get('display_mesh',o)['triangles']) for o in scene_data['static_objects']},
           'clinical_review':'pending','ue_import_geometry_verification':'required; this Blender audit does not claim UE import passed'}
    for obj in audit['objects'].values():
        if obj['degenerate_triangles'] or obj['nonmanifold_edges']:audit['passed']=False
    (OUT/'geometry-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    provenance={'schema':'endoforge.original-asset-provenance.v1','creator':'EndoForge procedural Blender authoring',
                'script':'Scripts/BlenderPhase6/build_assets.py','script_sha256':sha(Path(__file__)),
                'reference_policy':'Local teacher anatomy atlases and CholecSeg8K were inspected for organ relationships, serosal color/vascular detail and wet appearance. No source mesh or image pixel data are consumed by this script.',
                'project2_excluded':True,'source_copied_into_assets':False,
                'physical_asset_origin':'Preserved EndoForge Phase 5 authored physical asset, exact byte copy.',
                'limitation':'Not patient-specific anatomy; organ relationship and material parameters pending clinical validation.',
                'files':{str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ('provenance.json','anatomy-preview.png')}}
    (OUT/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    if render:
        s.render.filepath=str(OUT/'anatomy-preview.png');bpy.ops.render.render(write_still=True)
    print('PHASE6_ASSETS_COMPLETE',json.dumps(audit),flush=True)


def geometry_digest(scene):
    """Hash every non-appearance scene field, including collision and bindings."""
    def strip(value):
        if isinstance(value,dict):
            return {k:strip(v) for k,v in value.items()
                    if k not in ('material','material_sets','attachment_material','appearance_notes','asset_revision')}
        if isinstance(value,list):return [strip(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(strip(scene),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def blend_geometry_digest():
    """Object transforms, vertices, indices, UVs and stored smooth normals."""
    digest=hashlib.sha256()
    for obj in sorted((o for o in bpy.data.objects if o.type=='MESH'),key=lambda o:o.name):
        digest.update(obj.name.encode());digest.update(np.asarray(obj.matrix_world,dtype=np.float64).tobytes())
        digest.update(np.asarray([tuple(v.co) for v in obj.data.vertices],dtype=np.float64).tobytes())
        digest.update(np.asarray([loop.vertex_index for loop in obj.data.loops],dtype=np.int32).tobytes())
        digest.update(np.asarray([poly.loop_total for poly in obj.data.polygons],dtype=np.int32).tobytes())
        for layer in obj.data.uv_layers:
            digest.update(np.asarray([tuple(v.uv) for v in layer.data],dtype=np.float64).tobytes())
        digest.update(np.asarray([tuple(n.vector) for n in obj.data.corner_normals],dtype=np.float64).tobytes())
    return digest.hexdigest()


def materials_only():
    """Revise albedo/roughness/normal materials without regenerating geometry."""
    source=OUT/'scene.json';scene=json.loads(source.read_text(encoding='utf8'))
    geometry_before=geometry_digest(scene)
    protected=[OUT/'physics-mesh.json',*sorted((OUT/'meshes').glob('*.fbx'))]
    file_before={p.relative_to(OUT).as_posix():sha(p) for p in protected}
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'EndoForge_Anatomy.blend'),use_scripts=False)
    bpy.context.preferences.filepaths.save_version=0
    blend_before=blend_geometry_digest()
    descriptions={}
    for args in MATERIAL_PARAMETERS:
        _,descriptions[args[0]]=material(*args)
        print('PHASE6_MATERIAL_UPDATED',args[0],flush=True)
    # Refresh every nested material reference; preserve the numerical geometry.
    def replace(value):
        if isinstance(value,dict):
            for key,item in list(value.items()):
                if key in ('material','attachment_material') and isinstance(item,dict) and item.get('name') in descriptions:
                    value[key]=copy.deepcopy(descriptions[item['name']])
                else:replace(item)
        elif isinstance(value,list):
            for item in value:replace(item)
    replace(scene);scene['material_sets']=descriptions
    scene['asset_revision']='phase6-visual-v2-materials'
    revision_note='Material revision 2: original multiscale serosal colour, tapered vascular branches, restrained wet roughness and fine normal detail; no photographic pixels, baked lighting or geometry changes.'
    if revision_note not in scene['appearance_notes']:scene['appearance_notes'].append(revision_note)
    for im in list(bpy.data.images):
        if im.source=='FILE' and im.users==0:bpy.data.images.remove(im)
    geometry_after=geometry_digest(scene);blend_after=blend_geometry_digest()
    assert geometry_after==geometry_before,'Material-only update changed the scene geometry contract'
    assert blend_after==blend_before,'Material-only update changed Blender object geometry'
    assert file_before=={p.relative_to(OUT).as_posix():sha(p) for p in protected}
    source.write_text(json.dumps(scene,separators=(',',':')),encoding='utf8')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'EndoForge_Anatomy.blend'))
    report={'schema':'endoforge.phase6.material-only-revision.v1','passed':True,
            'scene_nonappearance_sha256_before':geometry_before,'scene_nonappearance_sha256_after':geometry_after,
            'blend_geometry_sha256_before':blend_before,'blend_geometry_sha256_after':blend_after,
            'unchanged_physics_and_fbx_sha256':file_before,
            'reference_review':['tmp/source-review/references/Cholecyst_CholecSeg8K_VID35_seg8k-contact.jpg',
                                'tmp/source-review/references/Cholecyst_CholecSeg8K_VID52_seg8k-contact.jpg'],
            'source_image_pixels_used':False,'baked_highlights_or_shadows':False,
            'limitation':'Reference-guided original appearance only, not patient anatomy or calibrated clinical optical properties.'}
    (OUT/'material-revision.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('PHASE6_MATERIAL_ONLY_COMPLETE',json.dumps(report),flush=True)


def material_swatches(destination):
    global OUT
    OUT=Path(destination).resolve();OUT.mkdir(parents=True,exist_ok=True)
    report=[]
    for name,color,roughness,seed,vessels,size in MATERIAL_PARAMETERS:
        paths=textures(name,color,seed,roughness,vessels,512)
        report.append({'name':name,'base_color':color,'roughness':roughness,
                       'normal_strength':NORMAL_STRENGTH.get(name,.09),**paths})
    (OUT/'swatches.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('PHASE6_SWATCHES_COMPLETE',str(OUT),flush=True)


if __name__=='__main__':
    if '--material-swatches' in sys.argv:material_swatches(sys.argv[sys.argv.index('--material-swatches')+1])
    elif '--materials-only' in sys.argv:materials_only()
    else:main('--render' in sys.argv)
