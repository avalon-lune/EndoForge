#pragma once

#include "CoreMinimal.h"
#include "ProceduralMeshComponent.h"

/** UE-only render data. None of these meshes participates in Chaos or changes the SOFA model. */
struct FTrainingRenderMesh
{
    TArray<FVector> Positions;
    TArray<int32> Triangles;
    TArray<FVector> Normals;
    TArray<FVector2D> UV;
    TArray<FLinearColor> Colors;
    TArray<FProcMeshTangent> Tangents;
};

struct FTrainingSurfaceSample
{
    int32 A = 0, B = 0, C = 0;
    FVector Weight = FVector(1, 0, 0);
};

namespace TrainingGeometry
{
    // Local +X follows the jaw from hinge to distal tip, +Y spans its width, +Z its thickness.
    // The 14.5 x 2.5 x 1.4 mm envelope matches the SOFA collision box. All bevels, grooves and
    // serrations lie inside it, at most 0.1 mm from that envelope; no false through-holes.
    FTrainingRenderMesh MakeSerratedJaw(int32 JawSign);
    FTrainingRenderMesh MakeBeveledBox(const FVector& HalfExtent, float BevelCm);
    void BuildSurfaceBindings(const TArray<FVector>& RestPositions, const TArray<int32>& Faces,
        int32 Subdivisions, TArray<FTrainingSurfaceSample>& OutSamples, FTrainingRenderMesh& OutMesh);
    void UpdateBoundSurface(const TArray<FVector>& Positions, const TArray<FVector>& Normals,
        const TArray<FTrainingSurfaceSample>& Samples, FTrainingRenderMesh& Mesh,
        double MaxSurfaceOffsetCm = 0.01);
}
