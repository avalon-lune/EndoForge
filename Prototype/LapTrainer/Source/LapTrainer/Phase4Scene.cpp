#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Engine/LocalPlayer.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Engine.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerInput.h"
#include "GameFramework/HUD.h"
#include "Kismet/GameplayStatics.h"
#include "ProceduralMeshComponent.h"
#include "SceneView.h"
#include "ImageUtils.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/Guid.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "UnrealClient.h"

namespace
{
TArray<TSharedPtr<FJsonValue>> V3(const FVector& P)
{ return {MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)}; }
TSharedPtr<FJsonValue> JV(const FVector& P) { return MakeShared<FJsonValueArray>(V3(P)); }
FString JsonText(const TSharedRef<FJsonObject>& O)
{ FString S; FJsonSerializer::Serialize(O,TJsonWriterFactory<TCHAR,TCondensedJsonPrintPolicy<TCHAR>>::Create(&S)); return S; }
}

bool ATrainingScene::IsPhase4() const { return Bridge && Bridge->IsPhase4(); }
FString ATrainingScene::GetSpecimenName() const { return IsPhase4() ? Bridge->GetSpecimen().ToUpper() : TEXT("FLAT"); }
FString ATrainingScene::GetSessionStatus() const
{
    if (!IsPhase4()) return FString();
    if (!Bridge->GetSessionError().IsEmpty()) return Bridge->GetSessionError().Left(80);
    if (Bridge->HasPendingSessionAction()) return TEXT("SESSION REQUEST PENDING");
    return FString::Printf(TEXT("%s | STEP %llu | TAKE %llu"),*Bridge->GetSessionMode().ToUpper(),
        static_cast<unsigned long long>(Bridge->GetStepIndex()),static_cast<unsigned long long>(Bridge->GetRecordedSteps()));
}
void ATrainingScene::InitializePhase4()
{
    bPhase4Test = FParse::Param(FCommandLine::Get(),TEXT("LapPhase4Test")) && !bVisualPreview;
    if (!IsPhase4()) return;
    // Development builds bind F5 to a renderer debug view by default. These keys belong to the exercise.
    if(APlayerController* PC=UGameplayStatics::GetPlayerController(this,0))
        if(PC->PlayerInput) PC->PlayerInput->DebugExecBindings.RemoveAll([](const FKeyBind& Bind)
        { return Bind.Key==EKeys::F5 || Bind.Key==EKeys::F6 || Bind.Key==EKeys::F7; });
    if (bPhase4Test)
    {
        if(!FParse::Value(FCommandLine::Get(),TEXT("LapCaptureDir="),CaptureDirectory))
            CaptureDirectory=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Automation/Phase4"));
        CaptureDirectory=FPaths::ConvertRelativePathToFull(CaptureDirectory);
        Phase4Directory=CaptureDirectory;
    }
    else Phase4Directory=FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Phase4"),FGuid::NewGuid().ToString(EGuidFormats::Digits)));
    IFileManager::Get().MakeDirectory(*Phase4Directory,true);
    UGameViewportClient::OnScreenshotCaptured().AddUObject(this,&ATrainingScene::OnSnapshotCaptured);
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE4 output=%s; 4 flat / 5 curved; F5 record, F6 replay, F7 snapshot"),*Phase4Directory);
}
FVector ATrainingScene::GetGraspReadyTarget() const
{
    // Initial front edge of the selected unloaded specimen. The actual approach remains bounded by native kinematics.
    if(bPhase5 && bPhase5HomeAdopted) return Phase5Targets[0];
    double Length=.08,Curvature=0;
    if(IsPhase4() && Bridge->GetAcceptedState().IsValid())
    {
        const auto Config=Bridge->GetAcceptedState()->GetObjectField(TEXT("config"));
        Length=Config->GetNumberField(TEXT("length_m")); Curvature=Config->GetNumberField(TEXT("curvature_m"));
    }
    // The 1.5 mm approach offset describes the jaw aim, not the specimen thickness.
    const double Z=.006+Curvature*FMath::Sin(PI*.006/Length)-.0015;
    return FVector(-2.2,(-Length*.5+.006)*100,Z*100);
}
void ATrainingScene::AdoptActualCommands()
{
    Phase5Latches[0]=Phase5Latches[1]=false;
    bGrasperLatched=false; bSuppressSpace=true;
    for(int32 I=0;I<2;++I)
    {
        if(const auto* T=Bridge->GetToolState(I)) { ToolTips[I]=T->ActualTipCm; ToolRolls[I]=T->RollDeg; }
        ToolClosed[I]=false;
    }
    LoadActiveCommand();
}
bool ATrainingScene::HandlePhase4Input(APlayerController* PC)
{
    if (!IsPhase4()) return false;
    if (PC->WasInputKeyJustPressed(EKeys::F7) && IsPhysicsConnected()) bSnapshotPending=true;
    if (!bPhase5 && (PC->WasInputKeyJustPressed(EKeys::Four) || PC->WasInputKeyJustPressed(EKeys::Five)))
    {
        Bridge->SetSpecimen(PC->WasInputKeyJustPressed(EKeys::Five)?TEXT("curved"):TEXT("flat"));
        ResetExercise(); return true;
    }
    if (PC->WasInputKeyJustPressed(EKeys::F5) && IsPhysicsConnected() && !Bridge->HasPendingSessionAction())
    {
        if(Bridge->GetSessionMode()==TEXT("recording")) Bridge->RequestSessionAction(TEXT("record_stop"));
        else { ResetExercise(); Bridge->RequestSessionAction(TEXT("record_start")); }
        return true;
    }
    if (PC->WasInputKeyJustPressed(EKeys::F6) && IsPhysicsConnected() && !Bridge->HasPendingSessionAction())
    {
        if(Bridge->IsReplayLocked()) { AdoptActualCommands(); Bridge->RequestSessionAction(TEXT("replay_stop")); }
        else { ResetExercise(); Bridge->RequestSessionAction(TEXT("replay_last")); }
        return true;
    }
    if (Bridge->GetPendingSessionAction()==TEXT("replay_stop"))
    { AdoptActualCommands(); return true; }
    if (Bridge->IsReplayLocked())
    {
        // Keep displayed command targets at the physically replayed poses; no latent live motion is accumulated.
        for(int32 I=0;I<2;++I) if(const auto* T=Bridge->GetToolState(I))
        { ToolTips[I]=T->ActualTipCm; ToolRolls[I]=T->RollDeg; ToolClosed[I]=T->JawOpenFraction<.5f; }
        bGrasperLatched=false; LoadActiveCommand();
        if(PC->WasInputKeyJustPressed(EKeys::R)) ResetExercise();
        return true;
    }
    return Bridge->HasPendingSessionAction();
}
TSharedRef<FJsonObject> ATrainingScene::BuildCameraRecord() const
{
    TSharedRef<FJsonObject> C=MakeShared<FJsonObject>();
    APlayerController* PC=UGameplayStatics::GetPlayerController(this,0);
    if(!PC || !PC->PlayerCameraManager) return C;
    FVector P; FRotator R; PC->GetPlayerViewPoint(P,R);
    const FRotationMatrix Rotation(R);
    const FVector Forward=Rotation.GetUnitAxis(EAxis::X),Right=Rotation.GetUnitAxis(EAxis::Y),Up=Rotation.GetUnitAxis(EAxis::Z);
    int32 W=0,H=0; PC->GetViewportSize(W,H);
    const double Fov=PC->PlayerCameraManager->GetFOVAngle();
    const double Focal=W/(2*FMath::Tan(FMath::DegreesToRadians(Fov*.5)));
    C->SetArrayField(TEXT("position_cm"),V3(P)); C->SetArrayField(TEXT("forward"),V3(Forward));
    C->SetArrayField(TEXT("right"),V3(Right)); C->SetArrayField(TEXT("up"),V3(Up));
    C->SetNumberField(TEXT("horizontal_fov_deg"),Fov);
    C->SetArrayField(TEXT("viewport"),{MakeShared<FJsonValueNumber>(W),MakeShared<FJsonValueNumber>(H)});
    C->SetArrayField(TEXT("view_rect"),{MakeShared<FJsonValueNumber>(0),MakeShared<FJsonValueNumber>(0),MakeShared<FJsonValueNumber>(W),MakeShared<FJsonValueNumber>(H)});
    C->SetNumberField(TEXT("fx_px"),Focal); C->SetNumberField(TEXT("fy_px"),Focal);
    C->SetNumberField(TEXT("cx_px"),W*.5); C->SetNumberField(TEXT("cy_px"),H*.5);
    C->SetStringField(TEXT("convention"),TEXT("UE +X forward +Y right +Z up; world cm; pixels top-left; no distortion; world positions=native metres*100"));
    if(ULocalPlayer* LP=PC->GetLocalPlayer())
    {
        FSceneViewProjectionData Projection;
        if(LP->ViewportClient && LP->GetProjectionData(LP->ViewportClient->Viewport,Projection))
        {
            const FMatrix M=Projection.ComputeViewProjectionMatrix();
            TArray<TSharedPtr<FJsonValue>> Rows;
            for(int32 I=0;I<4;++I)
            { TArray<TSharedPtr<FJsonValue>> Row; for(int32 J=0;J<4;++J) Row.Add(MakeShared<FJsonValueNumber>(M.M[I][J])); Rows.Add(MakeShared<FJsonValueArray>(Row)); }
            C->SetArrayField(TEXT("view_projection_matrix"),Rows);
            const FIntRect Rect=Projection.GetConstrainedViewRect();
            const FMatrix& PM=Projection.ProjectionMatrix;
            C->SetNumberField(TEXT("fx_px"),PM.M[0][0]*Rect.Width()*.5);C->SetNumberField(TEXT("fy_px"),PM.M[1][1]*Rect.Height()*.5);
            C->SetNumberField(TEXT("cx_px"),Rect.Min.X+(1+PM.M[2][0])*Rect.Width()*.5);C->SetNumberField(TEXT("cy_px"),Rect.Min.Y+(1-PM.M[2][1])*Rect.Height()*.5);
            C->SetArrayField(TEXT("view_rect"),{MakeShared<FJsonValueNumber>(Rect.Min.X),MakeShared<FJsonValueNumber>(Rect.Min.Y),MakeShared<FJsonValueNumber>(Rect.Max.X),MakeShared<FJsonValueNumber>(Rect.Max.Y)});
        }
    }
    return C;
}
void ATrainingScene::RecordPresentedState()
{
    if(!IsPhase4() || !Bridge->IsConnected() || !Bridge->GetAcceptedState().IsValid() || PresentedStateId==Bridge->GetStateId()) return;
    if(LastPhysicsFrame!=Bridge->GetFrameNumber() || BoundTopologyRevision!=Bridge->GetTopologyRevision()) return;
    PresentedStateId=Bridge->GetStateId();
    TSharedRef<FJsonObject> O=MakeShared<FJsonObject>();
    O->SetNumberField(TEXT("schema"),1); O->SetNumberField(TEXT("phase"),bPhase6?6:bPhase5?5:4);
    O->SetStringField(TEXT("record_kind"),TEXT("presented_state"));
    O->SetObjectField(TEXT("native_state"),Bridge->GetAcceptedState());
    O->SetObjectField(TEXT("camera"),BuildCameraRecord());
    O->SetNumberField(TEXT("render_vertex_count"),TissueRenderData.Positions.Num());
    O->SetNumberField(TEXT("render_topology_revision"),BoundTopologyRevision);
    PresentedBuffer+=JsonText(O)+TEXT("\n");
    if(PresentedBuffer.Len()>1024*1024) FlushPresentedStates();
}
void ATrainingScene::FlushPresentedStates()
{
    if(PresentedBuffer.IsEmpty() || Phase4Directory.IsEmpty()) return;
    const bool Ok=FFileHelper::SaveStringToFile(PresentedBuffer,*FPaths::Combine(Phase4Directory,bPhase5?TEXT("phase5-presented-states.jsonl"):TEXT("phase4-presented-states.jsonl")),
        FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,&IFileManager::Get(),FILEWRITE_Append|(bPhase6?FILEWRITE_AllowRead:0));
    if(!Ok) { Phase4Failures.AddUnique(TEXT("Presented state log write failed")); UE_LOG(LogTemp,Error,TEXT("LAP_PRESENTED_WRITE_FAILED state=%llu bytes=%d"),static_cast<unsigned long long>(PresentedStateId),PresentedBuffer.Len()); }
    PresentedBuffer.Empty();
}
void ATrainingScene::BeginSnapshot()
{
    if(!IsPhase4() || !Bridge->IsConnected() || !Bridge->GetAcceptedState().IsValid()) return;
    bSnapshotFrozen=true; SnapshotFreezeTicks=0; SnapshotStartedSeconds=FPlatformTime::Seconds();
    if(bPhase5) bPhase5CapturePrevious=true;
    SnapshotStem=FPaths::Combine(Phase4Directory,FString::Printf(TEXT("%s-snapshot-%03llu"),bPhase5?TEXT("phase5"):TEXT("phase4"),static_cast<unsigned long long>(++SnapshotCaptureId)));
    SnapshotNotice=TEXT("Freezing displayed state for snapshot...");
    if(APlayerController* PC=UGameplayStatics::GetPlayerController(this,0)) if(AHUD* HUD=PC->GetHUD())
    { bSnapshotHudWasVisible=HUD->bShowHUD; HUD->bShowHUD=false; }
}
void ATrainingScene::RestoreSnapshotHUD()
{
    if(APlayerController* PC=UGameplayStatics::GetPlayerController(this,0)) if(AHUD* HUD=PC->GetHUD()) HUD->bShowHUD=bSnapshotHudWasVisible;
}
void ATrainingScene::SaveFrozenSnapshot()
{
    SnapshotObject=MakeShared<FJsonObject>();
    SnapshotObject->SetNumberField(TEXT("schema"),1); SnapshotObject->SetNumberField(TEXT("phase"),bPhase6?6:bPhase5?5:4);
    SnapshotObject->SetStringField(TEXT("binding_method"),bPhase6?TEXT("bounded_pn_triangle"):TEXT("linear_barycentric"));
    SnapshotObject->SetNumberField(TEXT("max_offset_mm"),bPhase6?.12:0);
    SnapshotObject->SetNumberField(TEXT("capture_id"),SnapshotCaptureId);
    SnapshotObject->SetStringField(TEXT("screenshot"),FPaths::GetCleanFilename(SnapshotStem+TEXT(".png")));
    SnapshotObject->SetObjectField(TEXT("native_state"),Bridge->GetAcceptedState());
    if(bPhase5) {SnapshotObject->SetObjectField(TEXT("scene_geometry"),BuildPhase5RenderGeometry());SnapshotObject->SetStringField(TEXT("visual_manifest"),TEXT("dataset/visual-manifest.json"));SnapshotObject->SetStringField(TEXT("visual_manifest_sha1"),AnatomyVisualFingerprint);}
    auto CameraRecord=BuildCameraRecord(); SnapshotObject->SetObjectField(TEXT("camera"),CameraRecord);
    const FProcMeshSection* Mesh=TissueMesh->GetProcMeshSection(0);
    APlayerController* PC=UGameplayStatics::GetPlayerController(this,0);
    if(!Mesh || !PC || Mesh->ProcVertexBuffer.Num()!=TissueRenderBindings.Num())
    { Phase4Failures.AddUnique(TEXT("Snapshot render section unavailable")); bSnapshotFrozen=false; bResumeSnapshot=true; RestoreSnapshotHUD(); return; }
    TArray<TSharedPtr<FJsonValue>> Vertices,Faces,Bindings,Samples;
    FVector CameraPosition; FRotator CameraRotation; PC->GetPlayerViewPoint(CameraPosition,CameraRotation);
    const FRotationMatrix Rotation(CameraRotation);
    const FVector Forward=Rotation.GetUnitAxis(EAxis::X),Right=Rotation.GetUnitAxis(EAxis::Y),Up=Rotation.GetUnitAxis(EAxis::Z);
    const double Focal=CameraRecord->GetNumberField(TEXT("fx_px")),CX=CameraRecord->GetNumberField(TEXT("cx_px")),CY=CameraRecord->GetNumberField(TEXT("cy_px"));
    double PixelError=0,BindingError=0;
    FTrainingRenderMesh ReconstructedMesh;
    if(bPhase6){ReconstructedMesh=TissueRenderData;TrainingGeometry::UpdateBoundSurface(TissueVertices,TissueNormals,TissueRenderBindings,ReconstructedMesh,.012);}
    for(int32 I=0;I<Mesh->ProcVertexBuffer.Num();++I)
    {
        const FVector Actual=TissueMesh->GetComponentTransform().TransformPosition(FVector(Mesh->ProcVertexBuffer[I].Position));
        Vertices.Add(JV(Actual));
        const auto& B=TissueRenderBindings[I];
        TSharedRef<FJsonObject> Binding=MakeShared<FJsonObject>();
        Binding->SetArrayField(TEXT("nodes"),{MakeShared<FJsonValueNumber>(B.A),MakeShared<FJsonValueNumber>(B.B),MakeShared<FJsonValueNumber>(B.C)});
        Binding->SetArrayField(TEXT("weights"),V3(B.Weight)); Bindings.Add(MakeShared<FJsonValueObject>(Binding));
        const FVector Reconstructed=bPhase6?ReconstructedMesh.Positions[I]:TissueVertices[B.A]*B.Weight.X+TissueVertices[B.B]*B.Weight.Y+TissueVertices[B.C]*B.Weight.Z;
        BindingError=FMath::Max(BindingError,FVector::Distance(Actual,Reconstructed)*10);
        if(I%FMath::Max(1,Mesh->ProcVertexBuffer.Num()/96)==0)
        {
            FVector2D Pixel;
            const FVector D=Actual-CameraPosition; const double Depth=FVector::DotProduct(D,Forward);
            if(Depth>.01 && PC->ProjectWorldLocationToScreen(Actual,Pixel))
            {
                const FVector2D Independent(CX+Focal*FVector::DotProduct(D,Right)/Depth,CY-Focal*FVector::DotProduct(D,Up)/Depth);
                PixelError=FMath::Max(PixelError,FVector2D::Distance(Pixel,Independent));
                TSharedRef<FJsonObject> Sample=MakeShared<FJsonObject>(); Sample->SetNumberField(TEXT("render_index"),I);
                Sample->SetArrayField(TEXT("pixel"),{MakeShared<FJsonValueNumber>(Pixel.X),MakeShared<FJsonValueNumber>(Pixel.Y)});
                Samples.Add(MakeShared<FJsonValueObject>(Sample));
            }
        }
    }
    for(uint32 I:Mesh->ProcIndexBuffer) Faces.Add(MakeShared<FJsonValueNumber>(I));
    SnapshotObject->SetArrayField(TEXT("render_vertices_cm"),Vertices);
    SnapshotObject->SetArrayField(TEXT("render_triangles"),Faces);
    SnapshotObject->SetArrayField(TEXT("render_bindings"),Bindings);
    SnapshotObject->SetArrayField(TEXT("projected_samples"),Samples);
    SnapshotObject->SetNumberField(TEXT("max_projection_error_px"),PixelError);
    SnapshotObject->SetNumberField(TEXT("max_render_binding_error_mm"),BindingError);
    MaxProjectionErrorPx=FMath::Max(MaxProjectionErrorPx,PixelError); MaxBindingErrorMm=FMath::Max(MaxBindingErrorMm,BindingError);
    if(Samples.Num()<16) Phase4Failures.AddUnique(TEXT("Snapshot lacks projection samples"));
    FScreenshotRequest::RequestScreenshot(SnapshotStem+TEXT(".png"),false,false);
}
void ATrainingScene::OnSnapshotCaptured(int32 Width,int32 Height,const TArray<FColor>& Pixels)
{
    // The delegate intercepts all screenshots, so ordinary test captures must also be written.
    FString Path=bSnapshotFrozen ? SnapshotStem+TEXT(".png") : FScreenshotRequest::GetFilename();
    TArray64<uint8> Compressed; FImageUtils::PNGCompressImageArray(Width,Height,Pixels,Compressed);
    const bool ImageSaved=FFileHelper::SaveArrayToFile(Compressed,*Path);
    if(!bSnapshotFrozen) return;
    if(SnapshotObject.IsValid())
    {
        SnapshotObject->SetArrayField(TEXT("screenshot_size"),{MakeShared<FJsonValueNumber>(Width),MakeShared<FJsonValueNumber>(Height)});
        const bool JsonSaved=bPhase6?SavePhase6Json(SnapshotStem+TEXT(".json"),SnapshotObject.ToSharedRef()):FFileHelper::SaveStringToFile(JsonText(SnapshotObject.ToSharedRef()),*(SnapshotStem+TEXT(".json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
        if(ImageSaved && JsonSaved) { ++Phase4SnapshotCount; SnapshotNotice=TEXT("Snapshot saved: ")+FPaths::GetCleanFilename(SnapshotStem); }
        else { SnapshotNotice=TEXT("Snapshot save failed"); Phase4Failures.AddUnique(SnapshotNotice); }
    }
    SnapshotObject.Reset(); bSnapshotFrozen=false; bResumeSnapshot=true; RestoreSnapshotHUD();
}
void ATrainingScene::AdvancePhase4Test(int32 Stage)
{
    StopTestMotion();
    for(const FKey& K:{EKeys::F,EKeys::F5,EKeys::F6,EKeys::F7,EKeys::Four,EKeys::Five,EKeys::Two,EKeys::Tab,EKeys::H}) SetTestKey(K,false);
    Phase4Stage=Stage; Phase4StageTime=0; Phase4Dwell=0; Phase4Ticks=0;
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE4_STAGE %d specimen=%s session=%s"),Stage,*GetSpecimenName(),*GetSessionStatus());
}
void ATrainingScene::UpdatePhase4Test(float DeltaSeconds)
{
    if(!bPhase4Test || bPhase4Finished) return;
    Phase4Time+=DeltaSeconds;
    if(!IsPhysicsConnected())
    {
        if(bPhase4Started) Phase4Failures.AddUnique(TEXT("Physics stale/disconnected during regular input exercise"));
        if(Phase4Time>35) FinishPhase4Test(TEXT("Physics connection unavailable"));
        return;
    }
    bPhase4Started=true; Phase4StageTime+=DeltaSeconds; ++Phase4Ticks;
    if(!Bridge->IsHealthy() || Bridge->GetSafetyStopCount()>0 || Bridge->GetUnhealthyStateCount()>0 || Bridge->GetRejectedStateCount()>0)
    { FinishPhase4Test(TEXT("Unhealthy/rejected/protected native state during regular exercise")); return; }
    if(Phase4Time>300 || Phase4StageTime>70)
    { FinishPhase4Test(FString::Printf(TEXT("Input exercise timeout stage %d"),Phase4Stage)); return; }
    const bool First=Phase4Ticks==1;
    if(Phase4Stage>=21)
        for(int32 Tool=0;Tool<2;++Tool)
            if(const auto* State=Bridge->GetToolState(Tool))
                Phase4CollisionMaxNodeDepthMm=FMath::Max(Phase4CollisionMaxNodeDepthMm,static_cast<double>(State->PenetrationMm));
    switch(Phase4Stage)
    {
    case 0:
        SetTestKey(EKeys::Four,First);
        SetTestKey(EKeys::Tab,Phase4Ticks==3); SetTestKey(EKeys::H,Phase4Ticks==5);
        if(Phase4StageTime>.8 && Bridge->HasAcknowledgedReset() && Bridge->GetSpecimen()==TEXT("flat")) AdvancePhase4Test(1);
        break;
    case 1:
        SetTestKey(EKeys::Two,First); Phase4ReadyTarget=GetGraspReadyTarget();
        if(Phase4StageTime>.8 && Bridge->HasAcknowledgedReset() && FVector::Distance(ActualTips[0],Phase4ReadyTarget)<.03) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.4) { CaptureTest(TEXT("phase4_01_flat_ready.png")); AdvancePhase4Test(2); }
        break;
    case 2:
        SetTestKey(EKeys::F,First);
        if(IsGrasperHolding()) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.5) { bFlatGrip=true; CaptureTest(TEXT("phase4_02_flat_grasp.png")); AdvancePhase4Test(3); }
        break;
    case 3:
        if(DriveTestTo(Phase4ReadyTarget+FVector(0,0,.4)) && IsGrasperHolding() && Bridge->GetMaxDisplacementCm()>.2) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.6) { bFlatTraction=true; CaptureTest(TEXT("phase4_03_flat_traction.png")); AdvancePhase4Test(4); }
        break;
    case 4:
        SetTestKey(EKeys::F,First);
        if(Phase4StageTime>1.2 && !IsGrasperHolding() && !bGrasperLatched)
        { bFlatRelease=true; CaptureTest(TEXT("phase4_04_flat_release.png")); AdvancePhase4Test(5); }
        break;
    case 5:
        SetTestKey(EKeys::F7,First);
        if(Phase4SnapshotCount>=1) AdvancePhase4Test(6);
        break;
    case 6:
        SetTestKey(EKeys::Five,First);
        if(Phase4StageTime>.8 && Bridge->HasAcknowledgedReset() && Bridge->GetSpecimen()==TEXT("curved")) AdvancePhase4Test(7);
        break;
    case 7:
        SetTestKey(EKeys::F5,First);
        if(Bridge->GetSessionMode()==TEXT("recording") && Bridge->HasAcknowledgedReset())
        { bRecordingObserved=true; Phase4ReadyTarget=GetGraspReadyTarget(); AdvancePhase4Test(8); }
        break;
    case 8:
        if(DriveTestTo(Phase4ReadyTarget)) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.6) { CaptureTest(TEXT("phase4_05_curved_ready.png")); AdvancePhase4Test(9); }
        break;
    case 9:
        SetTestKey(EKeys::F,First);
        if(IsGrasperHolding()) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.5) { bCurvedGrip=true; CaptureTest(TEXT("phase4_06_curved_grasp.png")); AdvancePhase4Test(10); }
        break;
    case 10:
        if(DriveTestTo(Phase4ReadyTarget+FVector(0,0,.4)) && IsGrasperHolding() && Bridge->GetMaxDisplacementCm()>.2) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.6) { bCurvedTraction=true; CaptureTest(TEXT("phase4_07_curved_traction.png")); AdvancePhase4Test(11); }
        break;
    case 11:
        SetTestKey(EKeys::F7,First);
        if(Phase4SnapshotCount>=2) { bCapturePreservesRecording=Bridge->GetSessionMode()==TEXT("recording"); AdvancePhase4Test(12); }
        break;
    case 12:
        SetTestKey(EKeys::F,First);
        if(Phase4StageTime>1.2 && !IsGrasperHolding() && !bGrasperLatched)
        { bCurvedRelease=true; CaptureTest(TEXT("phase4_08_curved_release.png")); AdvancePhase4Test(13); }
        break;
    case 13:
        SetTestKey(EKeys::F5,First);
        if(Phase4StageTime>.5 && Bridge->GetSessionMode()==TEXT("idle") && Bridge->GetRecordedSteps()>20)
        { Phase4RecordLength=Bridge->GetRecordedSteps(); AdvancePhase4Test(14); }
        break;
    case 14:
        SetTestKey(EKeys::F6,First);
        if(Bridge->GetSessionMode()==TEXT("replaying")) { bReplayObserved=true; AdvancePhase4Test(15); }
        break;
    case 15:
        // Deliberate conflicting keyboard input must not accumulate a live target during native replay.
        SetTestKey(EKeys::W,true);
        if(Bridge->GetSessionMode()==TEXT("replaying") && FVector::Distance(ToolTip,ActualTips[ActiveTool])<.2) bReplayGuard=true;
        if(Bridge->GetSessionMode()==TEXT("replay_complete") && Bridge->GetStepIndex()>=Bridge->GetReplayLength())
        { bReplayComplete=true; CaptureTest(TEXT("phase4_09_replay_complete.png")); AdvancePhase4Test(16); }
        break;
    case 16:
        SetTestKey(EKeys::Tab,First);
        SetTestKey(EKeys::F7,Phase4Ticks==8);
        if(Phase4SnapshotCount>=3) AdvancePhase4Test(17);
        break;
    case 17:
        SetTestKey(EKeys::F6,First);
        if(Phase4StageTime>.6 && Bridge->GetSessionMode()==TEXT("idle") && !Bridge->IsReplayLocked()) AdvancePhase4Test(18);
        break;
    case 18:
        SetTestKey(EKeys::F6,First);
        if(Bridge->GetSessionMode()==TEXT("replaying") && IsGrasperHolding()) AdvancePhase4Test(19);
        break;
    case 19:
        if(First) bStoppedMidHold=IsGrasperHolding();
        SetTestKey(EKeys::F6,First);
        if(Bridge->GetSessionMode()==TEXT("idle") && !IsGrasperHolding() && !bGrasperLatched && Bridge->GetToolState(0)->JawOpenFraction>.9)
            Phase4Dwell+=DeltaSeconds;
        else Phase4Dwell=0;
        if(Phase4Dwell>.8) { bStopStayedOpen=true; AdvancePhase4Test(20); }
        break;
    case 20:
        // A fresh curved specimen exercises the formerly failing interior withdrawal.
        // Commands below still go through real PlayerController keys and native contact.
        SetTestKey(EKeys::Five,First);
        if(Phase4StageTime>.8 && Bridge->HasAcknowledgedReset() && Bridge->GetSpecimen()==TEXT("curved"))
        { Phase4ReadyTarget=GetGraspReadyTarget(); AdvancePhase4Test(21); }
        break;
    case 21:
        if(DriveTestTo(Phase4ReadyTarget)) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.4)
        { Phase4PathProgress=0; AdvancePhase4Test(22); }
        break;
    case 22:
    {
        const auto Config=Bridge->GetAcceptedState()->GetObjectField(TEXT("config"));
        const double Length=Config->GetNumberField(TEXT("length_m"));
        const double Curvature=Config->GetNumberField(TEXT("curvature_m"));
        const double StartY=Phase4ReadyTarget.Y*.01,EndY=-.015;
        const double Y=FMath::Lerp(StartY,EndY,Phase4PathProgress);
        const double Z=.006+Curvature*FMath::Sin(PI*(Y+Length*.5)/Length)-.0015;
        const FVector Waypoint(-2.2,Y*100,Z*100);
        if(DriveTestTo(Waypoint)) Phase4PathProgress=FMath::Min(1.,Phase4PathProgress+DeltaSeconds*.3);
        Phase4InteriorTarget=FVector(-2.2,EndY*100,(.006+Curvature*FMath::Sin(PI*(EndY+Length*.5)/Length)-.0015)*100);
        if(Phase4PathProgress>=1 && FVector::Distance(ActualTips[0],Phase4InteriorTarget)<.08)
        { CaptureTest(TEXT("phase4_10_curved_interior_ready.png")); AdvancePhase4Test(23); }
        break;
    }
    case 23:
        SetTestKey(EKeys::F,First);
        if(IsGrasperHolding()) Phase4Dwell+=DeltaSeconds; else Phase4Dwell=0;
        if(Phase4Dwell>.4) { bInteriorGrip=true; AdvancePhase4Test(24); }
        break;
    case 24:
        if(DriveTestTo(Phase4InteriorTarget+FVector(0,0,.4)) && IsGrasperHolding() && Bridge->GetMaxDisplacementCm()>.2)
            Phase4Dwell+=DeltaSeconds;
        else Phase4Dwell=0;
        if(Phase4Dwell>.5)
        { bInteriorTraction=true; CaptureTest(TEXT("phase4_11_curved_interior_traction.png")); AdvancePhase4Test(25); }
        break;
    case 25:
        SetTestKey(EKeys::F,First);
        if(Phase4StageTime>1.2 && !IsGrasperHolding() && Bridge->GetToolState(0)->JawOpenFraction>.95)
        {
            bInteriorReleased=true; Phase4PathProgress=0;
            Phase4RetreatStart=ActualTips[0]; Phase4PreviousRetreatTip=ActualTips[0];
            AdvancePhase4Test(26);
        }
        break;
    case 26:
    {
        // Follow one straight chord to home, without the earlier raised-arch detour.
        // Keyboard quantization is separately covered by the exact native trajectory matrix.
        const FVector Home(-2.2,-4.7,.6);
        const FVector Waypoint=FMath::Lerp(Phase4RetreatStart,Home,Phase4PathProgress);
        if(DriveTestTo(Waypoint)) Phase4PathProgress=FMath::Min(1.,Phase4PathProgress+DeltaSeconds*.18);
        Phase4RetreatTravelCm+=FVector::Distance(ActualTips[0],Phase4PreviousRetreatTip);
        Phase4PreviousRetreatTip=ActualTips[0];
        if(Phase4PathProgress>=1 && FVector::Distance(ActualTips[0],Home)<.08 && !IsGrasperHolding())
        { bDirectRetreatCompleted=true; CaptureTest(TEXT("phase4_12_curved_direct_retreat.png")); AdvancePhase4Test(27); }
        break;
    }
    case 27:
        if(Phase4StageTime>.8) FinishPhase4Test();
        break;
    }
}
void ATrainingScene::FinishPhase4Test(const FString& Failure)
{
    if(bPhase4Finished) return; bPhase4Finished=true;
    const TArray<FName> Keys=TestHeldKeys.Array(); for(const FName& K:Keys) SetTestKey(FKey(K),false);
    if(!Failure.IsEmpty()) Phase4Failures.AddUnique(Failure);
    FlushPresentedStates();
    auto Report=MakeShared<FJsonObject>(); auto Checks=MakeShared<FJsonObject>(); auto Metrics=MakeShared<FJsonObject>();
    auto Check=[&](const TCHAR* Name,bool Pass)
    { Checks->SetBoolField(Name,Pass); if(!Pass) Phase4Failures.AddUnique(FString(TEXT("Failed check: "))+Name); };
    Check(TEXT("physics_connected"),IsPhysicsConnected());
    Check(TEXT("healthy_without_rejected_states"),Bridge && Bridge->IsHealthy() && Bridge->GetUnhealthyStateCount()==0 && Bridge->GetRejectedStateCount()==0);
    Check(TEXT("regular_exercise_without_safety_stops"),Bridge && Bridge->GetSafetyStopCount()==0);
    Check(TEXT("flat_contact_grasp"),bFlatGrip); Check(TEXT("flat_traction"),bFlatTraction); Check(TEXT("flat_release"),bFlatRelease);
    Check(TEXT("curved_contact_grasp"),bCurvedGrip); Check(TEXT("curved_traction"),bCurvedTraction); Check(TEXT("curved_release"),bCurvedRelease);
    Check(TEXT("recording_native_commands"),bRecordingObserved && Phase4RecordLength>20);
    Check(TEXT("native_replay_completes"),bReplayObserved && bReplayComplete);
    Check(TEXT("replay_blocks_conflicting_live_input"),bReplayGuard);
    Check(TEXT("replay_stop_restores_live_mode"),Bridge && Bridge->GetSessionMode()==TEXT("idle"));
    Check(TEXT("snapshot_heartbeat_preserves_recording"),bCapturePreservesRecording);
    Check(TEXT("mid_grasp_replay_stop_releases_and_stays_open"),bStoppedMidHold && bStopStayedOpen);
    Check(TEXT("three_frozen_snapshots_saved"),Phase4SnapshotCount>=3);
    Check(TEXT("camera_projection_error_below_one_pixel"),Phase4SnapshotCount>=3 && MaxProjectionErrorPx<=1);
    Check(TEXT("render_surface_matches_native_bindings"),Phase4SnapshotCount>=3 && MaxBindingErrorMm<.001);
    Check(TEXT("presented_state_log_saved"),IFileManager::Get().FileSize(*FPaths::Combine(Phase4Directory,bPhase5?TEXT("phase5-presented-states.jsonl"):TEXT("phase4-presented-states.jsonl")))>0);
    Check(TEXT("curved_interior_grasp_traction_release"),bInteriorGrip && bInteriorTraction && bInteriorReleased);
    Check(TEXT("curved_direct_retreat_reaches_home"),bDirectRetreatCompleted && Phase4RetreatTravelCm>2.0);
    Check(TEXT("curved_direct_retreat_presented_node_depth_bounded"),bDirectRetreatCompleted && Phase4CollisionMaxNodeDepthMm<=.15);
    Metrics->SetNumberField(TEXT("snapshot_test_hold_s"),.85);
    Metrics->SetNumberField(TEXT("snapshots_saved"),Phase4SnapshotCount); Metrics->SetNumberField(TEXT("max_projection_error_px"),MaxProjectionErrorPx);
    Metrics->SetNumberField(TEXT("max_render_binding_error_mm"),MaxBindingErrorMm); Metrics->SetNumberField(TEXT("recorded_steps"),Phase4RecordLength);
    Metrics->SetNumberField(TEXT("elapsed_s"),Phase4Time); Metrics->SetNumberField(TEXT("unhealthy_state_count"),Bridge?Bridge->GetUnhealthyStateCount():0);
    Metrics->SetNumberField(TEXT("rejected_state_count"),Bridge?Bridge->GetRejectedStateCount():0); Metrics->SetNumberField(TEXT("safety_stop_count"),Bridge?Bridge->GetSafetyStopCount():0);
    Metrics->SetNumberField(TEXT("curved_direct_retreat_travel_mm"),Phase4RetreatTravelCm*10);
    Metrics->SetNumberField(TEXT("collision_presented_node_depth_max_mm"),Phase4CollisionMaxNodeDepthMm);
    Report->SetNumberField(TEXT("phase"),4); Report->SetNumberField(TEXT("report_version"),2);
    Report->SetStringField(TEXT("input_path"),TEXT("PlayerController InputKey -> regular controls; replay uses native recorded step commands; no visual playback."));
    Report->SetObjectField(TEXT("checks"),Checks); Report->SetObjectField(TEXT("metrics"),Metrics);
    TArray<TSharedPtr<FJsonValue>> Failures; for(const FString& F:Phase4Failures) Failures.Add(MakeShared<FJsonValueString>(F));
    Report->SetArrayField(TEXT("failures"),Failures); Report->SetBoolField(TEXT("passed"),Phase4Failures.IsEmpty());
    FFileHelper::SaveStringToFile(JsonText(Report),*FPaths::Combine(CaptureDirectory,TEXT("phase4-input-test.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    UE_LOG(LogTemp,Display,TEXT("LAP_PHASE4_TEST complete passed=%d directory=%s"),Phase4Failures.IsEmpty(),*CaptureDirectory);
    if(bAutoExit) FPlatformMisc::RequestExit(false);
}
