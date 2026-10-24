#pragma once

// Test the actual accepted SOFA trajectory; no node projection or path detour.
int testPhase5(Phase4Session&session,const std::filesystem::path&out,const json&options={}) {
    auto&t=session.tissue;const auto&a=*t.config.anatomy;
    std::filesystem::create_directories(out.parent_path());
    const auto tracePath=out.parent_path()/(out.stem().string()+"-states.jsonl");
    std::ofstream trace(tracePath,std::ios::binary);
    trace<<json({{"type","mesh"},{"case_id",out.stem().string()},{"triangles",t.triangles},{"rest_vertices",t.vertices()},
        {"tetrahedra",t.tets},{"fixed_indices",t.fixed},{"outer_surface_face_count",t.sourceFaces.size()},
        {"jaw_half_extents_m",{JawL*.5,JawW*.5,JawT*.5}},{"static_liver",a.source.at("static_liver")}}).dump()<<'\n';
    json report={{"phase",t.phase6Input?6:5},{"case_id",out.stem().string()},{"checks",json::object()},{"stages",json::array()},
                 {"options",options},{"config",t.config.data()},{"trace",tracePath.generic_string()}};
    double peakDepth=0,peakDisp=0,peakBed=0,peakFixed=0,minVol=1,minArea=1,minLumen=1,maxLumen=1,peakJump=0;
    bool healthy=true,finite=true,envelopeValid=true;double minLiverAlarm=1,maxLiverAlarm=0;int sample=0,cycle=0;std::vector<double>costs;std::vector<V>previous;
    const int cycles=options.value("cycles",1);const bool replay=options.value("replay",false),dual=options.value("dual",false);
    const int holdSteps=options.value("grasp_hold_steps",0),tractionHoldSteps=options.value("traction_hold_steps",0);
    const int singleTool=options.value("single_tool",0);
    const double minimumIncrement=options.value("minimum_traction_increment_m",0.0);
    const std::vector<int> testedTools=dual?std::vector<int>{0,1}:std::vector<int>{singleTool};
    const double roll=options.value("roll",90.0),lift=options.value("lift_m",.004),speed=options.value("speed_m_s",.018);
    const std::string path=options.value("path",std::string("straight"));
    if(cycles<1||cycles>100||speed<.002||speed>.018||lift<=0||lift>.01||holdSteps<0||holdSteps>18000||tractionHoldSteps<0||tractionHoldSteps>18000||singleTool<0||singleTool>1||minimumIncrement<0||minimumIncrement>lift)throw std::invalid_argument("Invalid Phase5 test options");
    std::vector<std::vector<V>>reference;std::vector<json>events;
    if(replay)session.beginRecord(1);
    auto tick=[&](const std::string&stage){
        if(!healthy)return;
        session.step();auto state=session.state();state["case_id"]=out.stem().string();state["stage"]=stage;state["sample"]=sample++;state["cycle"]=cycle;
        state["commanded_tips_m"]={jvec(t.tools[0].commanded),jvec(t.tools[1].commanded)};trace<<state.dump()<<'\n';
        costs.push_back(t.stepMs);peakDisp=std::max(peakDisp,t.maxDisp);healthy&=t.healthy&&t.safetyStops==0;
        for(auto&tool:t.tools){peakDepth=std::max(peakDepth,tool.penetration);finite&=std::isfinite(tool.force)&&std::isfinite(tool.penetration);}
        peakBed=std::max(peakBed,state["attachment_max_extension_m"].get<double>());minVol=std::min(minVol,t.minVolume);minArea=std::min(minArea,t.minArea);
        double volume=state["lumen_volume"]["ratio"].get<double>();minLumen=std::min(minLumen,volume);maxLumen=std::max(maxLumen,volume);
        double alarm=state["liver_alarm_distance_m"].get<double>(),speed=state["liver_envelope_observed_speed_m_s"].get<double>();
        envelopeValid&=std::isfinite(alarm)&&std::isfinite(speed)&&speed>=0&&std::abs(alarm-std::max(.0008,.00045+speed*Dt/t.lastSubsteps+.00015))<1e-12;
        minLiverAlarm=std::min(minLiverAlarm,alarm);maxLiverAlarm=std::max(maxLiverAlarm,alarm);
        const auto&x=t.dofs->x.getValue();for(int node:t.fixed)peakFixed=std::max(peakFixed,length(x[node]-t.rest[node]));
        for(size_t n=0;n<x.size();n++){finite&=std::isfinite(length(x[n]));if(previous.size()==x.size())peakJump=std::max(peakJump,length(x[n]-previous[n]));}previous.assign(x.begin(),x.end());
        if(replay){reference.push_back(previous);events.push_back({t.tools[0].grasping,t.tools[1].grasping,session.nodeIds,t.components,t.cutCount});}
    };
    auto stage=[&](const std::string&name){auto st=session.state();for(auto key:{"vertices","triangles","node_ids","parent_node_ids","material_node_ids"})st.erase(key);st["stage"]=name;st["cycle"]=cycle;
        if(t.fastElasticity&&options.value("assembly_compare",false)){auto[absolute,relative]=t.fastElasticity->compareWithSofaReference();st["assembly_reference_max_absolute_n_m"]=absolute;st["assembly_reference_max_relative"]=relative;bool ok=relative<1e-12;if(report["checks"].contains("assembly_matches_sofa_at_every_stage"))ok&=report["checks"]["assembly_matches_sofa_at_every_stage"].get<bool>();report["checks"]["assembly_matches_sofa_at_every_stage"]=ok;}
        report["stages"].push_back(st);std::cout<<"Phase5 "<<cycle<<" "<<name<<" grip="<<t.tools[0].grasping<<","<<t.tools[1].grasping<<" force="<<t.tools[0].force<<","<<t.tools[1].force<<" disp="<<t.maxDisp<<" healthy="<<healthy<<std::endl;};
    auto run=[&](int count,const std::string&name){for(int n=0;n<count&&healthy;n++)tick(name);stage(name);};
    auto check=[&](const std::string&name,bool pass){if(report["checks"].contains(name))pass&=report["checks"][name].get<bool>();report["checks"][name]=pass;};
    auto retainedHold=[&](int count,const std::string&name){
        bool retained=true,normalFinite=true,normalSubset=true;int completed=0;double maximumAngleDrift=0,maximumRate=0;const std::array<double,2> heldAngles{t.tools[0].angle,t.tools[1].angle};
        for(int n=0;n<count&&healthy;n++){
            tick(name);++completed;
            for(int k:testedTools){retained&=t.tools[k].grasping;maximumAngleDrift=std::max(maximumAngleDrift,std::abs(t.tools[k].angle-heldAngles[k]));maximumRate=std::max(maximumRate,std::abs(t.tools[k].actualAngleRate));for(double force:t.tools[k].innerNormalForce)normalFinite&=std::isfinite(force)&&force>=0;normalSubset&=t.tools[k].innerNormalForce[0]+t.tools[k].innerNormalForce[1]<=t.tools[k].force+1e-10;}
            if(!retained)break;
        }
        stage(name);check(name+"_every_step_retained",retained&&completed==count);
        report[name+"_completed_steps"]=completed;report[name+"_maximum_jaw_angle_drift_deg"]=maximumAngleDrift;
        if(t.config.phase6RegulatedGrip){check(name+"_normal_force_finite_nonnegative",normalFinite);check(name+"_normal_force_is_contact_load_subset",normalSubset);check(name+"_closure_rate_bounded",maximumRate<=Membrane::GripAngularRateDegS+1e-12);report[name+"_maximum_closure_rate_deg_s"]=maximumRate;}
        return retained&&completed==count;
    };
    std::array<V,2> targets=a.targets;
    json phase6Recipes;std::array<double,2> rolls{roll,roll};
    if(t.config.phase6RegulatedGrip){phase6Recipes=phase6AuthoredReadyRecipes(t)["recipes"];for(int k=0;k<2;k++){const auto&r=phase6Recipes[k];const auto&p=r["rest_ready_tip_m"];targets[k]=V(p[0].get<double>(),p[1].get<double>(),p[2].get<double>());rolls[k]=r["roll_deg"].get<double>()+roll-90.;}}
    if(options.contains("targets"))for(int k=0;k<2;k++)targets[k]=V(options["targets"][k][0].get<double>(),options["targets"][k][1].get<double>(),options["targets"][k][2].get<double>());
    const auto authoredTargets=targets;
    auto moveSelected=[&](const std::array<V,2>&destination,int minimum,const std::string&name,const std::vector<int>& selected){
        std::array<V,2>start{t.tools[0].tip,t.tools[1].tip};double distance=0;for(int k:selected)distance=std::max(distance,length(destination[k]-start[k]));
        bool retained=true;int motion=std::max(1,int(std::ceil(distance/speed/Dt)));for(int n=1;n<=std::max(minimum,motion)&&healthy;n++){double alpha=std::min(1.,double(n)/motion);for(int k:selected){t.tools[k].commanded=start[k]+(destination[k]-start[k])*alpha;t.tools[k].commandedRoll=rolls[k];}tick(name);if(name=="loaded_retraction")for(int k:selected)retained&=t.tools[k].grasping;}stage(name);
        if(name=="loaded_retraction")check("grip_retained_every_loaded_retraction_step",retained);
        if(t.config.phase6RegulatedGrip){bool arrived=true;for(int k:selected)arrived&=length(t.tools[k].tip-destination[k])<1e-8;check(name+"_target_reached",arrived);}
    };
    auto move=[&](const std::array<V,2>&destination,int minimum,const std::string&name){
        // The public controller drives one selected instrument at a time. Use
        // its right-then-left traction order, reversing that order on return.
        if(t.config.phase6RegulatedGrip&&dual&&(name=="traction"||name=="loaded_retraction")){
            const std::array<int,2> order=name=="traction"?std::array<int,2>{1,0}:std::array<int,2>{0,1};
            for(int k:order)moveSelected(destination,minimum,name,{k});
        }else moveSelected(destination,minimum,name,testedTools);
    };
    run(15,"rest");check("rest_equilibrium",t.maxDisp<.0001&&healthy);
    for(cycle=1;cycle<=cycles&&healthy;cycle++){
        if(t.config.phase6RegulatedGrip){
            targets=authoredTargets;
            for(int k:testedTools){
                const auto recipe=phase6ReadyRecipe(t,k,authoredTargets[k],authoredTargets[k],rolls[k],phase6Recipes[k]["approach_waypoints"]);
                const V frozen=phase6SampleReadyTarget(t,recipe);const auto waypoints=phase6ResolveReadyWaypoints(t,recipe,frozen);
                for(const auto&point:waypoints){auto destination=std::array<V,2>{t.tools[0].tip,t.tools[1].tip};destination[k]=point;moveSelected(destination,0,"approach",{k});}
                t.tools[k].closed=1;for(int n=0;n<90&&healthy&&!t.tools[k].grasping;n++)tick("grasp");
                check("selected_tool_"+std::to_string(k)+"_grips",t.tools[k].grasping);targets[k]=t.tools[k].tip;
                if(dual&&k==0){targets[0][2]+=.001;moveSelected(targets,0,"left_handoff_lift",{0});}
            }
        }else{move(targets,90,"approach");for(int k:testedTools)t.tools[k].closed=1;}
        run(60,"grasp");check("first_bilateral_contact_grip",t.tools[singleTool].grasping);if(dual)check("second_bilateral_contact_grip",t.tools[1].grasping);
        if(holdSteps&&!retainedHold(holdSteps,"extended_grasp_hold"))break;
        const auto beforeTraction=t.dofs->x.getValue();
        auto traction=targets;for(auto&p:traction)p[2]+=lift;
        if(path=="lateral")for(int k=0;k<2;k++)traction[k][0]+=(k?1:-1)*.001;
        if(path=="forward")for(auto&p:traction)p[1]-=.001;
        move(traction,50,"traction");double increment=0;for(size_t n=0;n<beforeTraction.size();n++)increment=std::max(increment,length(t.dofs->x.getValue()[n]-beforeTraction[n]));
        if(minimumIncrement>0)report["traction_increment_from_pre_lift_m"]=increment;
        check("grip_transfers_deformation",t.tools[singleTool].grasping&&(minimumIncrement>0?increment>=minimumIncrement:t.maxDisp>.002));if(dual)check("dual_hold_after_traction",t.tools[0].grasping&&t.tools[1].grasping);
        if(tractionHoldSteps&&!retainedHold(tractionHoldSteps,"extended_traction_hold"))break;
        if(tractionHoldSteps&&minimumIncrement>0){double retainedIncrement=0;for(size_t n=0;n<beforeTraction.size();n++)retainedIncrement=std::max(retainedIncrement,length(t.dofs->x.getValue()[n]-beforeTraction[n]));report["retained_traction_increment_from_pre_lift_m"]=retainedIncrement;check("extended_traction_deformation_retained",retainedIncrement>=minimumIncrement);}
        check("elastic_liver_bed_loaded",session.state()["attachment_max_extension_m"].get<double>()>1e-6);
        if(holdSteps||tractionHoldSteps){move(targets,50,"loaded_retraction");bool retained=true;for(int k:testedTools)retained&=t.tools[k].grasping;check("grip_retained_during_loaded_retraction",retained);}
        for(auto&tool:t.tools)tool.closed=0;run(45,"release");check("both_released",!t.tools[0].grasping&&!t.tools[1].grasping);
        move(a.home,90,"straight_retreat");run(30,"settle");check("release_recovery",t.maxDisp<.0005);
    }
    check("all_states_healthy",healthy);check("all_states_finite",finite);check("fixed_neck_stable",peakFixed<1e-8);
    check("liver_pairwise_envelope_matches_velocity_policy",envelopeValid&&t.anatomyIntersection&&t.anatomyIntersection->liverTests>0);
    check("node_penetration_bound",peakDepth<=.00015);check("valid_positive_elements",minVol>.1&&minArea>.1);check("no_cut_topology",t.cutCount==0&&t.components==1);
    if(cycles>=30)check("continuous_600_seconds_30_cycles",sample*Dt>=600&&cycle-1>=30&&session.simulationId==(replay?2:1));
    if(replay){
        session.finishRecord();const auto saved=session.lastSteps;report["replays"]=json::array();
        for(int repeat=1;repeat<=5;repeat++){
            session.resetTo(session.lastConfig,repeat+1);session.mode="replaying";double maxRms=0;bool same=true;
            for(size_t f=0;f<reference.size();f++){session.step();const auto&x=t.dofs->x.getValue();double sum=0;for(size_t n=0;n<x.size();n++){double d=length(x[n]-reference[f][n]);sum+=d*d;}maxRms=std::max(maxRms,std::sqrt(sum/x.size()));same&=json({t.tools[0].grasping,t.tools[1].grasping,session.nodeIds,t.components,t.cutCount})==events[f];}
            bool completed=session.mode=="replay_complete"&&session.stepIndex==reference.size();check("five_replays_exact_geometry_events",completed&&same&&maxRms<1e-10&&t.healthy&&t.safetyStops==0);
            report["replays"].push_back({{"repeat",repeat},{"max_frame_node_rms_m",maxRms},{"same_events",same},{"completed",completed}});std::cout<<"Phase5 replay "<<repeat<<" rms="<<maxRms<<" events="<<same<<std::endl;
        }
        json recording={{"schema","endoforge.actions.v2"},{"dt_s",Dt},{"config",t.config.data()},{"steps",saved}};
        session.loadRecording(recording);check("matching_recording_loads",session.lastSteps==saved);
        for(auto key:{"asset_fingerprint","model_version","physics_model_version","young_modulus_pa","liver_alarm_guard_m","liver_alarm_minimum_m","liver_alarm_policy_version"}){auto bad=recording;if(std::string(key)=="young_modulus_pa")bad["config"][key]=26000;else if(std::string(key)=="liver_alarm_guard_m")bad["config"][key]=.0001;else if(std::string(key)=="liver_alarm_minimum_m")bad["config"][key]=.0007;else if(std::string(key)=="liver_alarm_policy_version")bad["config"][key]=0;else bad["config"][key]="mismatch";bool rejected=false;try{session.loadRecording(bad);}catch(const std::exception&){rejected=true;}check(std::string("reject_recording_")+key,rejected&&session.lastSteps==saved);}
        auto bad=recording;bad["steps"][0]["tools"][0]["tip_m"]={1e308,1e308,1e308};bool rejected=false;try{session.loadRecording(bad);}catch(const std::exception&){rejected=true;}check("reject_invalid_recording_atomically",rejected&&session.lastSteps==saved);
        auto cmd=session.effectiveCommand();cmd["specimen"]="flat";cmd["reset_id"]=999;int before=t.resetId;rejected=false;try{session.command(cmd);}catch(const std::exception&){rejected=true;}check("reject_specimen_switch_atomically",rejected&&t.resetId==before&&t.config.name=="gallbladder");
    }
    bool pass=true;for(auto&[key,value]:report["checks"].items())pass&=value.get<bool>();
    std::sort(costs.begin(),costs.end());report["passed"]=pass;report["metrics"]={{"peak_node_depth_m",peakDepth},{"peak_displacement_m",peakDisp},{"peak_attachment_extension_m",peakBed},{"peak_fixed_error_m",peakFixed},{"min_tet_volume_ratio",minVol},{"min_triangle_area_ratio",minArea},{"min_lumen_volume_ratio",minLumen},{"max_lumen_volume_ratio",maxLumen},{"max_node_step_displacement_m",peakJump},{"samples",sample},{"duration_s",sample*Dt},{"completed_cycles",cycle-1},{"step_p95_ms",costs.empty()?0:costs[size_t(.95*(costs.size()-1))]}};
    report["metrics"]["minimum_liver_alarm_m"]=minLiverAlarm;report["metrics"]["maximum_liver_alarm_m"]=maxLiverAlarm;
    Phase4Session::writeJson(out,report);return pass?0:2;
}
