"""Original branching pigment fields with irregular flow and tapering hierarchy.

No photographic pixels, measured vessel anatomy or raised geometry. These masks
are an authored visual approximation; branches inherit their parent's position.
"""
import math
import numpy as np


def vascular_fields(size, seed, amount=4, width_scale=1.0, length_scale=1.0):
    rng = np.random.default_rng(seed)
    core = np.zeros((size, size), np.float32)
    halo = np.zeros_like(core)

    def stroke(a, b, width, alpha):
        radius = max(.45, width*size)
        soft_radius = radius*2.5+.7
        for wrap in (-1, 0, 1):
            p = (a+[wrap, 0])*[size, size-1]
            q = (b+[wrap, 0])*[size, size-1]
            lo = np.maximum(np.floor(np.minimum(p,q)-soft_radius*2).astype(int),0)
            hi = np.minimum(np.ceil(np.maximum(p,q)+soft_radius*2).astype(int),size-1)
            if np.any(hi<lo): continue
            yy,xx = np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            d=q-p; t=np.clip(((xx-p[0])*d[0]+(yy-p[1])*d[1])/max(float(d@d),1e-12),0,1)
            dist=(xx-p[0]-t*d[0])**2+(yy-p[1]-t*d[1])**2
            region=np.s_[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            np.maximum(core[region],np.exp(-dist/(2*radius*radius))*alpha,out=core[region])
            np.maximum(halo[region],np.exp(-dist/(2*soft_radius*soft_radius))*alpha,out=halo[region])

    def grow(start, heading, length, width, alpha, depth):
        count=max(18,int(length*size/2.0))
        positions=[np.asarray(start,float)]; angles=[]
        waviness=rng.uniform(.20,.42); wave=rng.uniform(0,math.tau)
        drift=rng.uniform(-.85,.85); walk=0.
        for i in range(count):
            t=i/count
            walk=.95*walk+rng.normal(0,.045)
            angle=heading+drift*t+waviness*math.sin(t*math.tau*3.5+wave)+walk
            positions.append(positions[-1]+np.array([math.cos(angle),math.sin(angle)])*length/count)
            angles.append(angle)
            taper=(1-.94*t)**.80
            stroke(positions[-2],positions[-1],width*taper,alpha*(.8+.2*math.sin(math.pi*t)))
        if depth:
            for j,at in enumerate([.24,.49,.72]):
                at+=rng.uniform(-.055,.055); k=min(count-1,int(count*at))
                side=(-1 if j%2 else 1)*rng.uniform(.42,.8)
                grow(positions[k],angles[k]+side,length*rng.uniform(.23,.40),width*.46,alpha*.72,depth-1)
    for i in range(amount):
        # Distributed roots, short hierarchical branches, no disjoint long hairs.
        root=np.array([(i+.45+rng.uniform(-.25,.25))/amount,rng.uniform(.69,.95)])
        grow(root,-math.pi/2+rng.uniform(-.40,.40),rng.uniform(.38,.58)*length_scale,
             rng.uniform(.00065,.00105)*width_scale,rng.uniform(.50,.80),2)
    return core,halo
