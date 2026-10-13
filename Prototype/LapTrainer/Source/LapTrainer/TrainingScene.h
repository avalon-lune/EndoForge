#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TrainingGeometry.h"
#include "TrainingScene.generated.h"

class UCameraComponent;
class UMaterialInterface;
class UProceduralMeshComponent;
class USimulationBridge;
class UStaticMesh;
class UStaticMeshComponent;
class USpotLightComponent;
struct FKey;

/** Visualisation and keyboard/mouse input only. SOFA owns tissue mechanics. */
UCLASS()
class LAPTRAINER_API ATrainingScene : public AActor
{
    GENERATED_BODY()

public:
    ATrainingScene();
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void CalcCamera(float DeltaTime, struct FMinimalViewInfo& OutResult) override;

    FVector GetToolTip() const { return RenderedTip; }
    FVector GetCommandedTip() const { return ToolTip; }
    bool IsJawClosed() const { return bJawClosed; }
    bool IsHelpVisible() const { return bShowHelp; }
    bool IsOverview() const { return bOverview; }
    FString GetViewName() const;
    bool IsMouseReleased() const { return bMouseReleased; }
    bool IsVisualPreview() const { return bVisualPreview; }
    bool IsPhysicsConnected() const;
    bool IsGraspActive() const;
    FString GetPhysicsStatus() const;
    float GetForceNewton() const;
    float GetSolveTimeMs() const;
    float GetSimulationTime() const;
    float GetFrameRate() const { return SmoothedFps; }
    int32 GetVertexCount() const { return TissueRenderData.Positions.Num(); }
    int32 GetPhysicsNodeCount() const;
    int32 GetResetCount() const { return ResetCount; }
    int32 GetPreset() const { return ActivePreset; }
    int32 GetContactCount() const;
    float GetContactForceNewton() const;
    float GetPenetrationMm() const;
    float GetSlipDistanceMm() const;
    float GetInsertionCm() const;
    float GetSwingAngleDeg() const;
    float GetRollDeg() const;
    float GetJawAngleDeg() const;
    bool IsMotionLimited() const { return bMotionLimited; }
    bool IsSlipping() const;
    FString GetGripState() const;
    FString GetActionHint() const;

protected:
    virtual void BeginPlay() override;

private:
    UPROPERTY() TObjectPtr<USceneComponent> SceneRoot;
    UPROPERTY() TObjectPtr<UCameraComponent> Camera;
    UPROPERTY() TObjectPtr<USpotLightComponent> EndoscopeLight;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> TissueMesh;
    UPROPERTY() TObjectPtr<USimulationBridge> Bridge;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> SceneMeshes;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Shaft;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Collar;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> JawLeft;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> JawRight;
    UPROPERTY() TObjectPtr<USceneComponent> InstrumentHeadRoot;
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> InstrumentDetailMeshes;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> ShaftSleeve;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> TrocarPort;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> ToolMarker;
    UPROPERTY() TObjectPtr<UStaticMesh> CubeMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
    UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
    UPROPERTY() TObjectPtr<UMaterialInterface> TissueMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> MetalMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> DarkMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> TableMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> AccentMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> InsulationMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> TrayMaterial;
    UPROPERTY() TObjectPtr<UMaterialInterface> PadBackingMaterial;

    TArray<FVector> TissueVertices;
    TArray<int32> TissueTriangles;
    TArray<FVector> TissueNormals;
    TArray<FVector2D> TissueUV;
    TArray<FLinearColor> TissueColors;
    TArray<FTrainingSurfaceSample> TissueRenderBindings;
    FTrainingRenderMesh TissueRenderData;
    int32 BoundNodeCount = 0;
    int32 BoundFaceCount = 0;
    FVector ToolTip = FVector(0.0, 0.0, 2.2);
    FVector RenderedTip = FVector(0.0, 0.0, 2.2);
    float ToolRoll = 0.0f;
    float JawOpenBlend = 1.0f;
    float SmoothedFps = 60.0f;
    float SimulationElapsed = 0.0f;
    float DemoElapsed = 0.0f;
    float PreviewElapsed = 0.0f;
    uint32 PreviewMask = 0;
    float KeyTestElapsed = 0.0f;
    float KeyTestWaitElapsed = 0.0f;
    float KeyTestPeakForce = 0.0f;
    float KeyTestMinHeight = 2.2f;
    float KeyTestMaxHeldHeight = 0.0f;
    uint32 KeyTestEventMask = 0;
    bool bPhase2Test = false;
    bool bPhase2Finished = false;
    bool bPhase2Contact = false;
    bool bPhase2ContactReleased = false;
    bool bPhase2Grasp = false;
    bool bPhase2Slip = false;
    bool bPhase2Released = false;
    bool bPhase2ReleaseStartedHolding = false;
    bool bPhase2ReleasedByOpening = false;
    bool bPhase2RepeatGrasp = false;
    bool bPhase2TractionHeld = false;
    bool bPhase2Roll = false;
    bool bPhase2RollReturned = false;
    bool bPhase2Started = false;
    bool bPhase2Preset1 = false;
    bool bPhase2Preset2 = false;
    bool bPhase2Limit = false;
    int32 Phase2Stage = 0;
    float Phase2StageTime = 0.0f;
    float Phase2WaitTime = 0.0f;
    float Phase2Dwell = 0.0f;
    float Phase2PeakContactN = 0.0f;
    float Phase2PeakGripN = 0.0f;
    float Phase2MaxPenetrationMm = 0.0f;
    float Phase2MaxSlipMm = 0.0f;
    float Phase2MaxTissueMm = 0.0f;
    float Phase2MaxRenderOffsetMm = 0.0f;
    float Phase2ContinuousHold = 0.0f;
    float Phase2LongestHold = 0.0f;
    int32 Phase2HoldFrames = 0;
    uint64 Phase2LastObservedFrame = MAX_uint64;
    uint32 Phase2StageMask = 0;
    TSet<FName> Phase2HeldKeys;
    TArray<FString> Phase2Failures;
    int32 DemoPhase = -1;
    uint32 DemoCaptureMask = 0;
    FString CaptureDirectory;
    uint64 LastPhysicsFrame = MAX_uint64;
    bool bJawClosed = false;
    bool bShowHelp = true;
    bool bOverview = false;
    bool bMouseReleased = false;
    bool bHasSurface = false;
    bool bResetRequested = false;
    bool bAutoDemo = false;
    bool bAutoExit = false;
    bool bKeyTest = false;
    bool bVisualPreview = false;
    bool bKeyTestFinished = false;
    bool bKeyTestCaptured = false;
    bool bKeyTestReleased = false;
    bool bMotionLimited = false;
    int32 ActivePreset = 1;
    int32 ResetCount = 0;
    int32 ViewMode = 0;

    void CreateEnvironment();
    void CreateInstrument();
    void ApplyWorkspaceLimits();
    void SelectPreset(int32 Preset);
    void UpdateInput(float DeltaSeconds);
    void UpdateKeyTest(float DeltaSeconds);
    void UpdateVisualPreview(float DeltaSeconds);
    void UpdatePhase2Test(float DeltaSeconds);
    void FinishPhase2Test(const FString& Failure = FString());
    void SetPhase2Key(const FKey& Key, bool bDown);
    void StopPhase2Motion();
    bool DrivePhase2To(const FVector& Target);
    void AdvancePhase2(int32 Stage);
    bool Phase2TimedOut(float TimeoutSeconds, const TCHAR* Action);
    void CapturePhase2(const TCHAR* Filename);
    void FinishKeyTest(const FString& Failure = FString());
    void UpdateInstrument(float DeltaSeconds);
    void UpdateCamera();
    void UpdateSimulation(float DeltaSeconds);
    void UpdateTissueSurface();
    void ResetExercise();
    UStaticMeshComponent* AddShape(const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Material,
        const FVector& Location, const FVector& Scale, const FRotator& Rotation = FRotator::ZeroRotator);
    void PositionRod(UStaticMeshComponent* Mesh, const FVector& A, const FVector& B, float RadiusCm);
};
