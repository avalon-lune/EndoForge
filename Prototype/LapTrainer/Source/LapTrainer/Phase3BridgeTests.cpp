#include "SimulationBridge.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPhase3BridgeProtocolTest, "EndoForge.Phase3.AtomicTopologyProtocol",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPhase3BridgeProtocolTest::RunTest(const FString& Parameters)
{
    USimulationBridge* Bridge = NewObject<USimulationBridge>();
    Bridge->AddToRoot();
    Bridge->ExpectedProtocol = 3;
    // Two connected triangles. Physical splits may increase the vertex count while
    // retaining all faces; malformed packets must never commit half of that change.
    const FString Base = TEXT(R"JSON({"type":"state","vertices":[[0,0,0],[0.01,0,0],[0,0.01,0],[0.01,0.01,0]],"triangles":[[0,1,2],[1,3,2]],"topology_revision":0,"cut_count":0,"component_count":1,"cut_length_m":0,"step_ms":1,"max_displacement_m":0,"reset_id":0,"healthy":true,"safety_stops":0,"message":"test","tools":[]})JSON");
    const FString Tool = TEXT(R"JSON({"tip_m":[0,0,0.006],"roll_deg":90,"jaw_open_fraction":1,"grasping":false,"force_n":0,"contact_count":0,"contact_force_n":0,"penetration_m":0,"slip_distance_m":0,"grip_state":"open","jaw_poses":[{"center_m":[0,0,0],"axis":[1,0,0],"side":[0,1,0],"normal":[0,0,1]},{"center_m":[0,0,0],"axis":[1,0,0],"side":[0,1,0],"normal":[0,0,1]}]})JSON");
    auto Read = [](const FString& S) { TSharedPtr<FJsonObject> O; FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(S), O); return O; };
    auto Packet = [&]()
    {
        TSharedPtr<FJsonObject> O = Read(Base);
        TArray<TSharedPtr<FJsonValue>> Tools;
        Tools.Add(MakeShared<FJsonValueObject>(Read(Tool)));
        Tools.Add(MakeShared<FJsonValueObject>(Read(Tool)));
        O->SetArrayField(TEXT("tools"), Tools);
        return O;
    };
    auto Deliver = [&](TSharedPtr<FJsonObject> O)
    {
        FString Text;
        FJsonSerializer::Serialize(O.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
        Bridge->HandleMessage(Text);
    };
    auto Hello = Packet();
    Hello->SetStringField(TEXT("type"), TEXT("hello"));
    Hello->SetNumberField(TEXT("protocol"), 3);
    Hello->SetStringField(TEXT("units"), TEXT("m"));
    Deliver(Hello);
    Deliver(Packet());
    TestTrue(TEXT("valid protocol 3 accepted"), Bridge->bHandshake && Bridge->bHasToolState && Bridge->ToolStates.Num() == 2);
    const uint64 InitialRevision = Bridge->MeshRevision;
    const double InitialFreshness = Bridge->LastStateSeconds;
    Deliver(Hello);
    TestEqual(TEXT("duplicate hello cannot overwrite live state"), Bridge->MeshRevision, InitialRevision);
    auto Unsolicited = Packet();
    Unsolicited->SetNumberField(TEXT("reset_id"), 5);
    Deliver(Unsolicited);
    TestEqual(TEXT("unsolicited reset cannot bypass topology guard"), Bridge->MeshRevision, InitialRevision);
    auto BadFace = Packet();
    BadFace->SetArrayField(TEXT("triangles"), Read(TEXT("{\"a\":[[0,1,999],[1,3,2]]}"))->GetArrayField(TEXT("a")));
    Deliver(BadFace);
    TestEqual(TEXT("invalid index rejects complete packet"), Bridge->MeshRevision, InitialRevision);
    TestEqual(TEXT("invalid packet does not refresh watchdog"), Bridge->LastStateSeconds, InitialFreshness);
    auto BadTool = Packet();
    BadTool->GetArrayField(TEXT("tools"))[1]->AsObject()->SetNumberField(TEXT("jaw_open_fraction"), 2);
    Deliver(BadTool);
    TestEqual(TEXT("invalid second tool leaves first tool and mesh untouched"), Bridge->MeshRevision, InitialRevision);
    auto Split = Packet();
    Split->SetArrayField(TEXT("vertices"), Read(TEXT("{\"a\":[[0,0,0],[0.01,0,0],[0,0.01,0],[0.01,0.01,0],[0.011,0,0],[0,0.011,0]]}"))->GetArrayField(TEXT("a")));
    Split->SetArrayField(TEXT("triangles"), Read(TEXT("{\"a\":[[0,1,2],[4,3,5]]}"))->GetArrayField(TEXT("a")));
    Split->SetNumberField(TEXT("cut_count"), 1);
    Split->SetNumberField(TEXT("component_count"), 2);
    Split->SetNumberField(TEXT("cut_length_m"), .01);
    Deliver(Split);
    TestEqual(TEXT("connectivity cannot change without revision"), Bridge->MeshRevision, InitialRevision);
    Split->SetNumberField(TEXT("topology_revision"), 1);
    Deliver(Split);
    TestTrue(TEXT("cut topology committed atomically"), Bridge->VerticesCm.Num() == 6 && Bridge->Triangles[3] == 4 && Bridge->CutCount == 1 && Bridge->ComponentCount == 2);
    const uint64 CutFrame = Bridge->MeshRevision;
    Deliver(Packet());
    TestEqual(TEXT("stale pre-cut state rejected"), Bridge->MeshRevision, CutFrame);
    auto Reset = Packet();
    Bridge->ResetId = 1;
    Reset->SetNumberField(TEXT("reset_id"), 1);
    Deliver(Reset);
    TestTrue(TEXT("acknowledged reset restores original topology"), Bridge->VerticesCm.Num() == 4 && Bridge->CutCount == 0 && Bridge->ComponentCount == 1 && Bridge->AcknowledgedResetId == 1);
    const uint64 ResetFrame = Bridge->MeshRevision;
    Deliver(Packet());
    TestEqual(TEXT("old reset cannot replace current tissue"), Bridge->MeshRevision, ResetFrame);
    TestEqual(TEXT("all invalid cases counted"), Bridge->RejectedStateCount, static_cast<uint64>(7));
    auto Protected = Packet();
    Protected->SetNumberField(TEXT("reset_id"), 1);
    Protected->SetNumberField(TEXT("safety_stops"), 2);
    Deliver(Protected);
    TestEqual(TEXT("healthy state still records numerical protection"), Bridge->GetSafetyStopCount(), static_cast<uint64>(2));
    Deliver(Reset);
    TestEqual(TEXT("reset cannot erase observed protection history"), Bridge->GetSafetyStopCount(), static_cast<uint64>(2));
    Bridge->RemoveFromRoot();
    return true;
}
#endif
