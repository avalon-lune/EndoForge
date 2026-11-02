"""Original curved vascular pigment fields for EndoForge's engineering tissues.

These deterministic, periodic-U colour masks are authored illustration, not
patient vasculature, a blood-flow model, relief, or baked illumination. NumPy is
the only dependency so the same generator runs inside the installed Blender.
"""
import numpy as np


def _curve(control, t):
    t=np.asarray(t,dtype=np.float64)[...,None];s=1-t
    p=np.asarray(control,dtype=np.float64)
    return s**3*p[0]+3*s*s*t*p[1]+3*s*t*t*p[2]+t**3*p[3]


def _tangent(control,t):
    p=np.asarray(control,dtype=np.float64);s=1-t
    d=3*s*s*(p[1]-p[0])+6*s*t*(p[2]-p[1])+3*t*t*(p[3]-p[2])
    return d/max(np.linalg.norm(d),1e-12)


def _paint(core,buried,control,width,opacity):
    size=core.shape[0]
    # Subpixel curve samples bound polyline chord length. The rasterized mark
    # is soft at every edge; it never becomes a hard hair-like line segment.
    control=np.asarray(control,dtype=np.float64)
    length=sum(np.linalg.norm(control[i+1]-control[i]) for i in range(3))
    times=np.linspace(0,1,max(32,int(length*size/2.5)))
    points=_curve(control,times)
    for i,(a,b) in enumerate(zip(points,points[1:])):
        t=(times[i]+times[i+1])/2
        radius=max(.45,width*size*(1-.88*t)**.7)
        halo=radius*3.4+1.0
        strength=opacity*(.48+.52*np.sin(np.pi*(.10+.78*t)))
        for wrap in (-1,0,1):
            p=(a+[wrap,0])*[size,size-1];q=(b+[wrap,0])*[size,size-1]
            lo=np.maximum(np.floor(np.minimum(p,q)-halo*2.3).astype(int),0)
            hi=np.minimum(np.ceil(np.maximum(p,q)+halo*2.3).astype(int),size-1)
            if np.any(hi<lo):continue
            yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            d=q-p;den=max(float(d@d),1e-12)
            u=np.clip(((xx-p[0])*d[0]+(yy-p[1])*d[1])/den,0,1)
            distance2=(xx-p[0]-u*d[0])**2+(yy-p[1]-u*d[1])**2
            tip_fade=np.clip((1-t)*20,0,1)*np.clip(t*28,0,1)
            mark=np.exp(-distance2/(2*radius*radius))*strength*tip_fade
            soft=np.exp(-distance2/(2*halo*halo))*strength*tip_fade
            region=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            np.maximum(core[region],mark,out=core[region])
            np.maximum(buried[region],soft,out=buried[region])


def vascular_fields(size,seed,amount=6,width_scale=1.0):
    """Return tapered curved vessel core and a separate soft subsurface fringe.

    Branch tangents match their parent at the junction. Width and opacity vary;
    the field carries no photographic pixels and no linear polygon-cell net.
    """
    if size<32 or amount<1 or width_scale<=0:raise ValueError('Invalid vascular field size/count/width')
    rng=np.random.default_rng(seed)
    core=np.zeros((size,size),np.float32);buried=np.zeros_like(core)
    for trunk in range(amount):
        start=np.array([rng.uniform(0,1),rng.uniform(-.08,.65)])
        direction=np.array([rng.uniform(-.35,.35),rng.uniform(.32,.60)])
        end=start+direction
        bend=np.array([rng.uniform(-.11,.11),rng.uniform(-.035,.035)])
        control=np.array([start,start+direction*.30+bend,end-direction*.25+bend*.45,end])
        width=rng.uniform(.00065,.00115)*width_scale
        alpha=rng.uniform(.45,.85)
        _paint(core,buried,control,width,alpha)
        for branch in range(rng.integers(2,5)):
            at=rng.uniform(.20,.78);origin=_curve(control,at)
            tangent=_tangent(control,at)
            side=np.array([tangent[1],-tangent[0]])*rng.choice([-1,1])
            length=rng.uniform(.055,.145)
            target=origin+(tangent*.55+side*rng.uniform(.55,1.1))*length
            branch_control=np.array([origin,origin+tangent*length*.35,
                                     target-tangent*length*.32+side*length*.12,target])
            _paint(core,buried,branch_control,width*rng.uniform(.40,.65),alpha*rng.uniform(.55,.80))
    # The field is evaluated with wrapped curve copies; duplicate samples at
    # U=0/1 are not needed by the renderer's repeating sampler.
    return core,buried
