"""Smooth thin-plate hepatic-bed field used by original Phase 7 authoring.

C1 interpolating field with compact quintic collar; no claim of global C2 at
thin-plate centers. Whole-triangle clearance and runtime tests remain required.
"""
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'Assets/Phase6/physics-mesh.json'

def quintic(x):
    t=np.clip(x,0,1);return t**3*(t*(6*t-15)+10)

def hull(points):
    points=sorted(set(map(tuple,points)))
    def cross(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lower=[];upper=[]
    for p in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    return np.asarray(lower[:-1]+upper[:-1])

def hull_distance(xy,polygon):
    a=polygon;b=np.roll(polygon,-1,axis=0);e=b-a;p=xy[:,None]-a
    t=np.clip(np.einsum('nkj,kj->nk',p,e)/np.sum(e*e,axis=1),0,1)
    distance=np.linalg.norm(p-t[:,:,None]*e,axis=2).min(1)
    inside=np.all(e[None,:,0]*p[:,:,1]-e[None,:,1]*p[:,:,0]>=-1e-14,axis=1)
    return np.where(inside,0,distance)

def macro_top(xy):
    ux=(xy[:,0]-.010)/.104;uy=(xy[:,1]-.052)/(.079*(1-.17*ux))
    r2=ux*ux+uy*uy;c=np.sqrt(np.maximum(0,1-r2))
    # Smooth negative part. Same value on both hemispheres; no max seam.
    negx=.5*(np.sqrt(ux*ux+.02**2)-ux)
    negy=.5*(np.sqrt(uy*uy+.02**2)-uy)
    breadth=1-.23*negx
    window=quintic(c/.40)
    bed=np.exp(-((xy[:,0]-.002)/.024)**2-((xy[:,1]-.012)/.035)**2)
    harmonic=np.cos(.4)*(3*ux*ux*uy-uy**3)+np.sin(.4)*(ux**3-3*ux*uy*uy)
    height=-.018+.040*c*breadth-.007*negy*r2
    height+=window*(-.006*bed+.0024*harmonic)
    return height,c,r2

class ThinPlate:
    def __init__(self,xy,z):
        self.center=xy.mean(0);self.scale=.025;self.points=(xy-self.center)/self.scale
        radius=np.linalg.norm(self.points[:,None]-self.points[None],axis=2)
        kernel=np.where(radius>0,radius**2*np.log(np.maximum(radius,1e-300)),0)
        poly=np.column_stack([np.ones(len(xy)),self.points])
        matrix=np.block([[kernel,poly],[poly.T,np.zeros((3,3))]])
        self.solution=np.linalg.solve(matrix,np.r_[z,np.zeros(3)])
        self.condition=float(np.linalg.cond(matrix))
    def __call__(self,xy):
        x=(xy-self.center)/self.scale;r=np.linalg.norm(x[:,None]-self.points[None],axis=2)
        k=np.where(r>0,r*r*np.log(np.maximum(r,1e-300)),0)
        return k@self.solution[:-3]+np.column_stack([np.ones(len(x)),x])@self.solution[-3:]

def underside(xy,triangles):
    a=triangles[:,0,:2];e=triangles[:,1,:2]-a;f=triangles[:,2,:2]-a
    det=e[:,0]*f[:,1]-e[:,1]*f[:,0];good=np.abs(det)>1e-14
    a=a[good];e=e[good];f=f[good];det=det[good];t=triangles[good]
    p=xy[:,None]-a
    u=(p[:,:,0]*f[:,1]-p[:,:,1]*f[:,0])/det
    v=(e[:,0]*p[:,:,1]-e[:,1]*p[:,:,0])/det
    inside=(u>=-1e-9)&(v>=-1e-9)&(u+v<=1+1e-9)
    z=t[:,0,2]+u*(t[:,1,2]-t[:,0,2])+v*(t[:,2,2]-t[:,0,2])
    return np.where(inside,z,np.inf).min(1)

def fit_bed_field(anchors, macro_height, equator_window, width=.024, extra=None):
    """Return evaluate(xy), fit for a supplied original smooth macroform.

    macro_height(xy[N,2])->height[N]; equator_window(xy)->weight[N] is one
    near all anchors and smoothly zero with derivatives at the sewn equator.
    Inputs/output metres. Exact sample queries retain anchors to float precision.
    Kernel r²log(r) is C1 (not C2 at centers); quintic collar is C2 away from
    geometric distance singularities. This is deliberately not a blanket C2 claim.
    """
    points=anchors if extra is None else np.vstack([anchors,extra])
    macro=macro_height(points[:,:2])
    # Interpolate residual to macroform; compact C2 transition reaches zero
    # outside the anchor hull collar and before the macro-liver equator.
    polygon=hull(anchors[:,:2])
    def weight(xy):
        return (1-quintic(hull_distance(xy,polygon)/width))*equator_window(xy)
    w=weight(points[:,:2]);assert np.min(w)>.01
    fit=ThinPlate(points[:,:2],(points[:,2]-macro)/w)
    def evaluate(xy):return macro_height(xy)+weight(xy)*fit(xy)
    return evaluate,fit

def fit_field(anchors,extra=None,width=.020):
    return fit_bed_field(anchors,lambda xy:macro_top(xy)[0],
                         lambda xy:quintic((macro_top(xy)[1]-.05)/.35),width,extra)

def macro_mesh_height(vertices,faces):
    """Optional upper-sheet mesh adapter; introduces its existing PL facets.

    Prefer an analytic macro_height when available. This adapter requires an
    upper surface that is a single-valued XY field and rejects uncovered queries.
    """
    triangles=np.asarray(vertices,dtype=float)[np.asarray(faces,dtype=int)]
    def evaluate(xy):
        output=[]
        # Mirroring z allows reusing the verified lowest-intersection helper.
        mirrored=triangles.copy();mirrored[:,:,2]*=-1
        for chunk in np.array_split(np.asarray(xy),max(1,int(np.ceil(len(xy)/256)))):
            values=-underside(chunk,mirrored)
            if not np.isfinite(values).all():raise ValueError('Macro height query outside upper sheet')
            output.extend(values.tolist())
        return np.asarray(output)
    return evaluate
