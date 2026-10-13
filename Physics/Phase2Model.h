#pragma once
#include <sofa/component/collision/response/contact/ContactListener.h>
#include <sofa/component/constraint/lagrangian/solver/GenericConstraintSolver.h>
#include <sofa/core/CollisionModel.h>
#include <sofa/core/MechanicalParams.h>
#include <sofa/core/behavior/ForceField.h>
using Listener=sofa::component::collision::response::contact::ContactListener;
using ConstraintSolver=sofa::component::constraint::lagrangian::solver::GenericConstraintSolver;
V cross3(const V&a,const V&b){return V(a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]);}
double dot3(const V&a,const V&b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
V unit(const V&v){double n=length(v);return n>1e-12?v/n:V(1,0,0);}
json jvec(const V&v){return {v[0],v[1],v[2]};}
constexpr double JawL=.0145,JawW=.0025,JawT=.0014,Pi=3.141592653589793;
const V Pivot(.12,-.14,.15);
struct JawPose{V center,axis,side,normal;};
V closestTriangle(const V&p,const V&a,const V&b,const V&c){
    const V ab=b-a,ac=c-a,ap=p-a;const double d1=dot3(ab,ap),d2=dot3(ac,ap);if(d1<=0&&d2<=0)return a;
    const V bp=p-b;const double d3=dot3(ab,bp),d4=dot3(ac,bp);if(d3>=0&&d4<=d3)return b;
    const double vc=d1*d4-d3*d2;if(vc<=0&&d1>=0&&d3<=0)return a+ab*(d1/(d1-d3));
    const V cp=p-c;const double d5=dot3(ab,cp),d6=dot3(ac,cp);if(d6>=0&&d5<=d6)return c;
    const double vb=d5*d2-d1*d6;if(vb<=0&&d2>=0&&d6<=0)return a+ac*(d2/(d2-d6));
    const double va=d3*d6-d5*d4;if(va<=0&&(d4-d3)>=0&&(d5-d6)>=0)return b+(c-b)*((d4-d3)/((d4-d3)+(d5-d6)));
    const double denom=1/(va+vb+vc);return a+ab*(vb*denom)+ac*(vc*denom);
}
bool rayTriangle(const V&p,const V&a,const V&b,const V&c){
    const V dir(.817231,.391721,.421173),ab=b-a,ac=c-a,h=cross3(dir,ac);double det=dot3(ab,h);if(std::abs(det)<1e-12)return false;
    double inv=1/det;V s=p-a;double u=dot3(s,h)*inv;if(u<0||u>1)return false;V q=cross3(s,ab);double v=dot3(dir,q)*inv;if(v<0||u+v>1)return false;return dot3(ac,q)*inv>1e-9;
}

class Tissue{
public:
    sofa::simulation::NodeSPtr root;
    MO *dofs=nullptr,*jawDofs[2]{};
    using FF=sofa::core::behavior::ForceField<sofa::defaulttype::Vec3Types>;
    FF *elastic=nullptr,*support=nullptr;
    struct MaterialAnchor{std::array<int,3> tri{};V weights,local;bool valid=false;};
    MaterialAnchor anchors[2];V innerPoints[2];
    ConstraintSolver* solver=nullptr;
    std::array<std::vector<Listener*>,2> listeners;
    std::array<JawPose,2> poses;
    std::vector<V> rest;
    std::vector<std::array<int,4>> tets;
    std::vector<std::array<int,3>> triangles;
    std::vector<int> fixed;
    V tip{0,-.015,.025},commanded{0,-.015,.025},graspStart{0,0,0};
    bool grasping=false,paused=false,healthy=true,latched=false,overloaded=false;
    double force=0,stepMs=0,maxDisp=0,time=0,closed=0,roll=0,commandedRoll=0,jawAngle=40,holdAngle=40;
    double penetration=0,contactForce=0,slip=0,minVolume=1,floorPenetration=0,animateMs=0,auditMs=0,rejectedMinVolume=1;
    bool needsOpen=false;int safetyStops=0;
    int resetId=0,contactCount=0,jawContact[2]{},innerContact[2]{},lossFrames=0;uint64_t frame=0;
    std::string message="Open jaws and approach tissue",gripState="open";
    Tissue(){makeMesh();create();}
    ~Tissue(){if(root)sofa::simulation::node::unload(root);}
    void makeMesh(){
        constexpr int Nx=13,Ny=9,Nz=3;
        auto id=[](int x,int y,int z){return x+Nx*(y+Ny*z);};
        for(int z=0;z<Nz;z++)for(int y=0;y<Ny;y++)for(int x=0;x<Nx;x++){
            rest.push_back(V(-.06+x*.12/(Nx-1),-.04+y*.08/(Ny-1),z*.012/(Nz-1)));if(y==Ny-1)fixed.push_back(id(x,y,z));
        }
        for(int z=0;z<Nz-1;z++)for(int y=0;y<Ny-1;y++)for(int x=0;x<Nx-1;x++){
            int a=id(x,y,z),b=id(x+1,y,z),c=id(x+1,y+1,z),d=id(x,y+1,z),e=id(x,y,z+1),f=id(x+1,y,z+1),g=id(x+1,y+1,z+1),h=id(x,y+1,z+1);
            for(auto t:std::vector<std::array<int,4>>{{a,b,c,g},{a,c,d,g},{a,d,h,g},{a,h,e,g},{a,e,f,g},{a,f,b,g}})tets.push_back(t);
        }
        std::map<std::array<int,3>,std::pair<int,std::array<int,3>>> faces;
        for(auto&t:tets)for(auto f:std::vector<std::array<int,3>>{{t[0],t[2],t[1]},{t[0],t[1],t[3]},{t[0],t[3],t[2]},{t[1],t[2],t[3]}}){auto k=f;std::sort(k.begin(),k.end());auto&v=faces[k];v.first++;v.second=f;}
        for(auto&[k,v]:faces)if(v.first==1)triangles.push_back(v.second);
    }
    std::vector<V> jawVertices(int j){
        const V axis=unit(Pivot-tip);V base=unit(cross3(axis,V(0,0,1)));if(length(cross3(axis,V(0,0,1)))<.01)base=unit(cross3(axis,V(0,1,0)));
        V side=base*std::cos(roll*Pi/180)+cross3(axis,base)*std::sin(roll*Pi/180),width=unit(cross3(axis,side));
        double sign=j?1.0:-1.0;V forward=-axis*std::cos(jawAngle*Pi/180)+side*(sign*std::sin(jawAngle*Pi/180));
        auto&p=poses[j];p.center=tip+axis*JawL+side*(sign*(JawT*.5+.000125))+forward*(JawL*.5);p.axis=unit(forward);p.side=width;p.normal=unit(cross3(forward,width));
        std::vector<V>v;for(int ring=0;ring<=5;ring++)for(auto c:std::vector<std::array<int,2>>{{-1,-1},{1,-1},{1,1},{-1,1}})v.push_back(p.center+p.axis*((ring/5.0-.5)*JawL)+p.side*(c[0]*JawW*.5)+p.normal*(c[1]*JawT*.5));return v;
    }
    void create(){
        auto sim=std::make_shared<sofa::simulation::graph::DAGSimulation>();sofa::simulation::Simulation::theSimulation=sim;
        root=sim->createNewGraph("LapPhase2");root->setDt(Dt);root->setGravity(V(0,0,0));
        add(root.get(),"FreeMotionAnimationLoop");
        solver=dynamic_cast<ConstraintSolver*>(add(root.get(),"BlockGaussSeidelConstraintSolver",{{"name","contactSolver"},{"maxIterations","500"},{"tolerance","0.0000001"},{"computeConstraintForces","true"}}).get());
        add(root.get(),"CollisionPipeline",{{"depth","8"}});add(root.get(),"BruteForceBroadPhase");add(root.get(),"BVHNarrowPhase");
        add(root.get(),"LocalMinDistance",{{"alarmDistance","0.0015"},{"contactDistance","0.0004"},{"angleCone","0"},{"useLMDFilters","true"}});
        add(root.get(),"CollisionResponse",{{"response","FrictionContactConstraint"},{"responseParams","mu=0.65"}});
        auto body=root->createChild("tissue");
        add(body.get(),"EulerImplicitSolver",{{"name","integrator"},{"rayleighStiffness","0.025"},{"rayleighMass","1.0"}});
        add(body.get(),"SparseLDLSolver",{{"name","linearSolver"},{"template","CompressedRowSparseMatrixMat3x3d"}});
        std::ostringstream tet,tri;for(auto&t:tets)for(int i:t)tet<<i<<' ';for(auto&t:triangles)for(int i:t)tri<<i<<' ';
        add(body.get(),"TetrahedronSetTopologyContainer",{{"name","topology"},{"position",vecText(rest)},{"tetrahedra",tet.str()}});
        dofs=dynamic_cast<MO*>(add(body.get(),"MechanicalObject",{{"name","dofs"},{"template","Vec3d"},{"position",vecText(rest)}}).get());
        add(body.get(),"UniformMass",{{"totalMass","0.1152"}});
        elastic=dynamic_cast<FF*>(add(body.get(),"TetrahedronFEMForceField",{{"name","elasticity"},{"method","large"},{"youngModulus","3500"},{"poissonRatio","0.35"}}).get());

        add(body.get(),"FixedProjectiveConstraint",{{"indices",indices(fixed)}});
        add(body.get(),"LinearSolverConstraintCorrection",{{"linearSolver","@linearSolver"},{"ODESolver","@integrator"}});
        auto surf=body->createChild("surface");
        add(surf.get(),"MeshTopology",{{"name","topology"},{"position",vecText(rest)},{"triangles",tri.str()}});
        add(surf.get(),"MechanicalObject",{{"name","dofs"},{"position",vecText(rest)}});
        for(auto name:{"TriangleCollisionModel","LineCollisionModel","PointCollisionModel"})add(surf.get(),name,{{"group","1"},{"contactStiffness","1000"},{"contactFriction","0.65"},{"selfCollision","false"}});
        add(surf.get(),"IdentityMapping",{{"input","@../dofs"},{"output","@dofs"}});
        std::ostringstream box;box<<"0 2 1 0 3 2 20 21 22 20 22 23 ";
        for(int r=0;r<5;r++)for(int k=0;k<4;k++){int a=r*4+k,b=r*4+(k+1)%4,c=b+4,d=a+4;box<<a<<' '<<b<<' '<<c<<' '<<a<<' '<<c<<' '<<d<<' ';}const std::string boxTris=box.str();
        for(int j=0;j<2;j++){
            auto node=root->createChild(std::string("jaw")+std::to_string(j));auto verts=jawVertices(j);
            add(node.get(),"MeshTopology",{{"name","topology"},{"position",vecText(verts)},{"triangles",boxTris}});
            jawDofs[j]=dynamic_cast<MO*>(add(node.get(),"MechanicalObject",{{"name","dofs"},{"position",vecText(verts)}}).get());
            int k=0;for(auto name:{"TriangleCollisionModel","LineCollisionModel","PointCollisionModel"}){
                std::string n="collision"+std::to_string(k++);
                auto model=add(node.get(),name,{{"name",n},{"group","2"},{"simulated","false"},{"moving","true"},{"contactFriction","0.65"},{"selfCollision","false"}});
                auto listener=sofa::core::objectmodel::New<Listener>(dynamic_cast<sofa::core::CollisionModel*>(model.get()),nullptr);listener->setName("contacts"+std::to_string(j)+n);root->addObject(listener);listeners[j].push_back(listener.get());
            }
        }
        auto tray=root->createChild("tray");
        const std::string plane="-.1375 -.1075 -.0043 .1375 -.1075 -.0043 .1375 .1075 -.0043 -.1375 .1075 -.0043";
        add(tray.get(),"MeshTopology",{{"name","topology"},{"position",plane},{"triangles","0 1 2 0 2 3"}});
        add(tray.get(),"MechanicalObject",{{"name","dofs"},{"position",plane}});
        add(tray.get(),"TriangleCollisionModel",{{"group","3"},{"simulated","false"},{"moving","false"},{"contactFriction","0.65"}});
        sofa::simulation::node::initRoot(root.get());
        if(!dofs||!solver)throw std::runtime_error("Phase2 required component unavailable");
    }
    void release(const std::string&reason="Released"){
        grasping=false;latched=false;force=0;gripState="released";message=reason;holdAngle=40;lossFrames=0;
    }
    void reset(int id){
        release("Reset complete");sofa::simulation::node::reset(root.get());resetId=id;time=0;maxDisp=0;healthy=true;closed=0;tip=commanded=V(0,-.015,.025);roll=commandedRoll=0;jawAngle=40;overloaded=false;slip=0;contactCount=0;contactForce=0;penetration=0;
        minVolume=1;floorPenetration=0;needsOpen=false;anchors[0].valid=anchors[1].valid=false;
        updateJaws(true);
    }
    V limitTip(V v){
        v=V(std::clamp(v[0],-.09,.09),std::clamp(v[1],-.07,.065),std::clamp(v[2],-.005,.09));
        V ref=unit(V(0,0,.012)-Pivot),dir=v-Pivot;double radius=std::clamp(length(dir),.12,.30);dir=unit(dir);
        double angle=std::acos(std::clamp(dot3(dir,ref),-1.0,1.0)),maxAngle=32*Pi/180;
        if(angle>maxAngle)dir=ref*std::cos(maxAngle)+unit(dir-ref*dot3(dir,ref))*std::sin(maxAngle);
        return Pivot+dir*radius;
    }
    bool command(const json&j){
        if(!j.is_object()||!j.contains("type")||j["type"]!="command")return false;
        if(!j.contains("reset_id")||!j["reset_id"].is_number_integer()||j["reset_id"].get<double>()<0||j["reset_id"].get<double>()>2147483647.0||!j.contains("tip_m")||!j["tip_m"].is_array()||j["tip_m"].size()!=3||!j.contains("closed")||!j["closed"].is_number()||!j.contains("paused")||!j["paused"].is_boolean())throw std::invalid_argument("Invalid command schema");
        if(j.contains("seq")&&(!j["seq"].is_number_integer()||j["seq"].get<double>()<0))throw std::invalid_argument("Invalid sequence");
        for(auto&v:j["tip_m"])if(!v.is_number())throw std::invalid_argument("Invalid coordinate");
        if(j.contains("roll_deg")&&!j["roll_deg"].is_number())throw std::invalid_argument("Invalid roll");
        V v(j["tip_m"][0].get<double>(),j["tip_m"][1].get<double>(),j["tip_m"][2].get<double>());double c=j["closed"].get<double>(),r=j.value("roll_deg",0.0);
        if(!std::isfinite(length(v))||!std::isfinite(c)||!std::isfinite(r))throw std::invalid_argument("Nonfinite command");
        int rid=j["reset_id"].get<int>();bool changed=rid!=resetId;if(changed)reset(rid);
        commanded=limitTip(v);closed=std::clamp(c,0.0,1.0);commandedRoll=std::remainder(r,360.0);paused=j["paused"].get<bool>();
        if(changed&&closed==0){tip=commanded;roll=commandedRoll;jawAngle=40;updateJaws(true);}
        return true;
    }
    void updateJaws(bool snap=false){
        for(int j=0;j<2;j++)if(jawDofs[j]){auto v=jawVertices(j);auto x=jawDofs[j]->x.getValue(),target=x;auto vel=jawDofs[j]->v.getValue();for(size_t i=0;i<v.size();i++){vel[i]=snap?V(0,0,0):(v[i]-x[i])/Dt;target[i]=v[i];}if(snap)jawDofs[j]->x.setValue(target);jawDofs[j]->xfree.setValue(target);jawDofs[j]->v.setValue(vel);jawDofs[j]->vfree.setValue(vel);}
    }
    void commitJaws(){
        for(int j=0;j<2;j++){auto points=jawVertices(j);auto x=jawDofs[j]->x.getValue();for(size_t i=0;i<points.size();i++)x[i]=points[i];jawDofs[j]->x.setValue(x);}
    }
    void contacts(){
        contactCount=0;penetration=0;jawContact[0]=jawContact[1]=innerContact[0]=innerContact[1]=0;
        for(int j=0;j<2;j++)for(auto*l:listeners[j])if(l)for(auto&group:l->getContactsVector())for(auto&c:group){
            if(c.value<=.00005){
                jawContact[j]++;contactCount++;
                bool first=c.elem.first.getCollisionModel()->getContext()==jawDofs[j]->getContext();V point=c.point[first?0:1],normal=first?V(c.normal):-V(c.normal);
                const double innerSign=j?-1.0:1.0;const V innerNormal=poses[j].normal*innerSign;
                if(dot3(point-poses[j].center,innerNormal)>JawT*.2&&dot3(normal,innerNormal)>.35){innerContact[j]++;innerPoints[j]=c.point[first?1:0];}
            }
        }
        // EulerImplicitSolver integrates delta-v: W = dt J A^-1 J^T, so lambda is impulse.
        contactForce=0;auto&lambda=solver->d_constraintForces.getValue();std::vector<bool> jawRows(lambda.size(),false);for(auto*jaw:jawDofs){const auto&matrix=jaw->c.getValue();for(auto row=matrix.begin();row!=matrix.end();++row)if(row.index()<jawRows.size())jawRows[row.index()]=true;}for(size_t i=0;i+2<lambda.size();i+=3)if(jawRows[i])contactForce+=std::sqrt(lambda[i]*lambda[i]+lambda[i+1]*lambda[i+1]+lambda[i+2]*lambda[i+2])/Dt;
        // Independent geometry audit: nearest-surface signed depth at 40 jaw boundary samples.
        // This is not the unsigned SOFA proximity violation and is reported separately from solver tolerance.
        auto&x=dofs->x.getValue();
        for(auto&p:poses)for(auto&tri:triangles){V samples[4]={x[tri[0]],x[tri[1]],x[tri[2]],(x[tri[0]]+x[tri[1]]+x[tri[2]])/3.0};for(auto&q:samples){V d=q-p.center;double dx=JawL*.5-std::abs(dot3(d,p.axis)),dy=JawW*.5-std::abs(dot3(d,p.side)),dz=JawT*.5-std::abs(dot3(d,p.normal));if(dx>0&&dy>0&&dz>0)penetration=std::max(penetration,std::min({dx,dy,dz}));}}
        for(auto&p:poses)for(int l=0;l<5;l++)for(int sy:{-1,1})for(int sz:{-1,1}){
            V point=p.center+p.axis*((l/4.0-.5)*JawL)+p.side*(sy*JawW*.5)+p.normal*(sz*JawT*.5),nearest,normal;double best=1e10;
            for(auto&tri:triangles){V a=x[tri[0]],b=x[tri[1]],c=x[tri[2]],q=closestTriangle(point,a,b,c);double ds=dot3(point-q,point-q);if(ds<best){best=ds;nearest=q;normal=unit(cross3(b-a,c-a));}}
            if(dot3(point-nearest,normal)<-1e-8){int crossings=0;for(auto&tri:triangles)if(rayTriangle(point,x[tri[0]],x[tri[1]],x[tri[2]]))crossings++;if(crossings%2)penetration=std::max(penetration,std::sqrt(best));}
        }
    }
    V localPoint(int j,const V&p){V d=p-poses[j].center;return V(dot3(d,poses[j].axis),dot3(d,poses[j].side),dot3(d,poses[j].normal));}
    void captureMaterial(){
        const auto&x=dofs->x.getValue();
        for(int j=0;j<2;j++){double best=1e9;V q;auto&a=anchors[j];
            for(auto&tri:triangles){V cp=closestTriangle(innerPoints[j],x[tri[0]],x[tri[1]],x[tri[2]]);double d=length(cp-innerPoints[j]);if(d<best){best=d;q=cp;a.tri=tri;}}
            V b=x[a.tri[1]]-x[a.tri[0]],c=x[a.tri[2]]-x[a.tri[0]],d=q-x[a.tri[0]];double bb=dot3(b,b),bc=dot3(b,c),cc=dot3(c,c),den=bb*cc-bc*bc;
            double u=(dot3(d,b)*cc-dot3(d,c)*bc)/den,v=(dot3(d,c)*bb-dot3(d,b)*bc)/den;a.weights=V(1-u-v,u,v);a.local=localPoint(j,q);a.valid=true;
        }
    }
    void measureSlip(){
        if(!latched)return;const auto&x=dofs->x.getValue();
        for(int j=0;j<2;j++){auto&a=anchors[j];if(a.valid){V q=x[a.tri[0]]*a.weights[0]+x[a.tri[1]]*a.weights[1]+x[a.tri[2]]*a.weights[2],d=localPoint(j,q)-a.local;slip=std::max(slip,std::sqrt(d[0]*d[0]+d[1]*d[1]));}}
    }
    double volumeRatio(){double result=1;const auto&x=dofs->x.getValue();for(auto&t:tets){double r=dot3(rest[t[1]]-rest[t[0]],cross3(rest[t[2]]-rest[t[0]],rest[t[3]]-rest[t[0]])),v=dot3(x[t[1]]-x[t[0]],cross3(x[t[2]]-x[t[0]],x[t[3]]-x[t[0]]))/r;if(!std::isfinite(v))return -1;result=std::min(result,v);}return result;}
    json balance(){
        FF::DataVecDeriv internal;sofa::defaulttype::Vec3Types::VecDeriv zero(rest.size());internal.setValue(zero);elastic->addForce(sofa::core::MechanicalParams::defaultInstance(),internal,dofs->x,dofs->v);if(support)support->addForce(sofa::core::MechanicalParams::defaultInstance(),internal,dofs->x,dofs->v);
        sofa::defaulttype::Vec3Types::VecDeriv lam(rest.size());const auto&matrix=dofs->c.getValue();const auto&lambda=solver->d_constraintForces.getValue();for(auto row=matrix.begin();row!=matrix.end();++row)for(auto col=row.begin();col!=row.end();++col)if(row.index()<lambda.size())lam[col.index()]+=col.val()*lambda[row.index()];V net(0,0,0),reaction(0,0,0);double residual=0,loadNorm=0;
        for(size_t i=0;i<rest.size();i++){V f= i<lam.size()?lam[i]/Dt:V(0,0,0);net+=f;loadNorm+=dot3(f,f);if(std::find(fixed.begin(),fixed.end(),int(i))!=fixed.end())reaction-=internal.getValue()[i];else{V r=internal.getValue()[i]+f;residual+=dot3(r,r);}}
        return {{"jaw_net_force_n",jvec(net)},{"fixed_reaction_n",jvec(reaction)},{"free_node_residual_l2_n",std::sqrt(residual)},{"jaw_nodal_force_l2_n",std::sqrt(loadNorm)},{"relative_residual",std::sqrt(residual/std::max(loadNorm,1e-20))}};
    }
    void step(){
        auto start=Clock::now();
        if(!paused&&healthy){
            const V oldTip=tip;double oldRoll=roll,oldAngle=jawAngle;
            V delta=commanded-tip;double dist=length(delta);if(dist>.02*Dt)delta*=.02*Dt/dist;
            if(!overloaded)tip+=delta;
            double rd=std::remainder(commandedRoll-roll,360.0);roll=std::remainder(roll+std::clamp(rd,-80*Dt,80*Dt),360.0);
            if(closed<.5){overloaded=false;needsOpen=false;if(latched)release();jawAngle=std::min(40.0,jawAngle+60*Dt);gripState="open";}
            else if(overloaded){jawAngle=std::min(40.0,jawAngle+60*Dt);}
            else if(!needsOpen){jawAngle=std::max(latched?holdAngle:2.0,jawAngle-35*Dt);}
            auto previousX=dofs->x.getValue(),previousV=dofs->v.getValue();
            updateJaws();auto aStart=Clock::now();sofa::simulation::node::animate(root.get(),Dt);animateMs=std::chrono::duration<double,std::milli>(Clock::now()-aStart).count();commitJaws();time+=Dt;auto cStart=Clock::now();contacts();auditMs=std::chrono::duration<double,std::milli>(Clock::now()-cStart).count();
            minVolume=volumeRatio();if(contactForce>2.0||penetration>.002||minVolume<.08){
                rejectedMinVolume=std::min(rejectedMinVolume,minVolume);dofs->x.setValue(previousX);dofs->v.setValue(previousV);tip=oldTip;roll=oldRoll;jawAngle=oldAngle;updateJaws(true);minVolume=volumeRatio();safetyStops++;
                if(contactForce>2.0||penetration>.002){overloaded=true;release("Contact overload - open jaws to continue");gripState="limit";}
                else{healthy=false;release("Element quality safety stop - press R");}
            }
            floorPenetration=0;for(auto&x:dofs->x.getValue())floorPenetration=std::max(floorPenetration,-.0043-x[2]);
            measureSlip();
            if(closed>=.5&&!overloaded&&!needsOpen&&healthy){
                if(innerContact[0]>0&&innerContact[1]>0&&contactForce>(latched?.02:.5)){
                    if(!latched){latched=true;holdAngle=jawAngle;graspStart=tip;slip=0;captureMaterial();}grasping=true;gripState=slip>.002?"slipping":"holding";lossFrames=0;message="Bilateral jaw contact - frictional grip";
                }else if(latched){if(++lossFrames>int(.20/Dt)){release("Contact lost - open and regrasp");needsOpen=true;gripState="slipping";}}
                else if(contactCount){gripState="contact";message="Unilateral contact - reposition before gripping";}
                if(contactForce>2.0||penetration>.002||length(tip-graspStart)>.055&&latched){std::cout<<"OVERLOAD force="<<contactForce<<" penetration="<<penetration<<std::endl;overloaded=true;release("Overload protection - open jaws to continue");gripState="limit";}
            }else if(contactCount&&closed<.5){gripState="contact";message="Jaw surface contacts deform tissue";}
        }
        force=contactForce;maxDisp=0;const auto&x=dofs->x.getValue();for(size_t i=0;i<x.size();i++){double d=length(x[i]-rest[i]);if(!std::isfinite(d)||d>.15){healthy=false;release("Solver safety stop - press R");break;}maxDisp=std::max(maxDisp,d);}
        frame++;stepMs=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
    }
    json vertices(){json a=json::array();for(auto&v:dofs->x.getValue())a.push_back(jvec(v));return a;}
    json hello(){return {{"type","hello"},{"protocol",2},{"units","m"},{"vertices",vertices()},{"triangles",triangles},{"solver","SOFA 26.06 FEM + frictional Lagrangian contact"},{"dt",Dt},{"material_validated",false},{"node_count",rest.size()},{"tet_count",tets.size()},{"grasp_model","bilateral jaw surface friction contact"},{"pivot_m",jvec(Pivot)}};}
    json state(){json jp=json::array();for(auto&p:poses)jp.push_back({{"center_m",jvec(p.center)},{"axis",jvec(p.axis)},{"side",jvec(p.side)},{"normal",jvec(p.normal)}});return {{"type","state"},{"frame",frame},{"reset_id",resetId},{"time",time},{"vertices",vertices()},{"grasping",grasping},{"force_n",force},{"step_ms",stepMs},{"max_displacement_m",maxDisp},{"healthy",healthy},{"message",message},{"tip_m",jvec(tip)},{"roll_deg",roll},{"jaw_poses",jp},{"jaw_angle_deg",jawAngle},{"jaw_open_fraction",(jawAngle-2)/38},{"contact_count",contactCount},{"jaw_contact_counts",{jawContact[0],jawContact[1]}},{"contact_force_n",contactForce},{"penetration_m",penetration},{"grip_state",gripState},{"slip_distance_m",slip},{"min_tet_volume_ratio",minVolume},{"floor_penetration_m",floorPenetration},{"safety_stops",safetyStops},{"sofa_animate_ms",animateMs},{"contact_audit_ms",auditMs},{"rejected_min_tet_volume_ratio",rejectedMinVolume}};}
};

int selfTest(Tissue&t,const std::filesystem::path&out){
    json report={{"phase",2},{"experimental",false},{"dt_s",Dt},{"node_count",t.rest.size()},{"tet_count",t.tets.size()},{"checks",json::object()},{"stages",json::array()}};
    std::vector<double> costs;double minVolume=1,maxPen=0,maxFloor=0,maxLoad=0,fixedError=0;bool regularHealthy=true;int rid=0;
    auto check=[&](const char*name,bool passed){report["checks"][name]=passed;};
    auto reset=[&](V tip,double roll){t.command({{"type","command"},{"reset_id",++rid},{"tip_m",jvec(tip)},{"closed",0},{"paused",false},{"roll_deg",roll}});};
    auto run=[&](double seconds,V tip,double closed,double roll,const char*stage,bool normal=true){
        t.commanded=t.limitTip(tip);t.commandedRoll=roll;t.closed=closed;int count=std::lround(seconds/Dt);double peak=0,peakPen=0,minV=1;bool everGrip=false,everLimit=false;
        for(int i=0;i<count;i++){t.step();costs.push_back(t.stepMs);peak=std::max(peak,t.contactForce);peakPen=std::max(peakPen,t.penetration);minV=std::min(minV,t.minVolume);everGrip|=t.grasping;everLimit|=t.overloaded;
            if(normal){regularHealthy&=t.healthy;minVolume=std::min(minVolume,t.minVolume);maxPen=std::max(maxPen,t.penetration);maxFloor=std::max(maxFloor,t.floorPenetration);maxLoad=std::max(maxLoad,t.contactForce);for(int j:t.fixed)fixedError=std::max(fixedError,length(t.dofs->x.getValue()[j]-t.rest[j]));}}
        auto state=t.state();state.erase("vertices");state.erase("jaw_poses");state["stage"]=stage;state["peak_load_n"]=peak;state["peak_penetration_m"]=peakPen;state["minimum_volume_ratio"]=minV;state["ever_grasping"]=everGrip;state["ever_overload"]=everLimit;report["stages"].push_back(state);std::cout<<stage<<" "<<state.dump()<<std::endl;return state;
    };
    auto rest=run(.6,V(0,-.015,.025),0,0,"unloaded_rest");check("unloaded_rest",t.maxDisp<1e-8);
    run(1.5,V(0,-.015,.006),0,0,"top_press");check("real_top_contact_deformation",t.contactCount>0&&t.maxDisp>.003&&!t.grasping);
    run(.7,V(0,-.015,.006),1,0,"top_close");check("unilateral_top_contact_not_grip",!t.grasping);
    reset(V(0,-.052,.006),90);run(1,V(0,-.037,.006),0,90,"edge_insert");run(1.6,V(0,-.037,.006),1,90,"bilateral_pinch");check("bilateral_contact_grip",t.grasping&&t.innerContact[0]>0&&t.innerContact[1]>0);
    run(1.2,V(.003,-.038,.014),1,90,"lift_8mm");check("friction_transfers_traction",t.grasping&&t.maxDisp>.006&&t.slip<.002);report["quasistatic_balance"]=t.balance();check("force_balance_units",report["quasistatic_balance"]["relative_residual"].get<double>()<.03);
    run(1.8,V(.005,-.040,.022),1,90,"pull_until_slip");check("physical_slip_and_release",!t.grasping&&t.needsOpen&&t.slip>.003);
    run(1,V(0,-.037,.006),1,90,"closed_cannot_regrasp");check("slip_requires_open_cycle",!t.grasping);
    run(3,V(.005,-.040,.028),0,90,"release_recovery");check("released_recovers",!t.grasping&&t.maxDisp<.001);
    for(int r=0;r<10;r++){reset(V(0,-.015,.025),r*37);t.step();if(!report["checks"].contains("ten_clean_resets"))report["checks"]["ten_clean_resets"]=true;report["checks"]["ten_clean_resets"]=report["checks"]["ten_clean_resets"].get<bool>()&&t.healthy&&t.maxDisp<1e-8&&t.resetId==rid;}
    reset(V(0,-.052,.006),90);run(1,V(0,-.037,.006),0,90,"stress_insert");run(1.6,V(0,-.037,.006),1,90,"stress_pinch");auto stress=run(3,V(0,-.037,-.005),1,90,"compression_overload",false);check("overload_or_quality_protection",t.overloaded||!t.healthy);report["stress_protection_kind"]=t.overloaded?"contact load limit":"element quality stop";
    reset(V(0,-.015,.025),0);check("reset_recovers_protection",t.healthy&&t.maxDisp==0);
    bool limits=true;for(V v:{V(10,10,10),V(-10,-10,-10),Pivot}){V q=t.limitTip(v),d=q-Pivot;double rad=length(d),angle=std::acos(std::clamp(dot3(unit(d),unit(V(0,0,.012)-Pivot)),-1.0,1.0))*180/Pi;limits&=rad>=.12-1e-8&&rad<=.30+1e-8&&angle<=32+1e-8;}check("rcm_radial_and_cone_limits",limits);
    check("regular_steps_healthy",regularHealthy);check("positive_element_volumes",minVolume>.08);check("sampled_penetration_under_1mm",maxPen<.001);check("support_penetration_under_0_1mm",maxFloor<.0001);check("fixed_edge_stationary",fixedError<1e-8);
    std::sort(costs.begin(),costs.end());report["metrics"]={{"step_p95_ms",costs[size_t(.95*(costs.size()-1))]},{"step_max_ms",costs.back()},{"min_tet_volume_ratio",minVolume},{"max_sampled_penetration_m",maxPen},{"max_floor_penetration_m",maxFloor},{"peak_total_jaw_load_n",maxLoad},{"fixed_error_m",fixedError}};
    bool passed=true;for(auto&v:report["checks"].items())passed&=v.value().get<bool>();report["passed"]=passed;std::ofstream(out)<<report.dump(2);return passed?0:2;
}
