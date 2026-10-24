#pragma once
#include "CoreMinimal.h"

/** Command-side state only. The authoritative pose always comes from SOFA. */
struct FPhase6ToolInputState
{
    bool bPositionTarget = false;
    bool bHoldTip = true;
    bool bHoldRoll = true;
    bool bBoundedTarget = true;
    bool bMovingLastFrame = false;
    bool bRollingLastFrame = false;
    TArray<FVector> ApproachWaypoints;
    int32 ApproachWaypointIndex = 0;
    FVector LastDirection = FVector::ZeroVector;
    float LastRollDirection = 0;
};

struct FPhase6InteractionState
{
    FPhase6ToolInputState Tools[2];
    int32 PreviousActiveTool = -1;
    double MaximumTargetLeadMm = 0;
    uint64 ManualFrames = 0;
    uint64 HoldFrames = 0;
    static constexpr double MaximumLeadCm = .1; // 1 mm; also enforced natively.
    static constexpr float MaximumRollLeadDeg = 4.f;
};
