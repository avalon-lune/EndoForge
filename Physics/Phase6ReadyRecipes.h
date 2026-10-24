#pragma once

// Shared by native diagnostics and the public Phase6 metadata contract. Binding
// uses the actual outer rest wall, not the anatomy asset's middle surface.
json phase6ReadyRecipe(const Membrane&t,int tool,const V&restReadyTip,const V&queryReferenceTip,double roll,const json&waypoints=json::array()){
    const V query=queryReferenceTip+unit(t.tools[tool].pivot-queryReferenceTip)*(JawL*.5);
    double best=std::numeric_limits<double>::max();int face=-1;V point;
    for(int f=0;f<int(t.sourceFaces.size());f++){const auto&ids=t.triangles[f];const V q=closestTriangle(query,t.rest[ids[0]],t.rest[ids[1]],t.rest[ids[2]]);const double distance=length(q-query);if(distance<best){best=distance;face=f;point=q;}}
    if(face<0)throw std::runtime_error("Phase6 ready binding requires an outer wall");
    const auto&ids=t.triangles[face];const V b=t.rest[ids[1]]-t.rest[ids[0]],c=t.rest[ids[2]]-t.rest[ids[0]],d=point-t.rest[ids[0]];
    const double bb=dot3(b,b),bc=dot3(b,c),cc=dot3(c,c),den=bb*cc-bc*bc,u=(dot3(d,b)*cc-dot3(d,c)*bc)/den,v=(dot3(d,c)*bb-dot3(d,b)*bc)/den;
    const V weights(1-u-v,u,v);
    return {{"tool",tool},{"rest_ready_tip_m",jvec(restReadyTip)},{"roll_deg",roll},
        {"material_binding",{{"triangle_id",face},{"node_ids",ids},{"barycentric",jvec(weights)},{"rest_surface_point_m",jvec(point)},{"rest_query_m",jvec(query)},{"tip_offset_m",jvec(restReadyTip-point)}}},
        {"approach_waypoints",waypoints}};
}

V phase6SampleReadyTarget(const Membrane&t,const json&recipe){
    const auto&b=recipe.at("material_binding");const auto&x=t.dofs->x.getValue();V target(b.at("tip_offset_m")[0],b.at("tip_offset_m")[1],b.at("tip_offset_m")[2]);
    for(int j=0;j<3;j++)target+=x.at(b.at("node_ids")[j].get<int>())*b.at("barycentric")[j].get<double>();return target;
}

std::vector<V> phase6ResolveReadyWaypoints(const Membrane&t,const json&recipe,const V&frozenTarget){
    const int k=recipe.at("tool").get<int>();V cursor=t.tools[k].tip;std::vector<V>result;
    for(const auto&waypoint:recipe.at("approach_waypoints")){
        const auto kind=waypoint.at("kind").get<std::string>();
        if(kind=="current_xy_at_z")cursor[2]=waypoint.at("z_m").get<double>();
        else if(kind=="toward_pivot_from_frozen_ready")cursor=frozenTarget+unit(t.tools[k].pivot-frozenTarget)*waypoint.at("distance_m").get<double>();
        else throw std::runtime_error("Unknown Phase6 ready waypoint");
        result.push_back(cursor);
    }
    result.push_back(frozenTarget);return result;
}

json phase6AuthoredReadyRecipes(const Membrane&t){
    const auto& authored=t.config.anatomy->source.at("phase6_interaction");
    if(authored.at("schema")!="endoforge.phase6.ready_poses.v1"||authored.at("recipes").size()!=2)throw std::runtime_error("Missing authored Phase6 ready poses");
    json recipes=json::array();
    for(int k=0;k<2;k++){
        const auto&r=authored.at("recipes").at(k);if(r.at("tool")!=k)throw std::runtime_error("Invalid ready tool identity");
        const auto&p=r.at("rest_ready_tip_m");V tip(p.at(0).get<double>(),p.at(1).get<double>(),p.at(2).get<double>());
        const double roll=r.at("roll_deg").get<double>();
        if(!std::isfinite(length(tip))||!std::isfinite(roll)||std::abs(roll)>180||length(t.limitTip(k,tip)-tip)>1e-10)throw std::runtime_error("Invalid authored RCM ready pose");
        const auto& waypoints=r.at("approach_waypoints");if(!waypoints.is_array()||waypoints.size()>8)throw std::runtime_error("Invalid ready waypoint list");
        for(const auto&w:waypoints){const auto kind=w.at("kind").get<std::string>();
            if(kind=="current_xy_at_z"){double z=w.at("z_m").get<double>();if(!std::isfinite(z)||z<-.002||z>.08)throw std::runtime_error("Invalid clearance waypoint");}
            else if(kind=="toward_pivot_from_frozen_ready"){double d=w.at("distance_m").get<double>();if(!std::isfinite(d)||d<0||d>.08)throw std::runtime_error("Invalid axial waypoint");}
            else throw std::runtime_error("Unknown authored ready waypoint");
        }
        auto recipe=phase6ReadyRecipe(t,k,tip,tip,roll,waypoints);
        for(const auto&point:phase6ResolveReadyWaypoints(t,recipe,tip)){
            if(length(t.limitTip(k,point)-point)>1e-10)throw std::runtime_error("Authored ready path violates RCM limits");
            auto tool=t.tools[k];tool.tip=point;tool.roll=roll;tool.angle=40;
            if(t.liverMotionGuard){auto pose=Membrane::collisionPose(tool);auto result=t.liverMotionGuard->admit(pose,pose);if(!result.initial_valid||result.blocked)throw std::runtime_error("Authored ready waypoint violates liver clearance");}
        }
        recipes.push_back(recipe);
    }
    return {{"schema","endoforge.phase6.ready_recipes.v1"},{"recipes",recipes}};
}
