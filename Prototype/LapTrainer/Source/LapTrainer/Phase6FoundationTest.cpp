#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "Camera/CameraComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "InputKeyEventArgs.h"
#include "InputCoreTypes.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformTime.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Dom/JsonObject.h"
#include "ImageUtils.h"
#include "RenderingThread.h"
#include "DynamicRHI.h"
#include "RHI.h"
#include "RHIStrings.h"
#include "ShaderPipelineCache.h"
#include "PipelineStateCache.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GenericPlatform/GenericApplication.h"
#include "UnrealClient.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

namespace
{
    double P6Percentile(TArray<double> Values,double Q)
    {
        if(Values.IsEmpty()) return -1;
        Values.Sort();const double Index=(Values.Num()-1)*Q;
        const int32 Lo=FMath::FloorToInt(Index),Hi=FMath::CeilToInt(Index);
        return FMath::Lerp(Values[Lo],Values[Hi],Index-Lo);
    }
    double P6Mean(const TArray<double>& Values)
    { double Sum=0;for(double V:Values)Sum+=V;return Values.Num()?Sum/Values.Num():-1; }
    TSharedPtr<FJsonValue> P6Vector(const FVector& V)
    { return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)}); }
    bool P6Save(const FString& Path,const TSharedRef<FJsonObject>& Object)
    { FString Text;auto Writer=TJsonWriterFactory<>::Create(&Text);FJsonSerializer::Serialize(Object,Writer);return FFileHelper::SaveStringToFile(Text,*Path,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM); }
    int32 P6CVar(const TCHAR* Name)
    { const auto* V=IConsoleManager::Get().FindConsoleVariable(Name);return V?V->GetInt():-1; }
    void P6Set(const TCHAR* Name,int32 Value)
    { if(auto* V=IConsoleManager::Get().FindConsoleVariable(Name))V->Set(Value,ECVF_SetByCode); }
    TSharedRef<FJsonObject> P6CVars()
    {
        auto O=MakeShared<FJsonObject>();
        for(const TCHAR* Name:{TEXT("r.DynamicGlobalIlluminationMethod"),TEXT("r.ReflectionMethod"),TEXT("r.RayTracing"),TEXT("r.Lumen.HardwareRayTracing"),TEXT("r.Lumen.DiffuseIndirect.Allow"),TEXT("r.Lumen.Reflections.Allow"),TEXT("r.Shadow.Virtual.Enable"),TEXT("r.RayTracing.Shadows"),TEXT("r.ShadowQuality"),TEXT("r.AntiAliasingMethod"),TEXT("r.ScreenPercentage")})
            O->SetNumberField(Name,P6CVar(Name));
        return O;
    }
    uint64 P6Applied(const USimulationBridge* Bridge)
    {
        double Seq=0;if(Bridge&&Bridge->GetAcceptedState().IsValid())Bridge->GetAcceptedState()->TryGetNumberField(TEXT("applied_command_seq"),Seq);
        return static_cast<uint64>(FMath::Max(0.0,Seq));
    }
    void P6Mouse(APlayerController* PC,double Delta,float Dt)
    {
        PC->InputKey(FInputKeyEventArgs(nullptr,FInputDeviceId::CreateFromInternalId(0),EKeys::MouseX,
            static_cast<float>(Delta),Dt,1,FPlatformTime::Cycles64()));
    }
}

FString ATrainingScene::GetPhase6StartupNotice() const
{
    if(bPhase6StartupFailed)return AnatomyError;
    if(!Bridge || !Bridge->IsConnected() || !bPhase5HomeAdopted)return TEXT("Connecting physics and loading anatomy...");
    return FString::Printf(TEXT("Preparing lighting and materials... %.1f s"),Phase6StartupDuration);
}

void ATrainingScene::RestorePhase6StartupRendering()
{
    if(auto* Viewport=Phase6StartupViewport.Get())Viewport->OnDrawn().Remove(Phase6StartupDrawHandle);
    Phase6StartupDrawHandle.Reset();Phase6StartupViewport.Reset();
    if(Phase6StartupPreviousRT>=0)
    {P6Set(TEXT("r.RayTracing.NonBlockingPipelineCreation"),Phase6StartupPreviousRT);Phase6StartupPreviousRT=-1;}
}

void ATrainingScene::OnPhase6StartupViewportDrawn()
{
    const auto* Viewport=Phase6StartupViewport.Get();
    auto* PC=UGameplayStatics::GetPlayerController(this,0);
    // OnDrawn also fires for skipped world rendering; mirror the actual draw guard.
    if(Viewport && !Viewport->bDisableWorldRendering && Viewport->Viewport &&
       Viewport->Viewport->GetSizeXY().X>0 && Viewport->Viewport->GetSizeXY().Y>0 &&
       PC && PC->GetLocalPlayer() && PC->GetViewTarget()==this &&
       FSlateApplication::IsInitialized() && FSlateApplication::Get().GetPlatformApplication()->IsAllowedToRender())
        ++Phase6StartupViewportDraws;
}

bool ATrainingScene::UpdatePhase6Startup()
{
    if(bPhase6StartupReady || bPhase6StartupFailed)return bPhase6StartupReady;
    const double Now=FPlatformTime::Seconds();
    if(Phase6StartupStarted<=0)
    {
        Phase6StartupStarted=Now;Phase6StartupStableSince=Now;
        Phase6StartupPreviousRT=P6CVar(TEXT("r.RayTracing.NonBlockingPipelineCreation"));
        // A complete material RT pipeline is required while rendering the real
        // initial viewport. An asynchronous opaque fallback is not readiness.
        P6Set(TEXT("r.RayTracing.NonBlockingPipelineCreation"),0);
        UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_STARTUP preparing actual viewport, input gated"));
    }
    Phase6StartupDuration=Now-Phase6StartupStarted;++Phase6StartupFrames;
    if(!Phase6StartupDrawHandle.IsValid())
        if(auto* Viewport=GetWorld()->GetGameViewport())
        {Phase6StartupViewport=Viewport;Phase6StartupDrawHandle=Viewport->OnDrawn().AddUObject(this,&ATrainingScene::OnPhase6StartupViewportDrawn);}
    const bool ViewDrawn=Phase6StartupViewportDraws>Phase6StartupLastViewportDraws;
    Phase6StartupLastViewportDraws=Phase6StartupViewportDraws;
    Phase6StartupPending=FShaderPipelineCache::NumPrecompilesRemaining();
    Phase6StartupPeakPending=FMath::Max(Phase6StartupPeakPending,Phase6StartupPending);
    const uint32 PSOs=PipelineStateCache::GetPSORuntimeCreationStats().TotalPSOCreations;
    bool Busy=Phase6StartupPending>0 || PipelineStateCache::IsPrecaching();
#if WITH_EDITOR
    Busy|=GShaderCompilingManager && GShaderCompilingManager->IsCompiling();
#endif
    const bool ModelReady=Bridge && Bridge->IsConnected() && Bridge->IsHealthy() && bPhase5HomeAdopted && bHasSurface;
    if(Busy || !ModelReady || !ViewDrawn || PSOs!=Phase6StartupPSOs)
    {Phase6StartupStableFrames=0;Phase6StartupStableSince=Now;bPhase6StartupFenceInvalidated|=bPhase6StartupFenceQueued;}
    else ++Phase6StartupStableFrames;
    Phase6StartupPSOs=PSOs;
    if(!AnatomyError.IsEmpty() || Phase6StartupDuration>90)
    {
        if(AnatomyError.IsEmpty())AnatomyError=TEXT("Scene preparation timed out. Close and relaunch the trainer.");
        bPhase6StartupFailed=true;RestorePhase6StartupRendering();
        UE_LOG(LogTemp,Error,TEXT("LAP_PHASE6_STARTUP failed: %s"),*AnatomyError);
        if(bPhase6Test)FinishPhase5Test(AnatomyError);
        return false;
    }
    const bool Stable=!Busy && ModelReady && ViewDrawn && Phase6StartupStableFrames>=120 && Now-Phase6StartupStableSince>=2;
    if(bPhase6StartupFenceQueued && bPhase6StartupFenceInvalidated && Phase6StartupFence.IsFenceComplete())
    {bPhase6StartupFenceQueued=false;bPhase6StartupFenceInvalidated=false;}
    if(!Stable)
    {
        // New work after a queued fence requires another fence after stability.
        return false;
    }
    if(!bPhase6StartupFenceQueued)
    {Phase6StartupFence.BeginFence(FRenderCommandFence::ESyncDepth::RHIThread);bPhase6StartupFenceQueued=true;return false;}
    if(bPhase6StartupFenceInvalidated || !Phase6StartupFence.IsFenceComplete())return false;
    RestorePhase6StartupRendering();bPhase6StartupReady=true;
    if(auto* PC=UGameplayStatics::GetPlayerController(this,0))PC->FlushPressedKeys();
    bPhase6PerfBaselineValid=false;bPhase5CapturePrevious=true;
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_STARTUP ready duration_s=%.3f frames=%d stable_frames=%d pending=%u peak_pending=%u runtime_psos=%u rhi_fence=complete viewport_frames=%d"),Phase6StartupDuration,Phase6StartupFrames,Phase6StartupStableFrames,Phase6StartupPending,Phase6StartupPeakPending,Phase6StartupPSOs,Phase6StartupViewportDraws);
    return true;
}

bool ATrainingScene::UpdatePhase6FoundationTest(float Dt)
{
    if(!bPhase6Test||bPhase6FoundationDone) return false;
    const double Now=FPlatformTime::Seconds();
    if(Phase6FoundationStartedSeconds<=0)Phase6FoundationStartedSeconds=Now;
    const double FoundationElapsed=Now-Phase6FoundationStartedSeconds;
    FString StartupFailure;
    if(!AnatomyError.IsEmpty())StartupFailure=AnatomyError;
    else if(FoundationElapsed>120)StartupFailure=TEXT("Phase 6 foundation exceeded 120 seconds");
    else if(FoundationElapsed>60&&!bPhase6ProofInProgress&&(!Bridge||!Bridge->IsConnected()||!bPhase5HomeAdopted))StartupFailure=TEXT("Phase 6 physics/anatomy connection did not become ready within 60 seconds");
    if(!StartupFailure.IsEmpty())
    {
        Phase6FoundationFailures.AddUnique(StartupFailure);bPhase6FoundationDone=true;bPhase6ProofInProgress=false;Phase6ProofVariant=-1;
        P6Set(TEXT("r.Lumen.DiffuseIndirect.Allow"),1);P6Set(TEXT("r.Lumen.Reflections.Allow"),1);P6Set(TEXT("r.ShadowQuality"),5);
        FinishPhase5Test(StartupFailure);return true;
    }
    APlayerController* PC=UGameplayStatics::GetPlayerController(this,0);
    if(!PC)return false;
    auto Fail=[&](const FString& Message){Phase6FoundationFailures.AddUnique(Message);UE_LOG(LogTemp,Error,TEXT("LAP_PHASE6_FOUNDATION %s"),*Message);};
    auto Release=[&](){StopTestMotion();SetTestKey(EKeys::RightMouseButton,false);SetTestKey(EKeys::C,false);SetTestKey(EKeys::R,false);P6Mouse(PC,0,Dt);};
    const int32 Pattern=Phase6InputTrial%8;
    const bool Mouse=Pattern>=6;
    auto MotionSample=[&](bool Stopped)
    {
        auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("trial"),Phase6InputTrial);O->SetNumberField(TEXT("tool"),ActiveTool);
        O->SetNumberField(TEXT("time_s"),Now);O->SetNumberField(TEXT("state_id"),Bridge->GetStateId());O->SetBoolField(TEXT("after_release"),Stopped);
        O->SetField(TEXT("target_tip_cm"),P6Vector(ToolTips[ActiveTool]));O->SetField(TEXT("actual_tip_cm"),P6Vector(ActualTips[ActiveTool]));
        Phase6MotionSamples.Add(MakeShared<FJsonValueObject>(O));
    };
    auto ObserveResponse=[&]()
    {
        if(!bPhase6ResponseObserved&&Bridge->GetStateId()>Phase6InputInitialState&&P6Applied(Bridge)>Phase6InputInitialCommand&&
            FVector::Distance(ActualTips[ActiveTool],Phase6InputOrigin)>.005)
        {
            bPhase6ResponseObserved=true;
            const double Latency=(Now-Phase6InputStarted)*1000;Phase6ResponseTimes.Add(Latency);
            auto Sample=MakeShared<FJsonObject>();Sample->SetNumberField(TEXT("trial"),Phase6InputTrial);
            Sample->SetNumberField(TEXT("tool"),ActiveTool);Sample->SetStringField(TEXT("input_source"),Mouse?TEXT("PlayerControllerMouse"):TEXT("PlayerControllerKeyboard"));
            Sample->SetStringField(TEXT("motion"),Mouse?(Pattern==6?TEXT("mouse_right"):TEXT("mouse_left")):(Pattern%2?TEXT("down"):TEXT("up")));
            Sample->SetStringField(TEXT("speed_mode"),Pattern<2?TEXT("precision"):Pattern<4?TEXT("default"):Pattern<6?TEXT("fast"):TEXT("mouse"));
            Sample->SetNumberField(TEXT("input_event_time_s"),Phase6InputStarted);
            Sample->SetNumberField(TEXT("accepted_state_received_time_s"),Now);
            Sample->SetStringField(TEXT("timestamp_semantics"),TEXT("UE actor observation of the newly accepted state; may follow socket receipt by one actor tick"));
            Sample->SetNumberField(TEXT("state_id"),Bridge->GetStateId());Sample->SetNumberField(TEXT("simulation_id"),Bridge->GetSimulationId());
            Sample->SetNumberField(TEXT("initial_state_id"),Phase6InputInitialState);
            Sample->SetNumberField(TEXT("initial_applied_command_seq"),Phase6InputInitialCommand);
            Sample->SetNumberField(TEXT("response_applied_command_seq"),P6Applied(Bridge));
            Sample->SetField(TEXT("initial_tip_cm"),P6Vector(Phase6InputOrigin));Sample->SetField(TEXT("actual_tip_cm"),P6Vector(ActualTips[ActiveTool]));
            Sample->SetNumberField(TEXT("response_threshold_mm"),.05);
            Phase6InputSamples.Add(MakeShared<FJsonValueObject>(Sample));
        }
    };
    if(Phase6InputStage<10)
    {
        if(!Bridge||!Bridge->IsConnected()||!bPhase5HomeAdopted)return false;
        if(!Bridge->IsHealthy()) {Fail(TEXT("Unhealthy native state during foundation input test"));Release();bPhase6FoundationDone=true;return false;}
    }
    switch(Phase6InputStage)
    {
    case 0:
        Release();SetTestKey(EKeys::R,true);Phase6InputStarted=Now;Phase6InputStage=1;break;
    case 1:
        SetTestKey(EKeys::R,false);
        if(Now-Phase6InputStarted>.8&&Bridge->HasAcknowledgedReset())Phase6InputStage=2;
        break;
    case 2:
        if(Phase6InputTrial>=16)
        { Release();SetTestKey(EKeys::R,true);Phase6InputStarted=Now;Phase6InputStage=10;break; }
        if(ActiveTool!=Phase6InputTrial/8)
        {SetTestKey(EKeys::C,true);Phase6InputStarted=Now;Phase6InputStage=3;break;}
        Release();Phase6InputOrigin=ActualTips[ActiveTool];Phase6InputInitialState=Bridge->GetStateId();
        Phase6InputInitialCommand=P6Applied(Bridge);Phase6InputStarted=Now;bPhase6ResponseObserved=false;
        Phase6TrialLead=0;Phase6StopTravel=0;
        if(Pattern<2)SetTestKey(EKeys::LeftControl,true);
        if(Pattern>=4&&Pattern<6)SetTestKey(EKeys::LeftShift,true);
        if(Mouse){SetTestKey(EKeys::RightMouseButton,true);P6Mouse(PC,Pattern==6?2.0:-2.0,Dt);}
        else SetTestKey(Pattern%2?EKeys::S:EKeys::W,true);
        Phase6InputStage=4;break;
    case 3:
        SetTestKey(EKeys::C,false);if(Now-Phase6InputStarted>.15)Phase6InputStage=2;break;
    case 4:
        ObserveResponse();
        MotionSample(false);
        Phase6TrialLead=FMath::Max(Phase6TrialLead,FVector::Distance(ToolTips[ActiveTool],ActualTips[ActiveTool])*10);
        if(Mouse)P6Mouse(PC,Pattern==6?2.0:-2.0,Dt);
        if(Now-Phase6InputStarted>=.30)
        {Release();Phase6InputStop=Now;Phase6StopPrevious=Phase6StopOrigin=ActualTips[ActiveTool];Phase6InputStage=5;MotionSample(true);}
        break;
    case 5:
        ObserveResponse();
        MotionSample(true);
        Phase6StopTravel+=FVector::Distance(Phase6StopPrevious,ActualTips[ActiveTool])*10;
        Phase6StopPrevious=ActualTips[ActiveTool];
        Phase6TrialLead=FMath::Max(Phase6TrialLead,FVector::Distance(ToolTips[ActiveTool],ActualTips[ActiveTool])*10);
        if(Now-Phase6InputStop>=.45)
        {
            if(!bPhase6ResponseObserved)Fail(FString::Printf(TEXT("Input trial %d produced no accepted actual-tip response"),Phase6InputTrial));
            Phase6PeakLead=FMath::Max(Phase6PeakLead,Phase6TrialLead);Phase6MaxStopTravel=FMath::Max(Phase6MaxStopTravel,Phase6StopTravel);
            auto Stop=MakeShared<FJsonObject>();Stop->SetNumberField(TEXT("trial"),Phase6InputTrial);Stop->SetNumberField(TEXT("tool"),ActiveTool);
            Stop->SetNumberField(TEXT("input_release_time_s"),Phase6InputStop);Stop->SetNumberField(TEXT("observation_end_time_s"),Now);
            Stop->SetNumberField(TEXT("post_release_path_length_mm"),Phase6StopTravel);Stop->SetNumberField(TEXT("target_lead_max_mm"),Phase6TrialLead);
            Stop->SetField(TEXT("release_tip_cm"),P6Vector(Phase6StopOrigin));Stop->SetField(TEXT("final_tip_cm"),P6Vector(ActualTips[ActiveTool]));
            Phase6StopSamples.Add(MakeShared<FJsonValueObject>(Stop));++Phase6InputTrial;Phase6InputStage=2;
        }
        break;
    case 10:
        SetTestKey(EKeys::R,false);
        if(Now-Phase6InputStarted>.8&&Bridge->HasAcknowledgedReset())
        {
            bPhase6ProofInProgress=true;bPhase5CapturePrevious=true;
            Phase6ProofState=Bridge->GetStateId();Phase6ProofSimulation=Bridge->GetSimulationId();
            Phase6ProofCamera=BuildCameraRecord();Phase6ProofVariant=0;Phase6ProofTicks=0;
            if(!Phase6ProofCapture)
            {
                Phase6ProofCapture=NewObject<USceneCaptureComponent2D>(this,TEXT("Phase6RenderingProof"));Phase6ProofCapture->SetupAttachment(SceneRoot);
                Phase6ProofCapture->bCaptureEveryFrame=false;Phase6ProofCapture->bCaptureOnMovement=false;Phase6ProofCapture->bAlwaysPersistRenderingState=true;
                Phase6ProofCapture->bUseRayTracingIfEnabled=true;
                Phase6ProofCapture->RegisterComponent();Phase6ProofTarget=NewObject<UTextureRenderTarget2D>(this,TEXT("Phase6RenderingProofTarget"));
                Phase6ProofTarget->RenderTargetFormat=RTF_RGBA8;Phase6ProofTarget->InitAutoFormat(1920,1080);Phase6ProofTarget->UpdateResourceImmediate(true);
            }
            Phase6ProofCapture->SetWorldLocationAndRotation(Camera->GetComponentLocation(),Camera->GetComponentRotation());Phase6ProofCapture->FOVAngle=Camera->FieldOfView;
            Phase6ProofCapture->bOverride_CustomNearClippingPlane=true;Phase6ProofCapture->CustomNearClippingPlane=.15f;
            Phase6ProofCapture->PostProcessSettings=Camera->PostProcessSettings;Phase6ProofCapture->PostProcessBlendWeight=1;
            Phase6ProofCapture->PostProcessSettings.bOverride_DynamicGlobalIlluminationMethod=true;Phase6ProofCapture->PostProcessSettings.DynamicGlobalIlluminationMethod=EDynamicGlobalIlluminationMethod::Lumen;
            Phase6ProofCapture->PostProcessSettings.bOverride_ReflectionMethod=true;Phase6ProofCapture->PostProcessSettings.ReflectionMethod=EReflectionMethod::Lumen;
            Phase6ProofCapture->PostProcessSettings.bOverride_MotionBlurAmount=true;Phase6ProofCapture->PostProcessSettings.MotionBlurAmount=0;
            Phase6ProofCapture->TextureTarget=Phase6ProofTarget;Phase6ProofCapture->CaptureSource=SCS_FinalColorLDR;
            Phase6ProofCapture->ShowFlags.SetMotionBlur(false);Phase6InputStage=11;
            Bridge->TickFrozenBridge();return true;
        }
        break;
    case 11:
    {
        // Native mechanics keep running. Only accepted displayed geometry and its
        // state identity remain frozen, exactly as in the stereo exporter.
        Bridge->TickFrozenBridge();bPhase5CapturePrevious=true;
        static const TCHAR* Names[]={TEXT("full"),TEXT("gi_off"),TEXT("reflections_off"),TEXT("shadows_off"),TEXT("full_repeat")};
        if(Phase6ProofTicks==0)
        {
            P6Set(TEXT("r.Lumen.DiffuseIndirect.Allow"),Phase6ProofVariant==1?0:1);
            P6Set(TEXT("r.Lumen.Reflections.Allow"),Phase6ProofVariant==2?0:1);
            P6Set(TEXT("r.ShadowQuality"),Phase6ProofVariant==3?0:5);
            Phase6ProofCapture->ShowFlags.SetDynamicShadows(Phase6ProofVariant!=3);
            UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_RENDER_PROOF %s state=%llu"),Names[Phase6ProofVariant],static_cast<unsigned long long>(Phase6ProofState));
        }
        Phase6ProofCapture->CaptureScene();FlushRenderingCommands();++Phase6ProofTicks;
        if(Phase6ProofTicks>=48)
        {
            TArray<FColor> Pixels;bool Ok=Phase6ProofTarget->GameThread_GetRenderTargetResource()->ReadPixels(Pixels);
            TArray64<uint8> Compressed;if(Ok)FImageUtils::PNGCompressImageArray(1920,1080,Pixels,Compressed);
            const FString Relative=FString::Printf(TEXT("render-proof-%s.png"),Names[Phase6ProofVariant]);
            Ok=Ok&&FFileHelper::SaveArrayToFile(Compressed,*FPaths::Combine(Phase5Directory,Relative));
            if(!Ok)Fail(TEXT("Render proof image export failed: ")+Relative);
            auto Image=MakeShared<FJsonObject>();Image->SetStringField(TEXT("variant"),Names[Phase6ProofVariant]);Image->SetStringField(TEXT("file"),Relative);
            Image->SetNumberField(TEXT("state_id"),Phase6ProofState);Image->SetNumberField(TEXT("simulation_id"),Phase6ProofSimulation);
            Image->SetObjectField(TEXT("camera"),Phase6ProofCamera);Image->SetObjectField(TEXT("cvars"),P6CVars());
            Image->SetBoolField(TEXT("exposure_locked"),Camera->PostProcessSettings.AutoExposureMethod==AEM_Manual);
            Image->SetBoolField(TEXT("displayed_geometry_frozen"),Bridge->GetStateId()==Phase6ProofState&&Bridge->GetSimulationId()==Phase6ProofSimulation);
            Image->SetBoolField(TEXT("native_simulation_paused"),false);Image->SetNumberField(TEXT("warmup_frames"),Phase6ProofTicks);
            Image->SetStringField(TEXT("capture_source"),TEXT("1920x1080 SceneCapture2D FinalColorLDR, persistent Lumen history, same fixed camera and displayed state"));
            Phase6Comparisons.Add(MakeShared<FJsonValueObject>(Image));++Phase6ProofVariant;Phase6ProofTicks=0;
            if(Phase6ProofVariant>=5)
            {
                P6Set(TEXT("r.Lumen.DiffuseIndirect.Allow"),1);P6Set(TEXT("r.Lumen.Reflections.Allow"),1);P6Set(TEXT("r.ShadowQuality"),5);
                bPhase6ProofInProgress=false;bPhase6FoundationDone=true;bPhase5CapturePrevious=true;bResumeSnapshot=true;Phase6ProofVariant=-1;
                Phase5PreviousNative=Bridge->GetNativeTime();Release();
                UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_FOUNDATION input_trials=%d samples=%d proof_images=%d"),Phase6InputTrial,Phase6InputSamples.Num(),Phase6Comparisons.Num());
            }
        }
        return true;
    }
    }
    return false;
}

void ATrainingScene::WritePhase6Runtime()
{
    auto Runtime=MakeShared<FJsonObject>();Runtime->SetStringField(TEXT("schema"),TEXT("endoforge.phase6.runtime.v1"));Runtime->SetNumberField(TEXT("phase"),6);
    const bool Diagnostic=FParse::Param(FCommandLine::Get(),TEXT("LapDiagnostic"));
    Runtime->SetStringField(TEXT("run_kind"),bPhase6Test?(Diagnostic?TEXT("diagnostic_test"):TEXT("acceptance_test")):TEXT("interactive_observation"));
    Runtime->SetStringField(TEXT("rhi"),GDynamicRHI?GDynamicRHI->GetName():TEXT("unavailable"));FString Shader;GetFeatureLevelName(GMaxRHIFeatureLevel,Shader);Runtime->SetStringField(TEXT("shader_model"),Shader);
    Runtime->SetObjectField(TEXT("cvars"),P6CVars());
    auto Startup=MakeShared<FJsonObject>();Startup->SetBoolField(TEXT("ready"),bPhase6StartupReady);
    Startup->SetBoolField(TEXT("failed"),bPhase6StartupFailed);Startup->SetNumberField(TEXT("duration_s"),Phase6StartupDuration);
    Startup->SetNumberField(TEXT("actor_ticks"),Phase6StartupFrames);Startup->SetNumberField(TEXT("rendered_viewport_frames"),Phase6StartupViewportDraws);Startup->SetNumberField(TEXT("stable_viewport_frames"),Phase6StartupStableFrames);
    Startup->SetNumberField(TEXT("pending_at_ready"),Phase6StartupPending);Startup->SetNumberField(TEXT("peak_pending"),Phase6StartupPeakPending);
    Startup->SetNumberField(TEXT("runtime_pso_creations"),Phase6StartupPSOs);Startup->SetBoolField(TEXT("rhi_fence_completed"),bPhase6StartupReady && Phase6StartupFence.IsFenceComplete());
    Startup->SetStringField(TEXT("scope"),TEXT("Same initial-viewport preparation in normal play and acceptance: actual procedural/static materials rendered, required RT pipeline blocks rather than using fallback, queues drained and PSO count stable for >=2s/120 guarded viewport draws, then RHI submission fence. Not a guarantee for unseen later views. Input is gated; startup time is reported separately, and all post-ready interactive samples are retained."));
    Runtime->SetObjectField(TEXT("startup"),Startup);
    Runtime->SetBoolField(TEXT("proof_capture_hardware_ray_tracing_requested"),Phase6ProofCapture && Phase6ProofCapture->bUseRayTracingIfEnabled);
    Runtime->SetNumberField(TEXT("ray_tracing_scene_captures_cvar"),P6CVar(TEXT("r.RayTracing.SceneCaptures")));
    auto Features=MakeShared<FJsonObject>();Features->SetBoolField(TEXT("lumen_gi"),P6CVar(TEXT("r.DynamicGlobalIlluminationMethod"))==1&&P6CVar(TEXT("r.Lumen.DiffuseIndirect.Allow"))==1);
    Features->SetBoolField(TEXT("lumen_reflections"),P6CVar(TEXT("r.ReflectionMethod"))==1&&P6CVar(TEXT("r.Lumen.Reflections.Allow"))==1);
    Features->SetBoolField(TEXT("hardware_ray_tracing"),GRHISupportsRayTracing&&P6CVar(TEXT("r.RayTracing"))==1);
    Features->SetBoolField(TEXT("lumen_hardware_ray_tracing"),GRHISupportsRayTracing&&P6CVar(TEXT("r.RayTracing"))==1&&P6CVar(TEXT("r.Lumen.HardwareRayTracing"))==1);
    Features->SetBoolField(TEXT("high_quality_shadows"),P6CVar(TEXT("r.ShadowQuality"))>=5&&(P6CVar(TEXT("r.Shadow.Virtual.Enable"))==1||P6CVar(TEXT("r.RayTracing.Shadows"))==1));Runtime->SetObjectField(TEXT("features"),Features);
    TArray<double> FrameMs;double Wall=0;for(float S:Phase5FrameTimes){FrameMs.Add(S*1000);Wall+=S;}
    auto Performance=MakeShared<FJsonObject>();Performance->SetNumberField(TEXT("mean_fps"),Wall>0?FrameMs.Num()/Wall:0);
    Performance->SetNumberField(TEXT("frame_p95_ms"),P6Percentile(FrameMs,.95));Performance->SetNumberField(TEXT("physics_step_mean_ms"),P6Mean(Phase6SolverTimes));Performance->SetNumberField(TEXT("physics_step_p95_ms"),P6Percentile(Phase6SolverTimes,.95));
    Performance->SetNumberField(TEXT("simulation_to_wall_ratio"),Phase5MeasuredWall>0?Phase5MeasuredNative/Phase5MeasuredWall:0);
    Performance->SetNumberField(TEXT("measured_wall_seconds"),Phase5MeasuredWall);Performance->SetNumberField(TEXT("measured_native_seconds"),Phase5MeasuredNative);
    Performance->SetNumberField(TEXT("display_measured_wall_seconds"),Wall);
    Performance->SetStringField(TEXT("progression_scope"),TEXT("All post-readiness live idle/recording progression; visible startup, frozen exports and post-freeze command-fence recovery excluded. New simulation IDs and mode changes rebuild baseline. Replay and replay-complete are excluded from solver throughput; normal replay display remains in FPS measurements."));
    Performance->SetNumberField(TEXT("display_frames"),FrameMs.Num());Performance->SetNumberField(TEXT("physics_step_samples"),Phase6SolverTimes.Num());
    Performance->SetNumberField(TEXT("gpu_samples"),Phase6GpuTimes.Num());if(Phase6GpuTimes.Num())Performance->SetNumberField(TEXT("gpu_frame_ms"),P6Mean(Phase6GpuTimes));else Performance->SetField(TEXT("gpu_frame_ms"),MakeShared<FJsonValueNull>());
    Performance->SetStringField(TEXT("gpu_measurement"),TEXT("UE GPU frame timestamp samples when available; unavailable is null, not zero load"));
    int32 Width=0,Height=0;if(auto* PC=UGameplayStatics::GetPlayerController(this,0))PC->GetViewportSize(Width,Height);
    Performance->SetNumberField(TEXT("width"),Width);Performance->SetNumberField(TEXT("height"),Height);Performance->SetBoolField(TEXT("capture_freeze_excluded"),true);
    if(bPhase6Test && !Diagnostic)Performance->SetNumberField(TEXT("concurrent_acceptance_workloads"),0);else Performance->SetField(TEXT("concurrent_acceptance_workloads"),MakeShared<FJsonValueNull>());
    Performance->SetStringField(TEXT("workload_scope"),TEXT("One owned UE/native package pair. External concurrent workload absence is also an orchestration condition; this process cannot enumerate other users' workloads."));
    Runtime->SetObjectField(TEXT("performance"),Performance);Runtime->SetArrayField(TEXT("render_comparisons"),Phase6Comparisons);
    Runtime->SetStringField(TEXT("visual_binding"),TEXT("Bounded cubic PN display surface, maximum 0.12 mm from native linear boundary; actual rendered triangles are exported"));
    Runtime->SetNumberField(TEXT("dynamic_render_vertices"),TissueRenderData.Positions.Num());Runtime->SetNumberField(TEXT("dynamic_render_triangles"),TissueRenderData.Triangles.Num()/3);
    if(!bPhase6Test)
    {
        Runtime->SetStringField(TEXT("scope"),TEXT("Normal interactive session observations, not an acceptance exercise; no synthetic input trials or feature ablations requested."));
        P6Save(FPaths::Combine(Phase5Directory,TEXT("phase6-runtime.json")),Runtime);
        UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_RUNTIME interactive observation saved; no acceptance result requested"));
        return;
    }
    auto Interaction=MakeShared<FJsonObject>();Interaction->SetStringField(TEXT("schema"),TEXT("endoforge.phase6.interaction.v1"));Interaction->SetNumberField(TEXT("phase"),6);
    Interaction->SetStringField(TEXT("latency_definition"),TEXT("PlayerController input event to first accepted actual-tip displacement >0.05 mm observed by the UE actor; includes one possible actor-tick scheduling delay; not hardware motion-to-photon"));
    auto Metrics=MakeShared<FJsonObject>();Metrics->SetNumberField(TEXT("response_p95_ms"),P6Percentile(Phase6ResponseTimes,.95));Metrics->SetNumberField(TEXT("target_lead_max_mm"),Phase6PeakLead);Metrics->SetNumberField(TEXT("stop_residual_travel_max_mm"),Phase6MaxStopTravel);
    Interaction->SetObjectField(TEXT("metrics"),Metrics);Interaction->SetArrayField(TEXT("samples"),Phase6InputSamples);Interaction->SetArrayField(TEXT("stop_samples"),Phase6StopSamples);Interaction->SetArrayField(TEXT("motion_samples"),Phase6MotionSamples);
    auto Checks=MakeShared<FJsonObject>();Checks->SetBoolField(TEXT("sixteen_real_controller_trials"),Phase6InputSamples.Num()==16&&Phase6StopSamples.Num()==16);
    Checks->SetBoolField(TEXT("product_startup_ready"),bPhase6StartupReady && !bPhase6StartupFailed && Phase6StartupPending==0 && Phase6StartupStableFrames>=120);
    Checks->SetBoolField(TEXT("latency_p95_within_150ms"),Phase6ResponseTimes.Num()==16&&P6Percentile(Phase6ResponseTimes,.95)<=150);
    // A micrometre-millionth tolerance handles accumulated double roundoff at
    // exactly 1 mm; the physical acceptance bound remains 1 mm.
    Checks->SetBoolField(TEXT("target_lead_within_1mm"),Phase6PeakLead<=1+1.e-9);Checks->SetBoolField(TEXT("post_release_travel_within_1mm"),Phase6MaxStopTravel<=1+1.e-9);
    Checks->SetBoolField(TEXT("five_frozen_render_comparisons"),Phase6Comparisons.Num()==5);Checks->SetBoolField(TEXT("healthy_native"),Bridge&&Bridge->IsHealthy()&&Bridge->GetSafetyStopCount()==0);
    Interaction->SetObjectField(TEXT("checks"),Checks);bool Passed=Phase6FoundationFailures.IsEmpty();for(const auto& Pair:Checks->Values)Passed&=Pair.Value->AsBool();Interaction->SetBoolField(TEXT("passed"),Passed);
    TArray<TSharedPtr<FJsonValue>> Errors;for(const auto& E:Phase6FoundationFailures)Errors.Add(MakeShared<FJsonValueString>(E));Interaction->SetArrayField(TEXT("errors"),Errors);
    if(!P6Save(FPaths::Combine(Phase5Directory,TEXT("phase6-runtime.json")),Runtime)||!P6Save(FPaths::Combine(Phase5Directory,TEXT("phase6-interaction-test.json")),Interaction))Phase5Failures.AddUnique(TEXT("Phase 6 runtime evidence write failed"));
    if(!Passed)Phase5Failures.AddUnique(TEXT("Phase 6 foundation input acceptance failed"));
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE6_RUNTIME input=%s p95_ms=%.3f lead_mm=%.3f stop_mm=%.3f fps=%.2f sim_wall=%.4f"),Passed?TEXT("PASS"):TEXT("FAIL"),P6Percentile(Phase6ResponseTimes,.95),Phase6PeakLead,Phase6MaxStopTravel,Wall>0?FrameMs.Num()/Wall:0,Phase5MeasuredWall>0?Phase5MeasuredNative/Phase5MeasuredWall:0);
}
