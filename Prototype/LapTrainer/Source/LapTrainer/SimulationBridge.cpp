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
}

void USimulationBridge::InitializeBridge()
{
    if (bInitialized) return;
    bInitialized = true;
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
    JawPoses.Reset();
    ToolStates.Reset();
    ContactCount = 0;
    ContactForceNewton = 0;
    PenetrationMm = 0;
    SlipDistanceMm = 0;
    GripState = TEXT("offline");
    LastStateSeconds = 0;
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
        Tools.Add(MakeShared<FJsonValueObject>(Tool));
    }
    Command->SetArrayField(TEXT("tools"), Tools);
    Command->SetNumberField(TEXT("reset_id"), ResetId);
    Command->SetBoolField(TEXT("paused"), false);
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
    QueueCommand(Commands, ActiveTool, bHealthy && IsConnected() && ResetId == AcknowledgedResetId);
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
        if (!Object->TryGetNumberField(TEXT("protocol"), Protocol) || Protocol != 3 ||
            !Object->TryGetStringField(TEXT("units"), Units) || Units != TEXT("m"))
        { Reject(TEXT("Phase 3 requires matching protocol 3 service")); return; }
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
    bool NewHealthy = true;
    TArray<FLapToolState> NewTools;
    FString Detail;
    if (!Hello)
    {
        auto IntField = [&](const TCHAR* Name, double& Out, double Max)
        { return ReadBoundedNumber(Object, Name, Out, 0, Max) && Out == FMath::FloorToDouble(Out); };
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
            NewTools.Add(MoveTemp(T));
        }
        Object->TryGetStringField(TEXT("message"), Detail);
    }
    VerticesCm = MoveTemp(NewVertices);
    Triangles = MoveTemp(NewTriangles);
    PhysicsNodeCount = VerticesCm.Num();
    ++MeshRevision;
    if (Hello)
    {
        Object->TryGetStringField(TEXT("solver"), SolverName);
        bHandshake = true;
        UE_LOG(LogTemp, Display, TEXT("EndoForge protocol 3 handshake: %s"), *SolverName);
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
