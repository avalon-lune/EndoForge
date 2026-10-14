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
/** Input and presentation only. Physical topology and tool contact belong to SOFA. */
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
    FVector GetOtherToolTip() const { return ActualTips[1 - ActiveTool]; }
    bool IsJawClosed() const { return bJawClosed; }
    bool IsHelpVisible() const { return bShowHelp; }
    bool IsOverview() const { return ViewMode == 1; }
    bool IsMouseReleased() const { return bMouseReleased; }
    bool IsVisualPreview() const { return bVisualPreview; }
    bool IsPhysicsConnected() const;
    bool IsPhysicsHealthy() const;
    bool HasProtectionNotice() const { return bProtectionNotice; }
    bool IsGraspActive() const;
    bool IsGrasperHolding() const;
    bool IsGrasperLatched() const { return bGrasperLatched; }
    int32 GetActiveTool() const { return ActiveTool; }
    FString GetToolName() const { return ActiveTool == 0 ? TEXT("GRASPER") : TEXT("SCISSORS"); }
    FString GetPhysicsStatus() const;
    FString GetViewName() const;
    float GetForceNewton() const;
    float GetSolveTimeMs() const;
    float GetSimulationTime() const { return SimulationElapsed; }
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
    int32 GetCutCount() const;
    int32 GetComponentCount() const;
    float GetCutLengthCm() const;
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
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Shafts;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Collars;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Sleeves;
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Ports;
    UPROPERTY() TArray<TObjectPtr<USceneComponent>> HeadRoots;
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> ToolJaws;
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> InstrumentDetailMeshes;
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
    TArray<FTrainingSurfaceSample> TissueRenderBindings;
    FTrainingRenderMesh TissueRenderData;
    int32 BoundNodeCount = 0, BoundFaceCount = 0;
    int32 BoundTopologyRevision = -1;
    FVector ToolTips[2] = { FVector(-2.2, -4.7, 0.6), FVector(2.2, -4.7, 0.6) };
    FVector ActualTips[2] = { FVector(-2.2, -4.7, 0.6), FVector(2.2, -4.7, 0.6) };
    float ToolRolls[2] = {90.0f, 90.0f};
    bool ToolClosed[2] = {false, false};
    FVector ToolTip = FVector(-2.2, -4.7, 0.6);
    FVector RenderedTip = FVector(-2.2, -4.7, 0.6);
    float ToolRoll = 90.0f, JawOpenBlend = 1.0f;
    float SmoothedFps = 60.0f, SimulationElapsed = 0.0f;
    int32 ActiveTool = 0, ActivePreset = 1, ResetCount = 0, ViewMode = 0;
    bool bJawClosed = false, bGrasperLatched = false, bSuppressSpace = false;
    bool bShowHelp = true, bMouseReleased = false, bHasSurface = false;
    bool bResetRequested = false, bVisualPreview = false, bMotionLimited = false;
    bool bWasPhysicsConnected = false;
    uint64 LastSafetyStopCount = 0;
    bool bProtectionNotice = false, bProtectionHasOpened = false;
    uint64 LastPhysicsFrame = MAX_uint64;
    bool bPhase3Test = false, bAutoExit = false, bTestFinished = false, bTestStarted = false;
    int32 TestStage = 0, TestStroke = 0, TestCutBaseline = 0, TestTopologyBaseline = 0;
    int32 TestStageTicks = 0;
    int32 TestGripFrames = 0;
    float TestTime = 0.0f, TestStageTime = 0.0f, TestDwell = 0.0f;
    float TestPeakDisplacementMm = 0.0f, TestMaxRenderOffsetMm = 0.0f;
    float TestPeakForceN = 0.0f;
    int32 TestPeakCuts = 0, TestPeakComponents = 1, TestPeakTopology = 0;
    bool bTestGrip = false, bTestTension = false, bTestSwitchHeld = false;
    bool bTestCut = false, bTestRelease = false, bTestTopologyRendered = false;
    bool bTestIndependentTool = false, bTestReset = false, bTestContinuousCuts = false;
    bool bTestOpeningNoCut = false, bTestInactiveNoCut = false;
    uint64 TestObservedFrame = MAX_uint64;
    uint64 TestPeakSafetyStops = 0;
    FVector TestParkedGrasper = FVector::ZeroVector;
    FVector TestBiteTarget = FVector::ZeroVector;
    FVector TestRetractTarget = FVector::ZeroVector;
    float TestClearanceZ = 0.0f;
    int32 TestWaypointPhase = 0;
    TSet<FName> TestHeldKeys;
    TArray<FString> TestFailures;
    FString CaptureDirectory;
    void CreateEnvironment();
    void CreateInstrument();
    FVector GetPivot(int32 Index) const;
    void SaveActiveCommand();
    void LoadActiveCommand();
    void SwitchTool();
    void ApplyWorkspaceLimits();
    void SelectPreset(int32 Preset);
    void UpdateInput(float DeltaSeconds);
    void UpdateInstrument(float DeltaSeconds);
    void UpdateCamera();
    void UpdateSimulation(float DeltaSeconds);
    void UpdateTissueSurface();
    void ResetExercise();
    void UpdatePhase3Test(float DeltaSeconds);
    void FinishPhase3Test(const FString& Failure = FString());
    void SetTestKey(const FKey& Key, bool bDown);
    void StopTestMotion();
    bool DriveTestTo(const FVector& Target);
    bool SampleUpperVertex(double X, double Y, FVector& OutPosition) const;
    void AdvanceTest(int32 Stage);
    bool TestTimedOut(float Seconds, const TCHAR* Action);
    void CaptureTest(const TCHAR* Filename);
    UStaticMeshComponent* AddShape(const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Material,
        const FVector& Location, const FVector& Scale, const FRotator& Rotation = FRotator::ZeroRotator);
    void PositionRod(UStaticMeshComponent* Mesh, const FVector& A, const FVector& B, float RadiusCm);
};
