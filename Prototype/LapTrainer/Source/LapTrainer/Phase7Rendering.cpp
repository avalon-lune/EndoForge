#include "TrainingScene.h"
#include "Camera/CameraComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "HAL/IConsoleManager.h"
#include "SimulationBridge.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "UnrealClient.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Misc/SecureHash.h"
#include "HAL/FileManager.h"
#include "ImageUtils.h"
#include "Materials/Material.h"
#include "Engine/SubsurfaceProfile.h"
#include "MaterialShared.h"
#include "RHI.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "ProceduralMeshComponent.h"
#include "RenderingThread.h"
#include "Serialization/JsonSerializer.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#if WITH_EDITOR
#include "ShaderCompiler.h"
#endif

namespace
{
TArray<TSharedPtr<FJsonValue>> P7Vector(const FVector& V)
{
    return {MakeShared<FJsonValueNumber>(V.X),MakeShared<FJsonValueNumber>(V.Y),MakeShared<FJsonValueNumber>(V.Z)};
}
}

void ATrainingScene::ConfigurePhase7Rendering()
{
    if(!AnatomyAsset.IsValid())return;
    const TSharedPtr<FJsonObject>* Profile=nullptr;
    FString Schema,Identity;
    if(!AnatomyAsset->TryGetObjectField(bPhase9?TEXT("phase9_render"):bPhase8?TEXT("phase8_render"):TEXT("phase7_render"),Profile) ||
       !(*Profile)->TryGetStringField(TEXT("schema"),Schema) || Schema!=(bPhase9?TEXT("endoforge.phase9.render_profile.v1"):bPhase8?TEXT("endoforge.phase8.render_profile.v1"):TEXT("endoforge.phase7.render_profile.v1")) ||
       !(*Profile)->TryGetStringField(TEXT("id"),Identity) || Identity.IsEmpty())
    {AnatomyError=FString::Printf(TEXT("Phase%d requires an explicit versioned render profile"),GetMilestone());return;}
    auto Number=[&](const TCHAR* Key,double Fallback,double Minimum,double Maximum)
    {
        double Value=Fallback;
        if(!(*Profile)->TryGetNumberField(Key,Value))
        {AnatomyError=FString::Printf(TEXT("Missing Phase%d render parameter: %s"),GetMilestone(),Key);return Fallback;}
        if(!FMath::IsFinite(Value) || Value<Minimum || Value>Maximum)
        {AnatomyError=FString::Printf(TEXT("Invalid Phase%d render parameter: %s"),GetMilestone(),Key);return Fallback;}
        return Value;
    };
    const double Intensity=Number(TEXT("light_intensity_cd"),.12,.005,2);
    const double Radius=Number(TEXT("light_source_radius_cm"),.16,.01,1);
    const double Exposure=Number(TEXT("exposure_bias"),0,-3,3);
    const double Vignette=Number(TEXT("vignette"),.08,0,.25);
    const double Bloom=Number(TEXT("bloom"),.025,0,.1);
    FVector Color(1,.97,.92);
    const TArray<TSharedPtr<FJsonValue>>* Values=nullptr;
    if(!(*Profile)->TryGetArrayField(TEXT("light_color_linear"),Values))
    {AnatomyError=FString::Printf(TEXT("Phase%d light color must be explicitly recorded"),GetMilestone());return;}
    else
    {
        if(Values->Num()!=3){AnatomyError=FString::Printf(TEXT("Phase%d light color must have three channels"),GetMilestone());return;}
        for(int I=0;I<3;++I)
        {
            if(!(*Values)[I]->TryGetNumber(Color[I]) || !FMath::IsFinite(Color[I]) || Color[I]<.1 || Color[I]>1)
            {AnatomyError=FString::Printf(TEXT("Invalid Phase%d light color"),GetMilestone());return;}
        }
    }
    auto& P=Camera->PostProcessSettings;
    P.bOverride_AutoExposureMethod=true;P.AutoExposureMethod=AEM_Manual;
    P.bOverride_AutoExposureBias=true;P.AutoExposureBias=Exposure;
    P.bOverride_AutoExposureApplyPhysicalCameraExposure=true;P.AutoExposureApplyPhysicalCameraExposure=false;
    P.bOverride_VignetteIntensity=true;P.VignetteIntensity=Vignette;
    P.bOverride_BloomIntensity=true;P.BloomIntensity=Bloom;
    P.bOverride_MotionBlurAmount=true;P.MotionBlurAmount=0;
    P.bOverride_SceneFringeIntensity=true;P.SceneFringeIntensity=0;
    // One near-axis illuminator models the common endoscope presentation.
    // No view-dependent color overlays, geometry displacement or lens warp.
    if(EndoscopeLight)
    {
        EndoscopeLight->SetIntensity(Intensity);
        EndoscopeLight->SetLightColor(FLinearColor(Color.X,Color.Y,Color.Z));
        EndoscopeLight->SetSourceRadius(Radius);
        EndoscopeLight->SetRelativeLocation(FVector(0,.12,.05));
        EndoscopeLight->SetInnerConeAngle(32);EndoscopeLight->SetOuterConeAngle(52);
        EndoscopeLight->SetShadowBias(.05);EndoscopeLight->SetShadowSlopeBias(.05);
        EndoscopeLight->SetCastShadows(true);
        EndoscopeLight->SetCastRaytracedShadows(ECastRayTracedShadow::Enabled);
        EndoscopeLight->ContactShadowLength=.35;EndoscopeLight->ContactShadowLengthInWS=true;
    }
    if(bPhase9 && FParse::Param(FCommandLine::Get(),TEXT("LapPhase9Grey")))
    {
        if(!FParse::Param(FCommandLine::Get(),TEXT("LapDiagnostic")))
        {AnatomyError=TEXT("Neutral-grey surface inspection requires -LapDiagnostic");return;}
        auto* Grey=LoadObject<UMaterial>(nullptr,TEXT("/Game/Phase9/Materials/M_Phase9DiagnosticGrey.M_Phase9DiagnosticGrey"));
        if(!Grey){AnatomyError=TEXT("Phase9 diagnostic grey material unavailable");return;}
        TissueMesh->SetMaterial(0,Grey);if(AnatomyAttachment)AnatomyAttachment->SetMaterial(0,Grey);
        for(auto Mesh:AnatomyMeshes)if(Mesh)Mesh->SetMaterial(0,Grey);
        for(auto Mesh:Phase6StaticMeshes)if(Mesh)Mesh->SetMaterial(0,Grey);
    }
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE%d_RENDER profile=%s light_cd=%.6f exposure=%.3f; physical identity separately recorded, no spatial postprocess"),GetMilestone(),*Identity,Intensity,Exposure);
#if WITH_EDITOR
    // UE5.7 can report compilation finished while on-demand permutations have
    // not yet been requested. Match UMaterialInterface::EnsureIsComplete's
    // submission step, but let the regular startup loop drain jobs without
    // blocking the physics bridge on the game thread.
    for(const FString& Path:{CommonMaterialPath(TEXT("M_Anatomy")),CommonMaterialPath(TEXT("M_Metal")),CommonMaterialPath(TEXT("M_Insulation"))})
    {
        auto* Material=LoadObject<UMaterial>(nullptr,*Path);
        auto* Resource=Material?Material->GetMaterialResource(GMaxRHIShaderPlatform):nullptr;
        if(Resource && !Resource->IsGameThreadShaderMapComplete())
        {
            Resource->IsCompilationFinished(); // Resolve deferred shader-cache lookup first.
            Resource->SubmitCompileJobs_GameThread(EShaderCompileJobPriority::ForceLocal);
            UE_LOG(LogTemp,Display,TEXT("LAP_PHASE%d_MATERIAL_PREPARE requested complete shader map: %s"),GetMilestone(),*Path);
        }
    }
#endif
    bPhase7ShapeReview=FParse::Param(FCommandLine::Get(),TEXT("LapPhase7ShapeReview")) || FParse::Param(FCommandLine::Get(),TEXT("LapPhase8ShapeReview")) || FParse::Param(FCommandLine::Get(),TEXT("LapPhase9ShapeReview"));
    if(bPhase7ShapeReview && !FParse::Param(FCommandLine::Get(),TEXT("LapDiagnostic")))
    {AnatomyError=TEXT("Multi-angle inspection requires -LapDiagnostic");return;}
    if(FParse::Param(FCommandLine::Get(),TEXT("LapPhase7Video")) || FParse::Param(FCommandLine::Get(),TEXT("LapPhase8Video")) || FParse::Param(FCommandLine::Get(),TEXT("LapPhase9Video")))
    {
        if(!FParse::Param(FCommandLine::Get(),TEXT("LapDiagnostic")))
        {AnatomyError=FString::Printf(TEXT("Video readback is diagnostic only; -LapPhase%dVideo requires -LapDiagnostic"),GetMilestone());return;}
        Phase7VideoDirectory=FPaths::Combine(Phase5Directory,TEXT("video"));
        IFileManager::Get().MakeDirectory(*Phase7VideoDirectory,true);
        if(auto* Viewport=GetWorld()->GetGameViewport())
        {
            bPhase7Video=true;Phase7VideoViewport=Viewport;
            Phase7VideoDrawHandle=Viewport->OnDrawn().AddUObject(this,&ATrainingScene::OnPhase7VideoFrame);
        }
        else AnatomyError=TEXT("Diagnostic video requires an actual game viewport");
    }
}

TSharedRef<FJsonObject> ATrainingScene::BuildPhase7VisualSettings() const
{
    auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("schema"),bPhase9?TEXT("endoforge.phase9.appearance.v1"):bPhase8?TEXT("endoforge.phase8.appearance.v1"):TEXT("endoforge.phase7.appearance.v1"));
    O->SetNumberField(TEXT("phase"),GetMilestone());O->SetNumberField(TEXT("mechanics_phase"),6);
    const TSharedPtr<FJsonObject>* Profile=nullptr;
    if(AnatomyAsset.IsValid() && AnatomyAsset->TryGetObjectField(bPhase9?TEXT("phase9_render"):bPhase8?TEXT("phase8_render"):TEXT("phase7_render"),Profile))O->SetObjectField(TEXT("authored_profile"),*Profile);
    O->SetStringField(TEXT("scope"),TEXT("Shared anatomical presentation, not a calibrated device profile or Project1/2 dataset. Native physical asset identity is separate from this appearance identity."));
    O->SetStringField(TEXT("anatomy_material_asset"),CommonMaterialPath(TEXT("M_Anatomy")));
    O->SetStringField(TEXT("instrument_material_asset"),CommonMaterialPath(TEXT("M_Metal")));
    O->SetStringField(TEXT("insulation_material_asset"),CommonMaterialPath(TEXT("M_Insulation")));
    if(bPhase8)
    {
        const auto* Tissue=LoadObject<UMaterial>(nullptr,*CommonMaterialPath(TEXT("M_Anatomy")));
        auto SSS=MakeShared<FJsonObject>();
        SSS->SetBoolField(TEXT("profile_shading_model"),Tissue && Tissue->GetShadingModels().HasShadingModel(MSM_SubsurfaceProfile));
        if(Tissue && Tissue->SubsurfaceProfile)
        {
            const auto* Asset=Tissue->SubsurfaceProfile.Get();const auto& S=Asset->Settings;
            SSS->SetStringField(TEXT("asset"),Asset->GetPathName());
            SSS->SetBoolField(TEXT("burley"),S.bEnableBurley);SSS->SetBoolField(TEXT("mean_free_path_enabled"),S.bEnableMeanFreePath);
            SSS->SetNumberField(TEXT("mean_free_path_distance_cm"),S.MeanFreePathDistance);
            SSS->SetArrayField(TEXT("mean_free_path_color"),P7Vector(FVector(S.MeanFreePathColor.R,S.MeanFreePathColor.G,S.MeanFreePathColor.B)));
            SSS->SetNumberField(TEXT("world_unit_scale"),S.WorldUnitScale);
            SSS->SetNumberField(TEXT("roughness0"),S.Roughness0);SSS->SetNumberField(TEXT("roughness1"),S.Roughness1);
            SSS->SetNumberField(TEXT("lobe_mix"),S.LobeMix);SSS->SetNumberField(TEXT("ior"),S.IOR);
            SSS->SetStringField(TEXT("implementation"),S.Implementation==ESubsurfaceImplementationTechniqueHint::SIH_Separable?TEXT("separable"):TEXT("adaptive_filtered_importance_sampling"));
        }
        O->SetObjectField(TEXT("actual_subsurface_profile"),SSS);
    }
    auto Steel=MakeShared<FJsonObject>();Steel->SetStringField(TEXT("revision"),TEXT("brushed-steel-v2"));
    Steel->SetStringField(TEXT("scope"),TEXT("Opaque metallic BRDF; no emission or extra fill lights. Roughness adds bounded UV brushing variation +/-0.025; mesh tangent frame defines anisotropy; low-amplitude shading normal only."));
    for(const TCHAR* Key:{TEXT("SteelRoughness"),TEXT("SteelAnisotropy"),TEXT("SteelMetallic")})
    {float Value=0;if(MetalMaterial&&MetalMaterial->GetScalarParameterValue(FMaterialParameterInfo(FName(Key)),Value))Steel->SetNumberField(Key,Value);else Steel->SetField(Key,MakeShared<FJsonValueNull>());}
    FLinearColor SteelColor;if(MetalMaterial&&MetalMaterial->GetVectorParameterValue(FMaterialParameterInfo(TEXT("SteelBaseColor")),SteelColor))Steel->SetArrayField(TEXT("SteelBaseColor"),P7Vector(FVector(SteelColor.R,SteelColor.G,SteelColor.B)));
    O->SetObjectField(TEXT("instrument_material_parameters"),Steel);
    O->SetStringField(TEXT("asset_identity"),TEXT("visual-manifest SHA1 binds scene and texture bytes, applied material parameters and actual render settings; delivery receipt additionally binds cooked content and executable"));
    const auto& P=Camera->PostProcessSettings;
    auto Actual=MakeShared<FJsonObject>();
    Actual->SetBoolField(TEXT("manual_exposure"),P.AutoExposureMethod==AEM_Manual);
    Actual->SetBoolField(TEXT("physical_camera_exposure"),P.AutoExposureApplyPhysicalCameraExposure);
    Actual->SetNumberField(TEXT("exposure_bias"),P.AutoExposureBias);
    Actual->SetNumberField(TEXT("vignette"),P.VignetteIntensity);Actual->SetNumberField(TEXT("bloom"),P.BloomIntensity);
    Actual->SetNumberField(TEXT("motion_blur"),P.MotionBlurAmount);Actual->SetNumberField(TEXT("chromatic_aberration"),P.SceneFringeIntensity);
    Actual->SetNumberField(TEXT("horizontal_fov_degrees"),Camera->FieldOfView);
    Actual->SetNumberField(TEXT("lumen_scene_quality"),P.LumenSceneLightingQuality);
    Actual->SetNumberField(TEXT("lumen_scene_detail"),P.LumenSceneDetail);
    Actual->SetNumberField(TEXT("lumen_final_gather_quality"),P.LumenFinalGatherQuality);
    Actual->SetNumberField(TEXT("lumen_reflection_quality"),P.LumenReflectionQuality);
    if(EndoscopeLight)
    {
        Actual->SetNumberField(TEXT("light_intensity_cd"),EndoscopeLight->Intensity);
        Actual->SetNumberField(TEXT("light_source_radius_cm"),EndoscopeLight->SourceRadius);
        const FLinearColor C=EndoscopeLight->GetLightColor();Actual->SetArrayField(TEXT("light_color_linear"),P7Vector(FVector(C.R,C.G,C.B)));
        Actual->SetArrayField(TEXT("light_relative_position_cm"),P7Vector(EndoscopeLight->GetRelativeLocation()));
        Actual->SetNumberField(TEXT("light_inner_cone_degrees"),EndoscopeLight->InnerConeAngle);
        Actual->SetNumberField(TEXT("light_outer_cone_degrees"),EndoscopeLight->OuterConeAngle);
        Actual->SetNumberField(TEXT("light_shadow_bias"),EndoscopeLight->ShadowBias);
        Actual->SetNumberField(TEXT("light_contact_shadow_length_cm"),EndoscopeLight->ContactShadowLength);
    }
    O->SetObjectField(TEXT("actual_settings"),Actual);
    O->SetArrayField(TEXT("material_shader_checks"),Phase7ShaderRecords);
    O->SetBoolField(TEXT("spatial_postprocess_applied"),false);
    O->SetBoolField(TEXT("world_position_offset_applied"),false);
    O->SetStringField(TEXT("dynamic_shading_normals"),TEXT("Two-pass edge-aware smoothing of native area normals (weight0.2, dot>=0.5), barycentrically interpolated after unchanged bounded PN positions; affects shading only, not geometric normals or silhouettes"));
    if(bPhase9)
    {
        O->SetStringField(TEXT("dynamic_shading_normals"),TEXT("Area-weighted normals of actual displayed triangles, accumulated across equal native-node barycentric supports; no spatial proximity welding, no smoothing across distinct cut identities."));
        O->SetStringField(TEXT("dynamic_surface_method"),TEXT("smooth_bounded_pn_triangle_v1: linear + delta * cap*tanh(length(delta)/cap)/length(delta); cap=0.12mm; native area normals; 8 subdivisions; delta zero preserved."));
        O->SetStringField(TEXT("dynamic_position_algorithm"),TEXT("smooth_bounded_pn_triangle_v1"));
        O->SetBoolField(TEXT("diagnostic_neutral_grey"),FParse::Param(FCommandLine::Get(),TEXT("LapPhase9Grey")));
    }
    O->SetStringField(TEXT("dynamic_uv_algorithm"),TEXT("periodic_u_triangle_unwrap_pole_mean_v1"));
    O->SetStringField(TEXT("manual_command_controller"),TEXT("phase7-outstanding-polyline-budget-v1: 1mm total accepted native target plus unacknowledged manual target path; bounded user intent distinct from actual queued target; native receipt-time hold; presets and finite wheel pulses unchanged"));
    O->SetStringField(TEXT("attachment_visual_geometry"),TEXT("Ordered continuous spring-boundary ribbon, exact native endpoints, Catmull-Rom interpolation capped 0.12mm from original triangles, arc-length UV with coincident seam. Actual geometry500 includes reconstructable binding; no independent membrane FEM or transparency masking."));
    O->SetStringField(TEXT("geometric_labels"),TEXT("Undistorted frozen pinhole views; RGB/depth use matching camera and triangles. Geometric normals exclude material normal-map microstructure. Main display AA is separate from no-AA paired capture."));
    return O;
}


void ATrainingScene::OnPhase7VideoFrame()
{
    if(!bPhase7Video || !bPhase6StartupReady || !Bridge || !Bridge->IsHealthy() ||
       (bPhase6Test && !bPhase6FoundationDone))return;
    auto* Viewport=Phase7VideoViewport.Get();
    if(!Viewport || Viewport->bDisableWorldRendering || !Viewport->Viewport)return;
    const double Now=FPlatformTime::Seconds();
    if(Phase7VideoStarted<=0)Phase7VideoStarted=Now;
    if(Now-Phase7VideoStarted>120 || Phase7VideoFrames>=1200)
    {StopPhase7Video(TEXT("bounded_capture_limit"));return;}
    if(Phase7VideoLastFrame>=0 && Now-Phase7VideoLastFrame<.1)return;
    const FIntPoint Size=Viewport->Viewport->GetSizeXY();
    if(Size.X<=0 || Size.Y<=0)return;
    const uint64 State=Bridge->GetStateId(),Simulation=Bridge->GetSimulationId(),Step=Bridge->GetStepIndex();
    const double NativeTime=Bridge->GetNativeTime();
    auto CameraRecord=BuildCameraRecord();
    TArray<FColor> Full,Small;
    if(!Viewport->Viewport->ReadPixels(Full) || Full.Num()!=Size.X*Size.Y)
    {Phase7VideoError=TEXT("Actual viewport readback failed");StopPhase7Video(TEXT("readback_failed"));return;}
    const int32 W=FMath::Min(960,Size.X),H=FMath::Max(2,FMath::RoundToInt(double(Size.Y)*W/Size.X/2)*2);
    FImageUtils::ImageResize(Size.X,Size.Y,Full,W,H,Small,true);
    TArray64<uint8> PNG;FImageUtils::PNGCompressImageArray(W,H,Small,PNG);
    const FString Name=FString::Printf(TEXT("frame-%06d.png"),Phase7VideoFrames);
    if(!FFileHelper::SaveArrayToFile(PNG,*FPaths::Combine(Phase7VideoDirectory,Name)))
    {Phase7VideoError=TEXT("Diagnostic video image write failed");StopPhase7Video(TEXT("image_write_failed"));return;}
    auto Frame=MakeShared<FJsonObject>();Frame->SetNumberField(TEXT("frame"),Phase7VideoFrames);
    Frame->SetStringField(TEXT("file"),Name);Frame->SetNumberField(TEXT("wall_elapsed_s"),Now-Phase7VideoStarted);
    Frame->SetNumberField(TEXT("monotonic_readback_started_s"),Now);Frame->SetNumberField(TEXT("native_time_s"),NativeTime);
    Frame->SetNumberField(TEXT("state_id"),State);Frame->SetNumberField(TEXT("simulation_id"),Simulation);Frame->SetNumberField(TEXT("step_index"),Step);
    Frame->SetArrayField(TEXT("source_viewport_size"),{MakeShared<FJsonValueNumber>(Size.X),MakeShared<FJsonValueNumber>(Size.Y)});
    Frame->SetArrayField(TEXT("video_size"),{MakeShared<FJsonValueNumber>(W),MakeShared<FJsonValueNumber>(H)});
    Frame->SetObjectField(TEXT("source_viewport_camera"),CameraRecord);
    Frame->SetStringField(TEXT("visual_manifest_sha1"),AnatomyVisualFingerprint);
    Frame->SetStringField(TEXT("native_session_mode"),Bridge->GetSessionMode());
    Frame->SetBoolField(TEXT("snapshot_or_export_frozen"),bSnapshotFrozen||bPhase5CapturePrevious);
    uint8 Digest[20];FSHA1::HashBuffer(PNG.GetData(),PNG.Num(),Digest);Frame->SetStringField(TEXT("png_sha1"),BytesToHex(Digest,20).ToLower());
    FString Text;FJsonSerializer::Serialize(Frame,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    if(!FFileHelper::SaveStringToFile(Text+TEXT("\n"),*FPaths::Combine(Phase7VideoDirectory,TEXT("frames.jsonl")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,&IFileManager::Get(),FILEWRITE_Append))
    {Phase7VideoError=TEXT("Diagnostic video identity write failed");StopPhase7Video(TEXT("identity_write_failed"));return;}
    ++Phase7VideoFrames;Phase7VideoLastFrame=Now;
}

void ATrainingScene::StopPhase7Video(const FString& Reason)
{
    if(auto* Viewport=Phase7VideoViewport.Get())Viewport->OnDrawn().Remove(Phase7VideoDrawHandle);
    Phase7VideoDrawHandle.Reset();Phase7VideoViewport.Reset();
    if(!bPhase7Video)return;bPhase7Video=false;
    auto Report=MakeShared<FJsonObject>();Report->SetStringField(TEXT("schema"),bPhase9?TEXT("endoforge.phase9.viewport_video.v1"):TEXT("endoforge.phase7.viewport_video.v1"));
    Report->SetNumberField(TEXT("phase"),GetMilestone());Report->SetBoolField(TEXT("diagnostic_only"),true);
    Report->SetNumberField(TEXT("frames"),Phase7VideoFrames);Report->SetNumberField(TEXT("maximum_capture_hz"),10);
    Report->SetNumberField(TEXT("maximum_duration_s"),120);Report->SetNumberField(TEXT("maximum_frames"),1200);
    Report->SetNumberField(TEXT("last_frame_elapsed_s"),Phase7VideoLastFrame>=0?Phase7VideoLastFrame-Phase7VideoStarted:0);
    Report->SetStringField(TEXT("stop_reason"),Reason);Report->SetStringField(TEXT("error"),Phase7VideoError);
    Report->SetStringField(TEXT("frame_records"),TEXT("frames.jsonl"));Report->SetStringField(TEXT("visual_manifest_sha1"),AnatomyVisualFingerprint);
    Report->SetStringField(TEXT("scope"),TEXT("Actual game viewport readback after OnDrawn, resized in linear color space to <=960px wide. Recorded camera describes the original viewport. Variable timestamp spacing includes actual rendering/readback/encoding costs and freeze gaps. This diagnostic is excluded from acceptance performance. State IDs are the accepted state supplied to that viewport draw; not hardware display presentation timestamps."));
    FString Text;FJsonSerializer::Serialize(Report,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text));
    FFileHelper::SaveStringToFile(Text,*FPaths::Combine(Phase7VideoDirectory,TEXT("video.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE%d_VIDEO frames=%d reason=%s error=%s"),GetMilestone(),Phase7VideoFrames,*Reason,*Phase7VideoError);
}


bool ATrainingScene::ValidatePhase7Materials()
{
    Phase7ShaderRecords.Reset();
    for(const FString& Path:{CommonMaterialPath(TEXT("M_Anatomy")),CommonMaterialPath(TEXT("M_Metal")),CommonMaterialPath(TEXT("M_Insulation"))})
    {
        auto* Material=LoadObject<UMaterial>(nullptr,*Path);
        auto* Resource=Material?Material->GetMaterialResource(GMaxRHIShaderPlatform):nullptr;
#if WITH_EDITOR
        const bool ErrorInspectionAvailable=true;
        const bool ErrorsEmpty=Resource && Resource->GetCompileErrors().IsEmpty();
        const bool Finished=Resource && Resource->IsCompilationFinished();
#else
        const bool ErrorInspectionAvailable=false,ErrorsEmpty=false;
        // Packaged builds have no runtime material compiler. Their evidence is
        // the complete precompiled cooked map, independently checked below.
        const bool Finished=Resource && Resource->IsGameThreadShaderMapComplete();
#endif
        const auto* Shader=Resource?Resource->GetGameThreadShaderMap():nullptr;
        const bool Valid=Shader && Shader->IsValidForRendering();
        const bool Complete=Resource && Resource->IsGameThreadShaderMapComplete();
#if WITH_EDITOR
        if(Resource && ErrorsEmpty && (!Finished || !Complete))
        {
            // A new usage can request more permutations after initial setup.
            // Keep all strict validity/completeness checks; do not treat an
            // unfinished editor shader queue as a permanent compile failure.
            Resource->SubmitCompileJobs_GameThread(EShaderCompileJobPriority::ForceLocal);
            return false;
        }
#endif
        auto Check=MakeShared<FJsonObject>();Check->SetStringField(TEXT("asset"),Path);
        Check->SetBoolField(TEXT("resource_exists"),Resource!=nullptr);Check->SetBoolField(TEXT("compile_error_inspection_available"),ErrorInspectionAvailable);
        Check->SetStringField(TEXT("completion_evidence"),ErrorInspectionAvailable?TEXT("Editor compiler finished; complete actual-platform shader map required"):TEXT("No runtime compiler; loaded complete cooked shader map required"));
        if(ErrorInspectionAvailable)Check->SetBoolField(TEXT("compile_errors_empty"),ErrorsEmpty);else Check->SetField(TEXT("compile_errors_empty"),MakeShared<FJsonValueNull>());
        Check->SetBoolField(TEXT("compilation_finished"),Finished);Check->SetBoolField(TEXT("shader_map_valid"),Valid);Check->SetBoolField(TEXT("shader_map_complete"),Complete);
        const bool Passed=Resource&&(!ErrorInspectionAvailable||ErrorsEmpty)&&Finished&&Valid&&Complete;
        Check->SetBoolField(TEXT("passed"),Passed);
        Phase7ShaderRecords.Add(MakeShared<FJsonValueObject>(Check));
        UE_LOG(LogTemp,Display,TEXT("LAP_PHASE%d_MATERIAL asset=%s resource=%d errors_empty=%d compiled=%d valid=%d complete=%d passed=%d"),GetMilestone(),*Path,Resource!=nullptr,ErrorsEmpty,Finished,Valid,Complete,Passed);
        if(!Passed)
        {
            AnatomyError=FString::Printf(TEXT("Phase%d material compilation/fallback validation failed: %s"),GetMilestone(),*Path);
#if WITH_EDITOR
            if(Resource)for(const FString& Error:Resource->GetCompileErrors())UE_LOG(LogTemp,Error,TEXT("LAP_PHASE%d_MATERIAL_ERROR %s"),GetMilestone(),*Error);
#endif
            return false;
        }
    }
    return true;
}


void ATrainingScene::UpdatePhase7ShadingNormals()
{
    // Deliberately after PN positional evaluation: shading cannot modify the
    // collision/display offset, hide a positional spike or change depth labels.
    TArray<FVector> Smooth=TissueNormals;
    for(int Iteration=0;Iteration<2;++Iteration)
    {
        TArray<FVector> Sum;Sum.Init(FVector::ZeroVector,Smooth.Num());
        TArray<int32> Count;Count.Init(0,Smooth.Num());
        for(int Face=0;Face+2<TissueTriangles.Num();Face+=3)
            for(int Edge=0;Edge<3;++Edge)
            {
                const int A=TissueTriangles[Face+Edge],B=TissueTriangles[Face+(Edge+1)%3];
                if(!Smooth.IsValidIndex(A)||!Smooth.IsValidIndex(B))continue;
                // Do not smear the thin wall rim across opposing sides.
                if(FVector::DotProduct(Smooth[A],Smooth[B])<.5)continue;
                Sum[A]+=Smooth[B];Sum[B]+=Smooth[A];++Count[A];++Count[B];
            }
        for(int I=0;I<Smooth.Num();++I)if(Count[I])
            Smooth[I]=(Smooth[I]*.8+Sum[I]/Count[I]*.2).GetSafeNormal(UE_SMALL_NUMBER,Smooth[I]);
    }
    for(int I=0;I<TissueRenderBindings.Num();++I)
    {
        const auto& S=TissueRenderBindings[I];
        TissueRenderData.Normals[I]=(Smooth[S.A]*S.Weight.X+Smooth[S.B]*S.Weight.Y+Smooth[S.C]*S.Weight.Z).GetSafeNormal(UE_SMALL_NUMBER,TissueRenderData.Normals[I]);
    }
}

void ATrainingScene::CapturePhase7ShapeReview(const FString& Stage)
{
    if(!bPhase7ShapeReview || !Phase6ProofCapture || !Phase6ProofTarget || !Bridge || TissueVertices.IsEmpty())return;
    ClosePhase7Progression(TEXT("frozen_capture"));
    bPhase5CapturePrevious=true;bResumeSnapshot=true;Bridge->TickFrozenBridge();
    const FTransform SavedCamera=Camera->GetComponentTransform(),SavedCapture=Phase6ProofCapture->GetComponentTransform();
    const float SavedFov=Camera->FieldOfView,SavedCaptureFov=Phase6ProofCapture->FOVAngle;
    FVector Center=FVector::ZeroVector;for(const auto& P:TissueVertices)Center+=P;Center/=TissueVertices.Num();
    const FVector Base=(SavedCamera.GetLocation()-Center).GetSafeNormal();
    const FVector Side=FVector::CrossProduct(Base,FVector::UpVector).GetSafeNormal();
    const uint64 State=Bridge->GetStateId(),Simulation=Bridge->GetSimulationId();
    const FString Dir=FPaths::Combine(Phase5Directory,TEXT("shape-review"),Stage);IFileManager::Get().MakeDirectory(*Dir,true);
    TArray<TSharedPtr<FJsonValue>> Views;
    const TCHAR* Names[]={TEXT("front"),TEXT("left-oblique"),TEXT("right-oblique"),TEXT("superior"),TEXT("attachment")};
    for(int View=0;View<5;++View)
    {
        FVector Target=Center,Direction=Base;double Distance=13.5;
        if(View==1)Direction=Base.RotateAngleAxis(-35,FVector::UpVector);
        if(View==2)Direction=Base.RotateAngleAxis(35,FVector::UpVector);
        if(View==3)Direction=Base.RotateAngleAxis(22,Side);
        if(View==4 && AnatomyAttachment)
        {
            if(const auto* Section=AnatomyAttachment->GetProcMeshSection(0))if(!Section->ProcVertexBuffer.IsEmpty())
            {Target=FVector::ZeroVector;for(const auto& V:Section->ProcVertexBuffer)Target+=AnatomyAttachment->GetComponentTransform().TransformPosition(FVector(V.Position));Target/=Section->ProcVertexBuffer.Num();}
            Direction=Base.RotateAngleAxis(-28,FVector::UpVector);Distance=10.5;
        }
        const FVector Position=Target+Direction*Distance;const FRotator Rotation=(Target-Position).Rotation();
        Camera->SetWorldLocationAndRotation(Position,Rotation);Camera->SetFieldOfView(52);
        Phase6ProofCapture->SetWorldLocationAndRotation(Position,Rotation);Phase6ProofCapture->FOVAngle=52;
        Phase6ProofCapture->PostProcessSettings=Camera->PostProcessSettings;
        Phase6ProofCapture->TextureTarget=Phase6ProofTarget;Phase6ProofCapture->CaptureSource=SCS_FinalColorLDR;
        for(int Warm=0;Warm<32;++Warm){Phase6ProofCapture->CaptureScene();FlushRenderingCommands();Bridge->TickFrozenBridge();}
        TArray<FColor> Pixels;TArray64<uint8> PNG;
        bool Saved=Phase6ProofTarget->GameThread_GetRenderTargetResource()->ReadPixels(Pixels);
        if(Saved && Pixels.Num()==1920*1080)FImageUtils::PNGCompressImageArray(1920,1080,Pixels,PNG);else Saved=false;
        const FString Name=FString(Names[View])+TEXT(".png");
        Saved=Saved&&FFileHelper::SaveArrayToFile(PNG,*FPaths::Combine(Dir,Name));
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("view"),Names[View]);O->SetStringField(TEXT("image"),Name);O->SetBoolField(TEXT("saved"),Saved);
        O->SetNumberField(TEXT("state_id"),State);O->SetNumberField(TEXT("simulation_id"),Simulation);
        O->SetBoolField(TEXT("displayed_state_unchanged"),Bridge->GetStateId()==State&&Bridge->GetSimulationId()==Simulation);
        O->SetBoolField(TEXT("native_simulation_paused"),false);
        O->SetArrayField(TEXT("camera_position_cm"),P7Vector(Position));O->SetArrayField(TEXT("camera_forward"),P7Vector(Rotation.Vector()));
        const FRotationMatrix Basis(Rotation);O->SetArrayField(TEXT("camera_right"),P7Vector(Basis.GetUnitAxis(EAxis::Y)));O->SetArrayField(TEXT("camera_up"),P7Vector(Basis.GetUnitAxis(EAxis::Z)));
        O->SetNumberField(TEXT("horizontal_fov_degrees"),52);O->SetNumberField(TEXT("width"),1920);O->SetNumberField(TEXT("height"),1080);
        O->SetStringField(TEXT("visual_manifest_sha1"),AnatomyVisualFingerprint);O->SetObjectField(TEXT("appearance"),BuildPhase7VisualSettings());
        if(EndoscopeLight)O->SetArrayField(TEXT("light_position_cm"),P7Vector(EndoscopeLight->GetComponentLocation()));
        uint8 Digest[20];FSHA1::HashBuffer(PNG.GetData(),PNG.Num(),Digest);O->SetStringField(TEXT("png_sha1"),BytesToHex(Digest,20).ToLower());
        Views.Add(MakeShared<FJsonValueObject>(O));
        if(!Saved)Phase5Failures.AddUnique(FString::Printf(TEXT("Phase%d multi-angle inspection image failed"),GetMilestone()));
    }
    Camera->SetWorldTransform(SavedCamera);Camera->SetFieldOfView(SavedFov);
    Phase6ProofCapture->SetWorldTransform(SavedCapture);Phase6ProofCapture->FOVAngle=SavedCaptureFov;
    auto Report=MakeShared<FJsonObject>();Report->SetStringField(TEXT("schema"),bPhase9?TEXT("endoforge.phase9.shape-review.v1"):TEXT("endoforge.phase7.shape-review.v1"));Report->SetStringField(TEXT("stage"),Stage);Report->SetArrayField(TEXT("views"),Views);
    Report->SetBoolField(TEXT("camera_restored"),Camera->GetComponentTransform().Equals(SavedCamera)&&Camera->FieldOfView==SavedFov);
    Report->SetStringField(TEXT("scope"),TEXT("Diagnostic frozen displayed-state inspection, five 1920x1080 views with near-axis light following capture camera. Actual native solver continues; accepted presentation is held using frozen bridge heartbeat. No geometric postprocess or model deformation added by review cameras."));
    SavePhase6Json(FPaths::Combine(Dir,TEXT("views.json")),Report);
    bResumeSnapshot=true;
}
