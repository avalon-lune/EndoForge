#pragma once
#include "Phase6FEM.h"
#include <map>

// Exact reuse of each element's local J*K*J^T, not a frozen global tangent.
// Current corotational R is applied every call. Both local inputs are compared
// exactly, so any rest/material/topology update invalidates the cached product.
// No time step, contact, material law or solver tolerance is changed.
class Phase9FEM : public Phase6FEM {
public:
    SOFA_CLASS(Phase9FEM,Phase6FEM);
    struct Entry {StrainDisplacement strain;MaterialStiffness material;StiffnessMatrix local;bool valid=false;};
    std::vector<Entry> localCache;
    using NodePair=std::pair<unsigned,unsigned>;
    std::vector<std::array<unsigned,4>> patternElements;
    std::vector<std::array<size_t,16>> elementSlots;
    std::vector<NodePair> blockNodes;
    std::vector<Mat3> assembledBlocks;
    void invalidate(){localCache.clear();patternElements.clear();elementSlots.clear();blockNodes.clear();assembledBlocks.clear();}
    void init()override{Phase6FEM::init();invalidate();}
    void reinit()override{Phase6FEM::reinit();invalidate();}
    void handleTopologyChange()override{Phase6FEM::handleTopologyChange();invalidate();}
    StiffnessMatrix elementMatrix(size_t id)override{
        if(localCache.size()!=_indexedElements->size())localCache.resize(_indexedElements->size());
        auto& cache=localCache[id];const auto& strain=strainDisplacements[id];const auto& material=materialsStiffnesses[id];
        bool equal=cache.valid;
        if(equal)for(int r=0;r<12&&equal;r++)for(int c=0;c<6;c++)if(cache.strain(r,c)!=strain(r,c)){equal=false;break;}
        if(equal)for(int r=0;r<6&&equal;r++)for(int c=0;c<6;c++)if(cache.material(r,c)!=material(r,c)){equal=false;break;}
        if(!equal){
            sofa::type::MatNoInit<6,12,double> transpose;transpose.transpose(strain);
            cache.local=strain*material*transpose;cache.strain=strain;cache.material=material;cache.valid=true;
        }
        if(method==SMALL)return cache.local;
        const auto& rotation=rotations[id];Mat3 rt;rt.transpose(rotation);StiffnessMatrix result;
        for(int a=0;a<4;a++)for(int b=0;b<4;b++){
            Mat3 block;cache.local.getsub(a*3,b*3,block);const Mat3 rotated=(rotation*block)*rt;
            for(int r=0;r<3;r++)for(int c=0;c<3;c++)result(a*3+r,b*3+c)=rotated(r,c);
        }
        return result;
    }
    void preparePattern(){
        const auto& elements=*_indexedElements;
        bool equal=patternElements.size()==elements.size();
        if(equal)for(size_t i=0;i<elements.size()&&equal;i++)for(int k=0;k<4;k++)if(patternElements[i][k]!=elements[i][k]){equal=false;break;}
        if(equal)return;
        patternElements.resize(elements.size());elementSlots.resize(elements.size());blockNodes.clear();
        std::map<NodePair,size_t> slots;
        for(size_t i=0;i<elements.size();i++){
            for(int k=0;k<4;k++)patternElements[i][k]=elements[i][k];
            for(int a=0;a<4;a++)for(int b=0;b<4;b++){
                const NodePair key{elements[i][a],elements[i][b]};
                const auto [it,inserted]=slots.emplace(key,slots.size());
                if(inserted)blockNodes.push_back(key);
                elementSlots[i][a*4+b]=it->second;
            }
        }
        assembledBlocks.resize(blockNodes.size());
    }
    void assembleBlocks(){
        preparePattern();for(auto& block:assembledBlocks)block.clear();
        // Accumulate each node-pair block in the original element order. All
        // couplings remain; only repeated sparse-container insertions vanish.
        for(size_t id=0;id<_indexedElements->size();id++){
            const auto stiffness=elementMatrix(id);
            for(int a=0;a<4;a++)for(int b=0;b<4;b++){
                Mat3 block;stiffness.getsub(a*3,b*3,block);
                assembledBlocks[elementSlots[id][a*4+b]]-=block;
            }
        }
    }
    void buildStiffnessMatrix(sofa::core::behavior::StiffnessMatrix* matrix)override{
        assembleBlocks();
        auto derivative=matrix->getForceDerivativeIn(this->mstate).withRespectToPositionsIn(this->mstate);
        for(size_t i=0;i<blockNodes.size();i++)derivative(blockNodes[i].first*3,blockNodes[i].second*3)+=assembledBlocks[i];
    }
    std::pair<double,double> compareWithSofaReference()override{
        auto result=Phase6FEM::compareWithSofaReference();assembleBlocks();
        // Independent direct global accumulation of SOFA's reference matrices
        // also checks the new sparse assembly pattern, signs and summation.
        std::map<NodePair,Mat3> reference;
        for(size_t id=0;id<_indexedElements->size();id++){
            Transformation rotation;if(method==SMALL)rotation.identity();else rotation=rotations[id];
            StiffnessMatrix first,expected;computeStiffnessMatrix(first,expected,materialsStiffnesses[id],strainDisplacements[id],rotation);
            const auto& element=(*_indexedElements)[id];
            for(int a=0;a<4;a++)for(int b=0;b<4;b++){
                const NodePair key{element[a],element[b]};
                auto [it,inserted]=reference.try_emplace(key);if(inserted)it->second.clear();
                for(int r=0;r<3;r++)for(int c=0;c<3;c++)it->second(r,c)-=expected(a*3+r,b*3+c);
            }
        }
        if(reference.size()!=blockNodes.size())throw std::runtime_error("Phase9 sparse assembly pattern differs from SOFA reference");
        double error=0,scale=0;
        for(size_t i=0;i<blockNodes.size();i++){
            const auto& expected=reference.at(blockNodes[i]);
            for(int r=0;r<3;r++)for(int c=0;c<3;c++){
                error=std::max(error,std::abs(expected(r,c)-assembledBlocks[i](r,c)));
                scale=std::max(scale,std::abs(expected(r,c)));
            }
        }
        result.first=std::max(result.first,error);result.second=std::max(result.second,error/std::max(1.,scale));return result;
    }
};
