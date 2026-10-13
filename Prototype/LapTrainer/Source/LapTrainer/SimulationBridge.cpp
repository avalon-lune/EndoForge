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
        TEXT("utc,reset_id,mesh_revision,command_x_cm,command_y_cm,command_z_cm,actual_x_cm,actual_y_cm,actual_z_cm,command_closed,command_roll_deg,actual_roll_deg,jaw_open_fraction,contacts,contact_force_n,grip_force_n,penetration_mm,slip_mm,solve_ms,grip_state,healthy\n"),
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

void USimulationBridge::QueueCommand(const FVector& TipCm, bool bClosed, float RollDeg)
{
    // A partially transmitted record must finish before the next record is queued.
    if (!SendBuffer.IsEmpty()) return;
    LastCommandTipCm = TipCm;
    bLastCommandClosed = bClosed;
    LastCommandRollDeg = RollDeg;
    TSharedRef<FJsonObject> Command = MakeShared<FJsonObject>();
    Command->SetStringField(TEXT("type"), TEXT("command"));
    Command->SetNumberField(TEXT("seq"), static_cast<double>(++CommandSequence));
    TArray<TSharedPtr<FJsonValue>> Tip;
    Tip.Add(MakeShared<FJsonValueNumber>(TipCm.X * .01));
    Tip.Add(MakeShared<FJsonValueNumber>(TipCm.Y * .01));
    Tip.Add(MakeShared<FJsonValueNumber>(TipCm.Z * .01));
    Command->SetArrayField(TEXT("tip_m"), Tip);
    Command->SetNumberField(TEXT("closed"), bClosed ? 1.0 : 0.0);
    Command->SetNumberField(TEXT("roll_deg"), FMath::IsFinite(RollDeg) ? FMath::UnwindDegrees(RollDeg) : 0.0f);
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
    QueueCommand(ToolTipCm, bClosed && bHealthy && IsConnected() && ResetId == AcknowledgedResetId, RollDeg);
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
    auto RejectState = [this](const TCHAR* Reason)
    {
        ++RejectedStateCount;
        Status = FString(TEXT("Invalid SOFA state: ")) + Reason;
        const double Now = FPlatformTime::Seconds();
        if (Now - LastRejectedStateLogSeconds > 3.0)
        {
            LastRejectedStateLogSeconds = Now;
            UE_LOG(LogTemp, Warning, TEXT("LAP_PROTOCOL %s"), *Status);
        }
    };
    TSharedPtr<FJsonObject> Object;
    auto Reader = TJsonReaderFactory<>::Create(Line);
    if (!FJsonSerializer::Deserialize(Reader, Object) || !Object.IsValid()) { RejectState(TEXT("malformed JSON")); return; }
    FString Type;
    if (!Object->TryGetStringField(TEXT("type"), Type)) { RejectState(TEXT("message type missing")); return; }
    TArray<int32> CandidateTriangles = Triangles;
    if (Type == TEXT("hello"))
    {
        double Protocol = 0;
        FString Units;
        if (!Object->TryGetNumberField(TEXT("protocol"), Protocol) || Protocol != 2 ||
            !Object->TryGetStringField(TEXT("units"), Units) || Units != TEXT("m"))
        { RejectState(TEXT("Phase 2 requires its matching SOFA service (protocol 2)")); return; }
        const TArray<TSharedPtr<FJsonValue>>* Faces = nullptr;
        if (!Object->TryGetArrayField(TEXT("triangles"), Faces)) { RejectState(TEXT("triangles missing")); return; }
        TArray<int32> NewTriangles;
        for (const auto& Face : *Faces)
        {
            const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
            if (!Face->TryGetArray(Values) || Values->Num() != 3) { RejectState(TEXT("invalid face")); return; }
            for (const auto& Value : *Values)
            {
                double Index = 0;
                if (!Value->TryGetNumber(Index) || !FMath::IsFinite(Index) || Index < 0 || Index > 99999 || Index != FMath::FloorToDouble(Index)) { RejectState(TEXT("invalid face index")); return; }
                NewTriangles.Add(static_cast<int32>(Index));
            }
        }
        if (NewTriangles.IsEmpty()) { RejectState(TEXT("empty mesh")); return; }
        CandidateTriangles = MoveTemp(NewTriangles);
    }
    if (Type == TEXT("hello") || (Type == TEXT("state") && bHandshake))
    {
        const TArray<TSharedPtr<FJsonValue>>* Nodes = nullptr;
        if (!Object->TryGetArrayField(TEXT("vertices"), Nodes) || Nodes->IsEmpty() || Nodes->Num() > 100000) { RejectState(TEXT("invalid vertex count")); return; }
        TArray<FVector> Updated;
        Updated.Reserve(Nodes->Num());
        for (const auto& Node : *Nodes)
        {
            const TArray<TSharedPtr<FJsonValue>>* Position = nullptr;
            if (!Node->TryGetArray(Position) || Position->Num() != 3) { RejectState(TEXT("invalid vertex")); return; }
            double X = 0, Y = 0, Z = 0;
            if (!(*Position)[0]->TryGetNumber(X) || !(*Position)[1]->TryGetNumber(Y) || !(*Position)[2]->TryGetNumber(Z)) { RejectState(TEXT("invalid vertex coordinates")); return; }
            const FVector P(X * 100.0, Y * 100.0, Z * 100.0);
            if (P.ContainsNaN() || P.GetAbsMax() > 10000) { RejectState(TEXT("non-finite or excessive vertex coordinates")); return; }
            Updated.Add(P);
        }
        for (const int32 Index : CandidateTriangles) if (!Updated.IsValidIndex(Index)) { RejectState(TEXT("face index outside vertex array")); return; }
        // Validate the whole protocol-2 state before committing either the mesh or the tool.
        // A malformed telemetry value must not keep the interaction watchdog alive.
        FVector NewTip = FVector::ZeroVector;
        TArray<FLapJawPose> NewJaws;
        double NewForce = 0, NewStep = 0, NewDisp = 0, NewReset = 0;
        double NewRoll = 0, NewOpen = 1, NewContacts = 0, NewContactForce = 0;
        double NewPenetration = 0, NewSlip = 0;
        bool NewGrasping = false, NewHealthy = true;
        FString NewGrip, Detail;
        if (Type == TEXT("state"))
        {
            if (Updated.Num() != VerticesCm.Num() ||
                !Object->TryGetBoolField(TEXT("grasping"), NewGrasping) ||
                !Object->TryGetBoolField(TEXT("healthy"), NewHealthy) ||
                !ReadBoundedNumber(Object, TEXT("force_n"), NewForce, 0, 100000) ||
                !ReadBoundedNumber(Object, TEXT("step_ms"), NewStep, 0, 60000) ||
                !ReadBoundedNumber(Object, TEXT("max_displacement_m"), NewDisp, 0, 10) ||
                !ReadBoundedNumber(Object, TEXT("reset_id"), NewReset, 0, MAX_int32) ||
                NewReset != FMath::FloorToDouble(NewReset) ||
                !ReadVector(Object, TEXT("tip_m"), NewTip, 100.0) ||
                !ReadBoundedNumber(Object, TEXT("roll_deg"), NewRoll, -36000, 36000) ||
                !ReadBoundedNumber(Object, TEXT("jaw_open_fraction"), NewOpen, 0, 1) ||
                !ReadBoundedNumber(Object, TEXT("contact_count"), NewContacts, 0, 100000) ||
                NewContacts != FMath::FloorToDouble(NewContacts) ||
                !ReadBoundedNumber(Object, TEXT("contact_force_n"), NewContactForce, 0, 100000) ||
                !ReadBoundedNumber(Object, TEXT("penetration_m"), NewPenetration, 0, 10) ||
                !ReadBoundedNumber(Object, TEXT("slip_distance_m"), NewSlip, 0, 10) ||
                !Object->TryGetStringField(TEXT("grip_state"), NewGrip) || NewGrip.Len() > 64)
            { RejectState(TEXT("required contact telemetry missing or out of bounds")); return; }
            const TArray<TSharedPtr<FJsonValue>>* PoseValues = nullptr;
            if (!Object->TryGetArrayField(TEXT("jaw_poses"), PoseValues) || PoseValues->Num() != 2)
            { RejectState(TEXT("expected two jaw frames")); return; }
            for (const auto& Value : *PoseValues)
            {
                const TSharedPtr<FJsonObject>* PoseObject = nullptr;
                if (!Value->TryGetObject(PoseObject) || !PoseObject->IsValid())
                { RejectState(TEXT("jaw frame is not an object")); return; }
                FLapJawPose Pose;
                if (!ReadVector(*PoseObject, TEXT("center_m"), Pose.CenterCm, 100.0) ||
                    !ReadVector(*PoseObject, TEXT("axis"), Pose.Axis) ||
                    !ReadVector(*PoseObject, TEXT("side"), Pose.Side) ||
                    !ReadVector(*PoseObject, TEXT("normal"), Pose.Normal))
                { RejectState(TEXT("jaw frame vectors missing or non-finite")); return; }
                if (!FMath::IsNearlyEqual(Pose.Axis.SizeSquared(), 1.0, 0.01) ||
                    !FMath::IsNearlyEqual(Pose.Side.SizeSquared(), 1.0, 0.01) ||
                    !FMath::IsNearlyEqual(Pose.Normal.SizeSquared(), 1.0, 0.01) ||
                    FMath::Abs(FVector::DotProduct(Pose.Axis, Pose.Side)) > 0.01 ||
                    FMath::Abs(FVector::DotProduct(Pose.Axis, Pose.Normal)) > 0.01 ||
                    FMath::Abs(FVector::DotProduct(Pose.Side, Pose.Normal)) > 0.01 ||
                    FVector::DotProduct(FVector::CrossProduct(Pose.Axis, Pose.Side), Pose.Normal) < 0.99)
                { RejectState(TEXT("jaw axes are not an orthonormal right-handed frame")); return; }
                NewJaws.Add(Pose);
            }
            Object->TryGetStringField(TEXT("message"), Detail);
        }
        VerticesCm = MoveTemp(Updated);
        Triangles = MoveTemp(CandidateTriangles);
        ++MeshRevision;
        if (Type == TEXT("hello"))
        {
            Object->TryGetStringField(TEXT("solver"), SolverName);
            bHandshake = true;
            PhysicsNodeCount = VerticesCm.Num();
            UE_LOG(LogTemp, Display, TEXT("LapTrainer physics handshake: %s"), *SolverName);
        }
        if (Type == TEXT("state"))
        {
            LastStateSeconds = FPlatformTime::Seconds();
            bGrasping = NewGrasping;
            bHealthy = NewHealthy;
            if (!NewHealthy) ++UnhealthyStateCount;
            ForceNewton = static_cast<float>(NewForce);
            PhysicsStepMs = static_cast<float>(NewStep);
            MaxDisplacementCm = static_cast<float>(NewDisp * 100);
            AcknowledgedResetId = static_cast<int32>(NewReset);
            ActualTipCm = NewTip;
            ActualRollDeg = static_cast<float>(NewRoll);
            JawOpenFraction = static_cast<float>(NewOpen);
            ContactCount = static_cast<int32>(NewContacts);
            ContactForceNewton = static_cast<float>(NewContactForce);
            PenetrationMm = static_cast<float>(NewPenetration * 1000);
            SlipDistanceMm = static_cast<float>(NewSlip * 1000);
            GripState = NewGrip;
            JawPoses = MoveTemp(NewJaws);
            bHasToolState = true;
            Status = bHealthy ? FString(TEXT("SOFA FEM | ")) + GripState : FString(TEXT("SOFA paused: ")) + Detail.Left(160);
            RecordTelemetry();
        }
    }
}

void USimulationBridge::RecordTelemetry()
{
    const double Now = FPlatformTime::Seconds();
    if (!bTelemetryEnabled || Now - LastTelemetrySeconds < 0.1) return;
    LastTelemetrySeconds = Now;
    FString SafeGrip = GripState.Replace(TEXT(","), TEXT("_")).Replace(TEXT("\n"), TEXT(" ")).Replace(TEXT("\r"), TEXT(" "));
    TelemetryBuffer += FString::Printf(TEXT("%s,%d,%llu,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%d,%.3f,%.3f,%.4f,%d,%.6f,%.6f,%.6f,%.6f,%.4f,%s,%d\n"),
        *FDateTime::UtcNow().ToIso8601(), AcknowledgedResetId, static_cast<unsigned long long>(MeshRevision),
        LastCommandTipCm.X, LastCommandTipCm.Y, LastCommandTipCm.Z, ActualTipCm.X, ActualTipCm.Y, ActualTipCm.Z,
        bLastCommandClosed ? 1 : 0, LastCommandRollDeg, ActualRollDeg, JawOpenFraction, ContactCount,
        ContactForceNewton, ForceNewton, PenetrationMm, SlipDistanceMm, PhysicsStepMs, *SafeGrip, bHealthy ? 1 : 0);
    if (Now - LastTelemetryFlushSeconds > 1.0) FlushTelemetry();
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
