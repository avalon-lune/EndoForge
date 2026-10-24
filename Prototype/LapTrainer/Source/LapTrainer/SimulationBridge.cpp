#include "SimulationBridge.h"
#include "Sockets.h"
#include "SocketSubsystem.h"
#include "IPAddress.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "HAL/PlatformTime.h"
#include "Math/RotationMatrix.h"
#include "Misc/DateTime.h"
#include "Misc/Guid.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "HAL/FileManager.h"

namespace
{
bool ReadBoundedNumber(const TSharedPtr<FJsonObject>& Object, const TCHAR* Name, double& Out, double Min, double Max)
{
    return Object->TryGetNumberField(Name, Out) && FMath::IsFinite(Out) && Out >= Min && Out <= Max;
}

bool ReadVector(const TSharedPtr<FJsonObject>& Object, const TCHAR* Name, FVector& Out, double Scale = 1.0)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    if (!Object->TryGetArrayField(Name, Values) || Values->Num() != 3) return false;
    double V[3] = {};
    for (int32 I = 0; I < 3; ++I)
        if (!(*Values)[I]->TryGetNumber(V[I]) || !FMath::IsFinite(V[I]) || FMath::Abs(V[I]) > 100.0) return false;
    Out = FVector(V[0], V[1], V[2]) * Scale;
    return true;
}

// A bounded, type-aware canonical signature binds nested collision settings and
// authored trocar arrays as well as scalars. Object member order is immaterial.
bool AppendConfigValue(const TSharedPtr<FJsonValue>& Value, FString& Out, int32 Depth = 0)
{
    if (!Value.IsValid() || Depth > 4 || Out.Len() > 16384) return false;
    switch (Value->Type)
    {
    case EJson::Number:
    { const double N=Value->AsNumber();if(!FMath::IsFinite(N))return false;Out+=FString::Printf(TEXT("n%.17g;"),N);return true; }
    case EJson::Boolean: Out+=Value->AsBool()?TEXT("b1;"):TEXT("b0;");return true;
    case EJson::String:
    { const FString S=Value->AsString();if(S.Len()>1024)return false;Out+=FString::Printf(TEXT("s%d:"),S.Len())+S;return true; }
    case EJson::Array:
    { const auto& A=Value->AsArray();if(A.Num()>32)return false;Out+=TEXT("[");for(const auto& V:A)if(!AppendConfigValue(V,Out,Depth+1))return false;Out+=TEXT("]");return true; }
    case EJson::Object:
    { const auto O=Value->AsObject();if(!O.IsValid()||O->Values.Num()>64)return false;TArray<FString> Keys;O->Values.GetKeys(Keys);Keys.Sort();Out+=TEXT("{");
      for(const auto& K:Keys){if(K.Len()>128)return false;Out+=FString::Printf(TEXT("k%d:"),K.Len())+K;if(!AppendConfigValue(O->Values[K],Out,Depth+1))return false;}Out+=TEXT("}");return true; }
    default:return false;
    }
}
}

void USimulationBridge::InitializeBridge()
{
    if (bInitialized) return;
    bInitialized = true;
    if (FParse::Param(FCommandLine::Get(), TEXT("LapPhase3Test")) || FParse::Param(FCommandLine::Get(), TEXT("LapPhase3")))
    { ExpectedProtocol = 3; PhysicsPort = 47323; }
    if (FParse::Param(FCommandLine::Get(), TEXT("LapPhase5")) || FParse::Param(FCommandLine::Get(), TEXT("LapPhase5Test")))
    { ExpectedProtocol = 5; PhysicsPort = 47327; RequestedSpecimen = TEXT("gallbladder"); }
    bPhase6Commands=FParse::Param(FCommandLine::Get(),TEXT("LapPhase6")) || FParse::Param(FCommandLine::Get(),TEXT("LapPhase6Test"));
    if(bPhase6Commands) { ExpectedProtocol=5;PhysicsPort=47329;RequestedSpecimen=TEXT("gallbladder"); }
    int32 RequestedPort = PhysicsPort;
    if (FParse::Value(FCommandLine::Get(), TEXT("LapPhysicsPort="), RequestedPort) && RequestedPort > 1024 && RequestedPort <= 65535)
        PhysicsPort = RequestedPort;
    const FString SessionDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("Sessions"));
    IFileManager::Get().MakeDirectory(*SessionDir, true);
    TelemetryPath = FPaths::Combine(SessionDir, TEXT("session-") + FDateTime::UtcNow().ToString(TEXT("%Y%m%d-%H%M%S")) + TEXT("-utc-") + FGuid::NewGuid().ToString(EGuidFormats::Digits).Left(8) + TEXT(".csv"));
    bTelemetryEnabled = FFileHelper::SaveStringToFile(
        TEXT("utc,reset_id,mesh_revision,topology_revision,cut_count,component_count,cut_length_cm,active_tool,tool_id,command_x_cm,command_y_cm,command_z_cm,actual_x_cm,actual_y_cm,actual_z_cm,command_closed,command_roll_deg,actual_roll_deg,jaw_open_fraction,contacts,contact_force_n,grip_force_n,penetration_mm,slip_mm,solve_ms,grip_state,healthy,safety_stops\n"),
        *TelemetryPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
    if (bTelemetryEnabled) UE_LOG(LogTemp, Display, TEXT("LAP_SESSION telemetry=%s; model forces are uncalibrated"), *TelemetryPath);
    NextConnectSeconds = 0;
    TryConnect();
}

void USimulationBridge::TryConnect()
{
    if (Socket || !bInitialized) return;
    const double Now = FPlatformTime::Seconds();
    if (Now < NextConnectSeconds) return;
    NextConnectSeconds = Now + 1.0;
    ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
    if (!Sockets) { Status = TEXT("Socket subsystem unavailable"); return; }
    Socket = Sockets->CreateSocket(NAME_Stream, TEXT("LapTrainerLocalPhysics"), false);
    if (!Socket) return;
    Socket->SetNonBlocking(true);
    Socket->SetNoDelay(true);
    int32 ActualBufferSize = 0;
    Socket->SetReceiveBufferSize(1024 * 1024, ActualBufferSize);
    TSharedRef<FInternetAddr> Address = Sockets->CreateInternetAddr();
    bool bValid = false;
    Address->SetIp(TEXT("127.0.0.1"), bValid);
    Address->SetPort(PhysicsPort);
    ConnectStartedSeconds = Now;
    Socket->Connect(*Address);
    Status = FString::Printf(TEXT("Connecting to SOFA on localhost:%d"), PhysicsPort);
}

void USimulationBridge::Disconnect(const FString& Reason)
{
    FlushTelemetry();
    if (Socket)
    {
        Socket->Close();
        ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM)->DestroySocket(Socket);
        Socket = nullptr;
    }
    ReceiveBuffer.Reset();
    SendBuffer.Reset();
    SendOffset = 0;
    bHandshake = false;
    bGrasping = false;
    bHasToolState = false;
    AcceptedState.Reset(); ModelMetadata.Reset(); ModelSignature.Empty(); SessionMode = TEXT("idle"); PendingSessionAction.Empty();
    PendingActionId = AcknowledgedActionId = 0; NativeStateId = SimulationId = 0;
    JawPoses.Reset();
    ToolStates.Reset();
    ContactCount = 0;
    ContactForceNewton = 0;
    PenetrationMm = 0;
    SlipDistanceMm = 0;
    GripState = TEXT("offline");
    LastStateSeconds = 0;
    AppliedCommandSequence = 0;
    FrozenResumeFenceSequence = FrozenResumeAfterStateId = 0;
    FrozenResumeFenceSeconds = 0;
    bFrozenResumePending = false;
    ForceNewton = 0;
    Status = Reason;
    NextConnectSeconds = FPlatformTime::Seconds() + 1.0;
}

void USimulationBridge::ShutdownBridge()
{
    FlushTelemetry();
    bInitialized = false;
    Disconnect(TEXT("Physics disconnected"));
}

void USimulationBridge::BeginDestroy()
{
    ShutdownBridge();
    Super::BeginDestroy();
}

bool USimulationBridge::IsConnected() const
{
    return Socket && bHandshake && LastStateSeconds > 0 &&
        FPlatformTime::Seconds() - LastStateSeconds < 1.0;
}

FString USimulationBridge::GetStatusText() const
{
    if (bHandshake && LastStateSeconds > 0 && !IsConnected()) return TEXT("Physics data stale - interaction suspended");
    if (IsConnected() && ResetId != AcknowledgedResetId) return TEXT("Resetting physics...");
    return Status;
}

bool USimulationBridge::GetSurface(TArray<FVector>& OutVerticesCm, TArray<int32>& OutTriangles) const
{
    if (VerticesCm.IsEmpty() || Triangles.IsEmpty()) return false;
    OutVerticesCm = VerticesCm;
    OutTriangles = Triangles;
    return true;
}

bool USimulationBridge::GetJawPose(int32 JawIndex, FTransform& OutPoseCm) const
{
    if (!HasToolState() || !JawPoses.IsValidIndex(JawIndex)) return false;
    const FLapJawPose& Pose = JawPoses[JawIndex];
    OutPoseCm = FTransform(FRotationMatrix::MakeFromXY(Pose.Axis, Pose.Side).ToQuat(), Pose.CenterCm);
    return true;
}

void USimulationBridge::RequestSessionAction(const FString& Action)
{
    if (ExpectedProtocol < 4 || !IsConnected() || HasPendingSessionAction()) return;
    PendingSessionAction = Action;
    PendingActionId = FMath::Max(PendingActionId, AcknowledgedActionId) + 1;
}

void USimulationBridge::QueueCommand(const TArray<FLapToolCommand>& Commands, int32 ActiveTool, bool bPermitClosure)
{
    // A partially transmitted record must finish before the next record is queued.
    if (!SendBuffer.IsEmpty() || Commands.Num() != 2) return;
    LastCommands = Commands;
    LastActiveTool = FMath::Clamp(ActiveTool, 0, 1);
    TSharedRef<FJsonObject> Command = MakeShared<FJsonObject>();
    Command->SetStringField(TEXT("type"), TEXT("command"));
    Command->SetNumberField(TEXT("seq"), static_cast<double>(++CommandSequence));
    Command->SetNumberField(TEXT("active_tool"), LastActiveTool);
    TArray<TSharedPtr<FJsonValue>> Tools;
    for (const FLapToolCommand& Input : Commands)
    {
        TSharedRef<FJsonObject> Tool = MakeShared<FJsonObject>();
        TArray<TSharedPtr<FJsonValue>> Tip;
        const FVector SafeTip = Input.TipCm.ContainsNaN() ? FVector(0, -4.7, 2.5) : Input.TipCm;
        Tip.Add(MakeShared<FJsonValueNumber>(SafeTip.X * .01));
        Tip.Add(MakeShared<FJsonValueNumber>(SafeTip.Y * .01));
        Tip.Add(MakeShared<FJsonValueNumber>(SafeTip.Z * .01));
        Tool->SetArrayField(TEXT("tip_m"), Tip);
        Tool->SetNumberField(TEXT("closed"), Input.bClosed && bPermitClosure ? 1.0 : 0.0);
        Tool->SetNumberField(TEXT("roll_deg"), FMath::IsFinite(Input.RollDeg) ? FMath::UnwindDegrees(Input.RollDeg) : 0.0f);
        if(bPhase6Commands) { Tool->SetBoolField(TEXT("hold_tip"),Input.bHoldTip);Tool->SetBoolField(TEXT("hold_roll"),Input.bHoldRoll);Tool->SetBoolField(TEXT("bounded_target"),Input.bBoundedTarget); }
        Tools.Add(MakeShared<FJsonValueObject>(Tool));
    }
    Command->SetArrayField(TEXT("tools"), Tools);
    Command->SetNumberField(TEXT("reset_id"), ResetId);
    Command->SetBoolField(TEXT("paused"), false);
    if (ExpectedProtocol >= 4)
    {
        Command->SetStringField(TEXT("specimen"), RequestedSpecimen);
        Command->SetNumberField(TEXT("action_id"), static_cast<double>(PendingActionId));
        if (HasPendingSessionAction()) Command->SetStringField(TEXT("session_action"), PendingSessionAction);
    }
    FString Text;
    auto Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Text);
    FJsonSerializer::Serialize(Command, Writer);
    Text += TEXT("\n");
    FTCHARToUTF8 Encoded(*Text);
    SendBuffer.Append(reinterpret_cast<const uint8*>(Encoded.Get()), Encoded.Length());
    SendOffset = 0;
}

void USimulationBridge::TickBridge(float DeltaSeconds, const FVector& ToolTipCm, bool bClosed, bool bReset, float RollDeg)
{
    TArray<FLapToolCommand> Commands;
    Commands.Add({ToolTipCm, bClosed, RollDeg});
    Commands.Add({FVector(2.2, -4.7, .6), false, 90.0f});
    TickDualBridge(DeltaSeconds, Commands, 0, bReset);
}

void USimulationBridge::TickDualBridge(float DeltaSeconds, const TArray<FLapToolCommand>& Commands, int32 ActiveTool, bool bReset)
{
    if (!bInitialized) InitializeBridge();
    if (bReset) ++ResetId;
    if (!Socket) { TryConnect(); return; }
    const ESocketConnectionState Connection = Socket->GetConnectionState();
    if (Connection == SCS_ConnectionError) { Disconnect(TEXT("SOFA unavailable - launch with StartTrainer.cmd")); return; }
    if (Connection != SCS_Connected)
    {
        if (FPlatformTime::Seconds() - ConnectStartedSeconds > 2.0) Disconnect(TEXT("Waiting for SOFA service"));
        return;
    }
    ReceiveMessages();
    if (!Socket) return;
    CheckFrozenResumeFence();
    const uint64 PreviousCommandSequence = CommandSequence;
    QueueCommand(Commands, ActiveTool, bHealthy && IsConnected() && ResetId == AcknowledgedResetId);
    if (bPhase6Commands && bFrozenResumePending && FrozenResumeFenceSequence == 0 &&
        CommandSequence > PreviousCommandSequence)
    {
        // QueueCommand may have declined while finishing a partially sent frozen
        // command. Only a newly queued ordinary command is a post-freeze fence.
        FrozenResumeFenceSequence = CommandSequence;
        FrozenResumeFenceSeconds = FPlatformTime::Seconds();
        UE_LOG(LogTemp, Display, TEXT("LAP_PHASE6_RESUME_FENCE queued=%llu after_state=%llu"),
            static_cast<unsigned long long>(FrozenResumeFenceSequence),
            static_cast<unsigned long long>(FrozenResumeAfterStateId));
    }
    if (SendOffset < SendBuffer.Num())
    {
        int32 Sent = 0;
        Socket->Send(SendBuffer.GetData() + SendOffset, SendBuffer.Num() - SendOffset, Sent);
        SendOffset += FMath::Max(0, Sent);
        if (SendOffset >= SendBuffer.Num()) { SendBuffer.Reset(); SendOffset = 0; }
    }
    const double Now = FPlatformTime::Seconds();
    if ((bHandshake && LastStateSeconds > 0 && Now - LastStateSeconds > 3.0) ||
        (LastStateSeconds == 0 && Now - ConnectStartedSeconds > 5.0))
        Disconnect(TEXT("SOFA timed out - reconnecting"));
}

void USimulationBridge::TickFrozenBridge()
{
    // A snapshot freezes only presentation. Keep the last user command alive without
    // consuming/committing newer states, so image geometry and metadata stay identical.
    if (!Socket || Socket->GetConnectionState()!=SCS_Connected || LastCommands.Num()!=2) return;
    if (bPhase6Commands && !IsReplayLocked())
    {
        // Each frozen heartbeat invalidates any earlier resume fence. This also
        // covers consecutive stereo/review captures in one actor tick.
        bFrozenResumePending = true;
        FrozenResumeFenceSequence = 0;
        FrozenResumeFenceSeconds = 0;
        FrozenResumeAfterStateId = NativeStateId;
    }
    else if (bPhase6Commands)
    {
        // Replay ignores live commands. Its snapshot recovery retains the
        // existing presentation-only behavior, without a live command fence.
        bFrozenResumePending = false;
        FrozenResumeFenceSequence = 0;
    }
    const TArray<FLapToolCommand> FrozenCommands=LastCommands;
    QueueCommand(FrozenCommands,LastActiveTool,bHealthy && ResetId==AcknowledgedResetId);
    if (SendOffset<SendBuffer.Num())
    {
        int32 Sent=0; Socket->Send(SendBuffer.GetData()+SendOffset,SendBuffer.Num()-SendOffset,Sent);
        SendOffset+=FMath::Max(0,Sent);
        if(SendOffset>=SendBuffer.Num()) { SendBuffer.Reset(); SendOffset=0; }
    }
}

void USimulationBridge::CheckFrozenResumeFence()
{
    if (bPhase6Commands && IsReplayLocked())
    {
        // A session action may enter replay while a live fence is pending.
        // Do not carry an unacknowledgeable live sequence across that boundary.
        if (bFrozenResumePending)
            UE_LOG(LogTemp, Display, TEXT("LAP_PHASE6_RESUME_FENCE bypassed mode=%s; no live-command freshness guarantee"), *SessionMode);
        bFrozenResumePending = false;
        FrozenResumeFenceSequence = 0;
        return;
    }
    if (!IsFrozenResumePending() || FrozenResumeFenceSequence == 0 || !IsHealthy() ||
        ResetId != AcknowledgedResetId || NativeStateId <= FrozenResumeAfterStateId ||
        LastStateSeconds < FrozenResumeFenceSeconds) return;
    if (AppliedCommandSequence < FrozenResumeFenceSequence) return;
    UE_LOG(LogTemp, Display, TEXT("LAP_PHASE6_RESUME_FENCE accepted=%llu applied=%llu state=%llu simulation=%llu native_s=%.9f"),
        static_cast<unsigned long long>(FrozenResumeFenceSequence),
        static_cast<unsigned long long>(AppliedCommandSequence),
        static_cast<unsigned long long>(NativeStateId),
        static_cast<unsigned long long>(SimulationId), NativeTime);
    bFrozenResumePending = false;
}

void USimulationBridge::ReceiveMessages()
{
    uint32 Pending = 0;
    uint8 Buffer[32768];
    // Bound work on the game thread even when the peer misbehaves.
    for (int32 ReadCount = 0; ReadCount < 32 && Socket && Socket->HasPendingData(Pending); ++ReadCount)
    {
        int32 Read = 0;
        if (!Socket->Recv(Buffer, FMath::Min<int32>(Pending, sizeof(Buffer)), Read) || Read <= 0) break;
        ReceiveBuffer.Append(Buffer, Read);
        if (ReceiveBuffer.Num() > 4 * 1024 * 1024) { Disconnect(TEXT("Physics protocol exceeded buffer limit")); return; }
    }
    int32 LineStart = 0;
    for (int32 Index = 0; Index < ReceiveBuffer.Num(); ++Index)
    {
        if (ReceiveBuffer[Index] != '\n') continue;
        const int32 Count = Index - LineStart;
        FUTF8ToTCHAR Decoded(reinterpret_cast<const ANSICHAR*>(ReceiveBuffer.GetData() + LineStart), Count);
        const FString Line(Decoded.Length(), Decoded.Get());
        HandleMessage(Line);
        LineStart = Index + 1;
    }
    if (LineStart > 0) ReceiveBuffer.RemoveAt(0, LineStart, EAllowShrinking::No);
}

void USimulationBridge::HandleMessage(const FString& Line)
{
    auto Reject = [this](const TCHAR* Reason)
    {
        ++RejectedStateCount;
        Status = FString(TEXT("Invalid SOFA state: ")) + Reason;
        if (FPlatformTime::Seconds() - LastRejectedStateLogSeconds > 3.0)
        {
            LastRejectedStateLogSeconds = FPlatformTime::Seconds();
            UE_LOG(LogTemp, Warning, TEXT("LAP_PROTOCOL %s"), *Status);
        }
    };
    TSharedPtr<FJsonObject> Object;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Line), Object) || !Object.IsValid())
    { Reject(TEXT("malformed JSON")); return; }
    FString Type;
    if (!Object->TryGetStringField(TEXT("type"), Type)) { Reject(TEXT("message type missing")); return; }
    const bool Hello = Type == TEXT("hello");
    if (!Hello && (Type != TEXT("state") || !bHandshake)) { Reject(TEXT("unexpected message")); return; }
    if (Hello)
    {
        if (bHandshake) { Reject(TEXT("duplicate handshake on an established connection")); return; }
        double Protocol = 0;
        FString Units;
        if (!Object->TryGetNumberField(TEXT("protocol"), Protocol) || Protocol != ExpectedProtocol ||
            !Object->TryGetStringField(TEXT("units"), Units) || Units != TEXT("m"))
        { Reject(TEXT("Client requires matching physics protocol")); return; }
    }
    // Positions, connectivity and tool poses are one transaction. Never display a new
    // topology with vertices or commands from a different accepted state.
    const TArray<TSharedPtr<FJsonValue>> *Nodes = nullptr, *Faces = nullptr;
    if (!Object->TryGetArrayField(TEXT("vertices"), Nodes) || Nodes->IsEmpty() || Nodes->Num() > 10000 ||
        !Object->TryGetArrayField(TEXT("triangles"), Faces) || Faces->IsEmpty() || Faces->Num() > 20000)
    { Reject(TEXT("missing or excessive mesh")); return; }
    TArray<FVector> NewVertices;
    for (const auto& Node : *Nodes)
    {
        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (!Node->TryGetArray(Values) || Values->Num() != 3) { Reject(TEXT("vertex shape")); return; }
        double P[3] = {};
        for (int32 I = 0; I < 3; ++I)
            if (!(*Values)[I]->TryGetNumber(P[I]) || !FMath::IsFinite(P[I]) || FMath::Abs(P[I]) > 2)
            { Reject(TEXT("vertex coordinate")); return; }
        NewVertices.Add(FVector(P[0], P[1], P[2]) * 100.0);
    }
    TArray<int32> NewTriangles;
    for (const auto& Face : *Faces)
    {
        const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
        if (!Face->TryGetArray(Values) || Values->Num() != 3) { Reject(TEXT("face shape")); return; }
        int32 Idx[3] = {};
        for (int32 I = 0; I < 3; ++I)
        {
            double N = 0;
            if (!(*Values)[I]->TryGetNumber(N) || !FMath::IsFinite(N) || N < 0 || N >= NewVertices.Num() || N != FMath::FloorToDouble(N))
            { Reject(TEXT("face index outside vertex array")); return; }
            Idx[I] = static_cast<int32>(N);
        }
        if (Idx[0] == Idx[1] || Idx[0] == Idx[2] || Idx[1] == Idx[2]) { Reject(TEXT("repeated triangle vertex")); return; }
        NewTriangles.Append(Idx, 3);
    }
    double NewTopology = 0, NewCuts = 0, NewComponents = 1, NewLength = 0;
    double NewStep = 0, NewDisp = 0, NewReset = 0, NewSafetyStops = 0;
    double NewAppliedSequence = 0;
    bool NewHealthy = true;
    TArray<FLapToolState> NewTools;
    FString Detail;
    if (!Hello)
    {
        auto IntField = [&](const TCHAR* Name, double& Out, double Max)
        { return ReadBoundedNumber(Object, Name, Out, 0, Max) && Out == FMath::FloorToDouble(Out); };
        if (bPhase6Commands)
        {
            if (!IntField(TEXT("applied_command_seq"), NewAppliedSequence, 9007199254740991.0) ||
                NewAppliedSequence > static_cast<double>(CommandSequence))
            { Reject(TEXT("invalid Phase 6 applied command sequence")); return; }
        }
        if (!IntField(TEXT("safety_stops"), NewSafetyStops, MAX_int32) ||
            !IntField(TEXT("topology_revision"), NewTopology, MAX_int32) ||
            !IntField(TEXT("cut_count"), NewCuts, 100000) || !IntField(TEXT("component_count"), NewComponents, 20000) || NewComponents < 1 ||
            !ReadBoundedNumber(Object, TEXT("cut_length_m"), NewLength, 0, 100) ||
            !ReadBoundedNumber(Object, TEXT("step_ms"), NewStep, 0, 60000) ||
            !ReadBoundedNumber(Object, TEXT("max_displacement_m"), NewDisp, 0, 10) ||
            !IntField(TEXT("reset_id"), NewReset, MAX_int32) || !Object->TryGetBoolField(TEXT("healthy"), NewHealthy))
        { Reject(TEXT("invalid topology or health telemetry")); return; }
        if (NewReset > ResetId || (bHasToolState && NewReset < AcknowledgedResetId))
        { Reject(TEXT("unsolicited or stale reset acknowledgement")); return; }
        if (bHasToolState && static_cast<int32>(NewReset) == AcknowledgedResetId)
        {
            if (NewTopology < TopologyRevision || NewCuts < CutCount)
            { Reject(TEXT("topology went backwards without reset")); return; }
            if (static_cast<uint64>(NewTopology) == TopologyRevision &&
                (NewTriangles != Triangles || NewVertices.Num() != VerticesCm.Num()))
            { Reject(TEXT("connectivity changed without a topology revision")); return; }
        }
        const TArray<TSharedPtr<FJsonValue>>* ToolValues = nullptr;
        if (!Object->TryGetArrayField(TEXT("tools"), ToolValues) || ToolValues->Num() != 2)
        { Reject(TEXT("expected two independent tools")); return; }
        for (const auto& Value : *ToolValues)
        {
            const TSharedPtr<FJsonObject>* Tool = nullptr;
            if (!Value->TryGetObject(Tool) || !Tool->IsValid()) { Reject(TEXT("tool object")); return; }
            FLapToolState T;
            double Roll = 0, Open = 0, Force = 0, Contacts = 0, ContactForce = 0, Pen = 0, Slip = 0;
            if (!ReadVector(*Tool, TEXT("tip_m"), T.ActualTipCm, 100) ||
                !ReadBoundedNumber(*Tool, TEXT("roll_deg"), Roll, -36000, 36000) ||
                !ReadBoundedNumber(*Tool, TEXT("jaw_open_fraction"), Open, 0, 1) ||
                !ReadBoundedNumber(*Tool, TEXT("force_n"), Force, 0, 100000) ||
                !ReadBoundedNumber(*Tool, TEXT("contact_count"), Contacts, 0, 100000) || Contacts != FMath::FloorToDouble(Contacts) ||
                !ReadBoundedNumber(*Tool, TEXT("contact_force_n"), ContactForce, 0, 100000) ||
                !ReadBoundedNumber(*Tool, TEXT("penetration_m"), Pen, 0, 10) ||
                !ReadBoundedNumber(*Tool, TEXT("slip_distance_m"), Slip, 0, 10) ||
                !(*Tool)->TryGetBoolField(TEXT("grasping"), T.bGrasping) ||
                !(*Tool)->TryGetStringField(TEXT("grip_state"), T.GripState) || T.GripState.Len() > 64)
            { Reject(TEXT("invalid dual tool telemetry")); return; }
            T.RollDeg = Roll; T.JawOpenFraction = Open; T.ForceNewton = Force;
            T.ContactCount = static_cast<int32>(Contacts); T.ContactForceNewton = ContactForce;
            T.PenetrationMm = Pen * 1000; T.SlipDistanceMm = Slip * 1000;
            if(bPhase6Commands)
            {
                const TSharedPtr<FJsonObject>* Guard=nullptr;FString Implementation;bool InitialValid=false;
                double Witness=0,Margin=0,Work=0,InitialClearance=0,EndpointClearance=0;
                if(!(*Tool)->TryGetObjectField(TEXT("motion_guard"),Guard)||!Guard->IsValid()||
                    !(*Guard)->TryGetStringField(TEXT("implementation"),Implementation)||Implementation!=TEXT("phase6-rcm-jaw-liver-ccd-v1")||
                    !(*Guard)->TryGetBoolField(TEXT("blocked"),T.bMotionBlocked)||!(*Guard)->TryGetBoolField(TEXT("initial_valid"),InitialValid)||
                    !(*Guard)->TryGetStringField(TEXT("reason"),T.MotionGuardReason)||T.MotionGuardReason.IsEmpty()||T.MotionGuardReason.Len()>96||
                    !ReadBoundedNumber(*Guard,TEXT("accepted_fraction"),T.MotionAcceptedFraction,0,1)||
                    !ReadBoundedNumber(*Guard,TEXT("witness_triangle"),Witness,-1,2000000)||Witness!=FMath::FloorToDouble(Witness)||
                    !ReadBoundedNumber(*Guard,TEXT("clearance_margin_m"),Margin,.00015,.00015)||
                    !ReadBoundedNumber(*Guard,TEXT("work_count"),Work,0,512)||Work!=FMath::FloorToDouble(Work)||
                    !ReadBoundedNumber(*Guard,TEXT("initial_clearance_m"),InitialClearance,0,1000)||
                    !ReadBoundedNumber(*Guard,TEXT("endpoint_clearance_m"),EndpointClearance,0,1000)||
                    (!InitialValid&&NewHealthy)||(InitialValid&&(InitialClearance<=Margin||EndpointClearance<=Margin||Work<1))||(!T.bMotionBlocked&&(T.MotionAcceptedFraction!=1||T.MotionGuardReason!=TEXT("clear")))||
                    (T.bMotionBlocked&&(T.MotionAcceptedFraction>=1||T.MotionGuardReason==TEXT("clear"))))
                {Reject(TEXT("invalid continuous rigid-liver motion guard"));return;}
                T.MotionWitnessTriangle=static_cast<int32>(Witness);T.MotionGuardWorkCount=static_cast<int32>(Work);T.MotionClearanceMm=EndpointClearance*1000;
            }
            const TArray<TSharedPtr<FJsonValue>>* Jaws = nullptr;
            if (!(*Tool)->TryGetArrayField(TEXT("jaw_poses"), Jaws) || Jaws->Num() != 2)
            { Reject(TEXT("tool needs two jaw frames")); return; }
            for (const auto& J : *Jaws)
            {
                const TSharedPtr<FJsonObject>* P = nullptr;
                FLapJawPose Pose;
                if (!J->TryGetObject(P) || !P->IsValid() ||
                    !ReadVector(*P, TEXT("center_m"), Pose.CenterCm, 100) ||
                    !ReadVector(*P, TEXT("axis"), Pose.Axis) || !ReadVector(*P, TEXT("side"), Pose.Side) || !ReadVector(*P, TEXT("normal"), Pose.Normal))
                { Reject(TEXT("jaw frame vectors")); return; }
                if (!FMath::IsNearlyEqual(Pose.Axis.SizeSquared(), 1.0, .01) ||
                    !FMath::IsNearlyEqual(Pose.Side.SizeSquared(), 1.0, .01) ||
                    !FMath::IsNearlyEqual(Pose.Normal.SizeSquared(), 1.0, .01) ||
                    FMath::Abs(FVector::DotProduct(Pose.Axis, Pose.Side)) > .01 ||
                    FMath::Abs(FVector::DotProduct(Pose.Axis, Pose.Normal)) > .01 ||
                    FMath::Abs(FVector::DotProduct(Pose.Side, Pose.Normal)) > .01 ||
                    FVector::DotProduct(FVector::CrossProduct(Pose.Axis, Pose.Side), Pose.Normal) < .99)
                { Reject(TEXT("jaw frame is not orthonormal")); return; }
                T.JawPoses.Add(Pose);
            }
            if(ExpectedProtocol==5 && !ReadVector(*Tool,TEXT("pivot_m"),T.PivotCm,100)) {Reject(TEXT("missing anatomy trocar pose"));return;}
            NewTools.Add(MoveTemp(T));
        }
        Object->TryGetStringField(TEXT("message"), Detail);
    }
    // Validate all Phase 4 identity/session metadata before committing geometry or tools.
    FString NewSpecimen, NewMode, NewError, NewConfigSignature;
    double NewNativeFrame=0;
    double NewStateId = 0, NewSimulationId = 0, NewActionId = 0, NewIndex = 0, NewReplayLength = 0, NewRecordedSteps = 0, NewTime = 0;
    TArray<int32> NewNodeIds, NewMaterialIds;
    if (ExpectedProtocol >= 4)
    {
        auto Int = [](const TSharedPtr<FJsonObject>& O, const TCHAR* N, double& V)
        { return ReadBoundedNumber(O, N, V, 0, 2147483647) && V == FMath::FloorToDouble(V); };
        const TSharedPtr<FJsonObject>* Session = nullptr;
        const TSharedPtr<FJsonObject>* Config = nullptr;
        if (!Object->TryGetStringField(TEXT("specimen"), NewSpecimen) ||
            (ExpectedProtocol == 5 ? NewSpecimen != TEXT("gallbladder") : (NewSpecimen != TEXT("flat") && NewSpecimen != TEXT("curved"))) ||
            !Object->TryGetObjectField(TEXT("config"), Config) || !Config->IsValid() ||
            !Int(Object, TEXT("state_id"), NewStateId) || !Int(Object, TEXT("simulation_id"), NewSimulationId) ||
            !Object->TryGetObjectField(TEXT("session"), Session) || !Session->IsValid() ||
            !(*Session)->TryGetStringField(TEXT("mode"), NewMode) ||
            !(NewMode == TEXT("idle") || NewMode == TEXT("recording") || NewMode == TEXT("replaying") || NewMode == TEXT("replay_complete")) ||
            !Int(*Session, TEXT("action_id"), NewActionId) || !Int(*Session, TEXT("step_index"), NewIndex) ||
            !Int(*Session, TEXT("replay_length"), NewReplayLength) || !Int(*Session, TEXT("recorded_steps"), NewRecordedSteps) ||
            !(*Session)->TryGetStringField(TEXT("error"), NewError) || NewError.Len() > 1024 ||
            (!Hello && !ReadBoundedNumber(Object, TEXT("time"), NewTime, 0, 10000000)))
        { Reject(TEXT("invalid Phase 4 snapshot/session metadata")); return; }
        FString ConfigName;
        if (!(*Config)->TryGetStringField(TEXT("name"),ConfigName) || ConfigName!=NewSpecimen)
        { Reject(TEXT("configuration specimen mismatch")); return; }
        NewConfigSignature=ConfigName;
        struct FConfigRange { const TCHAR* Name; double Min,Max; };
        const FConfigRange Ranges[]={{TEXT("width_m"),.08,.14},{TEXT("length_m"),.06,.10},{TEXT("thickness_m"),.001,.003},
            {TEXT("curvature_m"),0,.015},{TEXT("young_modulus_pa"),10000,60000},{TEXT("poisson_ratio"),.2,.45},
            {TEXT("density_kg_m3"),800,1200},{TEXT("rayleigh_mass"),1,20},{TEXT("rayleigh_stiffness"),.001,.05},
            {TEXT("friction"),.1,1.2},{TEXT("fixed_rows"),1,3},{TEXT("mesh_nx"),25,25},{TEXT("mesh_ny"),17,17},
            {TEXT("contact_offset_m"),.00045,.00045},{TEXT("alarm_distance_m"),.0015,.0015}};
        for (const auto& Range:Ranges)
        {
            double V=0, Lo=Range.Min, Hi=Range.Max;
            if(ExpectedProtocol==5)
            {
                const FString Field(Range.Name);
                if(Field==TEXT("width_m") || Field==TEXT("length_m")) { Lo=.005; Hi=1; }
                if(Field==TEXT("thickness_m")) { Lo=.0001; Hi=.02; }
                if(Field==TEXT("mesh_nx") || Field==TEXT("mesh_ny")) { Lo=1; Hi=10000; }
                if(Field==TEXT("fixed_rows")) { Lo=0; Hi=100000; }
            }
            if(!ReadBoundedNumber(*Config,Range.Name,V,Lo,Hi) ||
                (FCString::Strcmp(Range.Name,TEXT("fixed_rows"))==0 && V!=FMath::FloorToDouble(V)) ||
                (FCString::Strcmp(Range.Name,TEXT("curvature_m"))==0 && ConfigName==TEXT("flat") && V!=0))
            { Reject(TEXT("invalid effective physical configuration")); return; }
            NewConfigSignature+=FString::Printf(TEXT("|%.17g"),V);
        }
        FVector Gravity;
        if(!ReadVector(*Config,TEXT("gravity_m_s2"),Gravity) || !Gravity.IsZero())
        { Reject(TEXT("unsupported configured gravity")); return; }
        if(ExpectedProtocol==5)
        {
            if(bPhase6Commands)
            {
                const TSharedPtr<FJsonObject>* Guard=nullptr;FString Implementation,ForceScope,GuardAsset,Asset;double Number=0;
                if(!(*Config)->TryGetObjectField(TEXT("tool_motion_guard"),Guard)||!Guard->IsValid()||
                    !(*Guard)->TryGetStringField(TEXT("implementation"),Implementation)||Implementation!=TEXT("phase6-rcm-jaw-liver-ccd-v1")||
                    !ReadBoundedNumber(*Guard,TEXT("clearance_margin_m"),Number,.00015,.00015)||
                    !ReadBoundedNumber(*Guard,TEXT("maximum_intervals"),Number,512,512)||
                    !ReadBoundedNumber(*Guard,TEXT("maximum_depth"),Number,26,26)||
                    !ReadBoundedNumber(*Guard,TEXT("minimum_fraction"),Number,1./67108864.,1./67108864.)||
                    !(*Config)->TryGetStringField(TEXT("force_scope"),ForceScope)||ForceScope!=TEXT("soft_tissue_contact_impulse_only; rigid_liver_motion_guard_has_no_reaction_force")||
                    !(*Config)->TryGetStringField(TEXT("asset_fingerprint"),Asset)||!(*Guard)->TryGetStringField(TEXT("static_geometry_asset_fingerprint"),GuardAsset)||Asset!=GuardAsset)
                {Reject(TEXT("unrecognized Phase6 collision/force configuration"));return;}
            }
            if(!AppendConfigValue(MakeShared<FJsonValueObject>(*Config),NewConfigSignature))
            {Reject(TEXT("unsupported anatomy configuration value"));return;}
        }
        const TArray<TSharedPtr<FJsonValue>>* Parents=nullptr;
        if(!Object->TryGetArrayField(TEXT("parent_node_ids"),Parents) || Parents->Num()!=NewVertices.Num())
        { Reject(TEXT("parent identity count mismatch")); return; }
        for(const auto& Parent:*Parents)
        {
            double P=0;
            if(!Parent->TryGetNumber(P) || !FMath::IsFinite(P) || P < -1 || P>MAX_int32 || P!=FMath::FloorToDouble(P))
            { Reject(TEXT("invalid parent node identity")); return; }
        }
        if(!Hello && FMath::Abs(NewTime-NewIndex/30.0)>1e-5)
        { Reject(TEXT("simulation time does not match accepted step index")); return; }
        if(!Hello && !Int(Object,TEXT("frame"),NewNativeFrame))
        { Reject(TEXT("invalid native frame identity")); return; }
        if((NewMode==TEXT("replaying") || NewMode==TEXT("replay_complete")) &&
            (NewReplayLength<1 || NewIndex>NewReplayLength || (NewMode==TEXT("replay_complete") && NewIndex!=NewReplayLength)))
        { Reject(TEXT("invalid replay timeline")); return; }
        for (int32 Which = 0; Which < 2; ++Which)
        {
            const TArray<TSharedPtr<FJsonValue>>* Ids = nullptr;
            if (!Object->TryGetArrayField(Which == 0 ? TEXT("node_ids") : TEXT("material_node_ids"), Ids) || Ids->Num() != NewVertices.Num())
            { Reject(TEXT("node identity count mismatch")); return; }
            TSet<int32> Unique;
            for (const auto& Id : *Ids)
            {
                double N = 0;
                if (!Id->TryGetNumber(N) || !FMath::IsFinite(N) || N < 0 || N > MAX_int32 || N != FMath::FloorToDouble(N) || (Which == 0 && Unique.Contains(static_cast<int32>(N))))
                { Reject(TEXT("invalid or duplicate node identity")); return; }
                (Which == 0 ? NewNodeIds : NewMaterialIds).Add(static_cast<int32>(N));
                Unique.Add(static_cast<int32>(N));
            }
        }
        if (!Hello && bHasToolState)
        {
            if (NewStateId <= NativeStateId || NewSimulationId < SimulationId || NewActionId < AcknowledgedActionId || NewNativeFrame < NativeFrame)
            { Reject(TEXT("stale Phase 4 state identity")); return; }
            if (NewReset == AcknowledgedResetId && (NewIndex<StepIndex || NewTime+1e-9<NativeTime))
            { Reject(TEXT("simulation timeline regressed without reset")); return; }
            if (NewReset == AcknowledgedResetId && (NewSimulationId != SimulationId || NewSpecimen != Specimen || NewConfigSignature != ConfigSignature))
            { Reject(TEXT("configuration changed without reset")); return; }
            if (NewReset == AcknowledgedResetId && NewTopology == TopologyRevision &&
                (NewNodeIds != NodeIds || NewMaterialIds != MaterialIds))
            { Reject(TEXT("node identities changed without topology revision")); return; }
        }
    }
    FString NewModelSignature;
    if(ExpectedProtocol==5)
    {
        for(const TCHAR* Key:{TEXT("model_id"),TEXT("model_version"),TEXT("asset_fingerprint")})
        {
            FString Value;
            if(!Object->TryGetStringField(Key,Value))
            {
                double Version=0;
                if(FString(Key)==TEXT("model_version") && Object->TryGetNumberField(Key,Version) && FMath::IsFinite(Version) && Version>=1 && Version==FMath::FloorToDouble(Version)) Value=FString::Printf(TEXT("%.0f"),Version);
            }
            if(Value.IsEmpty() || Value.Len()>256) { Reject(TEXT("missing anatomy model provenance")); return; }
            NewModelSignature+=Value+TEXT("|");
        }
          NewModelSignature+=NewConfigSignature;
          if(!Hello && NewModelSignature!=ModelSignature)
        { Reject(TEXT("anatomy asset changed on an established connection")); return; }
    }
    VerticesCm = MoveTemp(NewVertices);
    Triangles = MoveTemp(NewTriangles);
    PhysicsNodeCount = VerticesCm.Num();
    ++MeshRevision;
    if (ExpectedProtocol >= 4)
    {
        ConfigSignature=NewConfigSignature; NativeFrame=static_cast<uint64>(NewNativeFrame);
        NativeStateId = static_cast<uint64>(NewStateId); SimulationId = static_cast<uint64>(NewSimulationId);
        StepIndex = static_cast<uint64>(NewIndex); ReplayLength = static_cast<uint64>(NewReplayLength);
        RecordedSteps = static_cast<uint64>(NewRecordedSteps); NativeTime = NewTime;
        Specimen = NewSpecimen; SessionMode = NewMode; SessionError = NewError;
        if (Hello || static_cast<int32>(NewReset)==ResetId) RequestedSpecimen = Specimen;
        AcknowledgedActionId = static_cast<uint64>(NewActionId);
        if (!HasPendingSessionAction()) PendingSessionAction.Empty();
        NodeIds = MoveTemp(NewNodeIds); MaterialIds = MoveTemp(NewMaterialIds);
        AcceptedState = Object;
    }
    if (Hello)
    {
        if(ExpectedProtocol==5) { ModelSignature=NewModelSignature; ModelMetadata=Object; }
        Object->TryGetStringField(TEXT("solver"), SolverName);
        bHandshake = true;
        UE_LOG(LogTemp, Display, TEXT("EndoForge protocol %d handshake: %s"), ExpectedProtocol, *SolverName);
        return;
    }
    ToolStates = MoveTemp(NewTools);
    TopologyRevision = static_cast<uint64>(NewTopology);
    CutCount = static_cast<int32>(NewCuts); ComponentCount = static_cast<int32>(NewComponents); CutLengthCm = NewLength * 100;
    PhysicsStepMs = NewStep; MaxDisplacementCm = NewDisp * 100;
    AcknowledgedResetId = static_cast<int32>(NewReset); bHealthy = NewHealthy;
    if (!bHealthy) ++UnhealthyStateCount;
    // Retain observed protection history across resets and reconnects.
    SafetyStopCount = FMath::Max(SafetyStopCount, static_cast<uint64>(NewSafetyStops));
    bHasToolState = true; LastStateSeconds = FPlatformTime::Seconds();
    if (bPhase6Commands)
    {
        AppliedCommandSequence = static_cast<uint64>(NewAppliedSequence);
    }
    const FLapToolState& Grasper = ToolStates[0];
    bGrasping = Grasper.bGrasping; ForceNewton = Grasper.ForceNewton;
    ActualTipCm = Grasper.ActualTipCm; ActualRollDeg = Grasper.RollDeg; JawOpenFraction = Grasper.JawOpenFraction;
    ContactCount = Grasper.ContactCount; ContactForceNewton = Grasper.ContactForceNewton;
    PenetrationMm = Grasper.PenetrationMm; SlipDistanceMm = Grasper.SlipDistanceMm;
    GripState = Grasper.GripState; JawPoses = Grasper.JawPoses;
    Status = bHealthy ? FString(TEXT("SOFA | ")) + Detail.Left(160) : FString(TEXT("SOFA paused: ")) + Detail.Left(160);
    RecordTelemetry();
}

void USimulationBridge::RecordTelemetry()
{
    const double Now = FPlatformTime::Seconds();
    if (!bTelemetryEnabled || Now - LastTelemetrySeconds < .1 || ToolStates.Num() != 2 || LastCommands.Num() != 2) return;
    LastTelemetrySeconds = Now;
    for (int32 I = 0; I < 2; ++I)
    {
        const FLapToolState& T = ToolStates[I];
        const FLapToolCommand& C = LastCommands[I];
        FString SafeGrip = T.GripState.Replace(TEXT(","), TEXT("_")).Replace(TEXT("\n"), TEXT(" ")).Replace(TEXT("\r"), TEXT(" "));
        TelemetryBuffer += FString::Printf(TEXT("%s,%d,%llu,%llu,%d,%d,%.5f,%d,%d,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%d,%.3f,%.3f,%.4f,%d,%.6f,%.6f,%.6f,%.6f,%.4f,%s,%d,%llu\n"),
            *FDateTime::UtcNow().ToIso8601(), AcknowledgedResetId, static_cast<unsigned long long>(MeshRevision),
            static_cast<unsigned long long>(TopologyRevision), CutCount, ComponentCount, CutLengthCm, LastActiveTool, I,
            C.TipCm.X, C.TipCm.Y, C.TipCm.Z, T.ActualTipCm.X, T.ActualTipCm.Y, T.ActualTipCm.Z,
            C.bClosed ? 1 : 0, C.RollDeg, T.RollDeg, T.JawOpenFraction, T.ContactCount,
            T.ContactForceNewton, T.ForceNewton, T.PenetrationMm, T.SlipDistanceMm, PhysicsStepMs, *SafeGrip, bHealthy ? 1 : 0, static_cast<unsigned long long>(SafetyStopCount));
    }
    if (Now - LastTelemetryFlushSeconds > 1) FlushTelemetry();
}

void USimulationBridge::FlushTelemetry()
{
    if (!bTelemetryEnabled || TelemetryBuffer.IsEmpty()) return;
    if (!FFileHelper::SaveStringToFile(TelemetryBuffer, *TelemetryPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM,
                                     &IFileManager::Get(), FILEWRITE_Append))
    {
        bTelemetryEnabled = false;
        UE_LOG(LogTemp, Warning, TEXT("LAP_SESSION telemetry write failed: %s"), *TelemetryPath);
    }
    TelemetryBuffer.Empty();
    LastTelemetryFlushSeconds = FPlatformTime::Seconds();
}
