#pragma once
#include "CoreMinimal.h"

namespace Phase7CommandBudget
{
    struct FPendingTarget { uint64 Sequence=0;FVector Tip=FVector::ZeroVector; };
    struct FResult { FVector Tip=FVector::ZeroVector;bool Hold=false;double OutstandingPathCm=0; };

    // Bound the whole still-executable polyline, rather than giving every
    // asynchronously queued target a fresh radius around stale feedback.
    struct FState
    {
        static constexpr double MaximumPathCm=.1;
        TArray<FPendingTarget> Pending;
        void Reset(){Pending.Reset();}
        FResult Queue(uint64 Sequence,uint64 Applied,const FVector& Actual,
                      const FVector& NativeTarget,const FVector& Desired,bool Hold)
        {
            Pending.RemoveAll([&](const FPendingTarget& P){return P.Sequence<=Applied;});
            FVector Tail=NativeTarget;double Used=FVector::Distance(Actual,Tail);
            for(const auto& P:Pending){Used+=FVector::Distance(Tail,P.Tip);Tail=P.Tip;}
            // An earlier unbounded preset can still be in flight when manual
            // control takes over. First stop at native receipt; do not invent
            // a delayed displayed-pose correction or discard the new intent.
            if(Hold||Used>MaximumPathCm+1e-8)
            {
                Pending.Add({Sequence,Tail});
                return {Actual,true,Used};
            }
            const FVector Next=Tail+(Desired-Tail).GetClampedToMaxSize(FMath::Max(0.,MaximumPathCm-Used));
            Used+=FVector::Distance(Tail,Next);Pending.Add({Sequence,Next});
            return {Next,false,Used};
        }
    };
}
