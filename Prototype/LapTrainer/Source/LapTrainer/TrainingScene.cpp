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
    bVisualPreview=FParse::Param(FCommandLine::Get(),TEXT("LapVisualPreview"));
    auto Material=[&](const TCHAR* Name) { return LoadObject<UMaterialInterface>(nullptr,*FString::Printf(TEXT("/Game/Materials/%s.%s"),Name,Name)); };
    TissueMaterial=Material(TEXT("M_Tissue")); MetalMaterial=Material(TEXT("M_Metal"));
    DarkMaterial=Material(TEXT("M_Dark")); TableMaterial=Material(TEXT("M_Table"));
    AccentMaterial=Material(TEXT("M_Accent")); InsulationMaterial=Material(TEXT("M_Insulation"));
    TrayMaterial=Material(TEXT("M_Tray")); PadBackingMaterial=Material(TEXT("M_PadBacking"));
    if(!TissueMaterial) TissueMaterial=UMaterial::GetDefaultMaterial(MD_Surface);
    if(!MetalMaterial) MetalMaterial=UMaterial::GetDefaultMaterial(MD_Surface);
    if(!DarkMaterial) DarkMaterial=UMaterial::GetDefaultMaterial(MD_Surface);
    if(!TableMaterial) TableMaterial=UMaterial::GetDefaultMaterial(MD_Surface);
    if(!AccentMaterial) AccentMaterial=UMaterial::GetDefaultMaterial(MD_Surface);
    if(!InsulationMaterial) InsulationMaterial=DarkMaterial;
    if(!TrayMaterial) TrayMaterial=MetalMaterial;
    if(!PadBackingMaterial) PadBackingMaterial=TableMaterial;
    TissueMesh->SetMaterial(0,TissueMaterial);
    CreateEnvironment(); CreateInstrument(); UpdateCamera();
    if(!bVisualPreview) { Bridge=NewObject<USimulationBridge>(this); Bridge->InitializeBridge(); }
    bPhase3Test=FParse::Param(FCommandLine::Get(),TEXT("LapPhase3Test")) && !bVisualPreview;
    bAutoExit=FParse::Param(FCommandLine::Get(),TEXT("LapAutoExit"));
    if(bPhase3Test)
    {
        if(!FParse::Value(FCommandLine::Get(),TEXT("LapCaptureDir="),CaptureDirectory))
            CaptureDirectory=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Automation/Phase3"));
        CaptureDirectory=FPaths::ConvertRelativePathToFull(CaptureDirectory);
        IFileManager::Get().MakeDirectory(*CaptureDirectory,true);
        UE_LOG(LogTemp,Display,TEXT("LAP_PHASE3_TEST: normal PlayerController InputKey path; native physical topology."));
    }
    if(APlayerController* PC=UGameplayStatics::GetPlayerController(this,0))
    { PC->SetViewTarget(this); PC->bShowMouseCursor=false; PC->SetInputMode(FInputModeGameOnly()); }
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
    // Dimensions in centimetres. The thin physical membrane spans x +/-6, y +/-4 at rest z=0.6.
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

    // Physical membrane placeholder; replaced atomically by the first authoritative state.
    TissueVertices={FVector(-6,-4,.6),FVector(6,-4,.6),FVector(6,4,.6),FVector(-6,4,.6)};
    TissueTriangles={0,1,2,0,2,3};
    UpdateTissueSurface(); bHasSurface=false;
}


void ATrainingScene::CreateInstrument()
{
    auto Procedural = [&](const FString& Name, const FTrainingRenderMesh& M, USceneComponent* Parent)
    {
        auto* P = NewObject<UProceduralMeshComponent>(this, FName(*Name));
        P->SetupAttachment(Parent); P->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        P->SetSimulatePhysics(false); P->RegisterComponent(); P->SetMaterial(0, MetalMaterial);
        P->CreateMeshSection_LinearColor(0, M.Positions, M.Triangles, M.Normals, M.UV, M.Colors, M.Tangents, false);
        InstrumentDetailMeshes.Add(P); return P;
    };
    for (int32 T = 0; T < 2; ++T)
    {
        auto Shape = [&](const TCHAR* Part, UMaterialInterface* Mat, const FVector& P, const FVector& S)
        { return AddShape(*FString::Printf(TEXT("Tool%d_%s"), T, Part), CylinderMesh, Mat, P, S); };
        Shafts.Add(Shape(TEXT("Shaft"), MetalMaterial, ToolTips[T], FVector::OneVector));
        Collars.Add(Shape(TEXT("Collar"), MetalMaterial, ToolTips[T], FVector::OneVector));
        Sleeves.Add(Shape(TEXT("Insulation"), InsulationMaterial, ToolTips[T], FVector::OneVector));
        Ports.Add(Shape(TEXT("TrocarSeal"), InsulationMaterial, GetPivot(T), FVector(.010,.010,.006)));
        auto* Root = NewObject<USceneComponent>(this, FName(*FString::Printf(TEXT("HeadFrame%d"), T)));
        Root->SetupAttachment(SceneRoot); Root->RegisterComponent(); HeadRoots.Add(Root);
        for (int32 Sign : {-1, 1})
        {
            ToolJaws.Add(Procedural(FString::Printf(TEXT("Tool%d_Blade%d"), T, Sign),
                T == 0 ? TrainingGeometry::MakeSerratedJaw(Sign) : TrainingGeometry::MakeScissorBlade(Sign), SceneRoot));
            auto* Fork = Procedural(FString::Printf(TEXT("Tool%d_Fork%d"), T, Sign),
                TrainingGeometry::MakeBeveledBox(FVector(.23,.048,.22), .012f), Root);
            Fork->SetRelativeLocation(FVector(-.09, Sign*.184, 0));
            auto* Pin = AddShape(*FString::Printf(TEXT("Tool%d_Pin%d"), T, Sign), CylinderMesh,
                MetalMaterial, FVector::ZeroVector, FVector(.0024,.0024,.0009));
            Pin->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
            Pin->SetRelativeLocation(FVector(0,Sign*.238,0)); Pin->SetRelativeRotation(FRotator(0,0,90));
            auto* Slot = AddShape(*FString::Printf(TEXT("Tool%d_PinSlot%d"), T, Sign), CubeMesh,
                DarkMaterial, FVector::ZeroVector, FVector(.0013,.00015,.0003));
            Slot->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
            Slot->SetRelativeLocation(FVector(0,Sign*.286,0)); Slot->SetRelativeRotation(FRotator(0,0,12));
        }
        // A thin identification band helps distinguish instruments without obscuring the blades.
        auto* Band = Shape(TEXT("Identifier"), T == 0 ? AccentMaterial.Get() : MetalMaterial.Get(),
            FVector::ZeroVector, FVector(.0049,.0049,.0013));
        Band->AttachToComponent(Root, FAttachmentTransformRules::KeepRelativeTransform);
        Band->SetRelativeLocation(FVector(-.48,0,0)); Band->SetRelativeRotation(FRotator(0,0,90));
    }
    UpdateInstrument(1.0f);
}
FVector ATrainingScene::GetPivot(int32 Index) const { return FVector(Index == 0 ? 12 : -12, -14, 15); }
void ATrainingScene::PositionRod(UStaticMeshComponent* Mesh, const FVector& A, const FVector& B, float RadiusCm)
{
    if (!Mesh) return;
    const FVector D = B-A; Mesh->SetWorldLocation((A+B)*.5);
    Mesh->SetWorldRotation(FRotationMatrix::MakeFromZ(D.GetSafeNormal()).Rotator());
    Mesh->SetWorldScale3D(FVector(RadiusCm/50.0f, RadiusCm/50.0f, D.Size()/100.0f));
}
void ATrainingScene::UpdateInstrument(float DeltaSeconds)
{
    for (int32 T = 0; T < 2; ++T)
    {
        const FLapToolState* State = Bridge && Bridge->IsConnected() ? Bridge->GetToolState(T) : nullptr;
        ActualTips[T] = State ? State->ActualTipCm : ToolTips[T];
        const float Roll = State ? State->RollDeg : ToolRolls[T];
        const float Open = State ? State->JawOpenFraction : (ToolClosed[T] ? 0.0f : 1.0f);
        const FVector Pivot = GetPivot(T), Axis = (Pivot-ActualTips[T]).GetSafeNormal();
        FVector Side = FVector::CrossProduct(Axis, FVector::UpVector).GetSafeNormal();
        if (Side.IsNearlyZero()) Side = FVector::RightVector;
        Side = Side.RotateAngleAxis(Roll, Axis);
        const FVector Width = FVector::CrossProduct(Axis, Side).GetSafeNormal();
        const FVector Joint = ActualTips[T]+Axis*1.45;
        PositionRod(Shafts[T], Joint+Axis*.30, Pivot+Axis*2.0, .20f);
        PositionRod(Sleeves[T], Joint+Axis*3.0, Pivot-Axis*.35, .205f);
        PositionRod(Collars[T], Joint-Axis*.18, Joint+Axis*.48, .24f);
        HeadRoots[T]->SetWorldLocation(Joint);
        HeadRoots[T]->SetWorldRotation(FRotationMatrix::MakeFromXY(-Axis, Width).Rotator());
        Ports[T]->SetWorldRotation(FRotationMatrix::MakeFromZ(Axis).Rotator());
        for (int32 J=0; J<2; ++J)
        {
            UProceduralMeshComponent* Jaw = ToolJaws[T*2+J];
            if (State && State->JawPoses.IsValidIndex(J))
            {
                const FLapJawPose& P = State->JawPoses[J];
                Jaw->SetWorldLocation(P.CenterCm);
                Jaw->SetWorldRotation(FRotationMatrix::MakeFromXY(P.Axis, P.Side).Rotator());
            }
            else
            {
                const double Sign = J == 0 ? -1.0 : 1.0;
                const double Angle = FMath::DegreesToRadians(FMath::Lerp(0.0, 40.0, static_cast<double>(Open)));
                const FVector Forward = -Axis*FMath::Cos(Angle)+Side*(Sign*FMath::Sin(Angle));
                Jaw->SetWorldLocation(Joint+Side*(Sign*.0825)+Forward*.725);
                Jaw->SetWorldRotation(FRotationMatrix::MakeFromXY(Forward, Width).Rotator());
            }
        }
        if (T == ActiveTool) JawOpenBlend = Open;
    }
    RenderedTip = ActualTips[ActiveTool];
}
void ATrainingScene::UpdateCamera()
{
    FVector Target(0,0,.6);
    FVector Position = ViewMode == 1 ? FVector(0,-.1,34) : ViewMode == 2 ? FVector(18,-27,8) : FVector(0,-28,29);
    if (ViewMode == 3)
    {
        const FVector Axis = (GetPivot(ActiveTool)-RenderedTip).GetSafeNormal();
        FVector Side = FVector::CrossProduct(Axis,FVector::UpVector).GetSafeNormal();
        if (Side.IsNearlyZero()) Side = FVector::RightVector;
        Target = RenderedTip+Axis*.75;
        Position = Target+(Side*3.4+FVector::UpVector*4.5-Axis*.8).GetSafeNormal()*7.8;
    }
    Camera->SetWorldLocation(Position); Camera->SetWorldRotation((Target-Position).Rotation());
    Camera->SetFieldOfView(ViewMode == 3 ? 42.0f : 47.0f);
    if (EndoscopeLight) EndoscopeLight->SetIntensity(ViewMode == 3 ? .006f : .30f);
}
void ATrainingScene::SaveActiveCommand() { ToolTips[ActiveTool]=ToolTip; ToolRolls[ActiveTool]=ToolRoll; ToolClosed[ActiveTool]=bJawClosed; }
void ATrainingScene::LoadActiveCommand() { ToolTip=ToolTips[ActiveTool]; ToolRoll=ToolRolls[ActiveTool]; bJawClosed=ToolClosed[ActiveTool]; }
void ATrainingScene::SwitchTool()
{
    SaveActiveCommand();
    ToolClosed[ActiveTool] = ActiveTool == 0 && bGrasperLatched;
    ActiveTool = 1-ActiveTool; LoadActiveCommand();
    bSuppressSpace = true;
    if (ViewMode == 3) UpdateCamera();
}
void ATrainingScene::ResetExercise()
{
    ToolTips[0]=FVector(-2.2,-4.7,.6); ToolTips[1]=FVector(2.2,-4.7,.6);
    ToolRolls[0]=ToolRolls[1]=90.0f; ToolClosed[0]=ToolClosed[1]=false;
    ActiveTool=0; ActivePreset=1; bGrasperLatched=false; bSuppressSpace=true;
    bProtectionNotice=false; bProtectionHasOpened=false;
    LoadActiveCommand(); bResetRequested=true; SimulationElapsed=0; ++ResetCount;
    UE_LOG(LogTemp,Display,TEXT("LAP_RESET requested count=%d"),ResetCount);
}
void ATrainingScene::SelectPreset(int32 Preset)
{
    if (Preset == 3)
    {
        SaveActiveCommand(); ToolClosed[1]=false;
        ToolTips[1]=FVector(2.2,-4.7,.6); ToolRolls[1]=90.0f;
        ActiveTool=1; LoadActiveCommand(); bSuppressSpace=true;
    }
    else
    {
        ResetExercise(); ActivePreset=Preset;
        if (Preset == 2) { ToolTips[0]=FVector(-2.2,-3.4,.45); LoadActiveCommand(); }
    }
}
void ATrainingScene::ApplyWorkspaceLimits()
{
    const FVector Requested=ToolTip, Pivot=GetPivot(ActiveTool);
    const FVector Reference=(FVector(0,0,.6)-Pivot).GetSafeNormal();
    ToolTip.X=FMath::Clamp(ToolTip.X,-8.5,8.5); ToolTip.Y=FMath::Clamp(ToolTip.Y,-6.5,6.0);
    ToolTip.Z=FMath::Clamp(ToolTip.Z,-.2,8.0);
    FVector Ray=ToolTip-Pivot; const double Length=FMath::Clamp(Ray.Size(),12.0,30.0);
    Ray=Ray.GetSafeNormal(UE_SMALL_NUMBER,Reference);
    const double CosLimit=FMath::Cos(FMath::DegreesToRadians(32.0)), Dot=FVector::DotProduct(Ray,Reference);
    if (Dot<CosLimit)
    {
        const FVector Tangent=(Ray-Reference*Dot).GetSafeNormal(UE_SMALL_NUMBER,FVector::RightVector);
        Ray=Reference*CosLimit+Tangent*FMath::Sin(FMath::DegreesToRadians(32.0));
    }
    ToolTip=Pivot+Ray*Length; ToolRoll=FMath::UnwindDegrees(ToolRoll);
    bMotionLimited=!ToolTip.Equals(Requested,.0001);
    SaveActiveCommand();
}
void ATrainingScene::UpdateInput(float DeltaSeconds)
{
    APlayerController* PC=UGameplayStatics::GetPlayerController(this,0); if (!PC) return;
    if (PC->WasInputKeyJustPressed(EKeys::Escape))
    {
        bMouseReleased=true; bGrasperLatched=false; bJawClosed=false; ToolClosed[0]=ToolClosed[1]=false; bSuppressSpace=true;
        PC->bShowMouseCursor=true; FInputModeGameAndUI Mode; Mode.SetHideCursorDuringCapture(false); PC->SetInputMode(Mode);
    }
    if (PC->WasInputKeyJustPressed(EKeys::RightMouseButton) && bMouseReleased)
    { bMouseReleased=false; PC->bShowMouseCursor=false; PC->SetInputMode(FInputModeGameOnly()); }
    if (PC->WasInputKeyJustPressed(EKeys::F10)) UKismetSystemLibrary::QuitGame(this,PC,EQuitPreference::Quit,false);
    if (PC->WasInputKeyJustPressed(EKeys::H)) bShowHelp=!bShowHelp;
    if (PC->WasInputKeyJustPressed(EKeys::Tab)) { ViewMode=(ViewMode+1)%4; UpdateCamera(); }
    if (PC->WasInputKeyJustPressed(EKeys::R)) ResetExercise();
    if (PC->WasInputKeyJustPressed(EKeys::One)) SelectPreset(1);
    if (PC->WasInputKeyJustPressed(EKeys::Two)) SelectPreset(2);
    if (PC->WasInputKeyJustPressed(EKeys::Three)) SelectPreset(3);
    if (bMouseReleased) return;
    if (PC->WasInputKeyJustPressed(EKeys::C)) SwitchTool();
    if (PC->WasInputKeyJustPressed(EKeys::F) && IsPhysicsConnected())
    {
        // The selected tool may close. Opening the parked grasper is always allowed.
        if(bGrasperLatched) bGrasperLatched=false;
        else if(ActiveTool==0) bGrasperLatched=true;
        if(bGrasperLatched && bProtectionHasOpened) bProtectionNotice=false;
    }
    if (!PC->IsInputKeyDown(EKeys::SpaceBar)) bSuppressSpace=false;
    const bool Space=PC->IsInputKeyDown(EKeys::SpaceBar) && !bSuppressSpace && IsPhysicsConnected();
    if(Space && ActiveTool==0 && bProtectionHasOpened && PC->WasInputKeyJustPressed(EKeys::SpaceBar)) bProtectionNotice=false;
    ToolClosed[0]=bGrasperLatched || (ActiveTool==0 && Space);
    ToolClosed[1]=ActiveTool==1 && Space; bJawClosed=ToolClosed[ActiveTool];
    const float Speed=PC->IsInputKeyDown(EKeys::LeftControl) ? .65f : PC->IsInputKeyDown(EKeys::LeftShift) ? 5.0f : 2.5f;
    FVector Right=Camera->GetRightVector(); Right.Z=0; Right.Normalize();
    FVector Up=Camera->GetUpVector(); Up.Z=0;
    if(!Up.Normalize()) { Up=Camera->GetForwardVector(); Up.Z=0; Up.Normalize(); }
    if (PC->IsInputKeyDown(EKeys::RightMouseButton))
    {
        float MX,MY; PC->GetInputMouseDelta(MX,MY);
        ToolTip+=(Right*FMath::Clamp(MX,-60.0f,60.0f)+Up*FMath::Clamp(MY,-60.0f,60.0f))*.025f;
    }
    if (PC->IsInputKeyDown(EKeys::Left)) ToolTip-=Right*Speed*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::Right)) ToolTip+=Right*Speed*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::Up)) ToolTip+=Up*Speed*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::Down)) ToolTip-=Up*Speed*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::W)) ToolTip.Z+=Speed*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::S)) ToolTip.Z-=Speed*DeltaSeconds;
    const FVector Axis=(GetPivot(ActiveTool)-ToolTip).GetSafeNormal();
    if (PC->IsInputKeyDown(EKeys::T)) ToolTip-=Axis*Speed*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::G)) ToolTip+=Axis*Speed*DeltaSeconds;
    if (PC->WasInputKeyJustPressed(EKeys::MouseScrollUp)) ToolTip.Z+=.18f;
    if (PC->WasInputKeyJustPressed(EKeys::MouseScrollDown)) ToolTip.Z-=.18f;
    if (PC->IsInputKeyDown(EKeys::Q)) ToolRoll-=80.0f*DeltaSeconds;
    if (PC->IsInputKeyDown(EKeys::E)) ToolRoll+=80.0f*DeltaSeconds;
}
void ATrainingScene::UpdateTissueSurface()
{
    if (TissueVertices.Num()<3 || TissueTriangles.Num()<3) return;
    TissueNormals.Init(FVector::ZeroVector,TissueVertices.Num());
    for (int32 I=0;I+2<TissueTriangles.Num();I+=3)
    {
        const int32 A=TissueTriangles[I],B=TissueTriangles[I+1],C=TissueTriangles[I+2];
        if (!TissueVertices.IsValidIndex(A)||!TissueVertices.IsValidIndex(B)||!TissueVertices.IsValidIndex(C)) continue;
        const FVector N=FVector::CrossProduct(TissueVertices[B]-TissueVertices[A],TissueVertices[C]-TissueVertices[A]);
        TissueNormals[A]+=N; TissueNormals[B]+=N; TissueNormals[C]+=N;
    }
    for (FVector& N:TissueNormals) N=N.GetSafeNormal(UE_SMALL_NUMBER,FVector::UpVector);
    const int32 Topology=Bridge ? Bridge->GetTopologyRevision() : 0;
    const bool Rebuild=!bHasSurface || BoundNodeCount!=TissueVertices.Num() ||
        BoundFaceCount!=TissueTriangles.Num() || BoundTopologyRevision!=Topology;
    if (Rebuild)
    {
        BoundNodeCount=TissueVertices.Num(); BoundFaceCount=TissueTriangles.Num(); BoundTopologyRevision=Topology;
        TrainingGeometry::BuildSurfaceBindings(TissueVertices,TissueTriangles,3,TissueRenderBindings,TissueRenderData);
        // The native tetrahedral layer supplies its complete physical boundary, including
        // lower faces and new cut walls. No invented caps or duplicate reverse faces are added.
    }
    // Linear barycentric binding: exact physical triangles, no cross-cut interpolation or offset.
    TrainingGeometry::UpdateBoundSurface(TissueVertices,TissueNormals,TissueRenderBindings,TissueRenderData,0.0);
    if (bPhase3Test)
        for(int32 I=0;I<TissueRenderBindings.Num();++I)
        {
            const auto& S=TissueRenderBindings[I];
            const FVector P=TissueVertices[S.A]*S.Weight.X+TissueVertices[S.B]*S.Weight.Y+TissueVertices[S.C]*S.Weight.Z;
            TestMaxRenderOffsetMm=FMath::Max(TestMaxRenderOffsetMm,static_cast<float>(FVector::Distance(P,TissueRenderData.Positions[I])*10));
        }
    if (Rebuild)
        TissueMesh->CreateMeshSection_LinearColor(0,TissueRenderData.Positions,TissueRenderData.Triangles,TissueRenderData.Normals,
            TissueRenderData.UV,TissueRenderData.Colors,TissueRenderData.Tangents,false);
    else TissueMesh->UpdateMeshSection_LinearColor(0,TissueRenderData.Positions,TissueRenderData.Normals,
        TissueRenderData.UV,TissueRenderData.Colors,TissueRenderData.Tangents);
    bHasSurface=true;
}
void ATrainingScene::UpdateSimulation(float DeltaSeconds)
{
    if(bVisualPreview || !Bridge) return;
    if(bWasPhysicsConnected && !Bridge->IsConnected())
    {
        bGrasperLatched=false; bJawClosed=false; ToolClosed[0]=ToolClosed[1]=false;
        bSuppressSpace=true;
    }
    TArray<FLapToolCommand> Commands;
    for(int32 T=0;T<2;++T) { FLapToolCommand C; C.TipCm=ToolTips[T]; C.bClosed=ToolClosed[T]; C.RollDeg=ToolRolls[T]; Commands.Add(C); }
    Bridge->TickDualBridge(DeltaSeconds,Commands,ActiveTool,bResetRequested); bResetRequested=false;
    const uint64 SafetyStops=Bridge->GetSafetyStopCount();
    if(SafetyStops>LastSafetyStopCount)
    {
        bGrasperLatched=false; bJawClosed=false; ToolClosed[0]=ToolClosed[1]=false;
        bSuppressSpace=true; bProtectionNotice=true; bProtectionHasOpened=false;
    }
    LastSafetyStopCount=SafetyStops;
    if(bProtectionNotice)
    {
        const FLapToolState* A=Bridge->GetToolState(0); const FLapToolState* B=Bridge->GetToolState(1);
        if(A && B && A->JawOpenFraction>.90f && B->JawOpenFraction>.90f) bProtectionHasOpened=true;
    }
    if(!bWasPhysicsConnected && Bridge->IsConnected()) bSuppressSpace=true;
    if(bWasPhysicsConnected && !Bridge->IsConnected())
    {
        bGrasperLatched=false; bJawClosed=false; ToolClosed[0]=ToolClosed[1]=false;
        bSuppressSpace=true;
    }
    bWasPhysicsConnected=Bridge->IsConnected();
    if(!Bridge->IsConnected()) return;
    SimulationElapsed+=DeltaSeconds;
    const uint64 Frame=Bridge->GetFrameNumber();
    if(Frame!=LastPhysicsFrame && Bridge->GetSurface(TissueVertices,TissueTriangles))
    { LastPhysicsFrame=Frame; UpdateTissueSurface(); }
}
void ATrainingScene::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if(DeltaSeconds>.0001f) SmoothedFps=FMath::FInterpTo(SmoothedFps,1.0f/DeltaSeconds,DeltaSeconds,2.0f);
    UpdatePhase3Test(DeltaSeconds);
    UpdateInput(DeltaSeconds); ApplyWorkspaceLimits(); UpdateSimulation(DeltaSeconds); UpdateInstrument(DeltaSeconds);
    if(ViewMode==3) UpdateCamera();
}
bool ATrainingScene::IsPhysicsConnected() const { return Bridge && Bridge->IsConnected(); }
bool ATrainingScene::IsPhysicsHealthy() const { return Bridge && Bridge->IsHealthy(); }
bool ATrainingScene::IsGraspActive() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return IsPhysicsConnected() && S && S->bGrasping; }
bool ATrainingScene::IsGrasperHolding() const { const auto* S=Bridge ? Bridge->GetToolState(0):nullptr; return IsPhysicsConnected() && S && S->bGrasping; }
FString ATrainingScene::GetPhysicsStatus() const { return Bridge ? Bridge->GetStatusText():TEXT("Initializing SOFA bridge"); }
float ATrainingScene::GetForceNewton() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->ForceNewton:0; }
float ATrainingScene::GetSolveTimeMs() const { return Bridge ? Bridge->GetPhysicsStepMs():0; }
FString ATrainingScene::GetViewName() const { return ViewMode==1 ? TEXT("OVERVIEW"):ViewMode==2 ? TEXT("SIDE INSPECTION"):ViewMode==3 ? TEXT("JAW DETAIL"):TEXT("ENDOSCOPE"); }
int32 ATrainingScene::GetPhysicsNodeCount() const { return Bridge ? Bridge->GetPhysicsNodeCount():0; }
int32 ATrainingScene::GetContactCount() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->ContactCount:0; }
float ATrainingScene::GetContactForceNewton() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->ContactForceNewton:0; }
float ATrainingScene::GetPenetrationMm() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->PenetrationMm:0; }
float ATrainingScene::GetSlipDistanceMm() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->SlipDistanceMm:0; }
float ATrainingScene::GetInsertionCm() const { return FVector::Distance(RenderedTip,GetPivot(ActiveTool)); }
float ATrainingScene::GetSwingAngleDeg() const
{
    const FVector P=GetPivot(ActiveTool);
    return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct((RenderedTip-P).GetSafeNormal(),(FVector(0,0,.6)-P).GetSafeNormal()),-1.0,1.0)));
}
float ATrainingScene::GetRollDeg() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->RollDeg:ToolRoll; }
float ATrainingScene::GetJawAngleDeg() const { return 40.0f*JawOpenBlend; }
int32 ATrainingScene::GetCutCount() const { return Bridge ? Bridge->GetCutCount():0; }
int32 ATrainingScene::GetComponentCount() const { return Bridge ? Bridge->GetComponentCount():1; }
float ATrainingScene::GetCutLengthCm() const { return Bridge ? Bridge->GetCutLengthCm():0; }
FString ATrainingScene::GetGripState() const { const auto* S=Bridge ? Bridge->GetToolState(ActiveTool):nullptr; return S ? S->GripState:TEXT("open"); }
bool ATrainingScene::IsSlipping() const { return GetGripState().Contains(TEXT("slip"),ESearchCase::IgnoreCase); }
FString ATrainingScene::GetActionHint() const
{
    if(IsPhysicsConnected() && !IsPhysicsHealthy()) return TEXT("Physics stopped. Last valid tool poses are frozen. Press R to reset.");
    if(bMouseReleased) return TEXT("Both instruments released. Right-click to resume.");
    if(bProtectionNotice) return TEXT("Protection released tools. Release SPACE, reposition and regrip; R resets. See physics status at right.");
    if(IsMotionLimited()) return TEXT("RCM travel limit reached. Retract or reduce the pivot angle.");
    if(ActiveTool==1) return TEXT("Hold SPACE until the cut; release to reopen. Lift clear before the next bite. C returns to grasper.");
    if(IsSlipping()) return TEXT("Tissue is sliding. Reduce traction or open and reposition.");
    if(IsGrasperHolding()) return TEXT("Raise gently with W. F latches the grasper so C can select scissors while holding.");
    return TEXT("2: ready position. F: latch grasper on tissue. W: traction. C: scissors. 1 / R: reset.");
}

void ATrainingScene::SetTestKey(const FKey& Key,bool bDown)
{
    const FName Name=Key.GetFName(); if(TestHeldKeys.Contains(Name)==bDown) return;
    APlayerController* PC=UGameplayStatics::GetPlayerController(this,0); if(!PC) return;
    if(bDown) TestHeldKeys.Add(Name); else TestHeldKeys.Remove(Name);
    PC->InputKey(FInputKeyEventArgs(nullptr,FInputDeviceId::CreateFromInternalId(0),Key,
        bDown?IE_Pressed:IE_Released,bDown?1.0f:0.0f,false,FPlatformTime::Cycles64()));
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE3_KEY stage=%d key=%s down=%d active=%d"),TestStage,*Key.ToString(),bDown,ActiveTool);
}
void ATrainingScene::StopTestMotion()
{
    for(const FKey& K:{EKeys::W,EKeys::S,EKeys::Up,EKeys::Down,EKeys::Left,EKeys::Right,EKeys::T,EKeys::G,
        EKeys::LeftControl,EKeys::LeftShift,EKeys::Q,EKeys::E}) SetTestKey(K,false);
}
bool ATrainingScene::DriveTestTo(const FVector& Target)
{
    const FVector Error=Target-ToolTip;
    FVector Right=Camera->GetRightVector(); Right.Z=0; Right.Normalize();
    FVector Up=Camera->GetUpVector(); Up.Z=0;
    if(!Up.Normalize()) { Up=Camera->GetForwardVector(); Up.Z=0; Up.Normalize(); }
    const double X=FVector::DotProduct(Error,Right),Y=FVector::DotProduct(Error,Up),Tol=.014;
    SetTestKey(EKeys::LeftControl,true);
    SetTestKey(EKeys::Right,X>Tol); SetTestKey(EKeys::Left,X<-Tol);
    SetTestKey(EKeys::Up,Y>Tol); SetTestKey(EKeys::Down,Y<-Tol);
    SetTestKey(EKeys::W,Error.Z>Tol); SetTestKey(EKeys::S,Error.Z<-Tol);
    return Error.Size()<.045 && FVector::Distance(RenderedTip,Target)<.10;
}
bool ATrainingScene::SampleUpperVertex(double X,double Y,FVector& OutPosition) const
{
    // Native topology stores the complete upper layer before the lower layer.
    // Follow the actual material point, including its deformed XY, within 10 mm.
    double BestDistance=1.0;
    bool Found=false;
    for(int32 I=0;I<TissueVertices.Num()/2;++I)
    {
        const FVector& P=TissueVertices[I];
        const double D=FMath::Square(P.X-X)+FMath::Square(P.Y-Y);
        if(D<=BestDistance) { BestDistance=D; OutPosition=P; Found=true; }
    }
    return Found;
}
void ATrainingScene::AdvanceTest(int32 Stage)
{
    StopTestMotion(); SetTestKey(EKeys::C,false); SetTestKey(EKeys::F,false);
    SetTestKey(EKeys::One,false); SetTestKey(EKeys::Two,false); SetTestKey(EKeys::R,false); SetTestKey(EKeys::Tab,false); SetTestKey(EKeys::H,false);
    TestStage=Stage; TestStageTime=0; TestDwell=0; TestStageTicks=0; TestGripFrames=0;
    if(Stage==4)
    {
        FVector P;
        if(!SampleUpperVertex(4,-3.5,P))
        {
            FinishPhase3Test(TEXT("First scissor aim has no upper material point within 10 mm")); return;
        }
        TestBiteTarget=P-FVector(0,0,.2);
    }
    if(Stage==7)
    {
        // Overlapping, short bites extend the initial incision from right to left.
        const double X=3.2-TestStroke*.8,Y=-2.9;
        FVector P;
        if(!SampleUpperVertex(X,Y,P))
        {
            FinishPhase3Test(TEXT("Next scissor aim has no upper material point within 10 mm")); return;
        }
        // This initial sample only plans clearance. Refresh at the end of translation,
        // then freeze for descent, so tissue relaxation during travel cannot stale the aim.
        TestBiteTarget=FVector(P.X,P.Y,FMath::Max(P.Z-.2,-.18));
        double Highest=FMath::Max(RenderedTip.Z,P.Z);
        for(const FVector& Vertex:TissueVertices) Highest=FMath::Max(Highest,Vertex.Z);
        TestClearanceZ=static_cast<float>(Highest+1.2);
        TestRetractTarget=FVector(ToolTip.X,ToolTip.Y,TestClearanceZ);
        TestWaypointPhase=0;
    }
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE3_STAGE stage=%d stroke=%d held=%d cuts=%d pieces=%d tip=%s"),
        TestStage,TestStroke,IsGrasperHolding(),GetCutCount(),GetComponentCount(),*RenderedTip.ToString());
}
bool ATrainingScene::TestTimedOut(float Seconds,const TCHAR* Action)
{
    if(TestStageTime<=Seconds) return false;
    const FString Reason=FString::Printf(TEXT("Stage %d timed out: %s"),TestStage,Action);
    TestFailures.AddUnique(Reason); UE_LOG(LogTemp,Error,TEXT("LAP_PHASE3_ASSERT %s"),*Reason); return true;
}
void ATrainingScene::CaptureTest(const TCHAR* Filename)
{ FScreenshotRequest::RequestScreenshot(FPaths::Combine(CaptureDirectory,Filename),true,false); }
void ATrainingScene::UpdatePhase3Test(float DeltaSeconds)
{
    if(!bPhase3Test || bTestFinished) return;
    TestTime+=DeltaSeconds;
    if(Bridge) TestPeakSafetyStops=FMath::Max(TestPeakSafetyStops,Bridge->GetSafetyStopCount());
    if(Bridge && Bridge->GetUnhealthyStateCount()>0) TestFailures.AddUnique(TEXT("Native physics reported unhealthy history"));
    if(Bridge && Bridge->GetRejectedStateCount()>0) TestFailures.AddUnique(TEXT("Malformed physics state rejected"));
    if(!IsPhysicsConnected())
    {
        if(bTestStarted) TestFailures.AddUnique(TEXT("Physics became stale or disconnected during exercise"));
        if(TestTime>35.0f) FinishPhase3Test(TEXT("Physics connection unavailable"));
        return;
    }
    bTestStarted=true;
    if(TestTime>660.0f) { FinishPhase3Test(TEXT("Overall exercise timeout")); return; }
    if(!Bridge->IsHealthy()) { FinishPhase3Test(TEXT("Native physics is unhealthy")); return; }
    TestStageTime+=DeltaSeconds;
    ++TestStageTicks;
    const bool NewFrame=TestObservedFrame!=Bridge->GetFrameNumber(); TestObservedFrame=Bridge->GetFrameNumber();
    TestPeakDisplacementMm=FMath::Max(TestPeakDisplacementMm,Bridge->GetMaxDisplacementCm()*10);
    TestPeakCuts=FMath::Max(TestPeakCuts,GetCutCount());
    TestPeakComponents=FMath::Max(TestPeakComponents,GetComponentCount());
    TestPeakTopology=FMath::Max(TestPeakTopology,static_cast<int32>(Bridge->GetTopologyRevision()));
    const FLapToolState* Grasper=Bridge->GetToolState(0);
    if(Grasper) TestPeakForceN=FMath::Max(TestPeakForceN,Grasper->ForceNewton);
    TestPeakSafetyStops=FMath::Max(TestPeakSafetyStops,Bridge->GetSafetyStopCount());
    if(TestPeakSafetyStops>0) { FinishPhase3Test(TEXT("Native protection stop occurred during regular exercise")); return; }
    if(GetCutCount()>0 && BoundTopologyRevision==Bridge->GetTopologyRevision() && NewFrame) bTestTopologyRendered=true;
    switch(TestStage)
    {
    case 0:
        SetTestKey(EKeys::Two,TestStageTicks==1);
        SetTestKey(EKeys::Tab,TestStageTicks==3);
        SetTestKey(EKeys::H,TestStageTicks==5);
        if(Bridge->HasAcknowledgedReset() &&
            FVector::Distance(ActualTips[0],FVector(-2.2,-3.4,.45))<.02 && GetCutCount()==0 && ViewMode==1 && !bShowHelp)
        { TestDwell+=DeltaSeconds; if(NewFrame) ++TestGripFrames; }
        else { TestDwell=0; TestGripFrames=0; }
        if(TestStageTime>.8f && TestDwell>=.25f && TestGripFrames>=4)
        { CaptureTest(TEXT("phase3_01_ready.png")); AdvanceTest(1); }
        else if(TestTimedOut(12,TEXT("preset 2 ready pose and reset acknowledgement"))) FinishPhase3Test();
        break;
    case 1:
        SetTestKey(EKeys::F,TestStageTicks==1);
        if(IsGrasperHolding())
        {
            TestDwell+=DeltaSeconds;
            if(NewFrame) ++TestGripFrames;
        }
        else { TestDwell=0; TestGripFrames=0; }
        if(TestDwell>.45f && TestGripFrames>=8) { bTestGrip=true; CaptureTest(TEXT("phase3_02_grasp.png")); AdvanceTest(2); }
        else if(TestTimedOut(12,TEXT("contact-supported grasper latch"))) FinishPhase3Test();
        break;
    case 2:
        if(DriveTestTo(FVector(-2.2,-3.4,.85)) && IsGrasperHolding() &&
            Bridge->GetMaxDisplacementCm()>.2f) TestDwell+=DeltaSeconds; else TestDwell=0;
        if(TestDwell>.6f)
        {
            bTestTension=true; TestParkedGrasper=ActualTips[0];
            CaptureTest(TEXT("phase3_03_traction.png")); AdvanceTest(3);
        }
        else if(TestTimedOut(15,TEXT("latched grasper raises membrane by at least 2 mm"))) FinishPhase3Test();
        break;
    case 3:
        SetTestKey(EKeys::C,TestStageTicks==1);
        if(TestStageTime>.6f && ActiveTool==1 && IsGrasperHolding() && bGrasperLatched &&
            FVector::Distance(ActualTips[0],TestParkedGrasper)<.08)
        { bTestSwitchHeld=true; AdvanceTest(4); }
        else if(TestTimedOut(6,TEXT("C switches to scissors while retaining grasper hold"))) FinishPhase3Test();
        break;
    case 4:
        // Closures are deliberately driven through the normal Space input, never a cut command.
        if(DriveTestTo(TestBiteTarget))
        {
            TestDwell+=DeltaSeconds;
            bTestIndependentTool=FVector::Distance(ActualTips[0],TestParkedGrasper)<.08;
        }
        else TestDwell=0;
        if(TestDwell>.5f)
        { TestCutBaseline=GetCutCount(); TestTopologyBaseline=static_cast<int32>(Bridge->GetTopologyRevision()); AdvanceTest(5); }
        else if(TestTimedOut(15,TEXT("independent scissors approach"))) FinishPhase3Test();
        break;
    case 5:
        SetTestKey(EKeys::SpaceBar,true);
        if(TestStageTime>1.5f && JawOpenBlend<=.45f)
        {
            bTestCut=GetCutCount()>TestCutBaseline && Bridge->GetTopologyRevision()>static_cast<uint64>(TestTopologyBaseline);
            if(!bTestCut) TestFailures.AddUnique(TEXT("Scissor closure did not sever physical connectivity"));
            if(!IsGrasperHolding()) TestFailures.AddUnique(TEXT("Grasper hold was lost during the first cut"));
            CaptureTest(TEXT("phase3_04_cut.png")); TestCutBaseline=GetCutCount(); AdvanceTest(6);
        }
        else if(TestTimedOut(15,TEXT("scissors closure reaches cutting angle"))) FinishPhase3Test();
        break;
    case 6:
        // Remaining closed and parked must not repeatedly re-cut; opening must not cut.
        if(TestStageTime<.65f)
        {
            if(GetCutCount()!=TestCutBaseline) TestFailures.AddUnique(TEXT("Stationary closed scissors cut repeatedly"));
        }
        else SetTestKey(EKeys::SpaceBar,false);
        if(TestStageTime>1.6f && JawOpenBlend>.90f)
        {
            bTestOpeningNoCut=GetCutCount()==TestCutBaseline;
            TestStroke=0; AdvanceTest(7);
        }
        else if(TestTimedOut(12,TEXT("scissors reopen after first cut"))) FinishPhase3Test();
        break;
    case 7:
    {
        const FVector Target=TestWaypointPhase==0 ? TestRetractTarget : TestWaypointPhase==1 ?
            FVector(TestBiteTarget.X,TestBiteTarget.Y,TestClearanceZ) : TestBiteTarget;
        if(DriveTestTo(Target)) TestDwell+=DeltaSeconds; else TestDwell=0;
        if(TestDwell>.3f)
        {
            StopTestMotion(); TestDwell=0;
            if(TestWaypointPhase==1)
            {
                FVector P;
                if(!SampleUpperVertex(3.2-TestStroke*.8,-2.9,P))
                {
                    FinishPhase3Test(TEXT("Refreshed scissor aim has no upper material point within 10 mm"));
                    break;
                }
                TestBiteTarget=FVector(P.X,P.Y,FMath::Max(P.Z-.2,-.18));
                ++TestWaypointPhase;
            }
            else if(TestWaypointPhase==0) ++TestWaypointPhase;
            else AdvanceTest(8);
        }
        else if(TestTimedOut(40,TEXT("retract, translate above membrane, and approach next bite"))) FinishPhase3Test();
        break;
    }
    case 8:
        SetTestKey(EKeys::SpaceBar,true);
        if(TestStageTime>1.35f && JawOpenBlend<=.45f) AdvanceTest(9);
        else if(TestTimedOut(15,TEXT("next closure reaches cutting angle"))) FinishPhase3Test();
        break;
    case 9:
        SetTestKey(EKeys::SpaceBar,false);
        if(TestStageTime>.95f && JawOpenBlend>.90f)
        {
            ++TestStroke;
            bTestContinuousCuts=GetCutCount()>TestCutBaseline;
            // Finish once repeated physical cutting and separation are both demonstrated.
            // Further fixed world-space targets can lie outside an already detached fragment.
            if(TestStroke>=12 || (GetCutCount()>=2 && GetComponentCount()>1 && bTestContinuousCuts))
            {
                CaptureTest(TEXT("phase3_05_separation.png"));
                AdvanceTest(10);
            }
            else AdvanceTest(7);
        }
        else if(TestTimedOut(12,TEXT("scissors fully reopen to rearm the next cut"))) FinishPhase3Test();
        break;
    case 10:
        // F releases the parked grasper while the scissors remain selected.
        SetTestKey(EKeys::F,TestStageTicks==1);
        if(TestStageTime>1.8f && !IsGrasperHolding() && !bGrasperLatched)
        {
            bTestRelease=true; TestCutBaseline=GetCutCount();
            CaptureTest(TEXT("phase3_06_release.png")); AdvanceTest(11);
        }
        else if(TestTimedOut(8,TEXT("F releases grasper while scissors are active"))) FinishPhase3Test();
        break;
    case 11:
        SetTestKey(EKeys::C,TestStageTicks==1);
        if(TestStageTime>.35f) SetTestKey(EKeys::SpaceBar,true);
        if(TestStageTime>1.6f)
        {
            bTestInactiveNoCut=ActiveTool==0 && GetCutCount()==TestCutBaseline;
            SetTestKey(EKeys::SpaceBar,false); AdvanceTest(12);
        }
        break;
    case 12:
        SetTestKey(EKeys::R,TestStageTicks==1);
        if(TestStageTime>1.6f && Bridge->HasAcknowledgedReset() && GetCutCount()==0 && GetComponentCount()==1 &&
            !IsGrasperHolding() && !bGrasperLatched && FVector::Distance(ActualTips[0],FVector(-2.2,-4.7,.6))<.08)
        { bTestReset=true; CaptureTest(TEXT("phase3_07_reset.png")); AdvanceTest(13); }
        else if(TestTimedOut(12,TEXT("R restores intact topology and releases both tools"))) FinishPhase3Test();
        break;
    case 13:
        if(TestStageTime>.7f) FinishPhase3Test();
        break;
    default: FinishPhase3Test(TEXT("Unexpected input test stage")); break;
    }
}
void ATrainingScene::FinishPhase3Test(const FString& Failure)
{
    if(bTestFinished) return; bTestFinished=true;
    const TArray<FName> Held=TestHeldKeys.Array(); for(const FName& K:Held) SetTestKey(FKey(K),false);
    if(!Failure.IsEmpty()) TestFailures.AddUnique(Failure);
    TSharedRef<FJsonObject> Report=MakeShared<FJsonObject>(),Checks=MakeShared<FJsonObject>(),Metrics=MakeShared<FJsonObject>();
    auto Check=[&](const TCHAR* Name,bool Good)
    { Checks->SetBoolField(Name,Good); if(!Good) TestFailures.AddUnique(FString::Printf(TEXT("Failed check: %s"),Name)); };
    int32 BladeVertices=0; double EnvelopeExcessMm=0;
    for(UProceduralMeshComponent* Jaw:ToolJaws)
        if(Jaw)
            if(const FProcMeshSection* Section=Jaw->GetProcMeshSection(0))
                for(const FProcMeshVertex& Vertex:Section->ProcVertexBuffer)
                {
                    ++BladeVertices;
                    const FVector Excess=FVector(Vertex.Position).GetAbs()-FVector(.725,.125,.070);
                    EnvelopeExcessMm=FMath::Max(EnvelopeExcessMm,FMath::Max(0.0,Excess.GetMax())*10);
                }
    Check(TEXT("physics_connected"),IsPhysicsConnected());
    Check(TEXT("healthy_without_rejected_states"),Bridge && Bridge->IsHealthy() && Bridge->GetUnhealthyStateCount()==0 && Bridge->GetRejectedStateCount()==0);
    Check(TEXT("regular_exercise_without_safety_stops"),TestPeakSafetyStops==0 && Bridge && Bridge->GetSafetyStopCount()==0);
    Check(TEXT("contact_grasp"),bTestGrip);
    Check(TEXT("traction_before_cut"),bTestTension);
    Check(TEXT("switch_keeps_latched_grasper"),bTestSwitchHeld);
    Check(TEXT("independent_tool_motion"),bTestIndependentTool);
    Check(TEXT("closure_changes_physical_topology"),bTestCut);
    Check(TEXT("repeated_closures_continue_cut"),bTestContinuousCuts);
    Check(TEXT("separated_components_observed"),TestPeakComponents>1);
    Check(TEXT("topology_render_binding_updated"),bTestTopologyRendered);
    Check(TEXT("render_matches_physical_surface"),!TissueRenderBindings.IsEmpty() && TestMaxRenderOffsetMm<.001f);
    Check(TEXT("both_instrument_models_inside_contact_envelopes"),ToolJaws.Num()==4 && BladeVertices>5000 && EnvelopeExcessMm<.001);
    Check(TEXT("opening_does_not_cut"),bTestOpeningNoCut);
    Check(TEXT("grasper_selection_does_not_cut"),bTestInactiveNoCut);
    Check(TEXT("parked_grasper_releases"),bTestRelease);
    Check(TEXT("reset_restores_intact_membrane"),bTestReset);
    Metrics->SetNumberField(TEXT("max_displacement_mm"),TestPeakDisplacementMm);
    Metrics->SetNumberField(TEXT("max_render_offset_mm"),TestMaxRenderOffsetMm);
    Metrics->SetNumberField(TEXT("peak_grasper_load_n"),TestPeakForceN);
    Metrics->SetNumberField(TEXT("instrument_blade_vertices"),BladeVertices);
    Metrics->SetNumberField(TEXT("blade_envelope_excess_mm"),EnvelopeExcessMm);
    Metrics->SetNumberField(TEXT("max_cut_count"),TestPeakCuts);
    Metrics->SetNumberField(TEXT("max_component_count"),TestPeakComponents);
    Metrics->SetNumberField(TEXT("max_topology_revision"),TestPeakTopology);
    Metrics->SetNumberField(TEXT("unhealthy_state_count"),Bridge?Bridge->GetUnhealthyStateCount():0);
    Metrics->SetNumberField(TEXT("rejected_state_count"),Bridge?Bridge->GetRejectedStateCount():0);
    Metrics->SetNumberField(TEXT("safety_stop_count"),TestPeakSafetyStops);
    Metrics->SetNumberField(TEXT("elapsed_s"),TestTime);
    Report->SetNumberField(TEXT("phase"),3); Report->SetNumberField(TEXT("report_version"),1);
    Report->SetStringField(TEXT("input_path"),TEXT("PlayerController InputKey -> normal UpdateInput. Test writes no tool pose or physical cut command."));
    Report->SetStringField(TEXT("scope"),TEXT("Software keyboard path, native membrane grasp and cutting, independent tools, topology/render synchronization. Native regression separately tests mass conservation and disconnected elastic response. Not clinical validation."));
    Report->SetObjectField(TEXT("checks"),Checks); Report->SetObjectField(TEXT("metrics"),Metrics);
    TArray<TSharedPtr<FJsonValue>> Failures; for(const FString& F:TestFailures) Failures.Add(MakeShared<FJsonValueString>(F));
    Report->SetArrayField(TEXT("failures"),Failures); Report->SetBoolField(TEXT("passed"),TestFailures.IsEmpty());
    FString Json; FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Json));
    const FString Path=FPaths::Combine(CaptureDirectory,TEXT("phase3-input-test.json"));
    const bool Saved=FFileHelper::SaveStringToFile(Json,*Path,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE3_TEST complete passed=%d saved=%d path=%s"),TestFailures.IsEmpty(),Saved,*Path);
    if(bAutoExit) FPlatformMisc::RequestExit(false);
}
