#include "TrainingScene.h"

void ATrainingScene::UpdatePhase9DisplaySurface(bool Rebuild)
{
    TrainingGeometry::UpdateBoundSurface(TissueVertices,TissueNormals,TissueRenderBindings,TissueRenderData,.012,true);
    if(Rebuild || Phase9NormalGroups.Num()!=TissueRenderBindings.Num())
    {
        // Weld normal accumulation by physical support, never by proximity.
        // UV seams share geometry while unrelated surfaces and cut sides keep
        // distinct node identities. The topology revision invalidates this map.
        TMap<FString,int32> Groups;Phase9NormalGroups.Reset();Phase9NormalGroupCount=0;
        for(const auto& S:TissueRenderBindings)
        {
            TArray<TPair<int32,int32>> Support;
            const int32 Nodes[3]={S.A,S.B,S.C};
            for(int32 K=0;K<3;++K)
            {
                const int32 W=FMath::RoundToInt(S.Weight[K]*8);
                if(W)Support.Emplace(Nodes[K],W);
            }
            Support.Sort([](const auto& A,const auto& B){return A.Key<B.Key;});
            FString Key;
            for(const auto& P:Support)Key+=FString::Printf(TEXT("%d:%d/"),P.Key,P.Value);
            int32* Found=Groups.Find(Key);
            if(Found)Phase9NormalGroups.Add(*Found);
            else {Groups.Add(Key,Phase9NormalGroupCount);Phase9NormalGroups.Add(Phase9NormalGroupCount++);}
        }
    }
    TArray<FVector> Sum;Sum.Init(FVector::ZeroVector,Phase9NormalGroupCount);
    const auto& P=TissueRenderData.Positions;const auto& F=TissueRenderData.Triangles;
    for(int32 I=0;I+2<F.Num();I+=3)
    {
        const int32 A=F[I],B=F[I+1],C=F[I+2];
        // Render winding is reversed for UE; retain outward physical normals.
        const FVector N=FVector::CrossProduct(P[C]-P[A],P[B]-P[A]);
        Sum[Phase9NormalGroups[A]]+=N;Sum[Phase9NormalGroups[B]]+=N;Sum[Phase9NormalGroups[C]]+=N;
    }
    for(int32 I=0;I<P.Num();++I)
        TissueRenderData.Normals[I]=Sum[Phase9NormalGroups[I]].GetSafeNormal(UE_SMALL_NUMBER,TissueRenderData.Normals[I]);
}
