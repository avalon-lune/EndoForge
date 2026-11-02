#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <exception>
#include <map>
#include <set>
#include <string>
#include <vector>

// Include after Phase4Session.h. This read-only audit accepts a live state from
// session.state(), not a snapshot (legacy snapshots already contain velocity).
// Run it at actual rest, contact, traction and rejected-step states. It neither
// creates contact nor changes the tag, mechanical state, or solver impulses.
inline json phase9AuditPhysicsOutput(const Phase4Session&session,const json&state){
    const auto&t=session.tissue;
    // Different summation orders and the two contact mappings can accumulate
    // double-precision roundoff. The absolute N term handles cancellation;
    // the relative term scales with load. Both are far below the 0.03 N grip
    // threshold. Velocity is copied directly, so its tolerance is much tighter.
    constexpr double forceAbs=1e-9,forceRel=1e-8,velocityAbs=1e-12,velocityRel=1e-10,durationAbs=1e-12;
    json errors=json::array(),metrics={{"tools",json::array()},{"contact_reaction_reference_exercised",false}};
    const bool enabled=t.config.phase9Outputs();
    const std::vector<std::string>newToolFields={"contact_force_sample_valid","contact_force_sample_duration_s","jaw_contact_resultants_on_tool_n","contact_resultant_on_tool_n","contact_resultant_magnitude_n","contact_force_sum_magnitudes_n"};
    auto fail=[&](const std::string&message){errors.push_back(message);};
    auto readVector=[&](const json&value,const std::string&label,V&out){
        if(!value.is_array()||value.size()!=3){fail(label+": expected XYZ array");return false;}
        for(int k=0;k<3;k++)if(!value[k].is_number()||!std::isfinite(value[k].get<double>())){fail(label+": expected finite XYZ components");return false;}
        out=V(value[0].get<double>(),value[1].get<double>(),value[2].get<double>());return true;
    };
    auto forceComparison=[&](const V&observed,const V&reference,const std::string&label,json&comparisons){
        const double error=length(observed-reference),limit=forceAbs+forceRel*std::max(length(observed),length(reference));
        comparisons.push_back({{"field",label},{"absolute_error_n",error},{"allowed_error_n",limit}});
        if(!std::isfinite(error)||error>limit)fail(label+": force-vector tolerance exceeded");
    };
    try{
        if(state.value("type","")!="state")fail("audit requires a live state object from Phase4Session::state()");
        const auto&tools=state.at("tools");
        if(!tools.is_array()||tools.size()!=2)fail("tools: expected exactly two entries");
        if(!enabled){
            for(const auto&field:{"output_schema","physics_output_definition","velocities_m_s"})if(state.contains(field))fail(std::string("untagged live state unexpectedly contains ")+field);
            for(const auto&field:newToolFields){if(state.contains(field))fail("untagged root unexpectedly contains "+field);for(size_t k=0;k<tools.size();k++)if(tools[k].contains(field))fail("untagged tool "+std::to_string(k)+" unexpectedly contains "+field);}
            metrics["contact_reference_status"]="phase9_tag_absent; no new force reference requested";
        }else{
            if(state.value("output_schema","")!=AnatomyAsset::Phase9OutputSchema)fail("output_schema: missing or unsupported Phase9 version");
            const auto&velocities=state.at("velocities_m_s");const auto&vertices=state.at("vertices");const auto&ids=state.at("node_ids");const auto&nativeVelocity=t.dofs->v.getValue();
            const size_t count=nativeVelocity.size();
            metrics["node_count"]=count;metrics["velocity_count"]=velocities.size();metrics["vertex_count"]=vertices.size();metrics["node_id_count"]=ids.size();
            if(!velocities.is_array()||!vertices.is_array()||!ids.is_array()||velocities.size()!=count||vertices.size()!=count||ids.size()!=count||session.nodeIds.size()!=count)fail("velocity/vertex/node_ids lengths differ from native tissue DOFs");
            if(ids!=json(session.nodeIds))fail("node_ids differ from current session node ordering");
            if(state.at("material_node_ids").size()!=count||state.at("parent_node_ids").size()!=count)fail("material/parent node ID lengths differ from velocity array");
            const std::set<uint64_t>uniqueIds(session.nodeIds.begin(),session.nodeIds.end());if(uniqueIds.size()!=count)fail("node_ids are not unique");
            double maximumVelocityError=0;
            if(velocities.is_array()&&velocities.size()==count)for(size_t n=0;n<count;n++){
                V observed;if(!readVector(velocities[n],"velocities_m_s["+std::to_string(n)+"]",observed))continue;
                const double error=length(observed-nativeVelocity[n]),limit=velocityAbs+velocityRel*std::max(length(observed),length(nativeVelocity[n]));maximumVelocityError=std::max(maximumVelocityError,error);
                if(!std::isfinite(error)||error>limit)fail("velocities_m_s["+std::to_string(n)+"] differs from native accepted/restored velocity");
            }
            metrics["maximum_velocity_error_m_s"]=maximumVelocityError;
            const bool expectedSample=t.time>0&&t.lastStepAccepted;
            metrics["expected_contact_sample_valid"]=expectedSample;
            // Use the unprojected collision-surface J, independently mapped on
            // the tissue side. SOFA removes fixed-neck columns from parent J;
            // their contact reaction still acts on a jaw. Verify that parent J
            // plus those fixed columns reconstructs every selected surface row.
            metrics["contact_reference_definition"]="Opposite unprojected collision-surface J^T impulse / accepted h; projected parent J plus fixed-node contributions independently checked";
            const auto&lambda=t.solver->d_constraintForces.getValue();std::map<size_t,V>tissueRowDirections;
            if(expectedSample){const auto&matrix=t.dofs->c.getValue();for(auto row=matrix.begin();row!=matrix.end();++row){V sum(0,0,0);for(auto col=row.begin();col!=row.end();++col)sum+=col.val();tissueRowDirections.emplace(size_t(row.index()),sum);}}
            std::map<size_t,V>surfaceRowDirections,surfaceFixedDirections;
            const std::set<int>fixedNodes(t.fixed.begin(),t.fixed.end());
            if(expectedSample){
                const auto* body=t.root->getChild("membrane");const auto* surface=body?body->getChild("surface"):nullptr;
                const auto* surfaceDofs=surface?dynamic_cast<const MO*>(surface->getMechanicalState()):nullptr;
                if(!surfaceDofs)fail("Missing independent collision-surface mechanical state");
                else for(auto row=surfaceDofs->c.getValue().begin();row!=surfaceDofs->c.getValue().end();++row){
                    V sum(0,0,0),fixed(0,0,0);for(auto col=row.begin();col!=row.end();++col){sum+=col.val();if(fixedNodes.count(int(col.index())))fixed+=col.val();}
                    surfaceRowDirections.emplace(size_t(row.index()),sum);surfaceFixedDirections.emplace(size_t(row.index()),fixed);
                }
            }
            std::set<size_t>allJawRows;
            for(size_t k=0;k<std::min(size_t(2),tools.size());k++){
                const auto&tool=tools[k];const auto&nativeTool=t.tools[k];const std::string label="tools["+std::to_string(k)+"]";json toolMetrics={{"tool",k},{"force_comparisons",json::array()},{"contact_reaction_reference_exercised",false}};
                for(const auto&field:newToolFields)if(!tool.contains(field))fail(label+": missing "+field);
                const bool sampleValid=tool.at("contact_force_sample_valid").get<bool>();
                if(sampleValid!=expectedSample||sampleValid!=nativeTool.contactForceSampleValid)fail(label+": contact sample validity disagrees with accepted-state lifecycle");
                for(const auto&field:{"force_n","contact_force_n","contact_force_sum_magnitudes_n"}){
                    const auto&value=tool.at(field);if(!value.is_number()||!std::isfinite(value.get<double>())||value.get<double>()!=nativeTool.force)fail(label+"."+field+": legacy scalar/alias changed");
                }
                if(!sampleValid){
                    if(!tool.at("contact_force_sample_duration_s").is_null()||!tool.at("contact_resultant_on_tool_n").is_null()||!tool.at("contact_resultant_magnitude_n").is_null()||tool.at("jaw_contact_resultants_on_tool_n")!=json{nullptr,nullptr})fail(label+": invalid sample must have null duration and resultants");
                    toolMetrics["contact_reference_status"]="unavailable_before_first_acceptance_or_after_rejection";
                }else{
                    const double h=tool.at("contact_force_sample_duration_s").get<double>(),expectedH=Dt/std::max(1,t.lastSubsteps);
                    if(!std::isfinite(h)||h<=0||std::abs(h-expectedH)>durationAbs||std::abs(h-nativeTool.contactForceSampleDuration)>durationAbs)fail(label+": sample duration does not equal final accepted substep");
                    toolMetrics["sample_duration_s"]=h;toolMetrics["expected_sample_duration_s"]=expectedH;
                    const auto&jawVectors=tool.at("jaw_contact_resultants_on_tool_n");if(!jawVectors.is_array()||jawVectors.size()!=2)fail(label+": expected two jaw vectors");
                    V net(0,0,0),summedJawVectors(0,0,0),oppositeTissueReference(0,0,0);bool vectorsValid=readVector(tool.at("contact_resultant_on_tool_n"),label+".contact_resultant_on_tool_n",net);size_t rowCount=0,nonzeroRowCount=0,missingTissueRows=0;
                    toolMetrics["jaws"]=json::array();
                    for(int j=0;j<2;j++){
                        V observed(0,0,0),reference(0,0,0),projectedReference(0,0,0),surfaceFixedReaction(0,0,0);double maximumProjectionError=0;const std::string jawLabel=label+".jaw_contact_resultants_on_tool_n["+std::to_string(j)+"]";
                        const bool jawValid=j<jawVectors.size()&&readVector(jawVectors[j],jawLabel,observed);vectorsValid&=jawValid;if(jawValid)summedJawVectors+=observed;
                        size_t jawRows=0,jawNonzeroRows=0;const auto&matrix=nativeTool.dofs[j]->c.getValue();
                        for(auto row=matrix.begin();row!=matrix.end();++row){const size_t index=size_t(row.index());++jawRows;++rowCount;if(!allJawRows.insert(index).second)fail(jawLabel+": constraint row is shared by multiple jaws");
                            if(index>=lambda.size()){fail(jawLabel+": jaw constraint row exceeds solver impulse vector");continue;}
                            if(lambda[index]!=0){++jawNonzeroRows;++nonzeroRowCount;}
                            const auto surface=surfaceRowDirections.find(index);
                            if(surface==surfaceRowDirections.end()){++missingTissueRows;fail(jawLabel+": selected jaw row is missing from unprojected tissue-surface Jacobian");continue;}
                            const double factor=double(lambda[index])/h;
                            const auto tissue=tissueRowDirections.find(index);const V parent=tissue==tissueRowDirections.end()?V(0,0,0):tissue->second;
                            const V fixed=surfaceFixedDirections.at(index),full=-surface->second*factor,reconstructed=-(parent+fixed)*factor;
                            const double projectionError=length(full-reconstructed),projectionLimit=forceAbs+forceRel*std::max(length(full),length(reconstructed));
                            maximumProjectionError=std::max(maximumProjectionError,projectionError);
                            if(!std::isfinite(projectionError)||projectionError>projectionLimit)fail(jawLabel+": projected parent plus fixed-node columns differs at row "+std::to_string(index));
                            reference+=full;projectedReference-=parent*factor;surfaceFixedReaction-=fixed*factor;
                        }
                        oppositeTissueReference+=reference;
                        if(jawValid){forceComparison(observed,reference,jawLabel+" vs opposite tissue-J reaction",toolMetrics["force_comparisons"]);forceComparison(observed,nativeTool.jawContactResultantsOnTool[j],jawLabel+" vs native cached sample",toolMetrics["force_comparisons"]);}
                        toolMetrics["jaws"].push_back({{"jaw",j},{"selected_constraint_rows",jawRows},{"nonzero_impulse_rows",jawNonzeroRows},{"opposite_tissue_reference_n",jvec(reference)},{"projected_parent_reference_n",jvec(projectedReference)},{"fixed_node_contribution_to_tool_reaction_n",jvec(surfaceFixedReaction)},{"maximum_row_projection_reconstruction_error_n",maximumProjectionError},{"surface_reference_error_n",length(observed-reference)}});
                    }
                    if(vectorsValid){
                        forceComparison(net,summedJawVectors,label+" total vs two jaws",toolMetrics["force_comparisons"]);forceComparison(net,oppositeTissueReference,label+" total vs opposite tissue-J reaction",toolMetrics["force_comparisons"]);forceComparison(net,nativeTool.contactResultantOnTool,label+" total vs native cached sample",toolMetrics["force_comparisons"]);
                        const double magnitude=tool.at("contact_resultant_magnitude_n").get<double>(),limit=forceAbs+forceRel*length(net);
                        if(!std::isfinite(magnitude)||std::abs(magnitude-length(net))>limit)fail(label+": reported resultant magnitude disagrees with vector");
                        if(length(net)>nativeTool.force+forceAbs+forceRel*std::max(nativeTool.force,length(net)))fail(label+": net force exceeds legacy sum of contact magnitudes");
                    }
                    toolMetrics["selected_constraint_rows"]=rowCount;toolMetrics["nonzero_impulse_rows"]=nonzeroRowCount;toolMetrics["missing_tissue_reference_rows"]=missingTissueRows;
                    toolMetrics["contact_reference_status"]=rowCount==0?"no_contact_constraint_rows":nonzeroRowCount==0?"contact_rows_with_zero_impulse":"contact_rows_with_nonzero_impulse";
                    if(nonzeroRowCount>0&&missingTissueRows==0){toolMetrics["contact_reaction_reference_exercised"]=true;metrics["contact_reaction_reference_exercised"]=true;}
                }
                metrics["tools"].push_back(toolMetrics);
            }
            if(tools.size()==2)for(const auto&field:newToolFields)if(!state.contains(field)||state.at(field)!=tools[0].at(field))fail("root tool-0 compatibility copy differs for "+field);
        }
    }catch(const std::exception&e){fail(std::string("audit input/access error: ")+e.what());}
    return {{"schema","endoforge.phase9-output-audit.v1"},{"passed",errors.empty()},{"phase9_outputs_enabled",enabled},{"frame",t.frame},{"time_s",t.time},{"tolerances",{{"force_absolute_n",forceAbs},{"force_relative",forceRel},{"velocity_absolute_m_s",velocityAbs},{"velocity_relative",velocityRel},{"duration_absolute_s",durationAbs}}},{"metrics",metrics},{"errors",errors}};
}
