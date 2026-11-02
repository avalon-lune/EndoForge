#include "TrainingScene.h"
#include "SimulationBridge.h"
#include "Dom/JsonObject.h"

void ATrainingScene::UpdatePhase7Progression()
{
    if(!bPhase7)return;
    const char* Boundary=nullptr;
    if(!bPhase6StartupReady)Boundary="startup";
    else if(bPhase5Finished)Boundary="finish";
    else if(bSnapshotFrozen)Boundary="frozen_capture";
    else if(bPhase6ProofInProgress||Phase6ProofVariant>=0)Boundary="render_proof";
    else if(bResumeSnapshot||(Bridge&&Bridge->IsFrozenResumePending()))Boundary="fence_recovery";
    else if(!Bridge||Bridge->GetPhase7ProgressionObservation().StateId==0)Boundary="disconnect";
    if(Boundary)Phase7ProgressionClock.Boundary(Boundary);
    else
    {
        // Do not use IsHealthy/IsConnected here: feedback age must remain in
        // measured wall time until an actual disconnect or explicit scope boundary.
        const auto& Observation=Bridge->GetPhase7ProgressionObservation();
        Phase7ProgressionClock.Feed(Observation);
        // A disconnect may be detected after the completed receive attempt.
        // Consume that final pair first, then close; do not drop its wait time.
        if(!Bridge->GetAcceptedState().IsValid())Phase7ProgressionClock.Boundary("disconnect");
    }
    Phase5MeasuredWall=Phase7ProgressionClock.GetWallSeconds();
    Phase5MeasuredNative=Phase7ProgressionClock.GetNativeSeconds();
    if(!Phase7ProgressionClock.IsValid())
        Phase5Failures.AddUnique(FString(TEXT("Paired progression accounting invalid: "))+UTF8_TO_TCHAR(Phase7ProgressionClock.GetError().c_str()));
}

void ATrainingScene::ClosePhase7Progression(const FString& Reason)
{
    if(!bPhase7)return;
    // Normally already consumed immediately after TickDualBridge. Idempotent
    // Feed guarantees the last completed live poll is never lost at a boundary.
    UpdatePhase7Progression();
    Phase7ProgressionClock.Boundary(TCHAR_TO_UTF8(*Reason));
}

TSharedRef<FJsonObject> ATrainingScene::BuildPhase7ProgressionRecord() const
{
    auto Root=MakeShared<FJsonObject>();
    Root->SetStringField(TEXT("schema"),TEXT("endoforge.phase7.paired-progression.v1"));
    Root->SetStringField(TEXT("scope"),TEXT("Native time and monotonic wall observation captured together after each nonblocking bridge read attempt, including no-new-state polls. Ordinary live waiting, input pauses, collision-blocked motion and slow solver steps remain measured. Only explicit lifecycle/presentation boundaries rebase; replay is recorded but excluded from live throughput. Samples are observed accepted states, never predicted progress."));
    TArray<TSharedPtr<FJsonValue>> Layout;
    for(const TCHAR* Field:{TEXT("poll_id"),TEXT("wall_s"),TEXT("native_s"),TEXT("simulation_id"),TEXT("mode"),TEXT("state_id")})Layout.Add(MakeShared<FJsonValueString>(Field));
    Root->SetArrayField(TEXT("sample_layout"),Layout);
    TArray<TSharedPtr<FJsonValue>> Samples;
    for(const auto& S:Phase7ProgressionClock.GetSamples())
    {
        TArray<TSharedPtr<FJsonValue>> Row;
        Row.Add(MakeShared<FJsonValueNumber>(static_cast<double>(S.PollId)));
        Row.Add(MakeShared<FJsonValueNumber>(S.WallSeconds));Row.Add(MakeShared<FJsonValueNumber>(S.NativeSeconds));
        Row.Add(MakeShared<FJsonValueNumber>(static_cast<double>(S.SimulationId)));
        Row.Add(MakeShared<FJsonValueString>(UTF8_TO_TCHAR(S.Mode.c_str())));
        Row.Add(MakeShared<FJsonValueNumber>(static_cast<double>(S.StateId)));
        Samples.Add(MakeShared<FJsonValueArray>(Row));
    }
    Root->SetArrayField(TEXT("samples"),Samples);
    TArray<TSharedPtr<FJsonValue>> Segments;
    for(const auto& S:Phase7ProgressionClock.GetSegments())
    {
        auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("start_sample_index"),static_cast<double>(S.StartSampleIndex));O->SetNumberField(TEXT("end_sample_index"),static_cast<double>(S.EndSampleIndex));
        O->SetNumberField(TEXT("wall_s"),S.WallSeconds);O->SetNumberField(TEXT("native_s"),S.NativeSeconds);Segments.Add(MakeShared<FJsonValueObject>(O));
    }
    Root->SetArrayField(TEXT("segments"),Segments);
    TArray<TSharedPtr<FJsonValue>> Boundaries;
    for(const auto& B:Phase7ProgressionClock.GetBoundaries())
    {
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("reason"),UTF8_TO_TCHAR(B.Reason.c_str()));O->SetNumberField(TEXT("after_sample_count"),static_cast<double>(B.AfterSampleCount));
        O->SetNumberField(TEXT("last_poll_id"),static_cast<double>(B.LastPollId));O->SetBoolField(TEXT("has_last_poll"),B.HasLastPoll);Boundaries.Add(MakeShared<FJsonValueObject>(O));
    }
    Root->SetArrayField(TEXT("boundaries"),Boundaries);
    Root->SetNumberField(TEXT("wall_s"),Phase7ProgressionClock.GetWallSeconds());Root->SetNumberField(TEXT("native_s"),Phase7ProgressionClock.GetNativeSeconds());
    Root->SetBoolField(TEXT("valid"),Phase7ProgressionClock.IsValid());Root->SetStringField(TEXT("error"),UTF8_TO_TCHAR(Phase7ProgressionClock.GetError().c_str()));
    return Root;
}
