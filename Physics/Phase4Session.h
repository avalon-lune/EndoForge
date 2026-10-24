#pragma once
// Phase 4 owns deterministic input scheduling and provenance. The underlying
// FEM/contact model remains available unchanged through the protocol-3 entry.
class Phase4Session {
public:
    Membrane tissue; std::filesystem::path directory,actionsPath,statesPath,metadataPath,lastActionsPath;
    uint64_t simulationId=1,stateId=0,actionId=0,stepIndex=0,nextNodeId=0;int identityRevision=-1;
    std::string mode="idle",error;json steps=json::array(),lastSteps=json::array();TissueConfig recordedConfig,lastConfig;
    bool pendingClear[2]{false,false};std::ofstream snapshots;std::vector<uint64_t> nodeIds;std::vector<int64_t> parents;std::vector<int> materialIds;
    struct Identity {uint64_t id;int material;std::set<int> faces;};std::map<std::string,Identity> identities;
    explicit Phase4Session(const TissueConfig& cfg={},const std::filesystem::path& dir={}):tissue(cfg),directory(dir),recordedConfig(cfg),lastConfig(cfg){
        if(cfg.phase6RegulatedGrip)phase6AuthoredReadyRecipes(tissue);
        if(!directory.empty()){std::filesystem::create_directories(directory);auto last=directory/"last-session.json";if(std::filesystem::exists(last)){try{std::ifstream in(last);json data;in>>data;loadRecording(data);actionsPath=data.value("actions_file","");lastActionsPath=actionsPath;}catch(const std::exception&e){error=std::string("Previous recording unavailable: ")+e.what();}}}updateIdentity();
    }
    ~Phase4Session(){try{if(mode=="recording")finishRecord();}catch(...){} }
    static void validate(const json& j){
        if(!j.is_object()||j.value("type","")!="command")throw std::invalid_argument("Command object required");
        for(auto key:{"reset_id","active_tool"})if(!j.contains(key)||!j[key].is_number_integer()||j[key].get<double>()<0||j[key].get<double>()>2147483647)throw std::invalid_argument("Invalid command integer");
        if(j["active_tool"].get<int>()>1||!j.contains("paused")||!j["paused"].is_boolean()||!j.contains("tools")||!j["tools"].is_array()||j["tools"].size()!=2)throw std::invalid_argument("Invalid tool command");
        for(auto&t:j["tools"]){if(!t.is_object()||!t.contains("tip_m")||!t["tip_m"].is_array()||t["tip_m"].size()!=3)throw std::invalid_argument("Invalid tip");for(auto&n:t["tip_m"])if(!n.is_number()||!std::isfinite(n.get<double>()))throw std::invalid_argument("Invalid coordinate");if(!std::isfinite(length(V(t["tip_m"][0].get<double>(),t["tip_m"][1].get<double>(),t["tip_m"][2].get<double>()))))throw std::invalid_argument("Tip magnitude overflow");for(auto key:{"roll_deg","closed"})if(!t.contains(key)||!t[key].is_number()||!std::isfinite(t[key].get<double>()))throw std::invalid_argument("Invalid tool scalar");}
        for(const auto&tool:j["tools"])for(auto key:{"hold_tip","hold_roll","bounded_target"})if(tool.contains(key)&&!tool[key].is_boolean())throw std::invalid_argument("Invalid motion flag");
        if(j.contains("clear_stroke_edges")&&(!j["clear_stroke_edges"].is_array()||j["clear_stroke_edges"].size()!=2||!j["clear_stroke_edges"][0].is_boolean()||!j["clear_stroke_edges"][1].is_boolean()))throw std::invalid_argument("Invalid recorded command effects");
        if(j.contains("seq")&&(!j["seq"].is_number_integer()||j["seq"].get<double>()<0))throw std::invalid_argument("Invalid sequence");
        if(j.contains("action_id")&&(!j["action_id"].is_number_integer()||j["action_id"].get<double>()<0||j["action_id"].get<double>()>9007199254740991.))throw std::invalid_argument("Invalid action ID");
        if(j.contains("specimen")&&(!j["specimen"].is_string()||(j["specimen"]!="flat"&&j["specimen"]!="curved"&&j["specimen"]!="gallbladder")))throw std::invalid_argument("Invalid specimen");
        if(j.contains("session_action")){if(!j["session_action"].is_string()||!j.contains("action_id"))throw std::invalid_argument("Session action requires ID");auto a=j["session_action"].get<std::string>();if(a!=""&&a!="record_start"&&a!="record_stop"&&a!="replay_last"&&a!="replay_stop")throw std::invalid_argument("Unknown session action");}
    }
    static json homeCommand(int rid=0){return {{"type","command"},{"reset_id",rid},{"paused",false},{"active_tool",0},{"tools",{{{"tip_m",{-.022,-.047,.006}},{"closed",0},{"roll_deg",90}},{{"tip_m",{.022,-.047,.006}},{"closed",0},{"roll_deg",90}}}}};}
    json effectiveCommand()const {json j=homeCommand(tissue.resetId);j["active_tool"]=tissue.activeTool;j["paused"]=tissue.paused;j["clear_stroke_edges"]={pendingClear[0],pendingClear[1]};for(int k=0;k<2;k++)j["tools"][k]={{"tip_m",jvec(tissue.tools[k].commanded)},{"roll_deg",tissue.tools[k].commandedRoll},{"closed",tissue.tools[k].closed}};return j;}
    void applyRecorded(const json& j){if(j.contains("clear_stroke_edges"))for(int k=0;k<2;k++)if(j["clear_stroke_edges"][k].get<bool>())tissue.tools[k].strokeEdges.clear();auto input=j;input["reset_id"]=tissue.resetId;
        // Recorded inputs are the effective command state after all UI events
        // within this simulation step, including a possible tool switch.
        if(tissue.config.anatomy){tissue.activeTool=j["active_tool"].get<int>();tissue.paused=j["paused"].get<bool>();for(int k=0;k<2;k++){const auto&v=j["tools"][k];tissue.tools[k].commanded=V(v["tip_m"][0].get<double>(),v["tip_m"][1].get<double>(),v["tip_m"][2].get<double>());tissue.tools[k].commandedRoll=v["roll_deg"].get<double>();tissue.tools[k].closed=v["closed"].get<double>();}}
        else tissue.command(input);}

    void resetTo(const TissueConfig& cfg,int rid){tissue.config=cfg;tissue.makeMesh();tissue.reset(rid);tissue.activeTool=0;tissue.adaptiveRetries=0;simulationId++;stepIndex=0;pendingClear[0]=pendingClear[1]=false;identityRevision=-1;identities.clear();nextNodeId=0;updateIdentity();}
    void reset(int rid){if(mode=="recording")finishRecord();mode="idle";actionId=0;resetTo(tissue.config,rid);}
    void updateIdentity(){
        if(identityRevision==tissue.revision)return;
        auto previous=identities;identities.clear();nodeIds.resize(tissue.rest.size());parents.assign(tissue.rest.size(),-1);materialIds.resize(tissue.rest.size());std::vector<std::set<int>> incident(tissue.layerNodes);
        for(int f=0;f<int(tissue.sourceFaces.size());f++)for(int n:tissue.triangles[f])incident[n].insert(f);
        for(int n=0;n<int(tissue.rest.size());n++){int top=n%tissue.layerNodes,layer=n/tissue.layerNodes,material=tissue.origins[n]+layer*int(tissue.original.size());std::string key=std::to_string(material)+":";for(int f:incident[top])key+=std::to_string(f)+",";auto old=previous.find(key);uint64_t id;
            if(old!=previous.end())id=old->second.id;else{id=nextNodeId++;for(auto&[oldkey,value]:previous)if(value.material==material){bool shares=false;for(int f:incident[top])if(value.faces.count(f)){shares=true;break;}if(shares){parents[n]=int64_t(value.id);break;}}}
            nodeIds[n]=id;materialIds[n]=material;identities.emplace(key,Identity{id,material,incident[top]});
        }identityRevision=tissue.revision;
    }
    void loadRecording(const json& j){
        if(j.value("schema","")!=(tissue.config.anatomy?"endoforge.actions.v2":"endoforge.actions.v1")||!j.contains("steps")||!j["steps"].is_array()||j["steps"].empty()||j["steps"].size()>180000||!j.contains("dt_s")||std::abs(j["dt_s"].get<double>()-Dt)>1e-12)throw std::invalid_argument("Invalid recording schema/length/timebase");
        TissueConfig config;if(tissue.config.anatomy){if(j.at("config")!=tissue.config.data())throw std::invalid_argument("Anatomy recording model/configuration fingerprint mismatch");config=tissue.config;}else config=TissueConfig::parse(j.at("config"));for(auto& step:j["steps"]){validate(step);if(step["paused"].get<bool>())throw std::invalid_argument("Recording contains paused simulation step");}lastSteps=j["steps"];lastConfig=config;
    }
    void beginRecord(int rid){
        if(mode=="recording")finishRecord();resetTo(tissue.config,rid);steps=json::array();recordedConfig=tissue.config;mode="recording";error.clear();
        if(!directory.empty()){auto stamp=std::to_string(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::system_clock::now().time_since_epoch()).count())+"-"+std::to_string(GetCurrentProcessId());auto stem=directory/("session-"+stamp);actionsPath=stem.string()+"-actions.json";statesPath=stem.string()+"-states.jsonl";metadataPath=stem.string()+"-metadata.json";snapshots.open(statesPath,std::ios::binary|std::ios::trunc);if(!snapshots)throw std::runtime_error("Cannot open session state file");snapshots<<snapshot().dump()<<'\n';}
    }
    void finishRecord(){
        if(!steps.empty()){lastSteps=steps;lastConfig=recordedConfig;lastActionsPath=actionsPath;}mode="idle";
        if(snapshots.is_open()){snapshots.flush();if(!snapshots)throw std::runtime_error("State recording write failed");snapshots.close();}
        if(!directory.empty()){json j={{"schema",recordedConfig.anatomy?"endoforge.actions.v2":"endoforge.actions.v1"},{"dt_s",Dt},{"config",recordedConfig.data()},{"steps",steps},{"actions_file",actionsPath.generic_string()}};writeJson(actionsPath,j);if(!steps.empty())writeJson(directory/"last-session.json",j);writeJson(metadataPath,{{"schema","endoforge.session.v1"},{"config",recordedConfig.data()},{"accepted_steps",steps.size()},{"duration_s",steps.size()*Dt},{"initial_state_included",true},{"actions_file",actionsPath.filename().generic_string()},{"states_file",statesPath.filename().generic_string()},{"material_validated",false},{"force_definition","sum of constraint impulse magnitudes divided by accepted substep duration"}});}
    }
    static void writeJson(const std::filesystem::path& p,const json& j){std::ofstream out(p,std::ios::binary|std::ios::trunc);out<<j.dump(2);out.flush();if(!out)throw std::runtime_error("Cannot write session file: "+p.string());}
    bool command(const json& j){
        validate(j);int rid=j["reset_id"].get<int>();uint64_t aid=j.value("action_id",uint64_t(0));auto action=j.value("session_action",std::string());bool fresh=!action.empty()&&aid>actionId;bool resetRequested=rid!=tissue.resetId;
        if(tissue.config.anatomy&&j.contains("specimen")&&j["specimen"]!="gallbladder")throw std::invalid_argument("Anatomy session cannot switch to a specimen");
        // A retransmitted or stale action must not replay its reset side effect.
        if(!action.empty()&&aid<=actionId)return true;
        TissueConfig desired=tissue.config;if(resetRequested&&j.contains("specimen")&&j["specimen"]!=tissue.config.name)desired=TissueConfig::preset(j["specimen"].get<std::string>());
        if(fresh&&(action=="record_start"||action=="replay_last")&&!resetRequested)throw std::invalid_argument("Record/replay start requires a new reset_id");
        if(fresh){
            if(action=="record_start"){tissue.config=desired;beginRecord(rid);actionId=aid;return true;}
            if(action=="replay_last"){if(mode=="recording")finishRecord();if(lastSteps.empty()){resetTo(desired,rid);mode="idle";error="No completed recording";actionId=aid;return true;}resetTo(lastConfig,rid);mode="replaying";error.clear();actionId=aid;return true;}
            if(action=="record_stop"){if(mode=="recording")finishRecord();actionId=aid;return true;}
            if(action=="replay_stop"){if(mode=="recording")finishRecord();mode="idle";tissue.stopInput("Replay stopped - tools released");tissue.paused=false;actionId=aid;return true;}
        }
        if(resetRequested){if(mode=="recording")finishRecord();mode="idle";resetTo(desired,rid);}
        if(mode=="replaying"||mode=="replay_complete")return true;
        bool accepted=tissue.command(j);if(accepted&&mode=="recording")for(int k=0;k<2;k++)pendingClear[k]|=tissue.tools[k].closed<.5||(k==1&&tissue.activeTool!=1);return accepted;
    }
    void stopInput(const std::string& reason){if(mode=="recording")finishRecord();mode="idle";tissue.stopInput(reason);}
    bool automated()const{return mode=="replaying"||mode=="replay_complete";}
    void step(){
        if(mode=="replay_complete"){stateId++;return;}
        if(mode=="replaying"){if(stepIndex>=lastSteps.size()){mode="replay_complete";return;}applyRecorded(lastSteps[size_t(stepIndex)]);}
        json input;if(mode=="recording")input=effectiveCommand();double before=tissue.time;int stops=tissue.safetyStops;tissue.step();stateId++;updateIdentity();
        if(tissue.time>before+Dt*.5){stepIndex++;pendingClear[0]=pendingClear[1]=false;if(mode=="recording"){input["paused"]=false;steps.push_back(input);if(snapshots.is_open()){snapshots<<snapshot().dump()<<'\n';if(!snapshots)throw std::runtime_error("Session state write failed");}}
            if(mode=="replaying"&&stepIndex>=lastSteps.size())mode="replay_complete";
            if(mode=="recording"&&steps.size()>=180000){finishRecord();error="Recording limit reached (180000 accepted steps / 100 simulated minutes)";}
        }
        if(tissue.safetyStops!=stops||!tissue.healthy){error="Simulation protection stop; reset required";if(mode=="recording")finishRecord();if(mode=="replaying")mode="idle";}
    }
    json session()const{return {{"mode",mode},{"action_id",actionId},{"step_index",stepIndex},{"replay_length",lastSteps.size()},{"recorded_steps",mode=="recording"?steps.size():lastSteps.size()},{"file",(mode=="recording"?actionsPath:lastActionsPath).filename().generic_string()},{"error",error}};}
    void extend(json& j){updateIdentity();j["protocol"]=tissue.config.anatomy?5:4;j["specimen"]=tissue.config.name;j["config"]=tissue.config.data();j["simulation_id"]=simulationId;j["state_id"]=stateId;j["node_ids"]=nodeIds;j["material_node_ids"]=materialIds;j["parent_node_ids"]=parents;j["session"]=session();j["total_mass_kg"]=std::accumulate(tissue.masses.begin(),tissue.masses.end(),0.);j["thickness_m"]=tissue.config.thickness;
        if(auto a=tissue.config.anatomy){j["model_id"]=a->source.at("model_id");j["model_version"]=a->source.at("version");j["asset_fingerprint"]=a->fingerprint;j["physics_model_version"]="phase5-tetra-wall-bound-bed-pairwise-v2";j["home_tips_m"]=a->source.at("home_tips_m");if(tissue.config.phase6RegulatedGrip)j["tool_pivots_m"]={jvec(a->pivots[0]),jvec(a->pivots[1])};j["grasp_targets_m"]=a->source.at("grasp_targets_m");j["outer_surface_face_count"]=tissue.sourceFaces.size();j["attachment_vertex_ids"]=tissue.bedNodes;j["attachment_segments_m"]=json::array();double load=0,maxExtension=0;const auto&x=tissue.dofs->x.getValue();for(size_t i=0;i<tissue.bedNodes.size();i++){int n=tissue.bedNodes[i];double extension=length(x[n]-a->anchors[i])-length(tissue.rest[n]-a->anchors[i]);load+=std::abs(extension*a->attachmentStiffness);maxExtension=std::max(maxExtension,std::abs(extension));j["attachment_segments_m"].push_back({jvec(x[n]),jvec(a->anchors[i])});}j["attachment_elastic_force_n"]=load;j["attachment_max_extension_m"]=maxExtension;j["tool_roles"]={"grasper","grasper"};j["cutting_enabled"]=false;if(tissue.anatomyIntersection){j["liver_alarm_distance_m"]=tissue.anatomyIntersection->liverAlarm();j["broadphase_alarm_distance_m"]=tissue.anatomyIntersection->getAlarmDistance();j["liver_proximity_tests"]=tissue.anatomyIntersection->liverTests;j["liver_envelope_observed_speed_m_s"]=tissue.anatomyIntersection->observedSpeed;}}}
    json lumenMetrics()const {double initial=0,current=0;const auto&x=tissue.dofs->x.getValue();for(size_t f=0;f<tissue.sourceFaces.size();f++){std::array<int,3> n{};for(int k=0;k<3;k++)n[k]=tissue.triangles[f][k]+tissue.layerNodes;initial+=dot3(tissue.rest[n[0]],cross3(tissue.rest[n[1]],tissue.rest[n[2]]))/6.;current+=dot3(x[n[0]],cross3(x[n[1]],x[n[2]]))/6.;}return {{"rest_m3",std::abs(initial)},{"current_m3",std::abs(current)},{"ratio",current/initial},{"fluid_pressure_model",false}};}
    json hello(){auto j=tissue.hello();extend(j);if(tissue.config.anatomy){j["solver"]="SOFA corotational tetrahedral hollow wall, frictional dual graspers, elastic liver-bed attachments";j["static_liver"]=tissue.config.anatomy->source.at("static_liver");j["attachment_anchor_bindings"]=tissue.config.anatomy->source.at("attachment_anchor_bindings");j["lumen_volume"]=lumenMetrics();if(tissue.config.phase6RegulatedGrip)j["phase6_ready_recipes"]=phase6AuthoredReadyRecipes(tissue);}return j;}
    json state(){auto j=tissue.state();extend(j);if(tissue.config.anatomy)j["lumen_volume"]=lumenMetrics();return j;}
    json snapshot(){auto j=state();if(tissue.config.anatomy&&stepIndex==0)j["anatomy_asset"]=tissue.config.anatomy->source;j["schema"]="endoforge.physics-state.v1";j["rest_vertices"]=json::array();j["velocities_m_s"]=json::array();for(auto&v:tissue.rest)j["rest_vertices"].push_back(jvec(v));for(auto&v:tissue.dofs->v.getValue())j["velocities_m_s"].push_back(jvec(v));j["tetrahedra"]=tissue.tets;j["fixed_indices"]=tissue.fixed;j["cut_material_edges"]=tissue.cuts;return j;}
};
