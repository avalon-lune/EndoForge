#pragma once

// Exercise the shortest physical handoff: no export/capture dwell, no waiting
// for controller calibration, and one material target sample before approach.
int testPhase6FastHandoff(Phase4Session& session,const std::filesystem::path& out,const json& options={}){
    auto&t=session.tissue;const auto&a=*t.config.anatomy;t.phase6Input=true;
    std::filesystem::create_directories(out.parent_path());
    const auto tracePath=out.parent_path()/(out.stem().string()+"-states.jsonl");
    std::ofstream trace(tracePath,std::ios::binary);bool healthy=true,retained=true,noToolOverlap=true,rcmLimits=true;int sample=0;
    const double insertion=options.value("insertion_depth_m",0.),speed=options.value("approach_speed_m_s",.018),dualLift=options.value("dual_lift_m",0.);
    const int preLiftHold=options.value("pre_lift_hold_steps",0),postLiftHold=options.value("post_lift_hold_steps",0),postContactWait=options.value("post_contact_wait_steps",0),dualHoldSteps=options.value("dual_hold_steps",1800);
    std::array<V,2> references=a.targets;
    if(options.contains("reference_targets_m"))for(int k=0;k<2;k++){const auto&v=options["reference_targets_m"].at(k);references[k]=V(v.at(0).get<double>(),v.at(1).get<double>(),v.at(2).get<double>());}
    std::array<double,2> readyRolls{90.,90.};if(options.contains("rolls_deg"))for(int k=0;k<2;k++)readyRolls[k]=options["rolls_deg"].at(k).get<double>();t.tools[0].commandedRoll=readyRolls[0];
    if(insertion<0||insertion>JawL*.5||speed<=0||speed>.018||preLiftHold<0||postLiftHold<0||postContactWait<0||dualHoldSteps<1||dualHoldSteps>18000)throw std::invalid_argument("Invalid fast handoff diagnostic options");
    auto overlap=[&](const JawPose&a,const JawPose&b){const V aa[3]{a.axis,a.side,a.normal},bb[3]{b.axis,b.side,b.normal};const double half[3]{JawL*.5,JawW*.5,JawT*.5};std::vector<V>axes;for(const auto&v:aa)axes.push_back(v);for(const auto&v:bb)axes.push_back(v);for(const auto&u:aa)for(const auto&v:bb)if(length(cross3(u,v))>1e-12)axes.push_back(unit(cross3(u,v)));for(const auto&axis:axes){double ar=0,br=0;for(int j=0;j<3;j++){ar+=half[j]*std::abs(dot3(axis,aa[j]));br+=half[j]*std::abs(dot3(axis,bb[j]));}if(std::abs(dot3(b.center-a.center,axis))>=ar+br-1e-10)return false;}return true;};
    double peakDepth=0,peakForce=0,minVolume=1,minArea=1,maxRcmCorrection=0;
    trace<<json({{"type","mesh"},{"triangles",t.triangles},{"rest_vertices",t.vertices()},{"tetrahedra",t.tets},{"fixed_indices",t.fixed},{"outer_surface_face_count",t.sourceFaces.size()},{"jaw_half_extents_m",{JawL*.5,JawW*.5,JawT*.5}},{"static_liver",a.source.at("static_liver")}}).dump()<<'\n';
    json report={{"schema","endoforge.phase6.fast-handoff.v1"},{"config",t.config.data()},{"options",options},{"checks",json::object()},{"events",json::array()},{"trace",tracePath.generic_string()}};
    auto tick=[&](const char*stage,bool requireLeft,bool requireBoth){session.step();auto state=session.state();state["stage"]=stage;state["sample"]=sample++;trace<<state.dump()<<'\n';healthy&=t.healthy&&t.safetyStops==0;if(requireLeft)retained&=t.tools[0].grasping;if(requireBoth)retained&=t.tools[1].grasping;for(const auto&tool:t.tools){peakDepth=std::max(peakDepth,tool.penetration);peakForce=std::max(peakForce,tool.force);}for(const auto&left:t.tools[0].poses)for(const auto&right:t.tools[1].poses)noToolOverlap&=!overlap(left,right);for(int k=0;k<2;k++){const double correction=length(t.limitTip(k,t.tools[k].tip)-t.tools[k].tip);maxRcmCorrection=std::max(maxRcmCorrection,correction);rcmLimits&=correction<=1e-10;}minVolume=std::min(minVolume,t.minVolume);minArea=std::min(minArea,t.minArea);};
    auto event=[&](const char*name){report["events"].push_back({{"stage",name},{"time_s",t.time},{"step",sample},{"tools",{t.toolState(0),t.toolState(1)}}});};
    auto move=[&](int k,const V&target,const char*stage,bool requireLeft,bool requireBoth=false){for(int n=0;n<900&&healthy&&retained&&length(t.tools[k].tip-target)>1e-12;n++){V delta=target-t.tools[k].tip;if(length(delta)>speed*Dt)delta*=speed*Dt/length(delta);t.tools[k].commanded=t.tools[k].tip+delta;tick(stage,requireLeft,requireBoth);}event(stage);};
    auto close=[&](int k,const char*stage,bool requireLeft){t.tools[k].closed=1;for(int n=0;n<90&&healthy&&retained&&!t.tools[k].grasping;n++)tick(stage,requireLeft,false);event(stage);return t.tools[k].grasping;};
    const V referenceLeft=references[0],derivedLeft=referenceLeft-unit(t.tools[0].pivot-referenceLeft)*insertion;const auto leftRecipe=phase6ReadyRecipe(t,0,derivedLeft,referenceLeft,readyRolls[0]);const V left=phase6SampleReadyTarget(t,leftRecipe);report["left_recipe"]=leftRecipe;report["left_reference_tip_m"]=jvec(referenceLeft);report["left_derived_tip_m"]=jvec(left);
    move(0,left,"left_approach",false);const bool first=close(0,"left_close",false);
    report["checks"]["left_grasp_established"]=first;
    if(first){
        for(int n=0;n<postContactWait&&healthy&&retained;n++)tick("left_post_contact_wait",true,false);event("left_post_contact_wait_end");
        for(int n=0;n<preLiftHold&&healthy&&retained;n++)tick("left_capture_equivalent_hold",true,false);
        move(0,t.tools[0].tip+V(0,0,.001),"immediate_left_1mm_lift",true);
        for(int n=0;n<postLiftHold&&healthy&&retained;n++)tick("post_lift_capture_equivalent_hold",true,false);
        const V original=references[1],derived=original-unit(t.tools[1].pivot-original)*insertion;
        json waypointRecipe=json::array();if(options.contains("right_clearance_height_m"))waypointRecipe.push_back({{"kind","current_xy_at_z"},{"z_m",options["right_clearance_height_m"]}});if(options.contains("right_axial_clearance_m"))waypointRecipe.push_back({{"kind","toward_pivot_from_frozen_ready"},{"distance_m",options["right_axial_clearance_m"]}});
        const auto recipe=phase6ReadyRecipe(t,1,derived,original,readyRolls[1],waypointRecipe);const V target=phase6SampleReadyTarget(t,recipe);
        report["right_material_target"]={{"sample_time_s",t.time},{"recipe",recipe},{"target_m",jvec(target)},{"sampled_once",true}};
        t.tools[1].commandedRoll=readyRolls[1];const auto waypoints=phase6ResolveReadyWaypoints(t,recipe,target);report["resolved_right_waypoints_m"]=json::array();
        for(size_t i=0;i+1<waypoints.size();i++){report["resolved_right_waypoints_m"].push_back(jvec(waypoints[i]));move(1,waypoints[i],"right_recipe_waypoint",true);}
        move(1,target,"immediate_right_approach",true);const bool second=close(1,"right_close",true);
        report["checks"]["right_grasp_established"]=second;report["checks"]["left_retained_through_handoff"]=retained;
        if(second)for(int n=0;n<postContactWait&&healthy&&retained;n++)tick("right_post_contact_wait",true,true);event("right_post_contact_wait_end");
        const auto beforeDualTraction=t.dofs->x.getValue();
        if(second&&retained&&dualLift>0){move(1,t.tools[1].tip+V(0,0,dualLift),"right_dual_traction",true,true);move(0,t.tools[0].tip+V(0,0,dualLift),"left_dual_traction",true,true);}
        double increment=0;for(size_t n=0;n<beforeDualTraction.size();n++)increment=std::max(increment,length(t.dofs->x.getValue()[n]-beforeDualTraction[n]));report["dual_traction_increment_m"]=increment;
        int held=0;if(second&&retained)for(;held<dualHoldSteps&&healthy&&retained;held++)tick("dual_hold",true,true);
        if(dualLift>0){double heldIncrement=0;for(size_t n=0;n<beforeDualTraction.size();n++)heldIncrement=std::max(heldIncrement,length(t.dofs->x.getValue()[n]-beforeDualTraction[n]));report["retained_dual_traction_increment_m"]=heldIncrement;report["checks"]["dual_traction_at_least_1_5mm"]=increment>=.0015&&heldIncrement>=.0015;}
        report["checks"]["dual_hold_every_step_retained"]=held==dualHoldSteps&&retained;if(dualHoldSteps==1800)report["checks"]["dual_hold_every_step_retained_60s"]=held==1800&&retained;report["dual_hold_requested_steps"]=dualHoldSteps;report["dual_hold_completed_steps"]=held;event("dual_hold_end");
        if(options.value("loaded_block_release_probe",false)){
            bool blocked=false;for(int n=0;n<120&&healthy&&retained&&!blocked;n++){t.tools[1].commanded=t.tools[1].tip+V(0,0,-.0001);tick("loaded_approach_liver",true,true);blocked=t.tools[1].motionGuard.blocked;}
            report["checks"]["loaded_collision_block_reached_with_grips"]=blocked&&retained;event("loaded_collision_block");
            t.tools[1].commanded=t.tools[1].tip;t.tools[1].closed=0;for(int n=0;n<45&&healthy;n++)tick("release_after_loaded_block",true,false);
            report["checks"]["loaded_block_release_succeeds"]=!t.tools[1].grasping&&t.tools[1].angle>39.99;event("loaded_block_release");
            const V withdrawal=t.tools[1].tip+unit(t.tools[1].pivot-t.tools[1].tip)*.025;move(1,withdrawal,"withdraw_after_loaded_block",true,false);
            report["checks"]["loaded_block_withdrawal_reached"]=length(t.tools[1].tip-withdrawal)<1e-9;
        }
    }else report["checks"]["dual_hold_every_step_retained"]=false;
    report["checks"]["healthy_without_safety_stop"]=healthy;report["checks"]["no_tool_jaw_obb_overlap_every_step"]=noToolOverlap;report["checks"]["actual_tip_matches_shared_rcm_limits_every_step"]=rcmLimits;report["checks"]["node_penetration_bound"]=peakDepth<=.00015;report["checks"]["positive_elements"]=minVolume>.1&&minArea>.1;
    report["metrics"]={{"peak_node_depth_m",peakDepth},{"maximum_rcm_limit_correction_m",maxRcmCorrection},{"peak_contact_force_n",peakForce},{"minimum_volume_ratio",minVolume},{"minimum_area_ratio",minArea},{"steps",sample},{"time_s",t.time}};
    bool passed=true;for(const auto&[key,value]:report["checks"].items())passed&=value.get<bool>();report["passed"]=passed;Phase4Session::writeJson(out,report);return passed?0:2;
}
#include <sofa/helper/AdvancedTimer.h>

// Offline diagnostics replay the recorded effective commands through the same
// session path as interactive replay. No geometry or contact state is restored.
int profilePhase6Recording(Phase4Session& session,const std::filesystem::path& recording,const std::filesystem::path& out,bool profile){
    std::ifstream input(recording);if(!input)throw std::runtime_error("Cannot open profile recording");json actions;input>>actions;
    session.loadRecording(actions);session.resetTo(session.lastConfig,session.tissue.resetId+1);session.mode="replaying";
    std::filesystem::create_directories(out.parent_path());std::ofstream trajectory(out.string()+".states.jsonl",std::ios::binary|std::ios::trunc);
    if(!trajectory)throw std::runtime_error("Cannot open profile trajectory");
    constexpr uint64_t firstProfileStep=943,lastProfileStep=1076;
    if(profile){sofa::helper::AdvancedTimer::setEnabled("Phase6RecordedStep",true);sofa::helper::AdvancedTimer::setInterval("Phase6RecordedStep",int(lastProfileStep-firstProfileStep));}
    json costs=json::array();bool healthy=true;const auto start=Clock::now();
    while(session.mode=="replaying"){
        const auto before=session.stepIndex;const bool measured=profile&&before>=firstProfileStep&&before<lastProfileStep;
        if(measured)sofa::helper::AdvancedTimer::begin("Phase6RecordedStep");session.step();if(measured)sofa::helper::AdvancedTimer::end("Phase6RecordedStep",std::cout);
        auto&t=session.tissue;healthy&=t.healthy&&t.safetyStops==0;costs.push_back({{"step",session.stepIndex},{"time_s",t.time},{"step_ms",t.stepMs}});
        auto state=t.state();json values={{"step",session.stepIndex},{"time_s",t.time},{"vertices",state["vertices"]},{"tools",state["tools"]},{"healthy",t.healthy},{"safety_stops",t.safetyStops},{"minimum_area_ratio",t.minArea},{"minimum_volume_ratio",t.minVolume}};
        trajectory<<values.dump()<<'\n';if(!trajectory)throw std::runtime_error("Cannot write profile trajectory");
        if(session.stepIndex==before)throw std::runtime_error("Profile replay failed to advance");
    }
    trajectory.close();json report={{"schema","endoforge.phase6-recorded-profile.v1"},{"recording",recording.generic_string()},{"profile_first_result_step",firstProfileStep+1},{"profile_last_result_step",lastProfileStep},{"steps",session.stepIndex},{"mode",session.mode},{"healthy",healthy},{"elapsed_wall_s",std::chrono::duration<double>(Clock::now()-start).count()},{"step_costs",costs}};
    Phase4Session::writeJson(out,report);return healthy&&session.mode=="replay_complete"?0:2;
}

// Controller contracts use the production command parser, session recorder and
// native FEM steps. No tissue nodes are overwritten for these tests.
int testPhase6(Phase4Session& session,const std::filesystem::path& out,bool profile=false){
    std::filesystem::create_directories(out.parent_path());
    auto&t=session.tissue;t.phase6Input=true;
    json report={{"phase",6},{"scope","native interaction contracts and unchanged FEM"},{"checks",json::object()},{"config",t.config.data()}};
    uint64_t seq=0;std::vector<double> costs;bool allHealthy=true;double maximumLead=0,maximumDrift=0;
    auto check=[&](const char*name,bool value){report["checks"][name]=value;std::cout<<name<<"="<<value<<std::endl;};
    auto command=[&](int active,bool bounded,bool holdTip,bool holdRoll){auto c=session.effectiveCommand();c["active_tool"]=active;c["seq"]=++seq;for(int k=0;k<2;k++){c["tools"][k]["bounded_target"]=bounded;c["tools"][k]["hold_tip"]=holdTip;c["tools"][k]["hold_roll"]=holdRoll;}return c;};
    if(profile){sofa::helper::AdvancedTimer::setEnabled("Phase6Step",true);sofa::helper::AdvancedTimer::setInterval("Phase6Step",30);}
    auto tick=[&](int count){for(int i=0;i<count;i++){if(profile)sofa::helper::AdvancedTimer::begin("Phase6Step");session.step();if(profile)sofa::helper::AdvancedTimer::end("Phase6Step",std::cout);costs.push_back(t.stepMs);allHealthy&=t.healthy&&t.safetyStops==0;}};
    tick(30);
    if(t.fastElasticity){const auto[absolute,relative]=t.fastElasticity->compareWithSofaReference();report["assembly_reference_comparison"]={{"element_count",t.tets.size()},{"entries_per_element",144},{"maximum_absolute_n_m",absolute},{"maximum_relative_to_element_peak",relative}};check("block_assembly_matches_sofa_element_matrices",relative<1e-12);}
    auto c=command(0,true,false,false);c["tools"][0]["tip_m"]={-.011,-.048,.07};c["tools"][0]["roll_deg"]=180.;
    session.command(c);maximumLead=length(t.tools[0].commanded-t.tools[0].tip);
    check("native_manual_target_bound_1mm",maximumLead<=.00100000001);
    check("native_manual_roll_bound_4deg",std::abs(std::remainder(t.tools[0].commandedRoll-t.tools[0].roll,360.))<=4.00000001);
    const V before=t.tools[0].tip;tick(1);
    check("movement_occurs_on_next_native_step",length(t.tools[0].tip-before)>.00059&&length(t.tools[0].tip-before)<=.00060000001);
    check("state_echoes_applied_command_sequence",t.state()["applied_command_seq"]==seq);
    c=command(0,true,true,true);c["tools"][0]["tip_m"]=jvec(before);c["tools"][0]["roll_deg"]=0.;session.command(c);
    const V stopped=t.tools[0].tip;const double stoppedRoll=t.tools[0].roll;tick(12);
    maximumDrift=length(t.tools[0].tip-stopped);
    check("hold_cancels_queue_without_feedback_backtracking",maximumDrift<1e-12&&std::abs(t.tools[0].roll-stoppedRoll)<1e-12);
    c=command(0,false,false,false);c["tools"][0]["tip_m"]={-.011,-.048,.065};session.command(c);
    check("explicit_approach_presets_keep_long_position_target",length(t.tools[0].commanded-t.tools[0].tip)>.01);tick(90);
    check("approach_reaches_target",length(t.tools[0].tip-V(-.011,-.048,.065))<1e-9);
    c=command(0,true,false,false);c["tools"][0]["tip_m"]={.06,-.048,.065};c["tools"][0]["roll_deg"]=170;session.command(c);tick(1);
    c=command(1,true,true,true);session.command(c);const V parked=t.tools[0].tip;const double parkedRoll=t.tools[0].roll;tick(8);
    check("switch_parks_translation_and_roll_of_previous_tool",length(t.tools[0].tip-parked)<1e-12&&std::abs(t.tools[0].roll-parkedRoll)<1e-12);
    const auto stable=session.effectiveCommand();c=command(1,true,true,true);c["tools"][1]["hold_tip"]="true";bool rejected=false;try{session.command(c);}catch(const std::exception&){rejected=true;}
    check("malformed_motion_flag_rejected_before_mutation",rejected&&stable==session.effectiveCommand());

    session.beginRecord(t.resetId+1);std::vector<std::vector<V>> reference;std::vector<V> referenceTips;std::vector<double> referenceRoll;
    for(int i=0;i<36;i++){
        c=command(0,true,i%12>=8,i%12>=8);c["tools"][0]["tip_m"]=jvec(t.tools[0].tip+V(0,0,.001));c["tools"][0]["roll_deg"]=t.tools[0].roll+4;
        session.command(c);tick(1);reference.emplace_back(t.dofs->x.getValue().begin(),t.dofs->x.getValue().end());referenceTips.push_back(t.tools[0].tip);referenceRoll.push_back(t.tools[0].roll);
    }
    session.finishRecord();bool ordinaryPositions=true;for(const auto&step:session.lastSteps)for(const auto&tool:step["tools"])ordinaryPositions&=!tool.contains("hold_tip")&&!tool.contains("hold_roll")&&!tool.contains("bounded_target");
    check("recording_contains_resolved_position_commands",ordinaryPositions&&session.lastSteps.size()==reference.size());
    session.resetTo(session.lastConfig,t.resetId+1);session.mode="replaying";double maxRms=0,maxPose=0;
    for(size_t i=0;i<reference.size();i++){tick(1);double sum=0;const auto&x=t.dofs->x.getValue();for(size_t n=0;n<x.size();n++){double d=length(x[n]-reference[i][n]);sum+=d*d;}maxRms=std::max(maxRms,std::sqrt(sum/x.size()));maxPose=std::max(maxPose,length(t.tools[0].tip-referenceTips[i]));maxPose=std::max(maxPose,std::abs(t.tools[0].roll-referenceRoll[i]));}
    check("effective_actions_replay_same_tool_poses",session.mode=="replay_complete"&&maxPose<1e-12);
    check("effective_actions_replay_same_tissue",maxRms<1e-10);
    check("native_steps_healthy",allHealthy);
    std::sort(costs.begin(),costs.end());double mean=std::accumulate(costs.begin(),costs.end(),0.)/costs.size();
    report["metrics"]={{"samples",costs.size()},{"step_mean_ms",mean},{"step_p95_ms",costs[size_t(.95*(costs.size()-1))]},{"maximum_native_target_lead_m",maximumLead},{"post_hold_drift_m",maximumDrift},{"replay_rms_m",maxRms},{"input_to_first_movement_simulated_s",Dt},{"ui_to_display_latency_measured",false}};
    bool passed=true;for(const auto&[name,value]:report["checks"].items())passed&=value.get<bool>();report["passed"]=passed;Phase4Session::writeJson(out,report);return passed?0:2;
}
