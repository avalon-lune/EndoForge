#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "Camera/CameraComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "ProceduralMeshComponent.h"
#include "Async/Async.h"
#include "HAL/PlatformProcess.h"
#include "Misc/FileHelper.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/Paths.h"
#include "ImageUtils.h"
#include "RenderingThread.h"

namespace
{
void P6CVar(const TCHAR* Name,float Value)
{
    if(auto* V=IConsoleManager::Get().FindConsoleVariable(Name))V->Set(Value,ECVF_SetByCode);
    else UE_LOG(LogTemp,Warning,TEXT("PHASE6_CVAR_UNAVAILABLE %s"),Name);
}
}

void ATrainingScene::InitializePhase6()
{
    bPhase6Test=FParse::Param(FCommandLine::Get(),TEXT("LapPhase6Test"));
    ResetPhase6Motion();ConfigurePhase6Rendering();UpdateCamera();WritePhase5Manifest();
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6 Initialized high-detail anatomy, feedback-bounded control, DX12 lighting validation test=%d"),bPhase6Test);
}

void ATrainingScene::ConfigurePhase6Rendering()
{
    auto& P=Camera->PostProcessSettings;
    P.bOverride_DynamicGlobalIlluminationMethod=true;P.DynamicGlobalIlluminationMethod=EDynamicGlobalIlluminationMethod::Lumen;
    P.bOverride_ReflectionMethod=true;P.ReflectionMethod=EReflectionMethod::Lumen;
    P.bOverride_LumenSceneLightingQuality=true;P.LumenSceneLightingQuality=4;
    P.bOverride_LumenSceneDetail=true;P.LumenSceneDetail=4;
    P.bOverride_LumenSceneViewDistance=true;P.LumenSceneViewDistance=150;
    P.bOverride_LumenMaxTraceDistance=true;P.LumenMaxTraceDistance=150;
    P.bOverride_LumenFinalGatherQuality=true;P.LumenFinalGatherQuality=4;
    P.bOverride_LumenReflectionQuality=true;P.LumenReflectionQuality=4;
    P.bOverride_LumenRayLightingMode=true;P.LumenRayLightingMode=ELumenRayLightingModeOverride::HitLighting;
    P.bOverride_LumenReflectionsScreenTraces=true;P.LumenReflectionsScreenTraces=false;
    P.bOverride_LumenFinalGatherScreenTraces=true;P.LumenFinalGatherScreenTraces=false;
    P.bOverride_VignetteIntensity=true;P.VignetteIntensity=.16f;
    P.bOverride_BloomIntensity=true;P.BloomIntensity=.08f;
    P.bOverride_MotionBlurAmount=true;P.MotionBlurAmount=0;
    if(EndoscopeLight)
    {
        EndoscopeLight->SetIntensity(.14);EndoscopeLight->SetSourceRadius(.12);
        EndoscopeLight->SetLightColor(FLinearColor(1,.94,.87));
        EndoscopeLight->SetShadowBias(.1);EndoscopeLight->SetShadowSlopeBias(.1);
        EndoscopeLight->SetCastShadows(true);EndoscopeLight->SetCastRaytracedShadows(ECastRayTracedShadow::Enabled);
        EndoscopeLight->ContactShadowLength=.5;EndoscopeLight->ContactShadowLengthInWS=true;
    }
    P6CVar(TEXT("r.DynamicGlobalIlluminationMethod"),1);P6CVar(TEXT("r.ReflectionMethod"),1);
    P6CVar(TEXT("r.Lumen.HardwareRayTracing"),1);P6CVar(TEXT("r.Lumen.HardwareRayTracing.LightingMode"),1);
    P6CVar(TEXT("r.Lumen.Reflections.HardwareRayTracing"),1);
    P6CVar(TEXT("r.Lumen.Reflections.HardwareRayTracing.HitLighting"),1);
    P6CVar(TEXT("r.Lumen.Reflections.ScreenTraces"),0);P6CVar(TEXT("r.Lumen.ScreenProbeGather.ScreenTraces"),0);
    P6CVar(TEXT("r.RayTracing.Shadows"),1);P6CVar(TEXT("r.RayTracing.NormalBias"),.01);
    P6CVar(TEXT("r.Lumen.Reflections.HardwareRayTracing.NormalBias"),.01);
    P6CVar(TEXT("r.Lumen.ScreenProbeGather.HardwareRayTracing.NormalBias"),.01);
    P6CVar(TEXT("r.ShadowQuality"),5);P6CVar(TEXT("r.Shadow.Virtual.Enable"),1);
    P6CVar(TEXT("r.Shadow.Virtual.ResolutionLodBiasLocal"),-1);
    P6CVar(TEXT("r.ScreenPercentage"),100);P6CVar(TEXT("r.ViewDistanceScale"),2);
    P6CVar(TEXT("r.MaxAnisotropy"),16);
}

void ATrainingScene::UpdatePhase6DisplaySurface()
{
    // Render detail follows the authoritative physical boundary. It cannot add
    // an arbitrary displacement that changes contact geometry or labels.
    TrainingGeometry::UpdateBoundSurface(TissueVertices,TissueNormals,TissueRenderBindings,TissueRenderData,.012);
}

bool ATrainingScene::SavePhase6Json(const FString& Path,const TSharedRef<FJsonObject>& Object)
{
    // The displayed state is immutable until this export finishes. Serialization
    // is CPU-only; the game thread retains socket ownership and its watchdog.
    auto Job=Async(EAsyncExecution::ThreadPool,[Path,Object]()
    {
        FString Text;FJsonSerializer::Serialize(Object,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
        return FFileHelper::SaveStringToFile(Text,*Path,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    });
    while(!Job.IsReady()){if(Bridge)Bridge->TickFrozenBridge();FPlatformProcess::Sleep(.01f);}
    return Job.Get();
}

void ATrainingScene::CapturePhase6Review(const FString& Name,bool Closeup)
{
    if(!bPhase6Test || !Phase6ProofCapture || !Phase6ProofTarget || !Bridge)return;
    bPhase5CapturePrevious=true;bResumeSnapshot=true;Bridge->TickFrozenBridge();
    Phase6ProofCapture->PostProcessSettings=Camera->PostProcessSettings;
    Phase6ProofCapture->ShowFlags.SetDynamicShadows(true);
    FVector Position=Camera->GetComponentLocation();FRotator Rotation=Camera->GetComponentRotation();
    if(Closeup)
    {
        FVector Target=ActualTips[0];
        if(Name.Contains(TEXT("organ")) && TissueVertices.Num())
        {Target=FVector::ZeroVector;for(auto P:TissueVertices)Target+=P;Target/=TissueVertices.Num();}
        const FVector Axis=(GetPivot(0)-Target).GetSafeNormal();
        const FVector ViewDirection=(Camera->GetComponentLocation()-Target).GetSafeNormal();
        if(Name.Contains(TEXT("organ")))
        {Position=Target+ViewDirection.RotateAngleAxis(18,FVector::UpVector)*10.5;}
        else
        {
            FVector Width=HeadRoots[0]->GetRightVector(),Opening=HeadRoots[0]->GetUpVector();
            if(FVector::DotProduct(Width,ViewDirection)<0)Width=-Width;
            if(FVector::DotProduct(Opening,ViewDirection)<0)Opening=-Opening;
            // Center the actual paired jaws and adjacent tissue. An elevated
            // side view exposes their gap without skimming the cavity wall.
            if(ToolJaws.Num()>=2 && ToolJaws[0] && ToolJaws[1])
                Target=(ToolJaws[0]->GetComponentLocation()+ToolJaws[1]->GetComponentLocation())*.5-Axis*.2;
            else Target+=Axis*.5;
            Position=Target+(Width*.75+Opening+Axis*.10).GetSafeNormal()*6.8;
        }
        Rotation=(Target-Position).Rotation();
    }
    Phase6ProofCapture->SetWorldLocationAndRotation(Position,Rotation);Phase6ProofCapture->FOVAngle=Closeup?48:Camera->FieldOfView;
    Phase6ProofCapture->CaptureSource=SCS_FinalColorLDR;Phase6ProofCapture->TextureTarget=Phase6ProofTarget;
    for(int I=0;I<32;++I){Phase6ProofCapture->CaptureScene();FlushRenderingCommands();Bridge->TickFrozenBridge();}
    TArray<FColor> Pixels;TArray64<uint8> PNG;
    if(Phase6ProofTarget->GameThread_GetRenderTargetResource()->ReadPixels(Pixels))
    {FImageUtils::PNGCompressImageArray(1920,1080,Pixels,PNG);FFileHelper::SaveArrayToFile(PNG,*FPaths::Combine(Phase5Directory,Name+TEXT(".png")));}
    bResumeSnapshot=true;
}

bool ATrainingScene::BuildPhase6StaticDisplay(UProceduralMeshComponent* Proxy,const TSharedPtr<FJsonObject>& Object)
{
    FString Asset;
    if(!Proxy || !Object->TryGetStringField(TEXT("static_mesh_asset"),Asset))
    {AnatomyError=TEXT("Phase6 static display asset is missing");return false;}
    auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Asset);
    if(!Mesh){AnatomyError=TEXT("Phase6 cooked static mesh unavailable: ")+Asset;return false;}
    auto* Display=NewObject<UStaticMeshComponent>(this,FName(*(Proxy->GetName()+TEXT("_Lumen"))));
    Display->SetupAttachment(SceneRoot);Display->SetMobility(EComponentMobility::Static);
    Display->SetStaticMesh(Mesh);Display->SetMaterial(0,Proxy->GetMaterial(0));
    Display->SetCollisionEnabled(ECollisionEnabled::NoCollision);Display->SetSimulatePhysics(false);
    Display->SetCastShadow(true);Display->SetVisibleInRayTracing(true);Display->SetAffectDynamicIndirectLighting(true);
    Display->RegisterComponent();Phase6StaticMeshes.Add(Display);
    // Retain exact authored triangles as the independent data-export reference.
    Proxy->SetVisibility(false);Proxy->SetCastShadow(false);Proxy->SetVisibleInRayTracing(false);
    return true;
}

void ATrainingScene::UpdatePhase6CameraInput(APlayerController* PC,float DeltaSeconds)
{
    if(!PC || bMouseReleased)return;
    bool Changed=false;
    if(PC->IsInputKeyDown(EKeys::MiddleMouseButton))
    {
        float X=0,Y=0;PC->GetInputMouseDelta(X,Y);
        Phase6CameraYaw=FMath::Clamp(Phase6CameraYaw+X*.18f,-35.f,35.f);
        Phase6CameraPitch=FMath::Clamp(Phase6CameraPitch+Y*.18f,-25.f,25.f);Changed=X!=0||Y!=0;
    }
    const int Zoom=int(PC->IsInputKeyDown(EKeys::PageDown))-int(PC->IsInputKeyDown(EKeys::PageUp));
    if(Zoom){Phase6CameraDistance=FMath::Clamp(Phase6CameraDistance+Zoom*DeltaSeconds*.4f,.65f,1.6f);Changed=true;}
    if(PC->WasInputKeyJustPressed(EKeys::Home)){Phase6CameraDistance=1;Phase6CameraYaw=Phase6CameraPitch=0;Changed=true;}
    if(Changed && ViewMode==3)ViewMode=0;
    if(Changed)UpdateCamera();
}
