#include "Phase6Interaction.h"
#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"

void ATrainingScene::ResetPhase6Motion()
{
    Phase6Interaction = FPhase6InteractionState{};
    for(auto& Waypoints:Phase6SampledApproachWaypoints)Waypoints.Reset();
}

void ATrainingScene::BeginPhase6PositionTarget(int32 Index,const TArray<FVector>& Waypoints)
{
    if (!bPhase6 || Index < 0 || Index > 1) return;
    const int32 Previous = Phase6Interaction.PreviousActiveTool;
    if (Previous >= 0 && Previous != Index)
    {
        Phase6Interaction.Tools[Previous] = FPhase6ToolInputState{};
        if (const auto* Parked = Bridge ? Bridge->GetToolState(Previous) : nullptr)
        {
            ToolTips[Previous] = Parked->ActualTipCm;
            ToolRolls[Previous] = Parked->RollDeg;
        }
    }
    auto& Input = Phase6Interaction.Tools[Index];
    Input = FPhase6ToolInputState{};
    Input.bPositionTarget = true;
    Input.bHoldTip = Input.bHoldRoll = Input.bBoundedTarget = false;
    Input.ApproachWaypoints = Waypoints;
    if (!Waypoints.IsEmpty())
    {
        ToolTips[Index] = Waypoints[0];
        if (ActiveTool == Index) ToolTip = Waypoints[0];
    }
    Phase6Interaction.PreviousActiveTool = Index;
}

void ATrainingScene::ConfigurePhase6Command(int32 Index, FLapToolCommand& Command) const
{
    if (!bPhase6 || Index < 0 || Index > 1) return;
    const auto& Input = Phase6Interaction.Tools[Index];
    Command.bHoldTip = bMouseReleased || Input.bHoldTip;
    Command.bHoldRoll = bMouseReleased || Input.bHoldRoll;
    Command.bBoundedTarget = Input.bBoundedTarget;
}

void ATrainingScene::UpdatePhase6Motion(APlayerController* PC, float DeltaSeconds,
                                       const FVector& Right, const FVector& Up)
{
    if (!PC || !Bridge || !Bridge->HasAcknowledgedReset() || Bridge->IsReplayLocked()) return;
    const auto* Actual = Bridge->GetToolState(ActiveTool);
    if (!Actual) return;
    auto& Control = Phase6Interaction;
    if (Control.PreviousActiveTool >= 0 && Control.PreviousActiveTool != ActiveTool)
    {
        const int32 Previous = Control.PreviousActiveTool;
        Control.Tools[Previous] = FPhase6ToolInputState{};
        if (const auto* Parked = Bridge->GetToolState(Previous))
        {
            ToolTips[Previous] = Parked->ActualTipCm;
            ToolRolls[Previous] = Parked->RollDeg;
        }
        Control.Tools[ActiveTool] = FPhase6ToolInputState{};
    }
    Control.PreviousActiveTool = ActiveTool;
    auto& Input = Control.Tools[ActiveTool];
    const bool Fine = PC->IsInputKeyDown(EKeys::LeftControl);
    const bool Fast = PC->IsInputKeyDown(EKeys::LeftShift);
    const double SpeedCmS = Fine ? .5 : Fast ? 1.8 : 1.2;
    const float RollSpeedDegS = Fine ? 15.f : Fast ? 60.f : 40.f;
    const double SafeDt = FMath::Clamp(double(DeltaSeconds), 0., .05);
    FVector Direction = FVector::ZeroVector;
    if (PC->IsInputKeyDown(EKeys::Left)) Direction -= Right;
    if (PC->IsInputKeyDown(EKeys::Right)) Direction += Right;
    if (PC->IsInputKeyDown(EKeys::Up)) Direction += Up;
    if (PC->IsInputKeyDown(EKeys::Down)) Direction -= Up;
    if (PC->IsInputKeyDown(EKeys::W)) Direction.Z += 1;
    if (PC->IsInputKeyDown(EKeys::S)) Direction.Z -= 1;
    const FVector Axis = (GetPivot(ActiveTool) - Actual->ActualTipCm).GetSafeNormal();
    if (PC->IsInputKeyDown(EKeys::T)) Direction -= Axis;
    if (PC->IsInputKeyDown(EKeys::G)) Direction += Axis;
    FVector Delta = Direction.GetClampedToMaxSize(1.) * SpeedCmS * SafeDt;
    const bool MouseHeld = PC->IsInputKeyDown(EKeys::RightMouseButton);
    if (MouseHeld)
    {
        float MX = 0, MY = 0;
        PC->GetInputMouseDelta(MX, MY);
        const double Sensitivity = Fine ? .00625 : Fast ? .025 : .0125;
        Delta += (Right * FMath::Clamp(MX, -60.f, 60.f) + Up * FMath::Clamp(MY, -60.f, 60.f)) * Sensitivity;
    }
    const int32 Wheel = int32(PC->WasInputKeyJustPressed(EKeys::MouseScrollUp)) -
                        int32(PC->WasInputKeyJustPressed(EKeys::MouseScrollDown));
    const float RollDirection = float(PC->IsInputKeyDown(EKeys::E)) - float(PC->IsInputKeyDown(EKeys::Q));
    const bool Moving = !Delta.IsNearlyZero(1.e-8);
    const bool Rolling = RollDirection != 0;
    if (Moving || Rolling)
    {
        // An explicit manual gesture cancels any long approach preset. Start
        // from measured feedback, never from an old unachieved target.
        if (Input.bPositionTarget)
        {
            ToolTip = Actual->ActualTipCm;
            ToolRoll = Actual->RollDeg;
            Input.bPositionTarget = false;
            Input.ApproachWaypoints.Reset();
        }
    }
    if (Wheel)
    {
        // A wheel click is a finite position pulse, not a one-frame velocity
        // that could disappear between two 30 Hz native updates.
        ToolTip = Actual->ActualTipCm + FVector(0, 0, Wheel * (Fine ? .02 : .05));
        ToolRoll = Actual->RollDeg;
        Input.ApproachWaypoints.Reset();
        Input.ApproachWaypointIndex = 0;
        Input.bPositionTarget = true;
    }
    if (Input.bPositionTarget)
    {
        Input.bHoldTip = Input.bHoldRoll = Input.bBoundedTarget = false;
        if (FVector::Distance(ToolTip, Actual->ActualTipCm) <= .002 &&
            FMath::Abs(FMath::FindDeltaAngleDegrees(Actual->RollDeg, ToolRoll)) <= .1f)
        {
            if (Input.ApproachWaypoints.IsValidIndex(Input.ApproachWaypointIndex + 1))
            {
                ToolTip = Input.ApproachWaypoints[++Input.ApproachWaypointIndex];
                ToolTips[ActiveTool] = ToolTip;
                return;
            }
            Input = FPhase6ToolInputState{};
            ToolTip = Actual->ActualTipCm;
            ToolRoll = Actual->RollDeg;
        }
        return;
    }
    Input.bBoundedTarget = true;
    if (Moving)
    {
        if (!Input.bMovingLastFrame || FVector::DotProduct(Delta, Input.LastDirection) < 0)
            ToolTip = Actual->ActualTipCm;
        ToolTip += Delta;
        const FVector Lead = (ToolTip - Actual->ActualTipCm).GetClampedToMaxSize(Control.MaximumLeadCm);
        ToolTip = Actual->ActualTipCm + Lead;
        Input.bHoldTip = false;
        Input.LastDirection = Delta.GetSafeNormal();
        ++Control.ManualFrames;
    }
    else if (MouseHeld && !Input.bHoldTip)
    {
        // Preserve the last small mouse displacement while the button remains
        // held. This catches short mouse samples without a long target queue.
        ToolTip = Actual->ActualTipCm + (ToolTip - Actual->ActualTipCm).GetClampedToMaxSize(Control.MaximumLeadCm);
    }
    else
    {
        // The native hold command uses the pose at receipt. Sending the stale
        // display pose as a new target would cause a small backward correction.
        ToolTip = Actual->ActualTipCm;
        Input.bHoldTip = true;
        ++Control.HoldFrames;
    }
    if (Rolling)
    {
        if (!Input.bRollingLastFrame || RollDirection * Input.LastRollDirection < 0)
            ToolRoll = Actual->RollDeg;
        ToolRoll = FMath::UnwindDegrees(ToolRoll + RollDirection * RollSpeedDegS * SafeDt);
        ToolRoll = FMath::UnwindDegrees(Actual->RollDeg + FMath::Clamp(
            FMath::FindDeltaAngleDegrees(Actual->RollDeg, ToolRoll), -Control.MaximumRollLeadDeg, Control.MaximumRollLeadDeg));
        Input.bHoldRoll = false;
        Input.LastRollDirection = RollDirection;
    }
    else
    {
        ToolRoll = Actual->RollDeg;
        Input.bHoldRoll = true;
    }
    Input.bMovingLastFrame = Moving;
    Input.bRollingLastFrame = Rolling;
    Control.MaximumTargetLeadMm = FMath::Max(Control.MaximumTargetLeadMm, FVector::Distance(ToolTip, Actual->ActualTipCm) * 10.);
}
