#include "Phase6ToolCollision.h"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
using namespace phase6collision;
int failures=0,checks=0;
void check(bool value,const char* name){++checks;std::cout<<(value?"PASS ":"FAIL ")<<name<<'\n';if(!value)++failures;}
Collider cube(Vec c,double h){
    std::vector<Vec> v;for(int i=0;i<8;i++)v.push_back(c+Vec{(i&1?1:-1)*h,(i&2?1:-1)*h,(i&4?1:-1)*h});
    return {v,{{0,4,6},{0,6,2},{1,3,7},{1,7,5},{0,1,5},{0,5,4},{2,6,7},{2,7,3},{0,2,3},{0,3,1},{4,5,7},{4,7,6}}};
}
double clearance(const Collider& c,const Pose& p){int w=-1;return c.surfaceDistance(jaws(p),w);}
int main(int argc,char**argv){
    if(argc==4&&std::string(argv[1])=="--native-admission"){
        std::ifstream mesh(argv[2]);int nv=0,nf=0;mesh>>nv>>nf;
        std::vector<Vec> vertices(nv);std::vector<std::array<int,3>> faces(nf);
        for(auto& v:vertices)mesh>>v.x>>v.y>>v.z;for(auto& f:faces)mesh>>f[0]>>f[1]>>f[2];
        Collider collider(vertices,faces);std::ifstream in(argv[3]);Pose p,previous[2];int count=0,blocked=0,invalid=0,maxWork=0;double minimum=INFINITY;
        while(in>>p.tip.x>>p.tip.y>>p.tip.z>>p.pivot.x>>p.pivot.y>>p.pivot.z>>p.roll_deg>>p.angle_deg){
            double ignored;for(int i=0;i<24;i++)in>>ignored;int tool=count%2;
            auto result=collider.admit(count<2?p:previous[tool],p);previous[tool]=p;
            minimum=std::min(minimum,result.initial_clearance_m);maxWork=std::max(maxWork,result.work_count);
            if(!result.initial_valid)++invalid;
            if(result.blocked){++blocked;if(blocked<=8)std::cout<<"blocked frame="<<count/2<<" tool="<<tool<<" fraction="<<result.accepted_fraction<<" reason="<<result.reason<<" initial_clearance="<<result.initial_clearance_m<<'\n';}
            ++count;
        }
        check(count>1000&&invalid==0&&blocked==0,"actual successful trajectory continuously admitted");
        std::cout<<std::setprecision(17)<<"poses="<<count<<" blocked="<<blocked<<" invalid="<<invalid<<" minimum_clearance_m="<<minimum<<" maximum_intervals="<<maxWork<<'\n';return failures?2:0;
    }
    if(argc==3&&std::string(argv[1])=="--native-frames"){
        std::ifstream in(argv[2]);double maximum=0;int count=0;Pose p;
        while(in>>p.tip.x>>p.tip.y>>p.tip.z>>p.pivot.x>>p.pivot.y>>p.pivot.z>>p.roll_deg>>p.angle_deg){
            auto boxes=jaws(p);for(const auto& b:boxes){for(Vec actual:std::array<Vec,4>{b.center,b.axis[0],b.axis[1],b.axis[2]}){Vec expected;in>>expected.x>>expected.y>>expected.z;maximum=std::max(maximum,length(actual-expected));}}++count;
        }
        check(count>1000&&maximum<1e-12,"actual native trace jaw frames");std::cout<<std::setprecision(17)<<"native_frames="<<count<<" max_error="<<maximum<<'\n';return failures?2:0;
    }
    Box box{{0,0,0},{{{1,0,0},{0,1,0},{0,0,1}}},{1,1,1}};
    check(std::abs(triangleBoxDistance2(box,{{{3,0,0},{3,.1,0},{3,0,.1}}})-4)<1e-12,"known triangle face distance");
    check(triangleBoxDistance2(box,{{{0,-2,-2},{0,2,-2},{0,0,2}}})==0,"triangle interior intersects box");
    check(std::abs(segmentDistance2({-1,0,0},{1,0,0},{0,-1,2},{0,1,2})-4)<1e-12,"interior edge distance");
    auto liver=cube({0,0,0},.01);
    Pose a{{-.05,-.005,-.006},{0,-.14,.15},90,20},b=a;b.tip.x=.05;
    check(clearance(liver,a)>.01&&clearance(liver,b)>.01,"translation endpoints clear");
    check(clearance(liver,interpolate(a,b,.5))==0,"translation midpoint intersects");
    auto crossing=liver.admit(a,b);
    check(crossing.initial_valid&&crossing.blocked&&crossing.accepted_fraction>0&&crossing.accepted_fraction<1,"endpoint-safe crossing is blocked");
    auto stopped=interpolate(a,b,crossing.accepted_fraction);
    check(clearance(liver,stopped)>.00015,"accepted endpoint remains outside margin");
    auto reverse=liver.admit(stopped,a);check(reverse.initial_valid&&!reverse.blocked&&reverse.accepted_fraction==1,"reverse away from blocking boundary");
    Pose safe=a;safe.tip.z=.05;Pose safeEnd=b;safeEnd.tip.z=.05;
    auto away=liver.admit(safe,safeEnd);check(!away.blocked&&away.accepted_fraction==1,"analytically high safe translation");
    auto encompassing=cube({0,0,0},.2);Pose inside{{0,0,0},{0,-.14,.15},90,20};
    auto rejected=encompassing.admit(inside,inside);check(!rejected.initial_valid&&rejected.accepted_fraction==0&&rejected.reason=="initial_inside_liver","initial solid containment rejected");
    Pose open{{0,0,0},{0,-.15,.15},0,0},closed=open;closed.angle_deg=40;
    auto openingObstacle=cube({.005759292,-.000618347,.000618347},.00012);
    check(clearance(openingObstacle,open)>.00015&&clearance(openingObstacle,closed)>.00015,"opening endpoints clear");
    auto opening=openingObstacle.admit(open,closed),closing=openingObstacle.admit(closed,open);
    check(opening.blocked&&opening.initial_valid&&opening.accepted_fraction>0&&opening.accepted_fraction<1,"pure opening sweep blocked");
    check(closing.blocked&&closing.initial_valid&&closing.accepted_fraction>0&&closing.accepted_fraction<1,"pure closing sweep blocked");
    Pose rollA{{0,0,0},{0,-.15,.15},0,20},rollB=rollA;rollB.roll_deg=180;
    auto rollingObstacle=cube({0,.003454117,.004690811},.00012);
    check(clearance(rollingObstacle,rollA)>.00015&&clearance(rollingObstacle,rollB)>.00015,"roll endpoints clear");
    auto rolling=rollingObstacle.admit(rollA,rollB);
    check(rolling.blocked&&rolling.initial_valid&&rolling.accepted_fraction>0&&rolling.accepted_fraction<1,"pure roll sweep blocked");
    bool boundValid=true;double worstRatio=0;std::mt19937 gen(4193);std::uniform_real_distribution<double> u(-1,1);
    for(int n=0;n<80;n++){
        Pose p{{u(gen)*.03,u(gen)*.03,.02+u(gen)*.02},{.08,.16,.10},u(gen)*170,20+u(gen)*20},q=p;
        q.tip=q.tip+Vec{u(gen)*.008,u(gen)*.008,u(gen)*.008};q.roll_deg+=u(gen)*60;q.angle_deg=20+u(gen)*20;
        double lo=.1,hi=.9,bound=motionBound(p,q,lo,hi);auto middle=jaws(interpolate(p,q,(lo+hi)*.5));
        for(int sample=0;sample<=80;sample++){auto now=jaws(interpolate(p,q,lo+(hi-lo)*sample/80));for(int j=0;j<2;j++)for(int i=0;i<8;i++){
            double d=length(corner(now[j],i)-corner(middle[j],i));boundValid&=d<=bound+1e-14;worstRatio=std::max(worstRatio,d/bound);}}
    }
    check(boundValid,"conservative bound independent dense trajectory screen");
    Settings exhausted;exhausted.maximum_intervals=1;auto capped=liver.admit(a,b,exhausted);
    check(capped.blocked&&capped.accepted_fraction==0,"uncertain work budget fails closed");
    auto repeat=liver.admit(a,b);check(repeat.accepted_fraction==crossing.accepted_fraction&&repeat.work_count==crossing.work_count&&repeat.witness_triangle==crossing.witness_triangle,"deterministic admission");
    std::cout<<std::setprecision(17)<<"checks="<<checks<<" failures="<<failures<<" crossing_alpha="<<crossing.accepted_fraction<<" intervals="<<crossing.work_count<<" worst_bound_ratio="<<worstRatio<<'\n';
    return failures?2:0;
}
