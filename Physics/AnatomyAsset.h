#pragma once

// Immutable authored geometry. The fingerprint is for reproducibility, not a
// cryptographic authenticity claim; delivery also hashes the source with SHA256.
struct AnatomyAsset {
    json source;
    std::string fingerprint;
    std::vector<V> vertices,normals,anchors,liverVertices;
    std::vector<std::array<int,3>> faces,liverFaces;
    std::set<int> fixedIds;
    std::vector<int> attachmentIds;
    std::array<V,2> home,targets;
    std::array<V,2> pivots{V(-.12,-.14,.15),V(.12,-.14,.15)};
    double thickness=.0011,attachmentStiffness=2.0,attachmentDamping=.02;
    static std::shared_ptr<AnatomyAsset> load(const std::filesystem::path& path) {
        std::ifstream input(path,std::ios::binary);
        if(!input)throw std::runtime_error("Cannot open anatomy asset: "+path.string());
        std::string bytes((std::istreambuf_iterator<char>(input)),{});
        auto a=std::make_shared<AnatomyAsset>();a->source=json::parse(bytes);
        uint64_t hash=14695981039346656037ULL;for(unsigned char c:bytes){hash^=c;hash*=1099511628211ULL;}
        std::ostringstream identity;identity<<"fnv1a64:"<<std::hex<<std::setw(16)<<std::setfill('0')<<hash;a->fingerprint=identity.str();
        const auto&j=a->source;
        if(j.value("schema","")!="endoforge.anatomy-mesh.v1")throw std::runtime_error("Unsupported anatomy asset schema");
        if(j.value("units","")!="m"||!j.contains("model_id")||!j["model_id"].is_string()||j["model_id"].get<std::string>().empty()||!j.contains("version")||!j["version"].is_number_integer()||j["version"].get<int>()<1)throw std::runtime_error("Anatomy SI units/model identity invalid");
        auto points=[](const json& values){std::vector<V> out;for(const auto&v:values){if(!v.is_array()||v.size()!=3)throw std::runtime_error("Invalid anatomy position");V p(v[0].get<double>(),v[1].get<double>(),v[2].get<double>());if(!std::isfinite(length(p))||length(p)>2)throw std::runtime_error("Invalid anatomy SI coordinate");out.push_back(p);}return out;};
        a->vertices=points(j.at("vertices_m"));a->normals=points(j.at("normals"));
        a->faces=j.at("triangles").get<std::vector<std::array<int,3>>>();
        if(a->vertices.size()<20||a->vertices.size()>10000||a->normals.size()!=a->vertices.size())throw std::runtime_error("Anatomy mesh size invalid");
        std::map<std::array<int,2>,int> edges;
        for(const auto&f:a->faces){for(int n:f)if(n<0||n>=int(a->vertices.size()))throw std::runtime_error("Anatomy face index invalid");
            if(length(cross3(a->vertices[f[1]]-a->vertices[f[0]],a->vertices[f[2]]-a->vertices[f[0]]))<1e-12)throw std::runtime_error("Degenerate anatomy triangle");
            for(int k=0;k<3;k++){int n=f[k],m=f[(k+1)%3];edges[{std::min(n,m),std::max(n,m)}]++;}}
        for(auto&[edge,count]:edges)if(count!=2)throw std::runtime_error("Gallbladder middle surface must be closed");
        for(auto&n:a->normals){if(length(n)<.9)throw std::runtime_error("Invalid anatomy surface normal");n=unit(n);}
        a->thickness=j.at("thickness_m").get<double>();if(!std::isfinite(a->thickness)||a->thickness<.0003||a->thickness>.005)throw std::runtime_error("Invalid anatomy wall thickness");
        a->fixedIds=j.at("fixed_vertex_ids").get<std::set<int>>();a->attachmentIds=j.at("attachment_vertex_ids").get<std::vector<int>>();
        a->anchors=points(j.at("attachment_anchor_positions_m"));
        if(a->attachmentIds.empty()||a->anchors.size()!=a->attachmentIds.size()||a->fixedIds.empty())throw std::runtime_error("Anatomy attachments missing");
        for(int n:a->fixedIds)if(n<0||n>=int(a->vertices.size()))throw std::runtime_error("Invalid fixed material vertex");
        for(int n:a->attachmentIds)if(n<0||n>=int(a->vertices.size()))throw std::runtime_error("Invalid attachment material vertex");
        auto h=points(j.at("home_tips_m")),g=points(j.at("grasp_targets_m"));if(h.size()!=2||g.size()!=2)throw std::runtime_error("Two anatomy poses required");
        for(int k=0;k<2;k++){a->home[k]=h[k];a->targets[k]=g[k];}
        if(j.contains("tool_pivots_m")){
            if(!j["tool_pivots_m"].is_array()||j["tool_pivots_m"].size()!=2)throw std::runtime_error("Exactly two explicit SI tool pivots are required");
            const auto pivots=points(j["tool_pivots_m"]);for(int k=0;k<2;k++){a->pivots[k]=pivots[k];const double insertion=length(a->home[k]-a->pivots[k]);if(insertion<.12||insertion>.30)throw std::runtime_error("Authored home violates RCM insertion range");}
        }
        a->liverVertices=points(j.at("static_liver").at("vertices_m"));a->liverFaces=j.at("static_liver").at("triangles").get<std::vector<std::array<int,3>>>();
        for(const auto&f:a->liverFaces)for(int n:f)if(n<0||n>=int(a->liverVertices.size()))throw std::runtime_error("Invalid liver index");
        const auto& bindings=j.at("attachment_anchor_bindings");
        if(!bindings.is_array()||bindings.size()!=a->anchors.size())throw std::runtime_error("Every attachment anchor requires a liver surface binding");
        for(size_t i=0;i<a->anchors.size();i++){
            const auto& binding=bindings[i];
            if(!binding.is_object()||!binding.contains("triangle_id")||!binding["triangle_id"].is_number_integer())throw std::runtime_error("Invalid liver anchor triangle binding");
            int face=binding["triangle_id"].get<int>();if(face<0||face>=int(a->liverFaces.size()))throw std::runtime_error("Liver anchor triangle out of range");
            const auto&w=binding.at("barycentric");if(!w.is_array()||w.size()!=3)throw std::runtime_error("Invalid liver anchor barycentric binding");
            V bound(0,0,0);double sum=0;for(int k=0;k<3;k++){if(!w[k].is_number())throw std::runtime_error("Invalid liver anchor weight");double weight=w[k].get<double>();if(!std::isfinite(weight)||weight< -1e-9||weight>1+1e-9)throw std::runtime_error("Invalid liver anchor weight");bound+=a->liverVertices[a->liverFaces[face][k]]*weight;sum+=weight;}
            if(std::abs(sum-1)>1e-9||length(bound-a->anchors[i])>1e-8)throw std::runtime_error("Liver attachment anchor floats away from its bound triangle");
        }
        return a;
    }
};
