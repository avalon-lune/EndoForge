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

/** A local, nonblocking transport. SOFA is the only owner of tissue mechanics. */
UCLASS()
class LAPTRAINER_API USimulationBridge : public UObject
{
    GENERATED_BODY()
public:
    void InitializeBridge();
    void TickBridge(float DeltaSeconds, const FVector& ToolTipCm, bool bClosed, bool bReset, float RollDeg = 0.0f);
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
    void TryConnect();
    void Disconnect(const FString& Reason);
    void ReceiveMessages();
    void HandleMessage(const FString& Line);
    void QueueCommand(const FVector& TipCm, bool bClosed, float RollDeg);
    void RecordTelemetry();
    void FlushTelemetry();
    FSocket* Socket = nullptr;
    int32 PhysicsPort = 47322;
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
