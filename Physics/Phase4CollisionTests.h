#pragma once
// Collision repair acceptance is deliberately separate from the historical
// Phase4 core suite. Inputs and every accepted output geometry are retained.
namespace p4collision {
struct Spec {std::string id,specimen,path;double roll=90,speed=.018,approach=0;bool grip=false,regression=false;};
inline std::vector<Spec> matrix(){
    std::vector<Spec> out{{"curved_straight_regression","curved","legacy_straight",90,.018,0,true,true}};
    for(auto shape:{"flat","curved"}){
        out.push_back({std::string(shape)+"_straight_90_fast",shape,"straight",90,.018,0,true});
        out.push_back({std::string(shape)+"_diagonal_75_slow",shape,"diagonal",75,.006,-30,false});
        out.push_back({std::string(shape)+"_elbow_105_medium",shape,"elbow",105,.012,30,false});
        out.push_back({std::string(shape)+"_tangent_60_fast",shape,"tangent",60,.018,-30,false});
        out.push_back({std::string(shape)+"_reverse_120_medium",shape,"reverse",120,.012,30,false});
        out.push_back({std::string(shape)+"_vertical_90_slow",shape,"vertical",90,.006,0,true});
        out.push_back({std::string(shape)+"_straight_90_slow",shape,"straight",90,.006,0,true});
        out.push_back({std::string(shape)+"_straight_90_medium",shape,"straight",90,.012,0,true});
    }
    out.push_back({"curved_straight_90_approach_left","curved","straight",90,.018,-30,true});
    out.push_back({"curved_straight_90_approach_right","curved","straight",90,.018,30,true});
    return out;
}
inline V target(const TissueConfig&c,double y=-.015){return V(-.022,y,.0045+c.curvature*std::sin(Pi*(y+c.length*.5)/c.length));}
inline bool intersects(const std::array<V,3>&tri,const V&half){
    std::vector<V> poly(tri.begin(),tri.end());
    for(int axis=0;axis<3&&!poly.empty();axis++)for(int sign:{-1,1}){
        std::vector<V> clipped;if(poly.empty())return false;V a=poly.back();double da=half[axis]-sign*a[axis];
        for(auto&b:poly){double db=half[axis]-sign*b[axis];if((da>=0)!=(db>=0))clipped.push_back(a+(b-a)*(da/(da-db)));if(db>=0)clipped.push_back(b);a=b;da=db;}poly.swap(clipped);
    }return !poly.empty();
}
inline double surfaceDepth(Membrane&t){
    const auto&x=t.dofs->x.getValue();double maximum=0;V half(JawL*.5,JawW*.5,JawT*.5);
    for(auto&tool:t.tools)for(auto&pose:tool.poses)for(auto&f:t.triangles){
        std::array<V,3> tri;for(int i=0;i<3;i++){V d=x[f[i]]-pose.center;tri[i]=V(dot3(d,pose.axis),dot3(d,pose.side),dot3(d,pose.normal));}
        bool outside=false;for(int a=0;a<3;a++){double lo=std::min({tri[0][a],tri[1][a],tri[2][a]}),hi=std::max({tri[0][a],tri[1][a],tri[2][a]});outside|=lo>=half[a]-maximum||hi<=-half[a]+maximum;}if(outside)continue;
        double lo=maximum,hi=std::min({half[0],half[1],half[2]});if(!intersects(tri,half-V(lo,lo,lo)))continue;
        for(int i=0;i<16;i++){double mid=(lo+hi)*.5;if(intersects(tri,half-V(mid,mid,mid)))lo=mid;else hi=mid;}maximum=std::max(maximum,lo);
    }return maximum;
}
struct Input {V p;int closed;std::string phase;};
inline std::vector<Input> trajectory(const Spec&c,const TissueConfig&cfg){
    std::vector<Input> out;V home(-.022,-.047,.006),p=target(cfg),q=home;
    auto hold=[&](V v,int n,int closed,const std::string&phase){for(int i=0;i<n;i++)out.push_back({v,closed,phase});q=v;};
    auto move=[&](V v,double speed,int closed,const std::string&phase){V start=q;int n=std::max(1,int(std::ceil(length(v-start)/(speed*Dt))));for(int i=1;i<=n;i++)out.push_back({start+(v-start)*(double(i)/n),closed,phase});q=v;};
    if(c.regression){for(int i=0;i<330;i++){V v=target(cfg);if(i<90){double y=i<45?-.034:-.034+.019*std::min(1.,(i-45)/35.);v=target(cfg,y);}if(i>=150&&i<180)v[2]+=.004;if(i>=210)v=home;out.push_back({v,i>=90&&i<180?1:0,i<90?"approach":i<150?"close":i<180?"traction":i<210?"release":"straight_withdraw"});}return out;}
    V edge=target(cfg,-.034);edge[0]-=.019*std::tan(c.approach*Pi/180.);move(edge,.018,0,"entry");hold(edge,12,0,"entry_settle");
    int approachSteps=45;for(int i=1;i<=approachSteps;i++){double a=double(i)/approachSteps;V v=target(cfg,-.034+.019*a);v[0]=edge[0]+(p[0]-edge[0])*a;out.push_back({v,0,"approach"});q=v;}
    hold(p,15,0,"approach_settle");hold(p,60,1,"close");V lifted=p+V(0,0,.004);move(lifted,c.speed,1,"traction");hold(lifted,25,1,"traction_hold");hold(lifted,30,0,"release");
    if(c.path=="diagonal")home[0]+=.012;
    if(c.path=="elbow")move(lifted+V(.008,0,.004),c.speed,0,"elbow_turn");
    if(c.path=="tangent")move(lifted+V(.012,0,0),c.speed,0,"tangent_withdraw");
    if(c.path=="reverse"){move(lifted+V(0,-.010,0),c.speed,0,"reverse_out");move(lifted+V(0,-.002,0),c.speed,0,"reverse_back");}
    if(c.path=="vertical")move(lifted+V(0,0,.016),c.speed,0,"vertical_withdraw");
    move(home,c.speed,0,c.path=="straight"?"straight_withdraw":"final_withdraw");hold(home,40,0,"withdraw_settle");return out;
}
}
inline int collisionTestPhase4(Phase4Session&,const std::filesystem::path&out,const std::string&filter=""){
    using namespace p4collision;if(!out.parent_path().empty())std::filesystem::create_directories(out.parent_path());json report={{"schema","endoforge.collision.matrix.v1"},{"kind","collision_matrix_v1"},{"phase",4},{"filter",filter},{"thresholds",{{"node_depth_m",.00015},{"surface_depth_m",.00015},{"endpoint_error_m",.0015},{"minimum_tool_travel_m",.025}}},{"coverage","fixed 19-case pairwise and controlled-variable matrix, not a full factorial or arbitrary-path guarantee"},{"cases",json::array()}};bool all=true;int reset=500;
    for(auto&c:matrix()){if(!filter.empty()&&c.id.find(filter)==std::string::npos)continue;Phase4Session isolated(TissueConfig::preset(c.specimen));auto& s=isolated;s.mode="idle";s.resetTo(TissueConfig::preset(c.specimen),reset++);auto cfg=s.tissue.config;auto inputs=trajectory(c,cfg);auto history=out.parent_path()/(c.id+".jsonl");std::ofstream stream(history,std::ios::binary);if(!stream)throw std::runtime_error("Cannot write collision trajectory");
        stream<<json({{"type","mesh"},{"case_id",c.id},{"config",cfg.data()},{"triangles",s.tissue.triangles},{"rest_vertices",s.tissue.vertices()},{"jaw_half_extents_m",{JawL*.5,JawW*.5,JawT*.5}},{"dt_s",Dt}}).dump()<<'\n';
        double maxNode=0,maxSurface=0,maxDisp=0,minVol=1,minArea=1,travel=0,endpoint=0,peakLift=0;int contacts=0,grips=0,liftGrip=0,slips=0,accepted=0;bool healthy=true,finite=true,released=true;V previous=s.tissue.tools[0].tip,tractionStart=previous;double startTime=s.tissue.time;
        auto emit=[&](int index,const Input&i,double depth){json tools=json::array();for(int k=0;k<2;k++){auto t=s.tissue.toolState(k);t["closed"]=s.tissue.tools[k].closed;tools.push_back(t);}stream<<json({{"type","collision_frame"},{"frame",index},{"step_index",s.stepIndex},{"time_s",s.tissue.time},{"phase",i.phase},{"command_tip_m",jvec(i.p)},{"actual_tip_m",jvec(s.tissue.tools[0].tip)},{"command_closed",i.closed},{"command_roll_deg",c.roll},{"vertices",s.tissue.vertices()},{"tools",tools},{"healthy",s.tissue.healthy},{"safety_stops",s.tissue.safetyStops},{"min_tet_volume_ratio",s.tissue.minVolume},{"min_triangle_area_ratio",s.tissue.minArea},{"surface_depth_m",depth},{"max_displacement_m",s.tissue.maxDisp}}).dump()<<'\n';};
        emit(-1,{previous,0,"initial"},surfaceDepth(s.tissue));auto command=Phase4Session::homeCommand(s.tissue.resetId);
        for(int i=0;i<int(inputs.size());i++){auto&input=inputs[i];command["tools"][0]["tip_m"]=jvec(input.p);command["tools"][0]["closed"]=input.closed;command["tools"][0]["roll_deg"]=c.roll;s.command(command);double before=s.tissue.time;s.step();accepted+=s.tissue.time>before+Dt*.5;auto&t=s.tissue.tools[0];double depth=surfaceDepth(s.tissue);maxSurface=std::max(maxSurface,depth);maxNode=std::max({maxNode,t.penetration,s.tissue.tools[1].penetration});maxDisp=std::max(maxDisp,s.tissue.maxDisp);minVol=std::min(minVol,s.tissue.minVolume);minArea=std::min(minArea,s.tissue.minArea);travel+=length(t.tip-previous);previous=t.tip;contacts+=t.contactCount>0;grips+=t.grasping;slips+=t.gripState=="slipping";healthy&=s.tissue.healthy&&s.tissue.safetyStops==0;for(auto&v:s.tissue.dofs->x.getValue())finite&=std::isfinite(length(v));if(input.phase=="close")tractionStart=t.tip;if(input.phase=="traction"||input.phase=="traction_hold"){peakLift=std::max(peakLift,t.tip[2]-tractionStart[2]);liftGrip+=t.grasping;}if(input.phase=="withdraw_settle"||input.phase=="straight_withdraw")released&=!t.grasping;emit(i,input,depth);}
        stream.flush();if(!stream)throw std::runtime_error("Collision trajectory flush failed");endpoint=length(previous-inputs.back().p);json checks={{"all_steps_accepted",accepted==int(inputs.size())},{"all_states_healthy",healthy},{"all_states_finite",finite},{"no_inverted_elements",minVol>0&&minArea>0},{"node_depth_within_0_15mm",maxNode<=.00015},{"surface_depth_within_0_15mm",maxSurface<=.00015},{"tool_moved_meaningfully",travel>=.025},{"reached_withdrawal_endpoint",endpoint<=.0015},{"contact_occurred",contacts>0},{"release_has_no_hidden_grip",released&&!s.tissue.tools[0].grasping},{"traction_has_actual_lift",peakLift>=.0025},{"required_bilateral_grip_and_traction",!c.grip||(grips>0&&liftGrip>0&&maxDisp>.002)}};bool passed=true;for(auto&item:checks.items())passed&=item.value().get<bool>();all&=passed;
        report["cases"].push_back({{"id",c.id},{"specimen",c.specimen},{"roll_deg",c.roll},{"command_speed_m_s",c.speed},{"approach_azimuth_deg",c.approach},{"path",c.path},{"expected_grip",c.grip},{"trajectory_file",history.filename().generic_string()},{"frame_count",inputs.size()+1},{"checks",checks},{"passed",passed},{"metrics",{{"accepted_steps",accepted},{"simulated_seconds",s.tissue.time-startTime},{"max_node_depth_m",maxNode},{"max_surface_depth_m",maxSurface},{"max_displacement_m",maxDisp},{"min_tet_volume_ratio",minVol},{"min_triangle_area_ratio",minArea},{"tool_travel_m",travel},{"withdrawal_endpoint_error_m",endpoint},{"actual_traction_lift_m",peakLift},{"contact_steps",contacts},{"gripped_steps",grips},{"traction_gripped_steps",liftGrip},{"slip_steps",slips},{"safety_stops",s.tissue.safetyStops}}}});
        std::cout<<"Collision "<<c.id<<" passed="<<passed<<" node="<<maxNode<<" surface="<<maxSurface<<" travel="<<travel<<" endpoint="<<endpoint<<std::endl;Phase4Session::writeJson(out,report);
    }if(report["cases"].empty())throw std::invalid_argument("Collision filter matched no case");report["passed"]=all;Phase4Session::writeJson(out,report);return all?0:2;
}
