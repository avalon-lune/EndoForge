#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "Camera/CameraComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/RectLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "InputKeyEventArgs.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Materials/Material.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "ProceduralMeshComponent.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "UnrealClient.h"
#include "UObject/ConstructorHelpers.h"

ATrainingScene::ATrainingScene()
{
    PrimaryActorTick.bCanEverTick = true;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeAsset(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderAsset(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereAsset(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    CubeMesh = CubeAsset.Object;
    CylinderMesh = CylinderAsset.Object;
    SphereMesh = SphereAsset.Object;
    SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    SetRootComponent(SceneRoot);
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("EndoscopeCamera"));
    Camera->SetupAttachment(SceneRoot);
    Camera->FieldOfView = 47.0f;
    Camera->bConstrainAspectRatio = false;
    Camera->PostProcessBlendWeight = 1.0f;
    Camera->PostProcessSettings.bOverride_AutoExposureMethod = true;
    Camera->PostProcessSettings.AutoExposureMethod = AEM_Manual;
    Camera->PostProcessSettings.bOverride_AutoExposureBias = true;
    Camera->PostProcessSettings.AutoExposureBias = 0.0f;
    Camera->PostProcessSettings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
    Camera->PostProcessSettings.AutoExposureApplyPhysicalCameraExposure = false;
    Camera->PostProcessSettings.bOverride_VignetteIntensity = true;
    Camera->PostProcessSettings.VignetteIntensity = 0.35f;
    Camera->PostProcessSettings.bOverride_MotionBlurAmount = true;
    Camera->PostProcessSettings.MotionBlurAmount = 0.0f;
    Camera->PostProcessSettings.bOverride_BloomIntensity = true;
    Camera->PostProcessSettings.BloomIntensity = 0.12f;
    TissueMesh = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("SOFATissueSurface"));
    TissueMesh->SetupAttachment(SceneRoot);
    TissueMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    TissueMesh->SetSimulatePhysics(false);
    TissueMesh->bUseAsyncCooking = false;
    TissueMesh->SetCastShadow(true);
}

void ATrainingScene::BeginPlay()
{
    Super::BeginPlay();
    bVisualPreview = FParse::Param(FCommandLine::Get(), TEXT("LapVisualPreview"));
    TissueMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Tissue.M_Tissue"));
    MetalMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Metal.M_Metal"));
    DarkMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Dark.M_Dark"));
    TableMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Table.M_Table"));
    AccentMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Accent.M_Accent"));
    InsulationMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Insulation.M_Insulation"));
    TrayMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_Tray.M_Tray"));
    PadBackingMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Materials/M_PadBacking.M_PadBacking"));
    if (!TissueMaterial) TissueMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    if (!MetalMaterial) MetalMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    if (!DarkMaterial) DarkMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    if (!TableMaterial) TableMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    if (!AccentMaterial) AccentMaterial = UMaterial::GetDefaultMaterial(MD_Surface);
    if (!InsulationMaterial) InsulationMaterial = DarkMaterial;
    if (!TrayMaterial) TrayMaterial = MetalMaterial;
    if (!PadBackingMaterial) PadBackingMaterial = TableMaterial;
    TissueMesh->SetMaterial(0, TissueMaterial);
    CreateEnvironment();
    CreateInstrument();
    UpdateCamera();
    if (!bVisualPreview)
    {
        Bridge = NewObject<USimulationBridge>(this);
        Bridge->InitializeBridge();
    }
    bAutoDemo = FParse::Param(FCommandLine::Get(), TEXT("LapAutoDemo"));
    bAutoExit = FParse::Param(FCommandLine::Get(), TEXT("LapAutoExit"));
    bKeyTest = FParse::Param(FCommandLine::Get(), TEXT("LapKeyTest"));
    bPhase2Test = FParse::Param(FCommandLine::Get(), TEXT("LapPhase2Test"));
    if (bPhase2Test) { bKeyTest = false; bAutoDemo = false; }
    if (bVisualPreview) { bKeyTest = false; bAutoDemo = false; bPhase2Test = false; }
    if (bKeyTest) bAutoDemo = false;
    if (bAutoDemo || bKeyTest || bVisualPreview || bPhase2Test)
    {
        if (!FParse::Value(FCommandLine::Get(), TEXT("LapCaptureDir="), CaptureDirectory))
            CaptureDirectory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Automation/LapDemo"));
        CaptureDirectory = FPaths::ConvertRelativePathToFull(CaptureDirectory);
        IFileManager::Get().MakeDirectory(*CaptureDirectory, true);
    }
    if (bAutoDemo) UE_LOG(LogTemp, Display, TEXT("LAP_AUTODEMO enabled: SOFA will receive an automatic tool input sequence."));
    if (bKeyTest) UE_LOG(LogTemp, Display, TEXT("LAP_KEYTEST enabled: injecting actual PlayerController key events through normal input polling."));
    if (bVisualPreview) UE_LOG(LogTemp, Display, TEXT("LAP_VISUAL_PREVIEW: geometry/material review only; this is NOT a physics acceptance test."));
    if (bPhase2Test) UE_LOG(LogTemp, Display, TEXT("LAP_PHASE2_TEST: actual PlayerController key events, authoritative SOFA jaw contacts, no direct tip-position writes."));
    if (APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0))
    {
        PC->SetViewTarget(this);
        PC->bShowMouseCursor = false;
        PC->SetInputMode(FInputModeGameOnly());
    }
}

void ATrainingScene::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    if (Bridge) Bridge->ShutdownBridge();
    Super::EndPlay(EndPlayReason);
}

void ATrainingScene::CalcCamera(float DeltaTime, FMinimalViewInfo& OutResult)
{
    Super::CalcCamera(DeltaTime, OutResult);
    OutResult.PerspectiveNearClipPlane = 0.15f;
}

UStaticMeshComponent* ATrainingScene::AddShape(const TCHAR* Name, UStaticMesh* Mesh,
    UMaterialInterface* Material, const FVector& Location, const FVector& Scale, const FRotator& Rotation)
{
    UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this, FName(Name));
    C->SetupAttachment(SceneRoot);
    C->SetStaticMesh(Mesh);
    C->SetMaterial(0, Material);
    C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    C->SetSimulatePhysics(false);
    C->SetMobility(EComponentMobility::Movable);
    C->RegisterComponent();
    C->SetWorldLocation(Location);
    C->SetWorldRotation(Rotation);
    C->SetWorldScale3D(Scale);
    SceneMeshes.Add(C);
    return C;
}

void ATrainingScene::CreateEnvironment()
{
    // All dimensions use centimetres. The simulated block occupies x +/-6, y +/-4, z 0..1.2.
    AddShape(TEXT("TrainingBase"), CubeMesh, DarkMaterial, FVector(0, 0, -1.7), FVector(0.30, 0.24, 0.02));
    AddShape(TEXT("TrainingSurface"), CubeMesh, PadBackingMaterial, FVector(0, 0, -0.58), FVector(0.275, 0.215, 0.003));
    AddShape(TEXT("TrayEdgeLeft"), CubeMesh, TrayMaterial, FVector(-14.4, 0, -0.25), FVector(0.005, 0.225, 0.009));
    AddShape(TEXT("TrayEdgeRight"), CubeMesh, TrayMaterial, FVector(14.4, 0, -0.25), FVector(0.005, 0.225, 0.009));
    AddShape(TEXT("TrayEdgeBack"), CubeMesh, TrayMaterial, FVector(0, 11.3, -0.25), FVector(0.293, 0.005, 0.009));
    AddShape(TEXT("TrayEdgeFront"), CubeMesh, TrayMaterial, FVector(0, -11.3, -0.25), FVector(0.293, 0.005, 0.009));
    AddShape(TEXT("BackAnchor"), CubeMesh, MetalMaterial, FVector(0, 4.2, 0.5), FVector(0.13, 0.006, 0.01));
    AddShape(TEXT("BackAnchorMark"), CubeMesh, AccentMaterial, FVector(0, 4.22, 1.025), FVector(0.12, 0.004, 0.0006));
    for (int32 I = 0; I <= 12; ++I)
    {
        const float X = -6.0f + I;
        const float TickLength = (I % 5 == 1) ? 0.65f : 0.35f;
        AddShape(*FString::Printf(TEXT("RulerTick_%d"), I), CubeMesh, AccentMaterial,
            FVector(X, -5.0, -0.414), FVector(0.0007f, TickLength / 100.0f, 0.00015f));
    }
    for (int32 I = 0; I < 4; ++I)
    {
        AddShape(*FString::Printf(TEXT("MountScrew_%d"), I), CylinderMesh, MetalMaterial,
            FVector((I & 1) ? 12.8 : -12.8, (I & 2) ? 9.5 : -9.5, -0.37), FVector(0.0045, 0.0045, 0.001));
    }

    auto* MainLight = NewObject<USpotLightComponent>(this, TEXT("EndoscopeLight"));
    EndoscopeLight = MainLight;
    MainLight->SetupAttachment(Camera);
    MainLight->SetMobility(EComponentMobility::Movable);
    MainLight->SetIntensityUnits(ELightUnits::Candelas);
    MainLight->SetIntensity(0.30f);
    MainLight->SetLightColor(FLinearColor(1.0f, 0.94f, 0.86f));
    MainLight->SetAttenuationRadius(130.0f);
    MainLight->SetInnerConeAngle(30.0f);
    MainLight->SetOuterConeAngle(53.0f);
    MainLight->SetSourceRadius(0.8f);
    MainLight->SetCastShadows(true);
    MainLight->RegisterComponent();
    MainLight->SetRelativeLocation(FVector(0, 1.0, 1.0));
    MainLight->SetRelativeRotation(FRotator::ZeroRotator);

    auto* Fill = NewObject<UPointLightComponent>(this, TEXT("SoftFill"));
    Fill->SetupAttachment(SceneRoot);
    Fill->SetIntensityUnits(ELightUnits::Candelas);
    Fill->SetIntensity(0.08f);
    Fill->SetLightColor(FLinearColor(0.57f, 0.73f, 1.0f));
    Fill->SetAttenuationRadius(90.0f);
    Fill->SetSourceRadius(8.0f);
    Fill->SetCastShadows(false);
    Fill->RegisterComponent();
    Fill->SetWorldLocation(FVector(-12, 1, 18));

    auto* SoftTop = NewObject<UDirectionalLightComponent>(this, TEXT("InspectionFill"));
    SoftTop->SetupAttachment(SceneRoot);
    SoftTop->SetMobility(EComponentMobility::Movable);
    SoftTop->SetIntensity(0.8f);
    SoftTop->SetLightColor(FLinearColor(0.90f, 0.96f, 1.0f));
    SoftTop->SetCastShadows(false);
    SoftTop->RegisterComponent();
    SoftTop->SetWorldRotation(FRotator(-65.0f, 35.0f, 0.0f));

    // Broad reflections describe the stainless-steel shape; no emissive "fake metal" material.
    auto* ReflectionKey = NewObject<URectLightComponent>(this, TEXT("InstrumentReflectionCard"));
    ReflectionKey->SetupAttachment(SceneRoot);
    ReflectionKey->SetMobility(EComponentMobility::Movable);
    ReflectionKey->SetIntensityUnits(ELightUnits::Lumens);
    ReflectionKey->SetIntensity(0.15f);
    ReflectionKey->SetLightColor(FLinearColor(0.89f, 0.94f, 1.0f));
    ReflectionKey->SetSourceWidth(13.0f);
    ReflectionKey->SetSourceHeight(5.0f);
    ReflectionKey->SetAttenuationRadius(80.0f);
    ReflectionKey->SetCastShadows(false);
    ReflectionKey->RegisterComponent();
    ReflectionKey->SetWorldLocation(FVector(-6, -9, 17));
    ReflectionKey->SetWorldRotation((FVector(0, -1, 1) - FVector(-6, -9, 17)).Rotation());

    // A static placeholder is displayed until the first SOFA state; it never deforms locally.
    TissueVertices = { FVector(-6,-4,0), FVector(6,-4,0), FVector(6,4,0), FVector(-6,4,0),
        FVector(-6,-4,1.2), FVector(6,-4,1.2), FVector(6,4,1.2), FVector(-6,4,1.2) };
    TissueTriangles = { 0,2,1, 0,3,2, 4,5,6, 4,6,7, 0,1,5, 0,5,4,
        1,2,6, 1,6,5, 2,3,7, 2,7,6, 3,0,4, 3,4,7 };
    UpdateTissueSurface();
    bHasSurface = false;
}

void ATrainingScene::CreateInstrument()
{
    Shaft = AddShape(TEXT("InstrumentShaft"), CylinderMesh, MetalMaterial, ToolTip, FVector::OneVector);
    Collar = AddShape(TEXT("InstrumentCollar"), CylinderMesh, MetalMaterial, ToolTip, FVector::OneVector);
    ShaftSleeve = AddShape(TEXT("InstrumentInsulation"), CylinderMesh, InsulationMaterial, ToolTip, FVector::OneVector);
    TrocarPort = AddShape(TEXT("TrocarSeal"), CylinderMesh, InsulationMaterial, FVector(12, -14, 15), FVector(0.010, 0.010, 0.006));
    InstrumentHeadRoot = NewObject<USceneComponent>(this, TEXT("InstrumentHeadFrame"));
    InstrumentHeadRoot->SetupAttachment(SceneRoot);
    InstrumentHeadRoot->RegisterComponent();
    auto Procedural = [&](const TCHAR* Name, const FTrainingRenderMesh& M, USceneComponent* Parent)
    {
        auto* P = NewObject<UProceduralMeshComponent>(this, FName(Name));
        P->SetupAttachment(Parent);
        P->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        P->SetSimulatePhysics(false);
        P->RegisterComponent();
        P->SetMaterial(0, MetalMaterial);
        P->CreateMeshSection_LinearColor(0, M.Positions, M.Triangles, M.Normals, M.UV, M.Colors, M.Tangents, false);
        InstrumentDetailMeshes.Add(P);
        return P;
    };
    // Service jaw index 0 is the -Side blade; index 1 is the +Side blade.
    JawLeft = Procedural(TEXT("SerratedJawNegative"), TrainingGeometry::MakeSerratedJaw(-1), SceneRoot);
    JawRight = Procedural(TEXT("SerratedJawPositive"), TrainingGeometry::MakeSerratedJaw(1), SceneRoot);
    for (int32 Sign : { -1, 1 })
    {
        UProceduralMeshComponent* Fork = Procedural(*FString::Printf(TEXT("HingeFork_%d"), Sign),
            TrainingGeometry::MakeBeveledBox(FVector(0.23, 0.048, 0.22), 0.012f), InstrumentHeadRoot);
        Fork->SetRelativeLocation(FVector(-0.09, Sign * 0.184, 0));
        UStaticMeshComponent* Pin = AddShape(*FString::Printf(TEXT("HingePin_%d"), Sign), CylinderMesh,
            MetalMaterial, FVector::ZeroVector, FVector(0.0024, 0.0024, 0.0009));
        Pin->AttachToComponent(InstrumentHeadRoot, FAttachmentTransformRules::KeepRelativeTransform);
        Pin->SetRelativeLocation(FVector(0, Sign * 0.238, 0));
        Pin->SetRelativeRotation(FRotator(0, 0, 90));
        UStaticMeshComponent* Slot = AddShape(*FString::Printf(TEXT("HingeScrewSlot_%d"), Sign), CubeMesh,
            DarkMaterial, FVector::ZeroVector, FVector(0.0013, 0.00015, 0.0003));
        Slot->AttachToComponent(InstrumentHeadRoot, FAttachmentTransformRules::KeepRelativeTransform);
        Slot->SetRelativeLocation(FVector(0, Sign * 0.286, 0));
        Slot->SetRelativeRotation(FRotator(0, 0, 12));
    }
    ToolMarker = AddShape(TEXT("ToolTargetMarker"), SphereMesh, AccentMaterial, ToolTip, FVector(0.0012));
    ToolMarker->SetCastShadow(false);
    ToolMarker->SetVisibility(false);
    UpdateInstrument(1.0f);
}

void ATrainingScene::PositionRod(UStaticMeshComponent* Mesh, const FVector& A, const FVector& B, float RadiusCm)
{
    if (!Mesh) return;
    const FVector D = B - A;
    Mesh->SetWorldLocation((A + B) * 0.5);
    Mesh->SetWorldRotation(FRotationMatrix::MakeFromZ(D.GetSafeNormal()).Rotator());
    Mesh->SetWorldScale3D(FVector(RadiusCm / 50.0f, RadiusCm / 50.0f, D.Size() / 100.0f));
}

void ATrainingScene::UpdateInstrument(float DeltaSeconds)
{
    const bool bAuthoritative = Bridge && Bridge->IsConnected() && Bridge->HasToolState();
    RenderedTip = bAuthoritative ? Bridge->GetActualTipCm() : ToolTip;
    const float ActualRoll = bAuthoritative ? Bridge->GetActualRollDeg() : ToolRoll;
    JawOpenBlend = bAuthoritative ? Bridge->GetJawOpenFraction() : (bJawClosed ? 0.0f : 1.0f);
    const FVector TrocarPivot(12.0, -14.0, 15.0);
    const FVector Axis = (TrocarPivot - RenderedTip).GetSafeNormal();
    FVector Side = FVector::CrossProduct(Axis, FVector::UpVector).GetSafeNormal();
    if (Side.IsNearlyZero()) Side = FVector::CrossProduct(Axis, FVector::RightVector).GetSafeNormal();
    Side = Side.RotateAngleAxis(ActualRoll, Axis);
    const FVector Width = FVector::CrossProduct(Axis, Side).GetSafeNormal();
    const FVector Joint = RenderedTip + Axis * 1.45;
    PositionRod(Shaft, Joint + Axis * 0.30, TrocarPivot + Axis * 2.0, 0.20f);
    PositionRod(ShaftSleeve, Joint + Axis * 3.0, TrocarPivot - Axis * 0.35, 0.205f);
    PositionRod(Collar, Joint - Axis * 0.18, Joint + Axis * 0.48, 0.24f);
    InstrumentHeadRoot->SetWorldLocation(Joint);
    InstrumentHeadRoot->SetWorldRotation(FRotationMatrix::MakeFromXY(-Axis, Width).Rotator());
    TrocarPort->SetWorldRotation(FRotationMatrix::MakeFromZ(Axis).Rotator());
    for (int32 I = 0; I < 2; ++I)
    {
        UProceduralMeshComponent* Jaw = I == 0 ? JawLeft.Get() : JawRight.Get();
        FTransform Pose;
        if (bAuthoritative && Bridge->GetJawPose(I, Pose)) Jaw->SetWorldTransform(Pose);
        else
        {
            const double Sign = I == 0 ? -1.0 : 1.0;
            const double Angle = FMath::DegreesToRadians(FMath::Lerp(2.0, 40.0, static_cast<double>(JawOpenBlend)));
            const FVector Forward = -Axis * FMath::Cos(Angle) + Side * (Sign * FMath::Sin(Angle));
            const FVector Hinge = Joint + Side * (Sign * 0.0825);
            Jaw->SetWorldLocation(Hinge + Forward * 0.725);
            Jaw->SetWorldRotation(FRotationMatrix::MakeFromXY(Forward, Width).Rotator());
        }
    }
    ToolMarker->SetWorldLocation(RenderedTip);
}

void ATrainingScene::UpdateCamera()
{
    FVector Target(0, 0, 0.8);
    FVector Position = ViewMode == 1 ? FVector(0, -0.1, 34.0) :
        ViewMode == 2 ? FVector(18, -27, 8) : FVector(15, -24, 28);
    if (ViewMode == 3)
    {
        const FVector Axis = (FVector(12, -14, 15) - RenderedTip).GetSafeNormal();
        FVector Side = FVector::CrossProduct(Axis, FVector::UpVector).GetSafeNormal();
        if (Side.IsNearlyZero()) Side = FVector::RightVector;
        Target = RenderedTip + Axis * 0.75;
        Position = Target + (Side * 3.4 + FVector::UpVector * 4.5 - Axis * 0.8).GetSafeNormal() * 7.8;
    }
    Camera->SetWorldLocation(Position);
    Camera->SetWorldRotation((Target - Position).Rotation());
    Camera->SetFieldOfView(ViewMode == 3 ? 42.0f : bOverview ? 49.0f : 47.0f);
    if (EndoscopeLight) EndoscopeLight->SetIntensity(ViewMode == 3 ? 0.006f : 0.30f);
}

void ATrainingScene::ResetExercise()
{
    ToolTip = FVector(0, 0, 2.2);
    ToolRoll = 0.0f;
    ActivePreset = 1;
    bJawClosed = false;
    bResetRequested = true;
    SimulationElapsed = 0.0f;
    DemoElapsed = 0.0f;
    DemoPhase = -1;
    DemoCaptureMask = 0;
    ++ResetCount;
    UE_LOG(LogTemp, Display, TEXT("LAP_RESET requested, count=%d"), ResetCount);
}

void ATrainingScene::SelectPreset(int32 Preset)
{
    ResetExercise();
    ActivePreset = Preset;
    if (Preset == 2)
    {
        ToolTip = FVector(0, -4.6, 0.6);
        ToolRoll = 90.0f;
    }
    else
    {
        ToolTip = FVector(0, -1.5, 2.5);
        ToolRoll = 0.0f;
    }
    UE_LOG(LogTemp, Display, TEXT("LAP_PRESET id=%d tip_cm=%s roll_deg=%.1f"), Preset, *ToolTip.ToString(), ToolRoll);
}

void ATrainingScene::ApplyWorkspaceLimits()
{
    const FVector Requested = ToolTip;
    const FVector Pivot(12, -14, 15);
    const FVector Reference = (FVector(0, 0, 1.2) - Pivot).GetSafeNormal();
    ToolTip.X = FMath::Clamp(ToolTip.X, -9.0, 9.0);
    ToolTip.Y = FMath::Clamp(ToolTip.Y, -7.0, 6.5);
    ToolTip.Z = FMath::Clamp(ToolTip.Z, -0.5, 9.0);
    FVector Ray = ToolTip - Pivot;
    const double Length = FMath::Clamp(Ray.Size(), 12.0, 30.0);
    Ray = Ray.GetSafeNormal(UE_SMALL_NUMBER, Reference);
    const double CosLimit = FMath::Cos(FMath::DegreesToRadians(32.0));
    const double Dot = FVector::DotProduct(Ray, Reference);
    if (Dot < CosLimit)
    {
        const FVector Tangent = (Ray - Reference * Dot).GetSafeNormal(UE_SMALL_NUMBER, FVector::RightVector);
        Ray = Reference * CosLimit + Tangent * FMath::Sin(FMath::DegreesToRadians(32.0));
    }
    ToolTip = Pivot + Ray * Length;
    ToolRoll = FMath::UnwindDegrees(ToolRoll);
    bMotionLimited = !ToolTip.Equals(Requested, 0.0001);
}

void ATrainingScene::UpdateInput(float DeltaSeconds)
{
    APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
    if (!PC) return;
    if (PC->WasInputKeyJustPressed(EKeys::Escape))
    {
        bMouseReleased = true;
        bJawClosed = false;
        PC->bShowMouseCursor = true;
        FInputModeGameAndUI Mode;
        Mode.SetHideCursorDuringCapture(false);
        PC->SetInputMode(Mode);
    }
    if (PC->WasInputKeyJustPressed(EKeys::RightMouseButton) && bMouseReleased)
    {
        bMouseReleased = false;
        PC->bShowMouseCursor = false;
        PC->SetInputMode(FInputModeGameOnly());
    }
    if (PC->WasInputKeyJustPressed(EKeys::F10))
    {
        UKismetSystemLibrary::QuitGame(this, PC, EQuitPreference::Quit, false);
    }
    if (PC->WasInputKeyJustPressed(EKeys::H)) bShowHelp = !bShowHelp;
    if (PC->WasInputKeyJustPressed(EKeys::Tab)) { ViewMode = (ViewMode + 1) % 4; bOverview = ViewMode == 1; UpdateCamera(); }
    if (PC->WasInputKeyJustPressed(EKeys::R)) ResetExercise();
    if (PC->WasInputKeyJustPressed(EKeys::One)) SelectPreset(1);
    if (PC->WasInputKeyJustPressed(EKeys::Two)) SelectPreset(2);
    if (bAutoDemo)
    {
        if (!IsPhysicsConnected()) return;
        DemoElapsed += DeltaSeconds;
        const int32 Phase = DemoElapsed < 2.0f ? 0 : DemoElapsed < 4.0f ? 1 :
            DemoElapsed < 6.0f ? 2 : DemoElapsed < 11.0f ? 3 : DemoElapsed < 14.0f ? 4 :
            DemoElapsed < 17.0f ? 5 : 6;
        if (Phase != DemoPhase)
        {
            DemoPhase = Phase;
            UE_LOG(LogTemp, Display, TEXT("LAP_AUTODEMO phase=%d grasp=%d force_N=%.4f tip_cm=%s"),
                Phase, IsGraspActive(), GetForceNewton(), *ToolTip.ToString());
            if (Phase == 6)
            {
                bResetRequested = true;
                SimulationElapsed = 0.0f;
                ++ResetCount;
            }
        }
        bJawClosed = Phase == 2 || Phase == 3;
        if (Phase == 0) ToolTip = FVector(0, 0, 2.2);
        else if (Phase == 1) ToolTip = FMath::Lerp(FVector(0, 0, 2.2), FVector(0, 0, 1.2), (DemoElapsed - 2.0f) / 2.0f);
        else if (Phase == 2) ToolTip = FVector(0, 0, 1.2);
        else if (Phase == 3) ToolTip = FMath::Lerp(FVector(0, 0, 1.2), FVector(1, 0, 3.0), (DemoElapsed - 6.0f) / 5.0f);
        else if (Phase == 4) ToolTip = FMath::Lerp(FVector(1, 0, 3.0), FVector(0, 0, 4.0), (DemoElapsed - 11.0f) / 3.0f);
        else ToolTip = Phase == 6 ? FVector(0, 0, 2.2) : FVector(0, 0, 4.0);
        const float CaptureTimes[] = { 1.5f, 5.5f, 10.5f, 15.5f, 18.5f };
        const TCHAR* CaptureNames[] = { TEXT("01_initial.png"), TEXT("02_grasp.png"), TEXT("03_traction.png"),
            TEXT("04_release.png"), TEXT("05_reset.png") };
        for (uint32 I = 0; I < 5; ++I)
        {
            if (DemoElapsed >= CaptureTimes[I] && !(DemoCaptureMask & (1u << I)))
            {
                DemoCaptureMask |= (1u << I);
                const FString Path = FPaths::Combine(CaptureDirectory, CaptureNames[I]);
                FScreenshotRequest::RequestScreenshot(Path, true, false);
                UE_LOG(LogTemp, Display, TEXT("LAP_AUTODEMO screenshot=%s grasp=%d force_N=%.4f"),
                    *Path, IsGraspActive(), GetForceNewton());
            }
        }
        if (DemoElapsed > 20.0f && bAutoExit)
        {
            UE_LOG(LogTemp, Display, TEXT("LAP_AUTODEMO complete. Requesting exit."));
            FPlatformMisc::RequestExit(false);
        }
        return;
    }
    if (bMouseReleased) return;
    const float Speed = PC->IsInputKeyDown(EKeys::LeftControl) ? 0.65f : PC->IsInputKeyDown(EKeys::LeftShift) ? 5.0f : 2.5f;
    FVector Right = Camera->GetRightVector();
    Right.Z = 0;
    Right.Normalize();
    const FVector Up = FVector::CrossProduct(FVector::UpVector, Right).GetSafeNormal();
    if (PC->IsInputKeyDown(EKeys::RightMouseButton))
    {
        float MX, MY;
        PC->GetInputMouseDelta(MX, MY);
        ToolTip += (Right * FMath::Clamp(MX, -60.0f, 60.0f) + Up * FMath::Clamp(MY, -60.0f, 60.0f)) * 0.025f;
    }
    if (PC->IsInputKeyDown(EKeys::Left)) ToolTip -= Right * Speed * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::Right)) ToolTip += Right * Speed * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::Up)) ToolTip += Up * Speed * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::Down)) ToolTip -= Up * Speed * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::W)) ToolTip.Z += Speed * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::S)) ToolTip.Z -= Speed * DeltaSeconds;
    const FVector ToolAxis = (FVector(12, -14, 15) - ToolTip).GetSafeNormal();
    if (PC->IsInputKeyDown(EKeys::T)) ToolTip -= ToolAxis * Speed * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::G)) ToolTip += ToolAxis * Speed * DeltaSeconds;
    if (PC->WasInputKeyJustPressed(EKeys::MouseScrollUp)) ToolTip.Z += 0.18f;
    if (PC->WasInputKeyJustPressed(EKeys::MouseScrollDown)) ToolTip.Z -= 0.18f;
    if (PC->IsInputKeyDown(EKeys::Q)) ToolRoll -= 80.0f * DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::E)) ToolRoll += 80.0f * DeltaSeconds;
    bJawClosed = PC->IsInputKeyDown(EKeys::SpaceBar);
}

void ATrainingScene::UpdateKeyTest(float DeltaSeconds)
{
    if (!bKeyTest || bKeyTestFinished) return;
    KeyTestWaitElapsed += DeltaSeconds;
    APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
    if (!PC || !IsPhysicsConnected())
    {
        if (KeyTestWaitElapsed > 15.0f) FinishKeyTest(TEXT("SOFA connection or PlayerController unavailable"));
        return;
    }
    KeyTestElapsed += DeltaSeconds;
    KeyTestMinHeight = FMath::Min(KeyTestMinHeight, static_cast<float>(ToolTip.Z));
    if (IsGraspActive())
    {
        bKeyTestCaptured = true;
        KeyTestMaxHeldHeight = FMath::Max(KeyTestMaxHeldHeight, static_cast<float>(ToolTip.Z));
        KeyTestPeakForce = FMath::Max(KeyTestPeakForce, GetForceNewton());
    }
    if (KeyTestElapsed > 5.0f && KeyTestElapsed < 6.0f && !IsGraspActive() && !bJawClosed)
        bKeyTestReleased = true;
    auto KeyEvent = [&](uint32 Index, float AtSeconds, const FKey& Key, EInputEvent Event)
    {
        if (KeyTestElapsed < AtSeconds || (KeyTestEventMask & (1u << Index))) return;
        KeyTestEventMask |= (1u << Index);
        const FInputKeyEventArgs Args(nullptr, FInputDeviceId::CreateFromInternalId(0), Key, Event,
            Event == IE_Released ? 0.0f : 1.0f, false, FPlatformTime::Cycles64());
        PC->InputKey(Args);
        UE_LOG(LogTemp, Display, TEXT("LAP_KEYTEST t=%.3f key=%s event=%s tip=%s grasp=%d force_N=%.5f"),
            KeyTestElapsed, *Key.ToString(), Event == IE_Released ? TEXT("release") : TEXT("press"),
            *ToolTip.ToString(), IsGraspActive(), GetForceNewton());
    };
    // Events are consumed by the regular PlayerController input tick, then UpdateInput polls them.
    // In particular, this test never writes ToolTip, bJawClosed, or the view mode directly.
    KeyEvent(0, 0.50f, EKeys::S, IE_Pressed);
    KeyEvent(1, 0.90f, EKeys::S, IE_Released);
    KeyEvent(2, 1.50f, EKeys::SpaceBar, IE_Pressed);
    KeyEvent(3, 2.50f, EKeys::W, IE_Pressed);
    KeyEvent(4, 3.30f, EKeys::W, IE_Released);
    KeyEvent(5, 4.50f, EKeys::SpaceBar, IE_Released);
    KeyEvent(6, 6.00f, EKeys::R, IE_Pressed);
    KeyEvent(7, 6.15f, EKeys::R, IE_Released);
    KeyEvent(8, 7.00f, EKeys::Tab, IE_Pressed);
    KeyEvent(9, 7.15f, EKeys::Tab, IE_Released);
    if (KeyTestElapsed > 8.0f && !(KeyTestEventMask & (1u << 10)))
    {
        KeyTestEventMask |= (1u << 10);
        FScreenshotRequest::RequestScreenshot(FPaths::Combine(CaptureDirectory, TEXT("06_key_input_overview.png")), true, false);
    }
    if (KeyTestElapsed > 9.0f) FinishKeyTest();
}

void ATrainingScene::UpdateVisualPreview(float DeltaSeconds)
{
    if (!bVisualPreview) return;
    PreviewElapsed += DeltaSeconds;
    if (PreviewElapsed > 8.0f && !(PreviewMask & 1u))
    {
        PreviewMask |= 1u;
        FScreenshotRequest::RequestScreenshot(FPaths::Combine(CaptureDirectory, TEXT("visual_01_scene.png")), true, false);
    }
    if (PreviewElapsed > 9.5f && !(PreviewMask & 2u))
    {
        PreviewMask |= 2u;
        ViewMode = 3;
        bOverview = false;
        bShowHelp = false;
        UpdateCamera();
    }
    if (PreviewElapsed > 10.5f && !(PreviewMask & 4u))
    {
        PreviewMask |= 4u;
        FScreenshotRequest::RequestScreenshot(FPaths::Combine(CaptureDirectory, TEXT("visual_02_jaw_detail.png")), true, false);
    }
    if (PreviewElapsed > 12.5f && bAutoExit)
    {
        UE_LOG(LogTemp, Display, TEXT("LAP_VISUAL_PREVIEW complete; geometry/material preview only."));
        FPlatformMisc::RequestExit(false);
    }
}

void ATrainingScene::SetPhase2Key(const FKey& Key, bool bDown)
{
    const FName Name = Key.GetFName();
    if (Phase2HeldKeys.Contains(Name) == bDown) return;
    APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
    if (!PC) return;
    if (bDown) Phase2HeldKeys.Add(Name); else Phase2HeldKeys.Remove(Name);
    PC->InputKey(FInputKeyEventArgs(nullptr, FInputDeviceId::CreateFromInternalId(0), Key,
        bDown ? IE_Pressed : IE_Released, bDown ? 1.0f : 0.0f, false, FPlatformTime::Cycles64()));
    UE_LOG(LogTemp, Display, TEXT("LAP_PHASE2_KEY stage=%d key=%s down=%d command=%s actual=%s"),
        Phase2Stage, *Key.ToString(), bDown, *ToolTip.ToString(), *RenderedTip.ToString());
}

void ATrainingScene::StopPhase2Motion()
{
    for (const FKey& Key : { EKeys::W, EKeys::S, EKeys::Up, EKeys::Down, EKeys::Left, EKeys::Right,
        EKeys::T, EKeys::G, EKeys::LeftControl, EKeys::LeftShift, EKeys::Q, EKeys::E }) SetPhase2Key(Key, false);
}

bool ATrainingScene::DrivePhase2To(const FVector& Target)
{
    const FVector Error = Target - ToolTip;
    FVector Right = Camera->GetRightVector(); Right.Z = 0; Right.Normalize();
    const FVector Up = FVector::CrossProduct(FVector::UpVector, Right).GetSafeNormal();
    const double X = FVector::DotProduct(Error, Right), Y = FVector::DotProduct(Error, Up);
    constexpr double Tolerance = 0.014;
    SetPhase2Key(EKeys::LeftControl, true);
    SetPhase2Key(EKeys::Right, X > Tolerance);
    SetPhase2Key(EKeys::Left, X < -Tolerance);
    SetPhase2Key(EKeys::Up, Y > Tolerance);
    SetPhase2Key(EKeys::Down, Y < -Tolerance);
    SetPhase2Key(EKeys::W, Error.Z > Tolerance);
    SetPhase2Key(EKeys::S, Error.Z < -Tolerance);
    return Error.Size() < 0.045 && FVector::Distance(RenderedTip, Target) < 0.12;
}

void ATrainingScene::AdvancePhase2(int32 Stage)
{
    StopPhase2Motion();
    Phase2Stage = Stage;
    Phase2StageTime = 0.0f;
    Phase2StageMask = 0;
    Phase2Dwell = 0.0f;
    Phase2ContinuousHold = 0.0f;
    Phase2HoldFrames = 0;
    UE_LOG(LogTemp, Display, TEXT("LAP_PHASE2_STAGE stage=%d contact=%d grip=%d state=%s force=%.5f tip=%s"),
        Stage, GetContactCount(), IsGraspActive(), *GetGripState(), GetForceNewton(), *RenderedTip.ToString());
}

bool ATrainingScene::Phase2TimedOut(float TimeoutSeconds, const TCHAR* Action)
{
    if (Phase2StageTime <= TimeoutSeconds) return false;
    const FString Reason = FString::Printf(TEXT("Stage %d timed out: %s"), Phase2Stage, Action);
    Phase2Failures.AddUnique(Reason);
    UE_LOG(LogTemp, Error, TEXT("LAP_PHASE2_ASSERT %s"), *Reason);
    return true;
}

void ATrainingScene::CapturePhase2(const TCHAR* Filename)
{
    const FString Path = FPaths::Combine(CaptureDirectory, Filename);
    FScreenshotRequest::RequestScreenshot(Path, true, false);
    UE_LOG(LogTemp, Display, TEXT("LAP_PHASE2_CAPTURE stage=%d path=%s"), Phase2Stage, *Path);
}

void ATrainingScene::UpdatePhase2Test(float DeltaSeconds)
{
    if (!bPhase2Test || bPhase2Finished) return;
    Phase2WaitTime += DeltaSeconds;
    if (Bridge && Bridge->GetUnhealthyStateCount() > 0)
        Phase2Failures.AddUnique(TEXT("SOFA reported an unhealthy state during this session"));
    if (Bridge && Bridge->GetRejectedStateCount() > 0)
        Phase2Failures.AddUnique(TEXT("Bridge rejected one or more malformed physics states"));
    if (!IsPhysicsConnected())
    {
        if (bPhase2Started) Phase2Failures.AddUnique(TEXT("Physics connection became unavailable or stale after test start"));
        if (Phase2WaitTime > 35.0f) FinishPhase2Test(TEXT("SOFA connection unavailable during test"));
        return;
    }
    bPhase2Started = true;
    if (!Bridge->IsHealthy()) Phase2Failures.AddUnique(TEXT("SOFA health check failed"));
    if (Phase2WaitTime > 210.0f) { FinishPhase2Test(TEXT("Phase 2 acceptance sequence timed out")); return; }
    Phase2StageTime += DeltaSeconds;
    const uint64 ObservedFrame = Bridge->GetFrameNumber();
    const bool bNewPhysicsFrame = ObservedFrame != Phase2LastObservedFrame;
    Phase2LastObservedFrame = ObservedFrame;
    Phase2PeakContactN = FMath::Max(Phase2PeakContactN, GetContactForceNewton());
    Phase2PeakGripN = FMath::Max(Phase2PeakGripN, GetForceNewton());
    Phase2MaxPenetrationMm = FMath::Max(Phase2MaxPenetrationMm, GetPenetrationMm());
    Phase2MaxSlipMm = FMath::Max(Phase2MaxSlipMm, GetSlipDistanceMm());
    if (Phase2Stage == 2 && GetContactCount() > 0 && GetContactForceNewton() > 0.005f) bPhase2Contact = true;
    if (Phase2Stage == 3 && bPhase2Contact && GetContactCount() == 0) bPhase2ContactReleased = true;
    if ((Phase2Stage >= 6 && Phase2Stage <= 8) || Phase2Stage == 12)
    {
        bPhase2Grasp |= IsGraspActive();
        if (Phase2Stage == 8 && !IsGraspActive())
            bPhase2Slip |= IsSlipping() || GetSlipDistanceMm() > 0.05f;
        if (Bridge) Phase2MaxTissueMm = FMath::Max(Phase2MaxTissueMm, Bridge->GetMaxDisplacementCm() * 10.0f);
    }
    if (Phase2Stage == 9 && !IsGraspActive() && JawOpenBlend > 0.9f) bPhase2Released = true;
    if (Phase2Stage == 10 && bMotionLimited) bPhase2Limit = true;

    switch (Phase2Stage)
    {
    case 0:
        SetPhase2Key(EKeys::One, Phase2StageTime < 0.15f);
        bPhase2Preset1 = ResetCount >= 1 && ActivePreset == 1 && Bridge->HasAcknowledgedReset() &&
            FVector::Distance(RenderedTip, FVector(0, -1.5, 2.5)) < 0.12 && FMath::Abs(GetRollDeg()) < 2.0f;
        if ((Phase2StageTime > 0.65f && bPhase2Preset1) || Phase2TimedOut(8.0f, TEXT("preset 1 acknowledged and actual pose reached")))
            AdvancePhase2(1);
        break;
    case 1:
        SetPhase2Key(EKeys::E, Phase2StageTime < 0.15f);
        if (Phase2StageTime > 0.15f && Phase2StageTime < 0.60f) bPhase2Roll |= GetRollDeg() > 5.0f;
        SetPhase2Key(EKeys::Q, Phase2StageTime > 0.60f && ToolRoll > 0.15f);
        if (Phase2StageTime > 0.8f && bPhase2Roll && FMath::Abs(ToolRoll) < 2.0f && FMath::Abs(GetRollDeg()) < 2.0f)
            Phase2Dwell += DeltaSeconds;
        else Phase2Dwell = 0.0f;
        bPhase2RollReturned |= Phase2Dwell >= 0.25f;
        if (bPhase2RollReturned || Phase2TimedOut(5.0f, TEXT("E rotation and Q return to actual zero roll"))) AdvancePhase2(2);
        break;
    case 2:
        if (!bPhase2Contact) DrivePhase2To(FVector(0, -1.5, 0.70));
        else { StopPhase2Motion(); Phase2Dwell += DeltaSeconds; }
        if (Phase2Dwell > 0.8f || Phase2TimedOut(15.0f, TEXT("surface contact and positive load")))
        { CapturePhase2(TEXT("phase2_01_surface_contact.png")); AdvancePhase2(3); }
        break;
    case 3:
        if (DrivePhase2To(FVector(0, -1.5, 2.8)) && bPhase2ContactReleased) Phase2Dwell += DeltaSeconds;
        else Phase2Dwell = 0.0f;
        if (Phase2Dwell > 0.5f || Phase2TimedOut(15.0f, TEXT("surface withdrawal and zero contact"))) AdvancePhase2(4);
        break;
    case 4:
        SetPhase2Key(EKeys::Two, Phase2StageTime < 0.15f);
        if ((Phase2StageTime > 1.1f && FVector::Distance(RenderedTip, FVector(0, -4.6, 0.6)) < 0.12 &&
            FMath::Abs(GetRollDeg() - 90.0f) < 3.0f && Bridge->HasAcknowledgedReset()) ||
            Phase2TimedOut(10.0f, TEXT("preset 2 acknowledged at actual edge approach pose")))
        {
            bPhase2Preset2 = ResetCount >= 2 && ActivePreset == 2 && FMath::Abs(GetRollDeg() - 90.0f) < 3.0f &&
                FVector::Distance(RenderedTip, FVector(0, -4.6, 0.6)) < 0.12 && Bridge->HasAcknowledgedReset();
            CapturePhase2(TEXT("phase2_02_edge_approach.png"));
            AdvancePhase2(5);
        }
        break;
    case 5:
        if (DrivePhase2To(FVector(0, -3.7, 0.6))) Phase2Dwell += DeltaSeconds;
        else Phase2Dwell = 0.0f;
        if (Phase2Dwell > 1.0f || Phase2TimedOut(18.0f, TEXT("actual open jaws inserted at tissue front edge"))) AdvancePhase2(6);
        break;
    case 6:
        SetPhase2Key(EKeys::SpaceBar, true);
        if (IsGraspActive()) Phase2Dwell += DeltaSeconds;
        else Phase2Dwell = 0.0f;
        if (Phase2Dwell > 0.8f || Phase2TimedOut(12.0f, TEXT("continuous bilateral contact grasp")))
        {
            CapturePhase2(bPhase2RepeatGrasp ? TEXT("phase2_03b_regrasp.png") : TEXT("phase2_03_contact_grasp.png"));
            if (bPhase2RepeatGrasp) AdvancePhase2(7);
            else
            {
                bPhase2ReleaseStartedHolding = IsGraspActive() && bJawClosed;
                if (!bPhase2ReleaseStartedHolding) Phase2Failures.AddUnique(TEXT("Explicit Space-release subtest did not start while holding tissue"));
                AdvancePhase2(12);
            }
        }
        break;
    case 7:
    {
        const bool bAtLift = DrivePhase2To(FVector(0.3, -3.8, 1.4));
        if (bAtLift && RenderedTip.Z >= 1.32 && IsGraspActive() && Bridge->GetMaxDisplacementCm() * 10.0f > 0.5f)
        {
            Phase2ContinuousHold += DeltaSeconds;
            if (bNewPhysicsFrame) ++Phase2HoldFrames;
            Phase2LongestHold = FMath::Max(Phase2LongestHold, Phase2ContinuousHold);
        }
        else { Phase2ContinuousHold = 0.0f; Phase2HoldFrames = 0; }
        bPhase2TractionHeld |= Phase2ContinuousHold >= 0.35f && Phase2HoldFrames >= 8;
        if ((bAtLift && bPhase2TractionHeld && Phase2ContinuousHold >= 0.5f) ||
            Phase2TimedOut(20.0f, TEXT("actual lift with continuous holding for at least 0.35 seconds")))
        { CapturePhase2(TEXT("phase2_04_traction.png")); AdvancePhase2(8); }
        break;
    }
    case 8:
        if (DrivePhase2To(FVector(0.5, -4.0, 2.2))) Phase2Dwell += DeltaSeconds;
        else Phase2Dwell = 0.0f;
        if ((Phase2Dwell > 1.8f && bPhase2Slip && !IsGraspActive()) || Phase2TimedOut(20.0f, TEXT("larger traction causes frictional slip and release")))
        { CapturePhase2(TEXT("phase2_05_frictional_slip.png")); AdvancePhase2(9); }
        break;
    case 9:
        SetPhase2Key(EKeys::SpaceBar, false);
        if ((Phase2StageTime > 2.6f && bPhase2Released) || Phase2TimedOut(10.0f, TEXT("jaws reopen after frictional slip")))
        { CapturePhase2(TEXT("phase2_06_release.png")); AdvancePhase2(10); }
        break;
    case 10:
        SetPhase2Key(EKeys::LeftShift, true);
        SetPhase2Key(EKeys::G, true);
        if ((bPhase2Limit && Phase2StageTime > 0.5f) || Phase2TimedOut(5.0f, TEXT("normal insertion input reaches RCM travel limit")))
        { CapturePhase2(TEXT("phase2_07_rcm_limit.png")); AdvancePhase2(11); }
        break;
    case 11:
        SetPhase2Key(EKeys::R, Phase2StageTime < 0.15f);
        // Three real Tab presses switch from the endoscope to the detailed jaw view.
        SetPhase2Key(EKeys::Tab, (Phase2StageTime > 0.7f && Phase2StageTime < 0.85f) ||
            (Phase2StageTime > 1.0f && Phase2StageTime < 1.15f) ||
            (Phase2StageTime > 1.3f && Phase2StageTime < 1.45f));
        if (Phase2StageTime > 2.2f && !(Phase2StageMask & 1u))
        { Phase2StageMask |= 1u; CapturePhase2(TEXT("phase2_08_jaw_detail.png")); }
        if (Phase2StageTime > 3.0f && Bridge->HasAcknowledgedReset() &&
            FVector::Distance(RenderedTip, FVector(0, 0, 2.2)) < 0.06 && Bridge->GetMaxDisplacementCm() * 10.0f < 0.2f)
            FinishPhase2Test();
        else if (Phase2TimedOut(12.0f, TEXT("R reset acknowledged, actual tool home and tissue recovery below 0.2 mm"))) FinishPhase2Test();
        break;
    case 12:
        // Entered while the first grasp is still active: this proves release caused by opening,
        // independently of the later traction/slip release scenario.
        SetPhase2Key(EKeys::SpaceBar, false);
        if (bPhase2ReleaseStartedHolding && !bJawClosed && !IsGraspActive() && JawOpenBlend > 0.9f && bNewPhysicsFrame)
            bPhase2ReleasedByOpening = true;
        if ((Phase2StageTime > 2.6f && bPhase2ReleasedByOpening) ||
            Phase2TimedOut(10.0f, TEXT("Space release opens previously holding jaws and releases tissue")))
        { CapturePhase2(TEXT("phase2_03a_space_release.png")); AdvancePhase2(13); }
        break;
    case 13:
        SetPhase2Key(EKeys::Two, Phase2StageTime < 0.15f);
        if ((Phase2StageTime > 1.1f && ResetCount >= 3 && Bridge->HasAcknowledgedReset() &&
            FVector::Distance(RenderedTip, FVector(0, -4.6, 0.6)) < 0.12 && FMath::Abs(GetRollDeg() - 90.0f) < 3.0f) ||
            Phase2TimedOut(10.0f, TEXT("second preset 2 reset before independent traction scenario")))
        { bPhase2RepeatGrasp = true; AdvancePhase2(5); }
        break;
    default: FinishPhase2Test(TEXT("Invalid acceptance stage")); break;
    }
}

void ATrainingScene::FinishPhase2Test(const FString& Failure)
{
    if (bPhase2Finished) return;
    bPhase2Finished = true;
    const TArray<FName> Held = Phase2HeldKeys.Array();
    for (const FName& Name : Held) SetPhase2Key(FKey(Name), false);
    double EnvelopeExcessMm = 0.0;
    int32 JawVertexCount = 0;
    for (UProceduralMeshComponent* Jaw : { JawLeft.Get(), JawRight.Get() })
    {
        if (!Jaw) continue;
        if (const FProcMeshSection* Section = Jaw->GetProcMeshSection(0))
            for (const FProcMeshVertex& Vertex : Section->ProcVertexBuffer)
            {
                ++JawVertexCount;
                const FVector V = FVector(Vertex.Position).GetAbs() - FVector(0.725, 0.125, 0.070);
                EnvelopeExcessMm = FMath::Max(EnvelopeExcessMm, FMath::Max(0.0, V.GetMax()) * 10.0);
            }
    }
    const bool bGeometry = JawVertexCount > 3000 && EnvelopeExcessMm < 0.001;
    const bool bRenderBound = !TissueRenderBindings.IsEmpty() && LastPhysicsFrame != MAX_uint64 && Phase2MaxRenderOffsetMm <= 0.1001f;
    const bool bReset = Bridge && Bridge->HasAcknowledgedReset() && ResetCount >= 4 && !IsGraspActive() &&
        ToolTip.Equals(FVector(0, 0, 2.2), 0.06) && RenderedTip.Equals(FVector(0, 0, 2.2), 0.06) &&
        Bridge->GetMaxDisplacementCm() * 10.0f < 0.2f;
    const bool bHealthy = Bridge && Bridge->IsHealthy() && Bridge->GetUnhealthyStateCount() == 0 && Bridge->GetRejectedStateCount() == 0;
    const bool bPenetration = Phase2MaxPenetrationMm < 1.0f;
    if (!Failure.IsEmpty()) Phase2Failures.AddUnique(Failure);
    TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    Report->SetNumberField(TEXT("phase"), 2);
    Report->SetNumberField(TEXT("report_version"), 2);
    Report->SetStringField(TEXT("input_path"), TEXT("PlayerController InputKey -> regular UpdateInput; closed-loop Ctrl/arrow/W/S key control, no direct test writes to ToolTip"));
    Report->SetStringField(TEXT("scope"), TEXT("Software input, SOFA jaw contact/friction, mesh binding and presentation regression; not clinical validation or full-shaft collision validation"));
    auto Check = [&](const TCHAR* Name, bool bOK, const TCHAR* Reason)
    {
        Report->SetBoolField(Name, bOK);
        if (!bOK) Phase2Failures.AddUnique(Reason);
    };
    Check(TEXT("physics_connected"), IsPhysicsConnected(), TEXT("Physics is disconnected at test completion"));
    Check(TEXT("healthy_without_rejected_states"), bHealthy, TEXT("Physics health or protocol validation failed"));
    Check(TEXT("surface_contact_detected"), bPhase2Contact, TEXT("Surface contact with positive load was not observed"));
    Check(TEXT("surface_contact_released"), bPhase2ContactReleased, TEXT("Surface contact did not clear after withdrawal"));
    Check(TEXT("bilateral_grasp_observed"), bPhase2Grasp, TEXT("Bilateral grasp was not observed"));
    Check(TEXT("traction_held_at_lift"), bPhase2TractionHeld, TEXT("Actual raised tool did not continuously hold tissue for at least 0.35 seconds and eight physics states"));
    Check(TEXT("frictional_slip_observed"), bPhase2Slip, TEXT("Larger traction did not cause observed frictional slip and loss of grasp"));
    Check(TEXT("opening_confirmed_ungrasped"), bPhase2Released, TEXT("Final opening after slip was not confirmed"));
    Check(TEXT("space_opening_released_held_tissue"), bPhase2ReleaseStartedHolding && bPhase2ReleasedByOpening,
        TEXT("Opening jaws with Space release did not transition from a confirmed holding state to release"));
    Check(TEXT("q_e_roll_input"), bPhase2Roll && bPhase2RollReturned, TEXT("E rotation and Q return to actual zero roll were not both observed"));
    Check(TEXT("preset_1_key"), bPhase2Preset1, TEXT("Preset 1 key did not reach its acknowledged actual pose"));
    Check(TEXT("preset_2_key_and_90deg_roll"), bPhase2Preset2, TEXT("Preset 2 key did not reach its acknowledged edge pose and roll"));
    Check(TEXT("rcm_travel_limit"), bPhase2Limit, TEXT("Normal input did not reach an RCM travel limit"));
    Check(TEXT("r_key_reset"), bReset, TEXT("R reset was not acknowledged at actual home pose with tissue displacement below 0.2 mm"));
    Check(TEXT("tab_detail_view"), ViewMode == 3, TEXT("Three Tab inputs did not select jaw detail view"));
    Check(TEXT("jaw_geometry_inside_collision_envelope"), bGeometry, TEXT("Detailed jaw geometry exceeds its collision envelope or is missing"));
    Check(TEXT("render_surface_within_0_1mm"), bRenderBound, TEXT("Rendered tissue is missing or exceeds its 0.1 mm physical surface offset bound"));
    Check(TEXT("sampled_penetration_under_1mm"), bPenetration, TEXT("Normal interaction sampled residual penetration reached or exceeded 1.0 mm"));
    Check(TEXT("positive_contact_load_and_tissue_motion"), Phase2PeakGripN > 0.01f && Phase2MaxTissueMm > 0.5f,
        TEXT("Contact load or physical tissue displacement remained below the required minimum"));
    Report->SetNumberField(TEXT("peak_contact_force_n"), Phase2PeakContactN);
    Report->SetNumberField(TEXT("peak_grip_force_n"), Phase2PeakGripN);
    Report->SetNumberField(TEXT("max_reported_penetration_mm"), Phase2MaxPenetrationMm);
    Report->SetNumberField(TEXT("max_slip_distance_mm"), Phase2MaxSlipMm);
    Report->SetNumberField(TEXT("max_tissue_displacement_mm"), Phase2MaxTissueMm);
    Report->SetNumberField(TEXT("max_render_surface_offset_mm"), Phase2MaxRenderOffsetMm);
    Report->SetNumberField(TEXT("longest_continuous_hold_at_lift_s"), Phase2LongestHold);
    Report->SetNumberField(TEXT("penetration_limit_mm"), 1.0);
    Report->SetNumberField(TEXT("unhealthy_state_count"), Bridge ? Bridge->GetUnhealthyStateCount() : 0);
    Report->SetNumberField(TEXT("rejected_state_count"), Bridge ? Bridge->GetRejectedStateCount() : 0);
    Report->SetNumberField(TEXT("reset_final_displacement_mm"), Bridge ? Bridge->GetMaxDisplacementCm() * 10.0f : -1.0f);
    Report->SetNumberField(TEXT("jaw_vertex_count"), JawVertexCount);
    Report->SetNumberField(TEXT("jaw_envelope_excess_mm"), EnvelopeExcessMm);
    Report->SetNumberField(TEXT("physics_nodes"), GetPhysicsNodeCount());
    Report->SetNumberField(TEXT("render_vertices"), GetVertexCount());
    TArray<TSharedPtr<FJsonValue>> Failures;
    for (const FString& Reason : Phase2Failures) Failures.Add(MakeShared<FJsonValueString>(Reason));
    Report->SetArrayField(TEXT("failures"), Failures);
    Report->SetStringField(TEXT("failure"), FString::Join(Phase2Failures, TEXT("; ")));
    const bool bPassed = Phase2Failures.IsEmpty();
    Report->SetBoolField(TEXT("passed"), bPassed);
    FString Json;
    const auto Writer = TJsonWriterFactory<>::Create(&Json);
    FJsonSerializer::Serialize(Report, Writer);
    const FString Path = FPaths::Combine(CaptureDirectory, TEXT("phase2-input-test.json"));
    const bool bSaved = FFileHelper::SaveStringToFile(Json, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    UE_LOG(LogTemp, Display, TEXT("LAP_PHASE2_TEST complete passed=%d saved=%d path=%s"), bPassed, bSaved, *Path);
    if (bAutoExit) FPlatformMisc::RequestExit(false);
}

void ATrainingScene::FinishKeyTest(const FString& Failure)
{
    if (bKeyTestFinished) return;
    bKeyTestFinished = true;
    const bool bLowered = KeyTestMinHeight < 1.5f;
    const bool bRaised = KeyTestMaxHeldHeight > 2.5f;
    const bool bForce = KeyTestPeakForce > 0.01f;
    const bool bReset = ResetCount >= 1 && ToolTip.Equals(FVector(0, 0, 2.2), 0.05) && !IsGraspActive();
    const bool bView = ViewMode == 1;
    const bool bPassed = Failure.IsEmpty() && IsPhysicsConnected() && bLowered && bKeyTestCaptured &&
        bRaised && bForce && bKeyTestReleased && bReset && bView;
    TSharedRef<FJsonObject> Report = MakeShared<FJsonObject>();
    Report->SetBoolField(TEXT("passed"), bPassed);
    Report->SetStringField(TEXT("method"), TEXT("PlayerController InputKey events consumed by normal UpdateInput; no direct tip-position writes"));
    Report->SetStringField(TEXT("scope"), TEXT("UE keyboard polling and SOFA integration regression; does not test physical mouse hardware or clinical validity"));
    Report->SetStringField(TEXT("failure"), Failure);
    Report->SetBoolField(TEXT("physics_connected"), IsPhysicsConnected());
    Report->SetBoolField(TEXT("s_key_lowered_tip"), bLowered);
    Report->SetBoolField(TEXT("space_key_captured_tissue"), bKeyTestCaptured);
    Report->SetBoolField(TEXT("w_key_raised_held_tissue"), bRaised);
    Report->SetBoolField(TEXT("traction_generated_force"), bForce);
    Report->SetBoolField(TEXT("space_release_released_tissue"), bKeyTestReleased);
    Report->SetBoolField(TEXT("r_key_reset"), bReset);
    Report->SetBoolField(TEXT("tab_key_changed_view"), bView);
    Report->SetNumberField(TEXT("min_tip_height_cm"), KeyTestMinHeight);
    Report->SetNumberField(TEXT("max_held_tip_height_cm"), KeyTestMaxHeldHeight);
    Report->SetNumberField(TEXT("peak_force_n"), KeyTestPeakForce);
    Report->SetNumberField(TEXT("reset_count"), ResetCount);
    Report->SetNumberField(TEXT("view_mode"), ViewMode);
    FString Json;
    const auto Writer = TJsonWriterFactory<>::Create(&Json);
    FJsonSerializer::Serialize(Report, Writer);
    const FString Path = FPaths::Combine(CaptureDirectory, TEXT("key-input-test.json"));
    const bool bSaved = FFileHelper::SaveStringToFile(Json, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    UE_LOG(LogTemp, Display, TEXT("LAP_KEYTEST complete passed=%d saved=%d path=%s"), bPassed, bSaved, *Path);
    if (bAutoExit) FPlatformMisc::RequestExit(false);
}

void ATrainingScene::UpdateTissueSurface()
{
    if (TissueVertices.Num() < 3 || TissueTriangles.Num() < 3) return;
    TissueNormals.Init(FVector::ZeroVector, TissueVertices.Num());
    for (int32 I = 0; I + 2 < TissueTriangles.Num(); I += 3)
    {
        const int32 A = TissueTriangles[I], B = TissueTriangles[I + 1], C = TissueTriangles[I + 2];
        if (!TissueVertices.IsValidIndex(A) || !TissueVertices.IsValidIndex(B) || !TissueVertices.IsValidIndex(C)) continue;
        const FVector N = FVector::CrossProduct(TissueVertices[B] - TissueVertices[A], TissueVertices[C] - TissueVertices[A]);
        TissueNormals[A] += N;
        TissueNormals[B] += N;
        TissueNormals[C] += N;
    }
    for (FVector& N : TissueNormals) N = N.GetSafeNormal(UE_SMALL_NUMBER, FVector::UpVector);
    const bool bRebuild = !bHasSurface || BoundNodeCount != TissueVertices.Num() || BoundFaceCount != TissueTriangles.Num();
    if (bRebuild)
    {
        BoundNodeCount = TissueVertices.Num();
        BoundFaceCount = TissueTriangles.Num();
        TrainingGeometry::BuildSurfaceBindings(TissueVertices, TissueTriangles, 3, TissueRenderBindings, TissueRenderData);
    }
    // PN interpolation removes coarse shading/facet artefacts while every sample stays bound to
    // the same SOFA face; displacement from that physical face is explicitly capped at 0.1 mm.
    TrainingGeometry::UpdateBoundSurface(TissueVertices, TissueNormals, TissueRenderBindings, TissueRenderData, 0.01);
    if (bPhase2Test)
        for (int32 I = 0; I < TissueRenderBindings.Num(); ++I)
        {
            const FTrainingSurfaceSample& S = TissueRenderBindings[I];
            const FVector Linear = TissueVertices[S.A] * S.Weight.X + TissueVertices[S.B] * S.Weight.Y + TissueVertices[S.C] * S.Weight.Z;
            Phase2MaxRenderOffsetMm = FMath::Max(Phase2MaxRenderOffsetMm,
                static_cast<float>(FVector::Distance(Linear, TissueRenderData.Positions[I]) * 10.0));
        }
    if (bRebuild)
    {
        TissueMesh->CreateMeshSection_LinearColor(0, TissueRenderData.Positions, TissueRenderData.Triangles,
            TissueRenderData.Normals, TissueRenderData.UV, TissueRenderData.Colors, TissueRenderData.Tangents, false);
        bHasSurface = true;
    }
    else
    {
        TissueMesh->UpdateMeshSection_LinearColor(0, TissueRenderData.Positions, TissueRenderData.Normals,
            TissueRenderData.UV, TissueRenderData.Colors, TissueRenderData.Tangents);
    }
}

void ATrainingScene::UpdateSimulation(float DeltaSeconds)
{
    if (bVisualPreview || !Bridge) return;
    Bridge->TickBridge(DeltaSeconds, ToolTip, bJawClosed, bResetRequested, ToolRoll);
    bResetRequested = false;
    if (!Bridge->IsConnected()) return;
    SimulationElapsed += DeltaSeconds;
    const uint64 Frame = Bridge->GetFrameNumber();
    if (Frame == LastPhysicsFrame) return;
    if (Bridge->GetSurface(TissueVertices, TissueTriangles))
    {
        LastPhysicsFrame = Frame;
        UpdateTissueSurface();
    }
}

void ATrainingScene::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (DeltaSeconds > 0.0001f) SmoothedFps = FMath::FInterpTo(SmoothedFps, 1.0f / DeltaSeconds, DeltaSeconds, 2.0f);
    UpdateKeyTest(DeltaSeconds);
    UpdatePhase2Test(DeltaSeconds);
    UpdateInput(DeltaSeconds);
    ApplyWorkspaceLimits();
    UpdateSimulation(DeltaSeconds);
    UpdateInstrument(DeltaSeconds);
    if (ViewMode == 3) UpdateCamera();
    UpdateVisualPreview(DeltaSeconds);
}

bool ATrainingScene::IsPhysicsConnected() const { return Bridge && Bridge->IsConnected(); }
bool ATrainingScene::IsGraspActive() const { return Bridge && Bridge->IsGraspActive(); }
FString ATrainingScene::GetPhysicsStatus() const { return Bridge ? Bridge->GetStatusText() : TEXT("Initializing SOFA bridge"); }
float ATrainingScene::GetForceNewton() const { return Bridge ? Bridge->GetForceNewton() : 0.0f; }
float ATrainingScene::GetSolveTimeMs() const { return Bridge ? Bridge->GetPhysicsStepMs() : 0.0f; }
float ATrainingScene::GetSimulationTime() const { return SimulationElapsed; }
FString ATrainingScene::GetViewName() const { return ViewMode == 1 ? TEXT("OVERVIEW") : ViewMode == 2 ? TEXT("SIDE INSPECTION") : ViewMode == 3 ? TEXT("JAW DETAIL") : TEXT("ENDOSCOPE"); }
int32 ATrainingScene::GetPhysicsNodeCount() const { return Bridge && Bridge->IsConnected() ? Bridge->GetPhysicsNodeCount() : 0; }
int32 ATrainingScene::GetContactCount() const { return Bridge && Bridge->IsConnected() ? Bridge->GetContactCount() : 0; }
float ATrainingScene::GetContactForceNewton() const { return Bridge ? Bridge->GetContactForceNewton() : 0.0f; }
float ATrainingScene::GetPenetrationMm() const { return Bridge ? Bridge->GetPenetrationMm() : 0.0f; }
float ATrainingScene::GetSlipDistanceMm() const { return Bridge ? Bridge->GetSlipDistanceMm() : 0.0f; }
float ATrainingScene::GetInsertionCm() const { return FVector::Distance(RenderedTip, FVector(12, -14, 15)); }
float ATrainingScene::GetSwingAngleDeg() const
{
    const FVector Pivot(12, -14, 15);
    return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct((RenderedTip - Pivot).GetSafeNormal(),
        (FVector(0, 0, 1.2) - Pivot).GetSafeNormal()), -1.0, 1.0)));
}
float ATrainingScene::GetRollDeg() const { return Bridge && Bridge->HasToolState() ? Bridge->GetActualRollDeg() : ToolRoll; }
float ATrainingScene::GetJawAngleDeg() const { return FMath::Lerp(2.0f, 40.0f, JawOpenBlend); }
FString ATrainingScene::GetGripState() const { return Bridge ? Bridge->GetGripState() : TEXT("open"); }
bool ATrainingScene::IsSlipping() const { return GetGripState().Contains(TEXT("slip"), ESearchCase::IgnoreCase) || GetGripState().Contains(TEXT("slid"), ESearchCase::IgnoreCase); }
FString ATrainingScene::GetActionHint() const
{
    if (IsMotionLimited()) return TEXT("Travel limit reached. Retract or reduce the pivot angle.");
    if (IsSlipping()) return TEXT("Tissue is sliding between the jaws. Reduce traction.");
    if (IsGraspActive()) return TEXT("Contact grip engaged. Raise gently with W; release SPACE to open.");
    if (GetContactCount() > 0 && !bJawClosed) return TEXT("Jaw contact detected. Hold SPACE to close when tissue is between the jaws.");
    if (bJawClosed && GetContactCount() > 0) return TEXT("Contact without a secure grip. Open and reposition around the tissue edge.");
    if (bJawClosed) return TEXT("No tissue held. Open the jaws and place tissue between both pads.");
    if (ActivePreset == 2) return TEXT("Edge approach: roll is 90 deg. Move to the edge, then hold SPACE.");
    return TEXT("Surface approach: lower gently with S. Press 2 for edge grasping.");
}
