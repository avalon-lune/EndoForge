#pragma once
#include <sofa/component/collision/detection/intersection/LocalMinDistance.h>

// Preserve SOFA's feature validity and constraint response. Only the proximity
// search envelope for the fixed liver is narrowed at rest and enlarged by the
// observed tissue velocity each accepted/adaptive substep. Jaw pairs retain the
// established 1.5 mm alarm and 0.45 mm contact offset.
class Phase5Intersection : public sofa::component::collision::detection::intersection::LocalMinDistance {
public:
    using LMD=sofa::component::collision::detection::intersection::LocalMinDistance;
    using Element=sofa::core::collision::ElementIntersector;
    using Context=sofa::core::collision::Intersection;
    using Model=sofa::core::CollisionModel;
    using Iterator=sofa::core::CollisionElementIterator;
    using Output=sofa::core::collision::DetectionOutputVector;
    SOFA_CLASS(Phase5Intersection,LMD);
    struct Adapter final:Element {
        Element* inner;const Context* context;uint64_t* counter;
        Adapter(Element*p,const Context*c,uint64_t*n):inner(p),context(c),counter(n){}
        bool canIntersect(Iterator a,Iterator b,const Context*)override{if(counter)++*counter;return inner->canIntersect(a,b,context);}
        int beginIntersect(Model*a,Model*b,Output*&out)override{return inner->beginIntersect(a,b,out);}
        int intersect(Iterator a,Iterator b,Output*out,const Context*)override{if(counter)++*counter;return inner->intersect(a,b,out,context);}
        int endIntersect(Model*a,Model*b,Output*out)override{return inner->endIntersect(a,b,out);}
        std::string name()const override{return "Phase5 pair envelope: "+inner->name();}
    };
    LMD::SPtr liverContext,jawContext;
    std::map<std::pair<Element*,bool>,std::unique_ptr<Adapter>> adapters;
    uint64_t liverTests=0;double observedSpeed=0;
    Phase5Intersection(){
        liverContext=sofa::core::objectmodel::New<LMD>();
        jawContext=sofa::core::objectmodel::New<LMD>();jawContext->d_alarmDistance.setValue(.0015);jawContext->d_contactDistance.setValue(.00045);
        d_alarmDistance.setValue(.0015);d_contactDistance.setValue(.00045);d_angleCone.setValue(0);d_useLMDFilters.setValue(false);
        liverContext->d_alarmDistance.setValue(.0008);liverContext->d_contactDistance.setValue(.00045);
    }
    static bool liver(Model*m){return m&&m->getLast()->getContext()&&m->getLast()->getContext()->getName()=="liver";}
    Element* findIntersector(Model*a,Model*b,bool&swap)override{
        auto*base=LMD::findIntersector(a,b,swap);if(!base)return nullptr;
        bool hepatic=liver(a)||liver(b);auto&adapter=adapters[{base,hepatic}];
        if(!adapter)adapter=std::make_unique<Adapter>(base,hepatic?liverContext.get():jawContext.get(),hepatic?&liverTests:nullptr);return adapter.get();
    }
    // Broad phase must cover the union of the pair-specific envelopes, even
    // when a fast tissue response requires more than the nominal jaw alarm.
    SReal getAlarmDistance()const override{return std::max(.0015,liverContext?liverContext->getAlarmDistance():.0015);}
    void setLiverEnvelope(double speed,double dt){observedSpeed=speed;liverContext->d_alarmDistance.setValue(std::max(.0008,.00045+speed*dt+.00015));}
    double liverAlarm()const{return liverContext->getAlarmDistance();}
};
