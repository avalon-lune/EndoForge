#pragma once

// Kinematic admission only. No tissue projection and no estimated reaction force.
// A certified interval stays outside the closed rigid surface by clearance_m.
// Unknown intervals fail closed. Parameters follow the native jaw/RCM formula.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <map>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace phase6collision {
inline constexpr const char* Implementation="phase6-rcm-jaw-liver-ccd-v1";
constexpr double Pi=3.14159265358979323846;
constexpr double JawLength=.0145,JawWidth=.0025,JawThickness=.0014;
constexpr double HingeSide=JawThickness*.5+.00010;
struct Vec {
    double x=0,y=0,z=0;
    double& operator[](int i){return i==0?x:i==1?y:z;}
    double operator[](int i)const{return i==0?x:i==1?y:z;}
};
inline Vec operator+(Vec a,Vec b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline Vec operator-(Vec a,Vec b){return {a.x-b.x,a.y-b.y,a.z-b.z};}
inline Vec operator-(Vec a){return {-a.x,-a.y,-a.z};}
inline Vec operator*(Vec a,double s){return {a.x*s,a.y*s,a.z*s};}
inline Vec operator/(Vec a,double s){return a*(1/s);}
inline double dot(Vec a,Vec b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline Vec cross(Vec a,Vec b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline double length(Vec a){return std::sqrt(dot(a,a));}
inline bool finite(Vec a){return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z);}
inline Vec unit(Vec a){double d=length(a);if(!(d>1e-12))throw std::domain_error("degenerate jaw frame");return a/d;}
struct Pose { Vec tip,pivot;double roll_deg=90,angle_deg=40; };
struct Box { Vec center;std::array<Vec,3> axis;Vec half{JawLength*.5,JawWidth*.5,JawThickness*.5}; };
struct Bounds {
    Vec lo{INFINITY,INFINITY,INFINITY},hi{-INFINITY,-INFINITY,-INFINITY};
    void add(Vec p){for(int k=0;k<3;k++){lo[k]=std::min(lo[k],p[k]);hi[k]=std::max(hi[k],p[k]);}}
    void add(const Bounds& b){add(b.lo);add(b.hi);}
};
inline std::array<Box,2> jaws(const Pose& p){
    if(!finite(p.tip)||!finite(p.pivot)||!std::isfinite(p.roll_deg)||!std::isfinite(p.angle_deg))throw std::domain_error("nonfinite jaw pose");
    const Vec a=unit(p.pivot-p.tip),base=unit(cross(a,{0,0,1}));
    const double roll=p.roll_deg*Pi/180,theta=p.angle_deg*Pi/180;
    const Vec s=base*std::cos(roll)+cross(a,base)*std::sin(roll),w=unit(cross(a,s));
    std::array<Box,2> result;
    for(int j=0;j<2;j++){
        const double sign=j?1:-1;const Vec f=-a*std::cos(theta)+s*(sign*std::sin(theta));
        result[j]={p.tip+a*JawLength+s*(sign*HingeSide)+f*(JawLength*.5),{unit(f),w,unit(cross(f,w))}};
    }
    return result;
}
inline Pose interpolate(const Pose& a,const Pose& b,double t){
    return {a.tip+(b.tip-a.tip)*t,a.pivot,a.roll_deg+std::remainder(b.roll_deg-a.roll_deg,360.)*t,a.angle_deg+(b.angle_deg-a.angle_deg)*t};
}
inline Vec corner(const Box& b,int i){Vec p=b.center;for(int k=0;k<3;k++)p=p+b.axis[k]*((i&(1<<k)?1:-1)*b.half[k]);return p;}
inline Bounds bounds(const Box& b){Bounds r;for(int i=0;i<8;i++)r.add(corner(b,i));return r;}
inline double boundsDistance2(const Bounds& a,const Bounds& b){double d=0;for(int k=0;k<3;k++){double v=std::max({a.lo[k]-b.hi[k],b.lo[k]-a.hi[k],0.});d+=v*v;}return d;}
inline Vec local(const Box& b,Vec p){p=p-b.center;return {dot(p,b.axis[0]),dot(p,b.axis[1]),dot(p,b.axis[2])};}
inline double pointBoxDistance2(Vec p,Vec h){double d=0;for(int k=0;k<3;k++){double v=std::max(0.,std::abs(p[k])-h[k]);d+=v*v;}return d;}
inline Vec closestTriangle(Vec p,Vec a,Vec b,Vec c){
    const Vec ab=b-a,ac=c-a,ap=p-a;const double d1=dot(ab,ap),d2=dot(ac,ap);
    if(d1<=0&&d2<=0)return a;
    const Vec bp=p-b;const double d3=dot(ab,bp),d4=dot(ac,bp);if(d3>=0&&d4<=d3)return b;
    const double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return a+ab*(d1/(d1-d3));
    const Vec cp=p-c;const double d5=dot(ab,cp),d6=dot(ac,cp);if(d6>=0&&d5<=d6)return c;
    const double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return a+ac*(d2/(d2-d6));
    const double va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return b+(c-b)*((d4-d3)/((d4-d3)+(d5-d6)));
    const double inv=1/(va+vb+vc);return a+ab*(vb*inv)+ac*(vc*inv);
}
inline double segmentDistance2(Vec p,Vec q,Vec r,Vec s){
    Vec d=q-p,e=s-r,v=p-r;double a=dot(d,d),b=dot(d,e),c=dot(e,e),f=dot(e,v),t=0,u=0;
    if(a<=1e-30&&c<=1e-30)return dot(v,v);
    if(a<=1e-30)u=std::clamp(f/c,0.,1.);
    else {double g=dot(d,v);if(c<=1e-30)t=std::clamp(-g/a,0.,1.);
        else {double den=a*c-b*b;if(den>1e-30)t=std::clamp((b*f-g*c)/den,0.,1.);u=(b*t+f)/c;
            if(u<0){u=0;t=std::clamp(-g/a,0.,1.);}else if(u>1){u=1;t=std::clamp((b-g)/a,0.,1.);}}}
    Vec delta=p+d*t-r-e*u;return dot(delta,delta);
}
inline bool triangleIntersectsBox(const std::array<Vec,3>& t,Vec h){
    const std::array<Vec,3> axes{{{1,0,0},{0,1,0},{0,0,1}}};
    auto separated=[&](Vec a){if(dot(a,a)<1e-30)return false;double lo=dot(t[0],a),hi=lo;for(int i=1;i<3;i++){double p=dot(t[i],a);lo=std::min(lo,p);hi=std::max(hi,p);}double radius=h.x*std::abs(a.x)+h.y*std::abs(a.y)+h.z*std::abs(a.z);return lo>radius||hi<-radius;};
    for(Vec a:axes)if(separated(a))return false;
    if(separated(cross(t[1]-t[0],t[2]-t[0])))return false;
    for(int e=0;e<3;e++)for(Vec a:axes)if(separated(cross(t[(e+1)%3]-t[e],a)))return false;
    return true;
}
inline double triangleBoxDistance2(const Box& box,const std::array<Vec,3>& world){
    std::array<Vec,3> t;for(int i=0;i<3;i++)t[i]=local(box,world[i]);
    if(triangleIntersectsBox(t,box.half))return 0;
    double best=INFINITY;for(Vec p:t)best=std::min(best,pointBoxDistance2(p,box.half));
    std::array<Vec,8> points;for(int i=0;i<8;i++){
        Vec p{(i&1?1:-1)*box.half.x,(i&2?1:-1)*box.half.y,(i&4?1:-1)*box.half.z};points[i]=p;
        Vec d=p-closestTriangle(p,t[0],t[1],t[2]);best=std::min(best,dot(d,d));}
    for(int i=0;i<8;i++)for(int k=0;k<3;k++)if(!(i&(1<<k)))for(int e=0;e<3;e++)
        best=std::min(best,segmentDistance2(points[i],points[i|(1<<k)],t[e],t[(e+1)%3]));
    return std::max(0.,best);
}
inline double segmentOriginDistance(Vec a,Vec b){Vec d=b-a;double n=dot(d,d),t=n>0?std::clamp(-dot(a,d)/n,0.,1.):0;return length(a+d*t);}

// For each material corner, p=tip+A*a(theta)+S*b(theta)+W*w.
// |a|<=2L+T/2; |b|<=hinge+L+T/2; |w|<=W/2.
// The normalized shaft and horizontal roll basis have derivative bounds
// |tip'|/min|pivot-tip| and |tip'_xy|/min|pivot-tip|_xy. Cross products give
// |S'|<=|A'|+2|base'|+|roll'|, |W'|<=|A'|+|S'|.
// Jaw-angle rotation has corner radius <=hypot(L,T/2). Integrating these
// bounds from interval midpoint proves a bound on EVERY jaw point, not samples.
inline double motionBound(const Pose& a,const Pose& b,double begin,double end){
    Pose p=interpolate(a,b,begin),q=interpolate(a,b,end);Vec u=p.pivot-p.tip,v=q.pivot-q.tip;
    double r=segmentOriginDistance(u,v);u.z=v.z=0;double h=segmentOriginDistance(u,v);
    if(!(r>1e-9&&h>1e-9))return INFINITY;
    Vec delta=q.tip-p.tip;double tip=length(delta)*.5;delta.z=0;double ba=tip/r,bb=length(delta)*.5/h;
    double roll=std::abs(std::remainder(b.roll_deg-a.roll_deg,360.))*Pi/180*(end-begin)*.5;
    double theta=std::abs(b.angle_deg-a.angle_deg)*Pi/180*(end-begin)*.5;
    double bs=ba+2*bb+roll;
    return tip+(2*JawLength+JawThickness*.5+JawWidth*.5)*ba+
        (HingeSide+JawLength+JawThickness*.5+JawWidth*.5)*bs+std::hypot(JawLength,JawThickness*.5)*theta;
}
struct Settings {
    double clearance_m=.00015;
    int maximum_intervals=512,maximum_depth=26;
    double minimum_fraction=1./67108864.;
};
struct Result {
    bool blocked=false,initial_valid=false;
    double accepted_fraction=0,initial_clearance_m=0,endpoint_clearance_m=0;
    int witness_triangle=-1,work_count=0;
    std::string reason;
};
class Collider {
    struct Node {Bounds box;int left=-1,right=-1,start=0,count=0;};
    std::vector<Vec> vertices_;
    std::vector<std::array<int,3>> faces_;
    std::vector<Bounds> faceBounds_;
    std::vector<Vec> centers_;
    std::vector<int> order_;
    std::vector<Node> nodes_;
    Bounds global_;
    int build(int first,int last){
        int index=int(nodes_.size());nodes_.push_back({});Bounds box,centers;
        for(int i=first;i<last;i++){box.add(faceBounds_[order_[i]]);centers.add(centers_[order_[i]]);}
        nodes_[index].box=box;
        if(last-first<=8){nodes_[index].start=first;nodes_[index].count=last-first;return index;}
        Vec extent=centers.hi-centers.lo;int axis=extent.y>extent.x?1:0;if(extent.z>extent[axis])axis=2;
        int middle=(first+last)/2;
        std::nth_element(order_.begin()+first,order_.begin()+middle,order_.begin()+last,[&](int a,int b){return centers_[a][axis]==centers_[b][axis]?a<b:centers_[a][axis]<centers_[b][axis];});
        int left=build(first,middle),right=build(middle,last);nodes_[index].left=left;nodes_[index].right=right;return index;
    }
    void nearest(int n,const Box& box,const Bounds& bb,double& best,int& witness)const{
        const auto& node=nodes_[n];if(boundsDistance2(node.box,bb)>best)return;
        if(node.count){for(int i=node.start;i<node.start+node.count;i++){
            int f=order_[i];if(boundsDistance2(faceBounds_[f],bb)>best)continue;const auto& ids=faces_[f];
            double d=triangleBoxDistance2(box,{vertices_[ids[0]],vertices_[ids[1]],vertices_[ids[2]]});
            if(d<best){best=d;witness=f;}if(best==0)return;}
        }else {int x=node.left,y=node.right;if(boundsDistance2(nodes_[x].box,bb)>boundsDistance2(nodes_[y].box,bb))std::swap(x,y);nearest(x,box,bb,best,witness);if(best>0)nearest(y,box,bb,best,witness);}
    }
    // Called only with a known positive distance from the surface. A globally
    // closed, consistently oriented, non-self-intersecting input is required.
    int inside(Vec p)const{
        for(int k=0;k<3;k++)if(p[k]<global_.lo[k]||p[k]>global_.hi[k])return 0;
        double sum=0;
        for(const auto& f:faces_){Vec a=vertices_[f[0]]-p,b=vertices_[f[1]]-p,c=vertices_[f[2]]-p;
            double la=length(a),lb=length(b),lc=length(c);
            double den=la*lb*lc+dot(a,b)*lc+dot(b,c)*la+dot(c,a)*lb;
            sum+=2*std::atan2(dot(a,cross(b,c)),den);}
        double value=std::abs(sum/(4*Pi));if(value<1e-6)return 0;if(std::abs(value-1)<1e-6)return 1;return -1;
    }
public:
    Collider(const std::vector<Vec>& vertices,const std::vector<std::array<int,3>>& faces):vertices_(vertices),faces_(faces){
        if(vertices.empty()||faces.empty())throw std::invalid_argument("empty rigid collision mesh");
        for(Vec v:vertices){if(!finite(v)||length(v)>1000)throw std::invalid_argument("invalid rigid collision vertex");global_.add(v);}
        std::map<std::array<int,2>,std::pair<int,int>> edges;
        for(const auto& f:faces){for(int n:f)if(n<0||n>=int(vertices.size()))throw std::invalid_argument("rigid collision index");
            if(length(cross(vertices[f[1]]-vertices[f[0]],vertices[f[2]]-vertices[f[0]]))<1e-16)throw std::invalid_argument("degenerate rigid collision triangle");
            Bounds box;for(int n:f)box.add(vertices[n]);faceBounds_.push_back(box);centers_.push_back((vertices[f[0]]+vertices[f[1]]+vertices[f[2]])/3);
            for(int k=0;k<3;k++){int a=f[k],b=f[(k+1)%3];auto& e=edges[{std::min(a,b),std::max(a,b)}];++e.first;e.second+=a<b?1:-1;}}
        for(const auto& item:edges)if(item.second.first!=2||item.second.second!=0)throw std::invalid_argument("rigid collision mesh must be closed and consistently oriented");
        order_.resize(faces.size());std::iota(order_.begin(),order_.end(),0);nodes_.reserve(faces.size()*2);build(0,int(faces.size()));
    }
    double surfaceDistance(const std::array<Box,2>& boxes,int& witness)const{
        double best=INFINITY;witness=-1;for(const auto& box:boxes)nearest(0,box,bounds(box),best,witness);return std::sqrt(best);
    }
    Result admit(const Pose& start,const Pose& target,const Settings& settings={})const{
        Result result;result.blocked=true;
        if(!std::isfinite(settings.clearance_m)||settings.clearance_m<0||settings.maximum_intervals<1||settings.maximum_depth<1||settings.maximum_depth>40||!(settings.minimum_fraction>0))throw std::invalid_argument("invalid admission settings");
        if(length(target.pivot-start.pivot)>1e-12){result.reason="pivot_changed";return result;}
        try{
            auto boxes=jaws(start);result.initial_clearance_m=surfaceDistance(boxes,result.witness_triangle);
            if(!(result.initial_clearance_m>settings.clearance_m)){result.reason="initial_clearance";return result;}
            for(const auto& box:boxes){int c=inside(box.center);if(c!=0){result.reason=c>0?"initial_inside_liver":"initial_solid_classification_uncertain";return result;}}
            result.initial_valid=true;double prefix=0;
            auto visit=[&](auto&& self,double a,double b,int depth)->bool{
                if(result.work_count>=settings.maximum_intervals){result.reason="interval_budget";return false;}
                ++result.work_count;double bound=motionBound(start,target,a,b);
                if(!std::isfinite(bound)){result.reason="rcm_frame_singularity";return false;}
                int witness=-1;double distance=surfaceDistance(jaws(interpolate(start,target,(a+b)*.5)),witness);
                // 1 pm reserve covers arithmetic-scale roundoff for this SI mesh.
                if(distance>settings.clearance_m+bound+1e-12){prefix=b;return true;}
                result.witness_triangle=witness;
                if(depth>=settings.maximum_depth||b-a<=settings.minimum_fraction){result.reason=distance<=settings.clearance_m?"rigid_liver_clearance":"uncertified_interval";return false;}
                double middle=(a+b)*.5;return self(self,a,middle,depth+1)&&self(self,middle,b,depth+1);
            };
            bool complete=visit(visit,0.,1.,0);result.accepted_fraction=complete?1.:std::max(0.,prefix-std::min(prefix*.5,settings.minimum_fraction));
            result.blocked=!complete;if(complete){result.reason="clear";result.witness_triangle=-1;}
            int endpointWitness=-1;result.endpoint_clearance_m=surfaceDistance(jaws(interpolate(start,target,result.accepted_fraction)),endpointWitness);
            if(!(result.endpoint_clearance_m>settings.clearance_m)){result.accepted_fraction=0;result.endpoint_clearance_m=result.initial_clearance_m;result.blocked=true;result.reason="endpoint_roundoff_guard";result.witness_triangle=endpointWitness;}
        }catch(const std::domain_error&){result.accepted_fraction=0;result.blocked=true;result.reason="invalid_rcm_frame";}
        return result;
    }
};
}
