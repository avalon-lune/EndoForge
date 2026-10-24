#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "SimulationBridge.generated.h"

class FSocket;

/** Authoritative rigid jaw frame, in UE centimetres. Axes are unit world vectors. */
struct FLapJawPose
{
    FVector CenterCm = FVector::ZeroVector;
    FVector Axis = FVector::ForwardVector;
    FVector Side = FVector::RightVector;
    FVector Normal = FVector::UpVector;
};

struct FLapToolCommand
{
    FVector TipCm = FVector::ZeroVector;
    bool bClosed = false;
    float RollDeg = 90.0f;
    bool bHoldTip = false;
    bool bHoldRoll = false;
    bool bBoundedTarget = false;
};

struct FLapToolState
{
    FVector ActualTipCm = FVector::ZeroVector;
    FVector PivotCm = FVector::ZeroVector;
    float RollDeg = 90.0f;
    float JawOpenFraction = 1.0f;
    bool bGrasping = false;
    float ForceNewton = 0;
    int32 ContactCount = 0;
    float ContactForceNewton = 0;
    float PenetrationMm = 0;
    float SlipDistanceMm = 0;
    FString GripState = TEXT("open");
    bool bMotionBlocked = false;
    FString MotionGuardReason;
    double MotionAcceptedFraction = 1;
    double MotionClearanceMm = 0;
    int32 MotionWitnessTriangle = -1;
    int32 MotionGuardWorkCount = 0;
    TArray<FLapJawPose> JawPoses;
};

/** A local, nonblocking transport. SOFA is the only owner of tissue mechanics. */
UCLASS()
class LAPTRAINER_API USimulationBridge : public UObject
{
    GENERATED_BODY()
public:
    void InitializeBridge();
    bool IsPhase4() const { return ExpectedProtocol >= 4; }
    bool IsPhase5() const { return ExpectedProtocol == 5; }
    const TSharedPtr<FJsonObject>& GetModelMetadata() const { return ModelMetadata; }
    void SetSpecimen(const FString& Name) { RequestedSpecimen = Name; }
    void RequestSessionAction(const FString& Action);
    FString GetSpecimen() const { return Specimen; }
    FString GetSessionMode() const { return SessionMode; }
    FString GetPendingSessionAction() const { return HasPendingSessionAction() ? PendingSessionAction : FString(); }
    FString GetSessionError() const { return SessionError; }
    bool IsReplayLocked() const { return SessionMode == TEXT("replaying") || SessionMode == TEXT("replay_complete") || PendingSessionAction == TEXT("replay_last"); }
    bool HasPendingSessionAction() const { return PendingActionId > AcknowledgedActionId; }
    uint64 GetStateId() const { return NativeStateId; }
    uint64 GetSimulationId() const { return SimulationId; }
    uint64 GetStepIndex() const { return StepIndex; }
    uint64 GetReplayLength() const { return ReplayLength; }
    uint64 GetRecordedSteps() const { return RecordedSteps; }
    double GetNativeTime() const { return NativeTime; }
    int32 GetAcknowledgedResetId() const { return AcknowledgedResetId; }
    const TSharedPtr<FJsonObject>& GetAcceptedState() const { return AcceptedState; }
    const TArray<int32>& GetNodeIds() const { return NodeIds; }
    const TArray<int32>& GetMaterialIds() const { return MaterialIds; }
    void TickBridge(float DeltaSeconds, const FVector& ToolTipCm, bool bClosed, bool bReset, float RollDeg = 0.0f);
    void TickFrozenBridge();
    void TickDualBridge(float DeltaSeconds, const TArray<FLapToolCommand>& Commands, int32 ActiveTool, bool bReset);
    // Phase 6 presentation freezes must not resume performance/input on queued,
    // pre-freeze feedback. Ordinary bridge ticks drain until a post-freeze command
    // is acknowledged by a newly accepted authoritative state.
    bool IsFrozenResumePending() const { return bPhase6Commands && bFrozenResumePending; }
    uint64 GetFrozenResumeFenceSequence() const { return FrozenResumeFenceSequence; }
    uint64 GetAppliedCommandSequence() const { return AppliedCommandSequence; }
    uint64 GetQueuedCommandSequence() const { return CommandSequence; }
    const FLapToolState* GetToolState(int32 Index) const { return HasToolState() && ToolStates.IsValidIndex(Index) ? &ToolStates[Index] : nullptr; }
    uint64 GetTopologyRevision() const { return TopologyRevision; }
    uint64 GetSafetyStopCount() const { return SafetyStopCount; }
    int32 GetCutCount() const { return CutCount; }
    int32 GetComponentCount() const { return ComponentCount; }
    float GetCutLengthCm() const { return CutLengthCm; }
    void ShutdownBridge();
    bool GetSurface(TArray<FVector>& OutVerticesCm, TArray<int32>& OutTriangles) const;
    bool IsConnected() const;
    bool IsHealthy() const { return IsConnected() && bHealthy; }
    uint64 GetUnhealthyStateCount() const { return UnhealthyStateCount; }
    uint64 GetRejectedStateCount() const { return RejectedStateCount; }
    bool HasAcknowledgedReset() const { return IsConnected() && ResetId == AcknowledgedResetId; }
    bool IsGraspActive() const { return IsConnected() && bGrasping; }
    FString GetStatusText() const;
    float GetForceNewton() const { return ForceNewton; }
    float GetPhysicsStepMs() const { return PhysicsStepMs; }
    float GetMaxDisplacementCm() const { return MaxDisplacementCm; }
    bool HasToolState() const { return IsConnected() && bHasToolState; }
    FVector GetActualTipCm() const { return ActualTipCm; }
    float GetActualRollDeg() const { return ActualRollDeg; }
    float GetJawOpenFraction() const { return JawOpenFraction; }
    int32 GetContactCount() const { return ContactCount; }
    float GetContactForceNewton() const { return ContactForceNewton; }
    float GetPenetrationMm() const { return PenetrationMm; }
    float GetSlipDistanceMm() const { return SlipDistanceMm; }
    FString GetGripState() const { return GripState; }
    int32 GetPhysicsNodeCount() const { return PhysicsNodeCount; }
    const TArray<FLapJawPose>& GetJawPoses() const { return JawPoses; }
    bool GetJawPose(int32 JawIndex, FTransform& OutPoseCm) const;
    uint64 GetFrameNumber() const { return MeshRevision; }
    virtual void BeginDestroy() override;
private:
    friend class FPhase3BridgeProtocolTest;
    friend class FPhase4BridgeProtocolTest;
    int32 ExpectedProtocol = 4;
    bool bPhase6Commands = false;
    FString RequestedSpecimen = TEXT("flat"), Specimen = TEXT("flat");
    FString SessionMode = TEXT("idle"), SessionError, PendingSessionAction;
    uint64 PendingActionId = 0, AcknowledgedActionId = 0;
    uint64 NativeStateId = 0, SimulationId = 0, StepIndex = 0, ReplayLength = 0, RecordedSteps = 0;
    double NativeTime = 0;
    TArray<int32> NodeIds, MaterialIds;
    FString ConfigSignature;
    uint64 NativeFrame = 0;
    TSharedPtr<FJsonObject> AcceptedState;
    TSharedPtr<FJsonObject> ModelMetadata;
    FString ModelSignature;
    void TryConnect();
    void Disconnect(const FString& Reason);
    void ReceiveMessages();
    void CheckFrozenResumeFence();
    void HandleMessage(const FString& Line);
    void QueueCommand(const TArray<FLapToolCommand>& Commands, int32 ActiveTool, bool bPermitClosure);
    void RecordTelemetry();
    void FlushTelemetry();
    FSocket* Socket = nullptr;
    int32 PhysicsPort = 47325;
    TArray<FLapToolState> ToolStates;
    TArray<FLapToolCommand> LastCommands;
    int32 LastActiveTool = 0;
    uint64 TopologyRevision = 0;
    uint64 SafetyStopCount = 0;
    int32 CutCount = 0;
    int32 ComponentCount = 1;
    float CutLengthCm = 0;
    TArray<uint8> ReceiveBuffer;
    TArray<uint8> SendBuffer;
    int32 SendOffset = 0;
    TArray<FVector> VerticesCm;
    TArray<int32> Triangles;
    double NextConnectSeconds = 0;
    double LastStateSeconds = 0;
    double ConnectStartedSeconds = 0;
    uint64 MeshRevision = 0;
    uint64 CommandSequence = 0;
    uint64 AppliedCommandSequence = 0;
    uint64 FrozenResumeFenceSequence = 0, FrozenResumeAfterStateId = 0;
    double FrozenResumeFenceSeconds = 0;
    bool bFrozenResumePending = false;
    uint64 UnhealthyStateCount = 0;
    uint64 RejectedStateCount = 0;
    int32 ResetId = 0;
    int32 AcknowledgedResetId = 0;
    bool bHandshake = false;
    bool bGrasping = false;
    bool bHealthy = true;
    bool bInitialized = false;
    bool bHasToolState = false;
    float ForceNewton = 0;
    float PhysicsStepMs = 0;
    float MaxDisplacementCm = 0;
    FVector ActualTipCm = FVector(0, 0, 2.2);
    float ActualRollDeg = 0;
    float JawOpenFraction = 1;
    int32 ContactCount = 0;
    int32 PhysicsNodeCount = 0;
    float ContactForceNewton = 0;
    float PenetrationMm = 0;
    float SlipDistanceMm = 0;
    FString GripState = TEXT("open");
    TArray<FLapJawPose> JawPoses;
    FVector LastCommandTipCm = FVector(0, 0, 2.2);
    bool bLastCommandClosed = false;
    float LastCommandRollDeg = 0;
    FString TelemetryPath;
    FString TelemetryBuffer;
    double LastTelemetrySeconds = 0;
    double LastTelemetryFlushSeconds = 0;
    double LastRejectedStateLogSeconds = 0;
    bool bTelemetryEnabled = false;
    FString Status = TEXT("Waiting for local SOFA service");
    FString SolverName;
};
