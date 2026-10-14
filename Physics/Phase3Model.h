#pragma once
#include <set>
#include <numeric>
#include <queue>

// A thin tetrahedral FEM training layer. Cuts duplicate both thickness layers
// along material mesh-edge fans; no tetrahedra, mass or elastic rest strain are
// discarded. This is bounded full-thickness cutting, not arbitrary organ cuts.
class Membrane {
public:
    using Face=std::array<int,3>; using Edge=std::array<int,2>;
    struct DSU {std::vector<int> p;explicit DSU(int n):p(n){std::iota(p.begin(),p.end(),0);}int get(int x){return p[x]==x?x:p[x]=get(p[x]);}void join(int a,int b){p[get(a)]=get(b);}};
    struct Tool {
        V tip,commanded,pivot;double roll=90,commandedRoll=90,closed=0,angle=40,holdAngle=40,force=0,slip=0,penetration=0;
        bool grasping=false,latched=false,needsOpen=false,strokeUsed=false;int contactCount=0,inner[2]{},lost=0;
        MO* dofs[2]{};std::array<JawPose,2> poses;std::array<std::vector<Listener*>,2> listeners;
        int anchorFace=-1;V anchorWeights,anchorLocal;std::vector<V> contactPoints;std::set<Edge> strokeEdges;std::string gripState="open";
    };
    static constexpr int Nx=25,Ny=17;static constexpr double Thickness=.0015,TotalMass=.0144,H=Dt;
    sofa::simulation::NodeSPtr root;MO* dofs=nullptr;ConstraintSolver* solver=nullptr;
    std::vector<V> original,rest;std::vector<Face> sourceFaces,triangles;std::vector<std::array<int,4>> tets;std::vector<int> origins,fixed;int layerNodes=0;
    std::map<Edge,std::vector<int>> edgeFaces;std::set<Edge> cuts;std::vector<double> masses;
    std::array<Tool,2> tools;int activeTool=0,resetId=0,revision=0,cutCount=0,components=1,safetyStops=0;
    bool healthy=true,paused=false;uint64_t frame=0;double time=0,stepMs=0,maxDisp=0,cutLength=0,lastRebuildMs=0,minArea=1,minVolume=1,integrationStep=Dt;int adaptiveRetries=0,lastSubsteps=1;
    std::string message="Grasper holds tissue; select scissors and close over membrane to cut";
    static Edge edge(int a,int b){return {std::min(a,b),std::max(a,b)};}
    Membrane(){makeMesh();reset(0);}~Membrane(){if(root)sofa::simulation::node::unload(root);}
    void makeMesh(){
        for(int y=0;y<Ny;y++)for(int x=0;x<Nx;x++)original.emplace_back(-.06+x*.005,-.04+y*.005,.006);
        for(int y=0;y<Ny-1;y++)for(int x=0;x<Nx-1;x++){int a=x+Nx*y,b=a+1,c=a+Nx,d=c+1;sourceFaces.push_back({a,b,d});sourceFaces.push_back({a,d,c});}
        for(int f=0;f<int(sourceFaces.size());f++)for(int k=0;k<3;k++)edgeFaces[edge(sourceFaces[f][k],sourceFaces[f][(k+1)%3])].push_back(f);
    }
    V limitTip(int k,V v)const{
        v=V(std::clamp(v[0],-.085,.085),std::clamp(v[1],-.065,.06),std::clamp(v[2],-.002,.08));
        V ref=unit(V(0,0,.006)-tools[k].pivot),dir=v-tools[k].pivot;double radius=std::clamp(length(dir),.12,.30);dir=unit(dir);
        double angle=std::acos(std::clamp(dot3(dir,ref),-1.0,1.0));if(angle>32*Pi/180)dir=ref*std::cos(32*Pi/180)+unit(dir-ref*dot3(dir,ref))*std::sin(32*Pi/180);
        return tools[k].pivot+dir*radius;
    }
    std::vector<V> jawVertices(int k,int j){
        auto&t=tools[k];V axis=unit(t.pivot-t.tip),base=unit(cross3(axis,V(0,0,1)));V side=base*std::cos(t.roll*Pi/180)+cross3(axis,base)*std::sin(t.roll*Pi/180),width=unit(cross3(axis,side));
        double sign=j?1.0:-1.0;V forward=-axis*std::cos(t.angle*Pi/180)+side*(sign*std::sin(t.angle*Pi/180));
        auto&p=t.poses[j];p.center=t.tip+axis*JawL+side*(sign*(JawT*.5+.00010))+forward*(JawL*.5);p.axis=unit(forward);p.side=width;p.normal=unit(cross3(forward,width));
        int segments=2;std::vector<V> v;for(int ring=0;ring<=segments;ring++)for(auto c:std::vector<std::array<int,2>>{{-1,-1},{1,-1},{1,1},{-1,1}})v.push_back(p.center+p.axis*((double(ring)/segments-.5)*JawL)+p.side*(c[0]*JawW*.5)+p.normal*(c[1]*JawT*.5));return v;
    }
    // Reconstruct vertex fans from immutable face IDs. A cut separates exactly
    // the two fans beside each cut edge, leaving crack-tip connectivity intact.
    void rebuildTopology(std::vector<V>& x,std::vector<V>& v){
        auto oldTriangles=triangles;auto oldX=x,oldV=v;int oldLayerNodes=layerNodes;DSU fans(int(sourceFaces.size()*3));
        auto corner=[&](int f,int vertex){for(int k=0;k<3;k++)if(sourceFaces[f][k]==vertex)return 3*f+k;throw std::runtime_error("Invalid mesh fan");};
        for(auto&[e,fs]:edgeFaces)if(fs.size()==2&&!cuts.count(e))for(int vertex:e)fans.join(corner(fs[0],vertex),corner(fs[1],vertex));
        std::map<int,int> nodeMap;rest.clear();origins.clear();triangles.clear();fixed.clear();x.clear();v.clear();
        for(int f=0;f<int(sourceFaces.size());f++){Face out;for(int k=0;k<3;k++){
            int fan=fans.get(3*f+k),org=sourceFaces[f][k];auto[it,inserted]=nodeMap.emplace(fan,int(rest.size()));out[k]=it->second;
            if(inserted){rest.push_back(original[org]+V(0,0,Thickness*.5));origins.push_back(org);if(org/Nx==Ny-1)fixed.push_back(out[k]);
                if(oldTriangles.empty()){x.push_back(rest.back());v.emplace_back(0,0,0);}else{x.push_back(oldX[oldTriangles[f][k]]);v.push_back(oldV[oldTriangles[f][k]]);}}
        }triangles.push_back(out);}
        layerNodes=int(rest.size());std::vector<int> bottomOld(layerNodes,-1);if(!oldTriangles.empty())for(int f=0;f<int(sourceFaces.size());f++)for(int k=0;k<3;k++)bottomOld[triangles[f][k]]=oldTriangles[f][k]+oldLayerNodes;
        for(int i=0;i<layerNodes;i++){rest.push_back(rest[i]-V(0,0,Thickness));origins.push_back(origins[i]);if(origins[i]/Nx==Ny-1)fixed.push_back(i+layerNodes);if(oldTriangles.empty()){x.push_back(rest.back());v.emplace_back(0,0,0);}else{x.push_back(oldX[bottomOld[i]]);v.push_back(oldV[bottomOld[i]]);}}
        // Consistent prism tessellation: sort each face by immutable material
        // vertex ID so neighboring prisms choose the same side-face diagonal.
        tets.clear();std::map<Edge,int> boundary;int surfaceCount=int(triangles.size());
        for(int f=0;f<surfaceCount;f++){auto top=triangles[f],sorted=top;std::sort(sorted.begin(),sorted.end(),[&](int a,int b){return origins[a]<origins[b];});int A=sorted[0],B=sorted[1],C=sorted[2],a=A+layerNodes,b=B+layerNodes,c=C+layerNodes;tets.push_back({a,b,c,C});tets.push_back({a,b,B,C});tets.push_back({a,A,B,C});triangles.push_back({top[2]+layerNodes,top[1]+layerNodes,top[0]+layerNodes});for(int k=0;k<3;k++)boundary[edge(top[k],top[(k+1)%3])]++;}
        std::map<Face,std::pair<int,Face>> volumeFaces;for(auto&tet:tets){if(dot3(rest[tet[1]]-rest[tet[0]],cross3(rest[tet[2]]-rest[tet[0]],rest[tet[3]]-rest[tet[0]]))<0)std::swap(tet[0],tet[1]);for(Face f:{Face{tet[0],tet[2],tet[1]},Face{tet[0],tet[1],tet[3]},Face{tet[0],tet[3],tet[2]},Face{tet[1],tet[2],tet[3]}}){auto key=f;std::sort(key.begin(),key.end());auto&entry=volumeFaces[key];entry.first++;entry.second=f;}}
        for(auto&[key,value]:volumeFaces)if(value.first==1){bool bottom=true,top=true;for(int i:key){bottom&=i>=layerNodes;top&=i<layerNodes;}if(!bottom&&!top)triangles.push_back(value.second);}
        masses.assign(rest.size(),0);for(auto&tet:tets){double volume=std::abs(dot3(rest[tet[1]]-rest[tet[0]],cross3(rest[tet[2]]-rest[tet[0]],rest[tet[3]]-rest[tet[0]])))/6;for(int i:tet)masses[i]+=volume*1000/4;}
        DSU connected(int(rest.size()));for(auto&f:triangles){connected.join(f[0],f[1]);connected.join(f[1],f[2]);}std::set<int> roots;for(int i=0;i<int(rest.size());i++)roots.insert(connected.get(i));components=int(roots.size());
    }
    void create(const std::vector<V>& x,const std::vector<V>& v){
        auto sim=std::make_shared<sofa::simulation::graph::DAGSimulation>();sofa::simulation::Simulation::theSimulation=sim;root=sim->createNewGraph("EndoForgePhase3");root->setDt(H);root->setGravity(V(0,0,0));
        add(root.get(),"FreeMotionAnimationLoop");solver=dynamic_cast<ConstraintSolver*>(add(root.get(),"BlockGaussSeidelConstraintSolver",{{"name","contactSolver"},{"maxIterations","80"},{"tolerance","0.000001"},{"computeConstraintForces","true"}}).get());
        add(root.get(),"CollisionPipeline",{{"depth","8"}});add(root.get(),"BruteForceBroadPhase");add(root.get(),"BVHNarrowPhase");
        add(root.get(),"LocalMinDistance",{{"alarmDistance","0.0015"},{"contactDistance","0.00045"},{"angleCone","0"},{"useLMDFilters","true"}});
        add(root.get(),"CollisionResponse",{{"response","FrictionContactConstraint"},{"responseParams","mu=0.8"}});
        auto body=root->createChild("membrane");add(body.get(),"EulerImplicitSolver",{{"name","integrator"},{"rayleighStiffness","0.015"},{"rayleighMass","8.0"}});add(body.get(),"SparseLDLSolver",{{"name","linearSolver"},{"template","CompressedRowSparseMatrixMat3x3d"}});
        std::ostringstream tri,tet;for(auto&f:triangles)for(int i:f)tri<<i<<' ';for(auto&f:tets)for(int i:f)tet<<i<<' ';
        add(body.get(),"TetrahedronSetTopologyContainer",{{"name","topology"},{"position",vecText(rest)},{"tetrahedra",tet.str()}});
        dofs=dynamic_cast<MO*>(add(body.get(),"MechanicalObject",{{"name","dofs"},{"template","Vec3d"},{"position",vecText(rest)},{"rest_position",vecText(rest)}}).get());
        add(body.get(),"DiagonalMass",{{"vertexMass",indices(masses)}});
        add(body.get(),"TetrahedronFEMForceField",{{"name","elasticity"},{"method","large"},{"youngModulus","25000"},{"poissonRatio","0.35"}});
        add(body.get(),"FixedProjectiveConstraint",{{"indices",indices(fixed)}});add(body.get(),"LinearSolverConstraintCorrection",{{"linearSolver","@linearSolver"},{"ODESolver","@integrator"},{"regularizationTerm","0.01"}});
        auto surface=body->createChild("surface");add(surface.get(),"MeshTopology",{{"name","topology"},{"position",vecText(rest)},{"triangles",tri.str()}});add(surface.get(),"MechanicalObject",{{"name","dofs"},{"position",vecText(rest)}});
        for(auto name:{"TriangleCollisionModel","PointCollisionModel"})add(surface.get(),name,{{"group","1"},{"contactFriction","0.8"},{"selfCollision","false"}});add(surface.get(),"IdentityMapping",{{"input","@../dofs"},{"output","@dofs"}});
        for(int k=0;k<2;k++)for(int j=0;j<2;j++){
            int segments=2,end=segments*4;std::ostringstream box;box<<"0 2 1 0 3 2 "<<end<<' '<<end+1<<' '<<end+2<<' '<<end<<' '<<end+2<<' '<<end+3<<' ';for(int r=0;r<segments;r++)for(int side=0;side<4;side++){int a=r*4+side,b=r*4+(side+1)%4,c=b+4,d=a+4;box<<a<<' '<<b<<' '<<c<<' '<<a<<' '<<c<<' '<<d<<' ';}
            tools[k].listeners[j].clear();auto node=root->createChild("tool"+std::to_string(k)+"jaw"+std::to_string(j));auto verts=jawVertices(k,j);
            add(node.get(),"MeshTopology",{{"name","topology"},{"position",vecText(verts)},{"triangles",box.str()}});tools[k].dofs[j]=dynamic_cast<MO*>(add(node.get(),"MechanicalObject",{{"name","dofs"},{"position",vecText(verts)}}).get());
            int n=0;for(auto name:{"TriangleCollisionModel","PointCollisionModel"}){if(k==1&&std::string(name)=="LineCollisionModel")continue;auto model=add(node.get(),name,{{"name","collision"+std::to_string(n++)},{"group","2"},{"simulated","false"},{"moving","true"},{"contactFriction","0.8"},{"selfCollision","false"}});
                auto listener=sofa::core::objectmodel::New<Listener>(dynamic_cast<sofa::core::CollisionModel*>(model.get()),nullptr);listener->setName("contacts"+std::to_string(k)+std::to_string(j)+std::to_string(n));root->addObject(listener);tools[k].listeners[j].push_back(listener.get());}
        }
        auto tray=root->createChild("tray");std::string plane="-.1375 -.1075 -.0043 .1375 -.1075 -.0043 .1375 .1075 -.0043 -.1375 .1075 -.0043";
        add(tray.get(),"MeshTopology",{{"name","topology"},{"position",plane},{"triangles","0 1 2 0 2 3"}});add(tray.get(),"MechanicalObject",{{"name","dofs"},{"position",plane}});add(tray.get(),"TriangleCollisionModel",{{"group","2"},{"simulated","false"},{"moving","false"},{"contactFriction","0.8"}});
        std::cout<<"Phase3 initializing graph nodes="<<rest.size()<<std::endl;sofa::simulation::node::initRoot(root.get());std::cout<<"Phase3 graph ready"<<std::endl;if(!dofs||!solver)throw std::runtime_error("Phase3 component unavailable");
        auto pos=dofs->x.getValue(),vel=dofs->v.getValue();for(size_t i=0;i<x.size();i++){pos[i]=x[i];vel[i]=v[i];}dofs->x.setValue(pos);dofs->v.setValue(vel);dofs->xfree.setValue(pos);dofs->vfree.setValue(vel);updateJaws(true);
    }
    void reset(int id){
        if(root){sofa::simulation::node::unload(root);root.reset();}cuts.clear();triangles.clear();tools={};
        for(int k=0;k<2;k++){tools[k].pivot=V(k?-.12:.12,-.14,.15);tools[k].tip=tools[k].commanded=V(k?.022:-.022,-.047,.006);}
        std::vector<V>x,v;rebuildTopology(x,v);create(x,v);resetId=id;revision++;cutCount=0;cutLength=0;time=0;maxDisp=0;healthy=true;paused=false;minArea=minVolume=1;message="Reset complete - intact membrane";
    }
    void release(int k,const std::string& reason){auto&t=tools[k];t.grasping=t.latched=false;t.anchorFace=-1;t.lost=0;t.gripState="released";message=reason;}
    void stopInput(const std::string& reason){for(int k=0;k<2;k++){tools[k].closed=0;tools[k].commanded=tools[k].tip;tools[k].strokeEdges.clear();release(k,reason);}}
    bool command(const json&j){
        if(!j.is_object()||j.value("type","")!="command")return false;
        if(!j.contains("reset_id")||!j["reset_id"].is_number_integer()||j["reset_id"].get<double>()<0||j["reset_id"].get<double>()>2147483647||!j.contains("paused")||!j["paused"].is_boolean()||!j.contains("active_tool")||!j["active_tool"].is_number_integer()||!j.contains("tools")||!j["tools"].is_array()||j["tools"].size()!=2)throw std::invalid_argument("Invalid phase3 command");
        int active=j["active_tool"].get<int>();if(active<0||active>1)throw std::invalid_argument("Invalid active tool");
        if(j.contains("seq")&&(!j["seq"].is_number_unsigned()&&!j["seq"].is_number_integer()||j["seq"].get<double>()<0))throw std::invalid_argument("Invalid sequence");
        std::array<V,2> positions;double closures[2],rolls[2];for(int k=0;k<2;k++){auto&t=j["tools"][k];if(!t.is_object()||!t.contains("tip_m")||!t["tip_m"].is_array()||t["tip_m"].size()!=3||!t.contains("closed")||!t["closed"].is_number()||!t.contains("roll_deg")||!t["roll_deg"].is_number())throw std::invalid_argument("Invalid tool");for(auto&a:t["tip_m"])if(!a.is_number())throw std::invalid_argument("Invalid tip");positions[k]=V(t["tip_m"][0].get<double>(),t["tip_m"][1].get<double>(),t["tip_m"][2].get<double>());closures[k]=t["closed"].get<double>();rolls[k]=t["roll_deg"].get<double>();if(!std::isfinite(length(positions[k]))||!std::isfinite(closures[k])||!std::isfinite(rolls[k]))throw std::invalid_argument("Nonfinite tool");}
        int rid=j["reset_id"].get<int>();bool changed=rid!=resetId;if(changed)reset(rid);if(active!=activeTool)tools[activeTool].commanded=tools[activeTool].tip;if(active!=1)tools[1].strokeEdges.clear();activeTool=active;paused=j["paused"].get<bool>();
        for(int k=0;k<2;k++){auto&t=tools[k];if(changed||k==active){t.commanded=limitTip(k,positions[k]);t.commandedRoll=std::remainder(rolls[k],360.0);t.closed=std::clamp(closures[k],0.0,1.0);}else if(closures[k]<.5)t.closed=0;if(t.closed<.5)t.strokeEdges.clear();}
        if(changed)updateJaws(true);return true;
    }
    void updateJaws(bool snap=false){for(int k=0;k<2;k++)for(int j=0;j<2;j++){auto& t=tools[k];auto vertices=jawVertices(k,j);auto x=t.dofs[j]->x.getValue(),target=x,vel=t.dofs[j]->v.getValue();for(size_t i=0;i<vertices.size();i++){vel[i]=snap?V(0,0,0):(vertices[i]-x[i])/integrationStep;target[i]=vertices[i];}if(snap)t.dofs[j]->x.setValue(target);t.dofs[j]->xfree.setValue(target);t.dofs[j]->v.setValue(vel);t.dofs[j]->vfree.setValue(vel);}}
    void commitJaws(){for(int k=0;k<2;k++)for(int j=0;j<2;j++){auto vertices=jawVertices(k,j);auto x=tools[k].dofs[j]->x.getValue();for(size_t i=0;i<vertices.size();i++)x[i]=vertices[i];tools[k].dofs[j]->x.setValue(x);}}
    void contacts(){
        const auto&lambda=solver->d_constraintForces.getValue();const auto&x=dofs->x.getValue();
        for(int k=0;k<2;k++){auto&t=tools[k];t.contactCount=0;t.inner[0]=t.inner[1]=0;t.force=0;t.penetration=0;t.contactPoints.clear();std::vector<bool> rows(lambda.size(),false);
            for(int j=0;j<2;j++){
                for(auto*l:t.listeners[j])for(auto&group:l->getContactsVector())for(auto&c:group)if(c.value<.0001){t.contactCount++;bool first=c.elem.first.getCollisionModel()->getContext()==t.dofs[j]->getContext();V point=c.point[first?0:1],normal=first?V(c.normal):-V(c.normal);V innerNormal=t.poses[j].normal*(j?-1.:1.);if(dot3(point-t.poses[j].center,innerNormal)>JawT*.1&&dot3(normal,innerNormal)>.15){t.inner[j]++;t.contactPoints.emplace_back(c.point[first?1:0]);}}
                auto&matrix=t.dofs[j]->c.getValue();for(auto row=matrix.begin();row!=matrix.end();++row)if(row.index()<rows.size())rows[row.index()]=true;
            }
            for(size_t i=0;i+2<lambda.size();i+=3)if(rows[i])t.force+=std::sqrt(lambda[i]*lambda[i]+lambda[i+1]*lambda[i+1]+lambda[i+2]*lambda[i+2])/integrationStep;
            for(auto&p:t.poses)for(auto&q:x){V d=q-p.center;double a=JawL*.5-std::abs(dot3(d,p.axis)),b=JawW*.5-std::abs(dot3(d,p.side)),c=JawT*.5-std::abs(dot3(d,p.normal));if(a>0&&b>0&&c>0)t.penetration=std::max(t.penetration,std::min({a,b,c}));}
        }
    }
    void captureAnchor(){auto&t=tools[0];const auto&x=dofs->x.getValue();double best=1e9;V cp;for(int f=0;f<int(sourceFaces.size());f++){auto&a=triangles[f];V q=closestTriangle(t.tip,x[a[0]],x[a[1]],x[a[2]]);if(length(q-t.tip)<best){best=length(q-t.tip);cp=q;t.anchorFace=f;}}
        auto&a=triangles[t.anchorFace];V b=x[a[1]]-x[a[0]],c=x[a[2]]-x[a[0]],d=cp-x[a[0]];double bb=dot3(b,b),bc=dot3(b,c),cc=dot3(c,c),den=bb*cc-bc*bc,u=(dot3(d,b)*cc-dot3(d,c)*bc)/den,v=(dot3(d,c)*bb-dot3(d,b)*bc)/den;t.anchorWeights=V(1-u-v,u,v);t.anchorLocal=cp-t.tip;t.slip=0;
    }
    bool split(const std::set<Edge>& batch){
        auto oldCuts=cuts;auto oldRest=rest;auto oldOrigins=origins;auto oldFixed=fixed;auto oldTriangles=triangles;auto oldTets=tets;int oldLayers=layerNodes;auto oldMasses=masses;auto oldTools=tools;auto oldRoot=root;auto oldDofs=dofs;auto oldSolver=solver;int oldComponents=components;double oldLength=cutLength;
        bool any=false;for(auto&e:batch)if(edgeFaces.count(e)&&edgeFaces[e].size()==2&&!cuts.count(e)){cuts.insert(e);cutLength+=length(original[e[1]]-original[e[0]]);any=true;}if(!any)return false;
        auto start=Clock::now();std::vector<V>x(dofs->x.getValue().begin(),dofs->x.getValue().end()),v(dofs->v.getValue().begin(),dofs->v.getValue().end());rebuildTopology(x,v);
        // Keep the entire old SOFA graph alive until the replacement is ready.
        // On construction failure its positions, constraints and anchors remain
        // valid, so no partial revision is sent to the renderer.
        try{root.reset();create(x,v);}catch(...){if(root)sofa::simulation::node::unload(root);root=oldRoot;dofs=oldDofs;solver=oldSolver;cuts=oldCuts;rest=oldRest;origins=oldOrigins;fixed=oldFixed;triangles=oldTriangles;tets=oldTets;layerNodes=oldLayers;masses=oldMasses;tools=oldTools;components=oldComponents;cutLength=oldLength;message="Topology rebuild rejected - previous state retained";safetyStops++;return false;}
        sofa::simulation::node::unload(oldRoot);revision++;cutCount++;lastRebuildMs=std::chrono::duration<double,std::milli>(Clock::now()-start).count();message="Physical cut - membrane connectivity split";return true;
    }
    bool bladeCut(){
        auto&t=tools[1];if(activeTool!=1||t.closed<.5||t.strokeUsed)return false;
        // Native inner-blade contact seeds nearest 5 mm material mesh edges
        // inside a 12 mm blade segment / 7 mm closing-wedge envelope. The
        // 3.6 mm contact-to-edge snap is a disclosed discretization bound.
        V back=unit(t.pivot-t.tip),a=t.tip,b=t.tip+back*.012;const auto&x=dofs->x.getValue();std::set<Edge> batch;
        for(auto&[e,faces]:edgeFaces)if(faces.size()==2&&!cuts.count(e)){
            int f=faces.front(),ia=-1,ib=-1;for(int j=0;j<3;j++){if(sourceFaces[f][j]==e[0])ia=triangles[f][j];if(sourceFaces[f][j]==e[1])ib=triangles[f][j];}
            V midpoint=(x[ia]+x[ib])*.5,ab=b-a;double s=std::clamp(dot3(midpoint-a,ab)/dot3(ab,ab),0.,1.);V closest=a+ab*s;
            bool actualContact=false;for(auto&cp:t.contactPoints)if(length(cp-midpoint)<.0036){actualContact=true;break;}
            // Only inner blade contacts can seed a cut, and only within the
            // finite 12 mm moving blade wedge. Store contacted material edges
            // during this closing stroke; apply once the blades reach 18 deg.
            if(actualContact&&dot3(midpoint-a,back)>-.002&&dot3(midpoint-a,back)<.014&&length(midpoint-closest)<=.007)t.strokeEdges.insert(e);
        }
        if(t.angle>18)return false;t.strokeUsed=true;
        // Resolve the contacted wedge to one incision path, never a radial set
        // of severed edges that would punch out every touched triangle. Within
        // each contacted component choose the greatest blade-axis span, then
        // find its shortest mesh-edge path. Every retained edge was seeded by
        // an actual inner-blade contact during this same closing stroke.
        std::map<int,std::vector<int>> graph;for(auto&e:t.strokeEdges){graph[e[0]].push_back(e[1]);graph[e[1]].push_back(e[0]);}
        std::set<int> seen;double bestSpan=-1;int first=-1,last=-1;
        for(auto&[seed,adj]:graph)if(!seen.count(seed)){std::queue<int> q;q.push(seed);seen.insert(seed);int low=seed,high=seed;while(!q.empty()){int n=q.front();q.pop();if(dot3(original[n],back)<dot3(original[low],back))low=n;if(dot3(original[n],back)>dot3(original[high],back))high=n;for(int m:graph[n])if(seen.insert(m).second)q.push(m);}double span=dot3(original[high]-original[low],back);if(span>bestSpan){bestSpan=span;first=low;last=high;}}
        if(first>=0&&last>=0&&first!=last){std::map<int,double> distance;std::map<int,int> previous;for(auto&[n,adj]:graph)distance[n]=1e10;distance[first]=0;using Entry=std::pair<double,int>;std::priority_queue<Entry,std::vector<Entry>,std::greater<Entry>> queue;queue.push({0,first});while(!queue.empty()){auto[d,n]=queue.top();queue.pop();if(d>distance[n])continue;for(int m:graph[n]){double next=d+length(original[m]-original[n]);if(next<distance[m]){distance[m]=next;previous[m]=n;queue.push({next,m});}}}if(distance[last]<1e9){for(int n=last;n!=first;n=previous[n])batch.insert(edge(n,previous[n]));}}
        if(batch.empty()){message="Scissors closed clear of tissue - no cut";return false;}return split(batch);
    }
    void step(){
        auto start=Clock::now();if(!paused&&healthy){auto prevX=dofs->x.getValue(),prevV=dofs->v.getValue();std::array<V,2> oldTip;double oldAngle[2],oldRoll[2];
            for(int k=0;k<2;k++){auto&t=tools[k];oldTip[k]=t.tip;oldAngle[k]=t.angle;oldRoll[k]=t.roll;V d=t.commanded-t.tip;double distance=length(d);if(distance>.018*Dt)d*=.018*Dt/distance;t.tip+=d;t.roll=std::remainder(t.roll+std::clamp(std::remainder(t.commandedRoll-t.roll,360.),-60*Dt,60*Dt),360.);
                if(t.closed<.5){if(t.latched)release(k,"Jaws opened - released");t.strokeEdges.clear();t.needsOpen=false;t.angle=std::min(40.,t.angle+65*Dt);if(t.angle>28)t.strokeUsed=false;t.gripState="open";}else if(!t.needsOpen){if(t.latched&&t.force<.03)t.holdAngle=std::max(0.,t.holdAngle-.6);t.angle=std::max(t.latched?t.holdAngle:(k==1?8.:0.),t.angle-40*Dt);}
            }
            std::array<V,2> nextTip;double nextAngle[2],nextRoll[2];for(int k=0;k<2;k++){nextTip[k]=tools[k].tip;nextAngle[k]=tools[k].angle;nextRoll[k]=tools[k].roll;}
            bool accepted=false,finite=true;double oldTime=root->getTime();
            for(int parts:{1,2,4}){
                if(parts>1){adaptiveRetries++;dofs->x.setValue(prevX);dofs->v.setValue(prevV);dofs->xfree.setValue(prevX);dofs->vfree.setValue(prevV);root->setTime(oldTime);for(int k=0;k<2;k++){tools[k].tip=oldTip[k];tools[k].angle=oldAngle[k];tools[k].roll=oldRoll[k];}updateJaws(true);}
                integrationStep=Dt/parts;root->setDt(integrationStep);minVolume=minArea=1;finite=true;accepted=true;lastSubsteps=parts;
                for(int sub=1;sub<=parts;sub++){
                    for(int k=0;k<2;k++){tools[k].tip=oldTip[k]+(nextTip[k]-oldTip[k])*(double(sub)/parts);tools[k].angle=oldAngle[k]+(nextAngle[k]-oldAngle[k])*(double(sub)/parts);tools[k].roll=oldRoll[k]+std::remainder(nextRoll[k]-oldRoll[k],360.)*(double(sub)/parts);}
                    updateJaws();sofa::simulation::node::animate(root.get(),integrationStep);commitJaws();contacts();const auto&trial=dofs->x.getValue();
                    for(auto&f:triangles){double den=length(cross3(rest[f[1]]-rest[f[0]],rest[f[2]]-rest[f[0]]));double ratio=length(cross3(trial[f[1]]-trial[f[0]],trial[f[2]]-trial[f[0]]))/den;if(!std::isfinite(ratio))finite=false;minArea=std::min(minArea,ratio);}
                    for(auto&tet:tets){double restVolume=dot3(rest[tet[1]]-rest[tet[0]],cross3(rest[tet[2]]-rest[tet[0]],rest[tet[3]]-rest[tet[0]]));double ratio=dot3(trial[tet[1]]-trial[tet[0]],cross3(trial[tet[2]]-trial[tet[0]],trial[tet[3]]-trial[tet[0]]))/restVolume;if(!std::isfinite(ratio))finite=false;minVolume=std::min(minVolume,ratio);}
                    for(size_t i=0;i<trial.size();i++)if(!std::isfinite(length(trial[i]))||length(trial[i]-rest[i])>.20)finite=false;
                    if(!finite||minVolume<.08||minArea<.035||!std::isfinite(tools[0].force)||!std::isfinite(tools[1].force)||tools[0].force>3||tools[1].force>3){accepted=false;break;}
                }
                if(accepted)break;
            }
            const auto&x=dofs->x.getValue();
            if(!accepted){dofs->x.setValue(prevX);dofs->v.setValue(prevV);dofs->xfree.setValue(prevX);dofs->vfree.setValue(prevV);root->setTime(oldTime);for(int k=0;k<2;k++){tools[k].tip=oldTip[k];tools[k].angle=oldAngle[k];tools[k].roll=oldRoll[k];tools[k].force=0;tools[k].contactCount=0;tools[k].penetration=0;}updateJaws(true);safetyStops++;stopInput("Safety stop - open tools or reset");if(!finite||minVolume<.08||minArea<.035)healthy=false;}
            else{
                time+=Dt;
                auto&t=tools[0];if(t.closed>=.5&&!t.needsOpen){if(t.inner[0]>0&&t.inner[1]>0&&t.force>(t.latched?.00001:.03)){if(!t.latched){t.latched=true;t.holdAngle=t.angle;captureAnchor();}t.grasping=true;t.lost=0;t.gripState="holding";}
                    else if(t.latched&&++t.lost>9){release(0,"Friction contact lost - open and regrasp");t.needsOpen=true;t.gripState="slipping";}else if(!t.latched)t.gripState=t.contactCount?"contact":"closing";}
                if(t.anchorFace>=0){auto&f=triangles[t.anchorFace];V q=x[f[0]]*t.anchorWeights[0]+x[f[1]]*t.anchorWeights[1]+x[f[2]]*t.anchorWeights[2];t.slip=std::max(t.slip,length(q-t.tip-t.anchorLocal));}
                if(tools[1].closed>=.5)tools[1].gripState=tools[1].strokeUsed?"closed":"cutting";bladeCut();
            }
        }
        maxDisp=0;const auto&x=dofs->x.getValue();for(size_t i=0;i<x.size();i++){double d=length(x[i]-rest[i]);if(!std::isfinite(d)||d>.20){healthy=false;stopInput("Solver safety stop - reset");break;}maxDisp=std::max(maxDisp,d);}frame++;stepMs=std::chrono::duration<double,std::milli>(Clock::now()-start).count();
    }
    json vertices()const{json a=json::array();for(auto&v:dofs->x.getValue())a.push_back(jvec(v));return a;}
    json toolState(int k)const{auto&t=tools[k];json jp=json::array();for(auto&p:t.poses)jp.push_back({{"center_m",jvec(p.center)},{"axis",jvec(p.axis)},{"side",jvec(p.side)},{"normal",jvec(p.normal)}});return {{"tip_m",jvec(t.tip)},{"roll_deg",t.roll},{"jaw_open_fraction",t.angle/40},{"jaw_angle_deg",t.angle},{"grasping",t.grasping},{"force_n",t.force},{"contact_force_n",t.force},{"contact_count",t.contactCount},{"inner_contacts",{t.inner[0],t.inner[1]}},{"penetration_m",t.penetration},{"slip_distance_m",t.slip},{"grip_state",t.gripState},{"jaw_poses",jp},{"pivot_m",jvec(t.pivot)}};}
    json hello(){return {{"type","hello"},{"protocol",3},{"units","m"},{"vertices",vertices()},{"triangles",triangles},{"topology_revision",revision},{"solver","SOFA TetrahedronFEM + friction contact; full-thickness mesh-edge fan splitting"},{"dt",Dt},{"material_validated",false},{"thickness_m",Thickness},{"mesh_spacing_m",.005},{"total_mass_kg",TotalMass},{"tool_count",2},{"pivot_m",jvec(tools[0].pivot)}};}
    json state(){json j={{"type","state"},{"protocol",3},{"frame",frame},{"reset_id",resetId},{"time",time},{"vertices",vertices()},{"triangles",triangles},{"topology_revision",revision},{"cut_count",cutCount},{"cut_edge_count",cuts.size()},{"component_count",components},{"cut_length_m",cutLength},{"step_ms",stepMs},{"topology_rebuild_ms",lastRebuildMs},{"max_displacement_m",maxDisp},{"healthy",healthy},{"message",message},{"active_tool",activeTool},{"tools",{toolState(0),toolState(1)}},{"safety_stops",safetyStops},{"min_triangle_area_ratio",minArea},{"min_tet_volume_ratio",minVolume},{"adaptive_retries",adaptiveRetries},{"last_substeps",lastSubsteps}};auto first=toolState(0);for(auto&[key,value]:first.items())j[key]=value;return j;}
};

int selfTestPhase3(Membrane&t,const std::filesystem::path&out){
    json r={{"phase",3},{"checks",json::object()},{"stages",json::array()}};bool allHealthy=true,allFinite=true;std::vector<double> costs;auto check=[&](const char*n,bool b){r["checks"][n]=b;std::cout<<n<<"="<<b<<std::endl;};
    auto run=[&](int n,const char*name){for(int i=0;i<n;i++){t.step();costs.push_back(t.stepMs);allHealthy&=t.healthy&&t.safetyStops==0;for(auto&tool:t.tools)allFinite&=std::isfinite(tool.force)&&std::isfinite(tool.penetration);for(auto&x:t.dofs->x.getValue())allFinite&=std::isfinite(length(x));}auto j=t.state();j.erase("vertices");j.erase("triangles");j.erase("jaw_poses");j["stage"]=name;r["stages"].push_back(j);std::cout<<name<<" "<<j.dump()<<std::endl;};
    run(15,"rest");check("rest_equilibrium",t.healthy&&t.maxDisp<1e-8);
    auto &g=t.tools[0],&s=t.tools[1];g.commanded=V(-.022,-.034,.0045);run(24,"approach");g.closed=1;run(45,"grasp");check("bilateral_grip",g.grasping);g.commanded[2]+=.004;run(30,"traction");check("grip_transfers_traction",g.grasping&&t.maxDisp>.002);
    t.activeTool=1;{int id=16+Membrane::Nx;auto q=t.dofs->x.getValue()[id];s.commanded=q+V(0,0,-.002);}run(35,"scissors_approach");s.closed=1;run(30,"scissors_cut");check("blade_closure_changes_topology",t.cutCount>0&&t.rest.size()>2*t.original.size());check("dual_tool_hold_during_cut",g.grasping);check("cut_state_healthy",t.healthy);
    int n=t.cutCount;run(10,"closed_stationary");check("one_cut_per_closure",t.cutCount==n);s.closed=0;run(25,"scissors_open");t.activeTool=0;s.commanded=V(.005,-.038,.003);run(35,"inactive_scissors_move");s.closed=1;run(35,"inactive_scissors_close");check("inactive_scissors_cannot_cut",t.cutCount==n);
    t.reset(10);s.commanded=V(.022,-.035,.05);run(90,"clear_air");t.activeTool=1;s.closed=1;run(35,"air_closure");check("air_closure_does_not_cut",t.cutCount==0);
    t.reset(11);auto initialMass=std::accumulate(t.masses.begin(),t.masses.end(),0.);std::set<Membrane::Edge> full;for(int x=0;x<Membrane::Nx-1;x++)full.insert(Membrane::edge(x+Membrane::Nx*3,x+1+Membrane::Nx*3));t.split(full);check("full_cut_separates_components",t.components==2);check("cut_preserves_mass",std::abs(std::accumulate(t.masses.begin(),t.masses.end(),0.)-initialMass)<1e-12);check("cut_preserves_material_elements",t.tets.size()==3*t.sourceFaces.size());
    int rev=t.revision,nodeCount=int(t.rest.size());check("repeated_same_edge_cut_idempotent",!t.split(full)&&t.revision==rev&&t.rest.size()==nodeCount);
    // Verify constitutive decoupling with a displacement on one fragment: the
    // other side has no shared node and remains at equilibrium after integration.
    auto x=t.dofs->x.getValue();for(size_t i=0;i<x.size();i++)if(t.origins[i]/Membrane::Nx<3&&t.origins[i]%Membrane::Nx<12)x[i][2]+=.001;t.dofs->x.setValue(x);run(15,"separated_load_probe");double other=0;for(size_t i=0;i<t.rest.size();i++)if(t.origins[i]/Membrane::Nx>3)other=std::max(other,length(t.dofs->x.getValue()[i]-t.rest[i]));check("separated_fragment_has_no_cross_cut_elastic_load",other<1e-8);
    t.reset(12);check("reset_restores_intact_topology",t.cuts.empty()&&t.components==1&&t.rest.size()==2*t.original.size()&&t.resetId==12);bool limits=true;for(int k=0;k<2;k++)for(V p:{V(10,10,10),V(-10,-10,-10),t.tools[k].pivot}){V d=t.limitTip(k,p)-t.tools[k].pivot;limits&=length(d)>=.12-1e-8&&length(d)<=.30+1e-8;}check("both_rcm_insertion_limits",limits);
    t.stopInput("timeout");check("watchdog_opens_both_tools",t.tools[0].closed==0&&t.tools[1].closed==0&&!t.tools[0].grasping);
    check("every_regular_step_healthy_without_protection",allHealthy);check("every_regular_state_finite",allFinite);std::sort(costs.begin(),costs.end());r["metrics"]={{"step_p95_ms",costs[size_t(.95*(costs.size()-1))]},{"step_max_ms",costs.back()},{"samples",costs.size()}};
    bool passed=true;for(auto&v:r["checks"].items())passed&=v.value().get<bool>();r["passed"]=passed;r["model"]={{"center_grid_nodes",t.original.size()},{"physical_node_count",t.rest.size()},{"boundary_triangle_count",t.triangles.size()},{"faces",t.sourceFaces.size()},{"spacing_m",.005},{"mass_kg",initialMass},{"bulk_young_pa",25000},{"tet_count",t.tets.size()},{"thickness_m",Membrane::Thickness},{"physics_substep_s",Membrane::H},{"output_dt_s",Dt},{"scissor_min_half_angle_deg",8},{"cut_commit_half_angle_deg",18},{"contact_compliance_regularization",.01}};std::ofstream(out)<<r.dump(2);return passed?0:2;
}
