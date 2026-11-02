#pragma once
#include "TrainingGeometry.h"
class FJsonObject;

namespace Phase7AttachmentGeometry
{
// Equal subdivisions align both possible original quad diagonals. Bounding
// vertex offsets then bounds complete displayed triangles, not only samples.
constexpr int32 AlongSubdivisions=6, SpanSubdivisions=6;
constexpr double MaximumOffsetCm=.012;
struct FBinding
{
    TArray<int32> ClosedBoundaryMaterialIds;
    TArray<FVector> VertexBindings; // [-1,pair,endpoint] or [edge,u,v].
    TArray<int32> TrianglePatchIndices;
    TArray<int32> OriginalEdgeDirections;
    TArray<FIntPoint> SeamVertexPairs;
    double MeasuredMaximumOffsetCm=0;
};
// Presentation of the native attachment spring envelope, not an extra FEM.
// First 2*N vertices always preserve all native endpoint pairs exactly.
bool Build(const TArray<int32>& MaterialIds,const TArray<FVector>& NativePairsCm,
           const TArray<FIntPoint>& BoundaryEdges,FTrainingRenderMesh& OutMesh,
           FBinding& OutBinding,FString& Error);
TSharedRef<FJsonObject> ToJson(const FBinding& Binding,const TArray<FIntPoint>& OriginalEdges,int32 NativePairCount);
}
