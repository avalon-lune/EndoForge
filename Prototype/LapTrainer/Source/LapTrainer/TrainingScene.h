#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "TrainingGeometry.h"
#include "Phase6Interaction.h"
#include "RenderCommandFence.h"
#include "TrainingScene.generated.h"
class UCameraComponent;
class UMaterialInterface;
class UProceduralMeshComponent;
class USimulationBridge;
class UStaticMesh;
class UStaticMeshComponent;
class USpotLightComponent;
struct FKey;
struct FLapToolCommand;
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
    bool IsPhase4() const;
    bool IsPhase5() const { return bPhase5; }
    bool IsPhase6() const { return bPhase6; }
    bool IsPhase6Preparing() const { return bPhase6 && !bVisualPreview && !bPhase6StartupReady; }
    FString GetPhase6StartupNotice() const;
    FString GetSpecimenName() const;
    FString GetSessionStatus() const;
    FString GetSnapshotNotice() const { return SnapshotNotice; }
    bool IsPhysicsConnected() const;
    bool IsPhysicsHealthy() const;
    bool HasProtectionNotice() const { return bProtectionNotice; }
    bool IsGraspActive() const;
    bool IsGrasperHolding() const;
    bool IsGrasperLatched() const { return bGrasperLatched; }
    int32 GetActiveTool() const { return ActiveTool; }
    FString GetToolName() const { return bPhase5 ? (ActiveTool == 0 ? TEXT("LEFT GRASPER") : TEXT("RIGHT GRASPER")) : (ActiveTool == 0 ? TEXT("GRASPER") : TEXT("SCISSORS")); }
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
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> AnatomyMeshes;
    UPROPERTY() TArray<TObjectPtr<UProceduralMeshComponent>> AnatomyRods;
    UPROPERTY() TObjectPtr<UProceduralMeshComponent> AnatomyAttachment;
    UPROPERTY() TObjectPtr<class USceneCaptureComponent2D> AnatomyCapture;
    UPROPERTY() TObjectPtr<class UTextureRenderTarget2D> AnatomyRGBTarget;
    UPROPERTY() TObjectPtr<class UTextureRenderTarget2D> AnatomyDepthTarget;
    TArray<FString> AnatomyNames;
    TArray<int32> AnatomyIds;
    int32 AnatomyGallbladderId=100;
    FString AnatomyPhysicsFingerprint,AnatomyVisualFingerprint;
    TSharedPtr<FJsonObject> AnatomyAsset;
    FString AnatomyDirectory, Phase5Directory, AnatomyError;
    FString AnatomyModelId, AnatomyModelVersion;
    bool bPhase5=false, bPhase5Test=false, bPhase5Finished=false, bPhase5HomeAdopted=false;
    bool bPhase6=false, bPhase6Test=false;
    FPhase6InteractionState Phase6Interaction;
    void ResetPhase6Motion();
    void BeginPhase6PositionTarget(int32 Index,const TArray<FVector>& Waypoints = {});
    void ConfigurePhase6Command(int32 Index, FLapToolCommand& Command) const;
    void UpdatePhase6Motion(class APlayerController* PC,float DeltaSeconds,const FVector& Right,const FVector& Up);
    UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Phase6StaticMeshes;
    UPROPERTY() TObjectPtr<class USceneCaptureComponent2D> Phase6ProofCapture;
    UPROPERTY() TObjectPtr<class UTextureRenderTarget2D> Phase6ProofTarget;
    TArray<double> Phase6GpuTimes,Phase6SolverTimes;
    TArray<TSharedPtr<FJsonValue>> Phase6Comparisons,Phase6InputSamples;
    TArray<double> Phase6ResponseTimes;
    int32 Phase6InputStage=0,Phase6InputTrial=0,Phase6ProofVariant=-1,Phase6ProofTicks=0;
    double Phase6InputStarted=0,Phase6InputStop=0,Phase6StopTravel=0,Phase6PeakLead=0,Phase6MaxStopTravel=0;
    FVector Phase6InputOrigin=FVector::ZeroVector,Phase6StopPrevious=FVector::ZeroVector;
    bool bPhase6ResponseObserved=false,bPhase6FoundationDone=false;
    uint64 Phase6InputInitialState=0,Phase6InputInitialCommand=0;
    TArray<TSharedPtr<FJsonValue>> Phase6StopSamples;
    TArray<TSharedPtr<FJsonValue>> Phase6MotionSamples;
    TSharedPtr<FJsonObject> Phase6ProofCamera;
    TArray<FString> Phase6FoundationFailures;
    double Phase6TrialLead=0;
    FVector Phase6StopOrigin=FVector::ZeroVector;
    bool bPhase6ProofInProgress=false;
    double Phase6FoundationStartedSeconds=0;
    bool bPhase6StartupReady=false,bPhase6StartupFenceQueued=false,bPhase6StartupFailed=false,bPhase6StartupFenceInvalidated=false;
    double Phase6StartupStarted=0,Phase6StartupStableSince=0,Phase6StartupDuration=0;
    int32 Phase6StartupFrames=0,Phase6StartupStableFrames=0,Phase6StartupPreviousRT=-1;
    uint32 Phase6StartupPSOs=0,Phase6StartupPending=0,Phase6StartupPeakPending=0;
    int32 Phase6StartupViewportDraws=0,Phase6StartupLastViewportDraws=0;
    TWeakObjectPtr<class UGameViewportClient> Phase6StartupViewport;
    FDelegateHandle Phase6StartupDrawHandle;
    FRenderCommandFence Phase6StartupFence;
    void OnPhase6StartupViewportDrawn();
    bool UpdatePhase6Startup();
    void RestorePhase6StartupRendering();
    bool bPhase6PerfBaselineValid=false;
    uint64 Phase6PerfSimulation=MAX_uint64,Phase6SolverSimulation=MAX_uint64,Phase6SolverStep=MAX_uint64;
    FString Phase6PerfMode;
    TSet<FName> Phase6DeferredTestPresses;
    TArray<TSharedPtr<FJsonValue>> Phase6ReadyTargetSamples;
    TSharedPtr<FJsonObject> Phase6ReadyRecipes[2];
    TArray<FVector> Phase6SampledApproachWaypoints[2];
    float Phase6ReadyRolls[2] = {90,90};
    FVector Phase6SampledReadyTargets[2];
    FVector Phase6RightApproachTarget=FVector::ZeroVector;
    bool bPhase6RightApproachSampled=false;
    bool SamplePhase6ReadyTarget(int32 Index,const FString& Source,FVector& OutTarget);
    uint64 Phase6ProofState=0,Phase6ProofSimulation=0;
    float Phase6CameraDistance=1.0f,Phase6CameraYaw=0,Phase6CameraPitch=0;
    void InitializePhase6();
    void ConfigurePhase6Rendering();
    bool UpdatePhase6FoundationTest(float DeltaSeconds);
    void WritePhase6Runtime();
    void UpdatePhase6CameraInput(class APlayerController* PC,float DeltaSeconds);
    void UpdatePhase6DisplaySurface();
    bool BuildPhase6StaticDisplay(UProceduralMeshComponent* Proxy,const TSharedPtr<FJsonObject>& Object);
    bool SavePhase6Json(const FString& Path,const TSharedRef<FJsonObject>& Object);
    void CapturePhase6Review(const FString& Name,bool Closeup=false);
    bool Phase5Latches[2]={false,false};
    int32 Phase5SequenceCounts[2]={0,0};
    int32 Phase5Stage=0, Phase5Ticks=0, Phase5DatasetFrames=0;
    float Phase5Elapsed=0, Phase5StageElapsed=0, Phase5Dwell=0;
    FVector Phase5Homes[2], Phase5Targets[2], Phase5LiftTargets[2];
    bool bPhase5Grip[2]={false,false}, bPhase5Traction=false, bPhase5Dual=false, bPhase5DualTractionRetained=false, bPhase5Release=false;
    uint64 Phase5DualCaptureStep=0;
    double Phase5DualTractionMm=0;
    FVector Phase6DualBaselineTips[2]={FVector::ZeroVector,FVector::ZeroVector};
    FVector Phase6DualTractionDeltas[2]={FVector::ZeroVector,FVector::ZeroVector};
    uint64 Phase6TestLiftFence=0;
    double Phase5LeftTractionMm=0;
    TArray<FVector> Phase5LeftBaselineVertices,Phase5DualBaselineVertices;
    bool bPhase5Record=false, bPhase5Replay=false, bPhase5ReplayDone=false;
    double Phase5PeakDisplacementMm=0, Phase5PeakPenetrationMm=0;
    uint64 Phase5RecordLength=0, Phase5LastCapturedStep=MAX_uint64;
    TArray<FString> Phase5Failures;
    TArray<float> Phase5FrameTimes;
    bool bPhase5CapturePrevious=false;
    double Phase5MeasuredWall=0,Phase5MeasuredNative=0,Phase5PreviousNative=0;
    void CreatePhase5Environment();
    void InitializePhase5();
    void UpdatePhase5Rods();
    void UpdatePhase5Attachment();
    void WritePhase5Manifest();
    void UpdatePhase5Tangents(FTrainingRenderMesh& M) const;
    void UpdatePhase5Test(float DeltaSeconds);
    void AdvancePhase5Test(int32 Stage);
    void FinishPhase5Test(const FString& Failure=FString());
    bool AdoptPhase5Metadata();
    bool CapturePhase5Stereo(const FString& Sequence,int32 Frame);
    TSharedRef<FJsonObject> BuildPhase5RenderGeometry() const;
    void ApplyPhase5Material(UProceduralMeshComponent* Mesh,const TSharedPtr<FJsonObject>& Material);
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
    bool bPhase4Test = false;
    int32 Phase4Stage = 0, Phase4Ticks = 0, Phase4SnapshotCount = 0;
    float Phase4Time = 0, Phase4StageTime = 0, Phase4Dwell = 0;
    bool bPhase4Started = false, bPhase4Finished = false;
    bool bFlatGrip = false, bFlatTraction = false, bFlatRelease = false;
    bool bCurvedGrip = false, bCurvedTraction = false, bCurvedRelease = false;
    bool bRecordingObserved = false, bReplayObserved = false, bReplayComplete = false, bReplayGuard = false;
    uint64 PresentedStateId = MAX_uint64, Phase4RecordLength = 0;
    double MaxProjectionErrorPx = 0, MaxBindingErrorMm = 0;
    FVector Phase4ReadyTarget = FVector::ZeroVector;
    FVector Phase4InteriorTarget = FVector::ZeroVector, Phase4RetreatStart = FVector::ZeroVector;
    FVector Phase4PreviousRetreatTip = FVector::ZeroVector;
    double Phase4PathProgress = 0, Phase4RetreatTravelCm = 0, Phase4CollisionMaxNodeDepthMm = 0;
    bool bInteriorGrip = false, bInteriorTraction = false, bInteriorReleased = false, bDirectRetreatCompleted = false;
    FString Phase4Directory, PresentedBuffer, SnapshotNotice, SnapshotStem;
    TSharedPtr<FJsonObject> SnapshotObject;
    bool bSnapshotFrozen = false, bSnapshotPending = false, bResumeSnapshot = false;
    bool bSnapshotHudWasVisible = true;
    void RestoreSnapshotHUD();
    bool bCapturePreservesRecording = false, bStoppedMidHold = false, bStopStayedOpen = false;
    int32 SnapshotFreezeTicks = 0;
    double SnapshotStartedSeconds = 0;
    uint64 SnapshotCaptureId = 0;
    TArray<FString> Phase4Failures;
    void InitializePhase4();
    bool HandlePhase4Input(class APlayerController* PC);
    void AdoptActualCommands();
    FVector GetGraspReadyTarget() const;
    void UpdatePhase4Test(float DeltaSeconds);
    void AdvancePhase4Test(int32 Stage);
    void FinishPhase4Test(const FString& Failure = FString());
    void RecordPresentedState();
    void FlushPresentedStates();
    TSharedRef<FJsonObject> BuildCameraRecord() const;
    void BeginSnapshot();
    void SaveFrozenSnapshot();
    void OnSnapshotCaptured(int32 Width, int32 Height, const TArray<FColor>& Pixels);
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
    FVector TestEntryTarget = FVector::ZeroVector;
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
    bool SampleTestMaterialPoint(double RestX, double RestY, FVector& OutPosition) const;
    void AdvanceTest(int32 Stage);
    bool TestTimedOut(float Seconds, const TCHAR* Action);
    void CaptureTest(const TCHAR* Filename);
    UStaticMeshComponent* AddShape(const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Material,
        const FVector& Location, const FVector& Scale, const FRotator& Rotation = FRotator::ZeroRotator);
    void PositionRod(UStaticMeshComponent* Mesh, const FVector& A, const FVector& B, float RadiusCm);
};
