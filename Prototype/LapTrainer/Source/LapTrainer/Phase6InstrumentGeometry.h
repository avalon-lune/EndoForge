#pragma once

#include "TrainingGeometry.h"

/** Phase 6 display geometry only. Authoritative native jaw boxes are unchanged. */
namespace Phase6InstrumentGeometry
{
    // Same local axis and 14.5 x 2.5 x 1.4 mm envelope as the native jaw.
    // Smooth 0.18 mm edge radii, actual recessed teeth and a shallow drainage
    // channel. No invented fenestration or unsupported gripping surface.
    FTrainingRenderMesh MakeSerratedJaw(int32 JawSign);
    // Same mounting centre/extents as the previous fork; a rounded hinge housing.
    FTrainingRenderMesh MakeRoundedFork();

    struct FJawAudit
    {
        bool bFinite = true;
        bool bInsideCollisionEnvelope = true;
        int32 VertexCount = 0;
        int32 TriangleCount = 0;
        int32 DegenerateTriangles = 0;
        double MaximumInteriorGapMm = 0;
    };
    FJawAudit AuditJaw(const FTrainingRenderMesh& Mesh);
}
