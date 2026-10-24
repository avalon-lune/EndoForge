#include "SimulationBridge.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPhase4BridgeProtocolTest, "EndoForge.Phase4.AtomicSnapshotProtocol",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPhase4BridgeProtocolTest::RunTest(const FString& Parameters)
{
    USimulationBridge* Bridge = NewObject<USimulationBridge>();
    Bridge->AddToRoot();
    Bridge->ExpectedProtocol = 4;
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
        O->SetStringField(TEXT("specimen"),TEXT("flat"));
        O->SetObjectField(TEXT("config"),Read(TEXT(R"JSON({"name":"flat","width_m":0.12,"length_m":0.08,"thickness_m":0.0015,"curvature_m":0,"young_modulus_pa":25000,"poisson_ratio":0.35,"density_kg_m3":1000,"rayleigh_mass":8,"rayleigh_stiffness":0.015,"friction":0.8,"fixed_rows":1,"mesh_nx":25,"mesh_ny":17,"gravity_m_s2":[0,0,0],"contact_offset_m":0.00045,"alarm_distance_m":0.0015})JSON")));
        O->SetNumberField(TEXT("simulation_id"),1);
        O->SetNumberField(TEXT("time"),.033333333);
        O->SetNumberField(TEXT("frame"),1);
        O->SetArrayField(TEXT("parent_node_ids"),Read(TEXT("{\"a\":[-1,-1,-1,-1]}"))->GetArrayField(TEXT("a")));
        O->SetArrayField(TEXT("node_ids"),Read(TEXT("{\"a\":[0,1,2,3]}"))->GetArrayField(TEXT("a")));
        O->SetArrayField(TEXT("material_node_ids"),Read(TEXT("{\"a\":[0,1,2,3]}"))->GetArrayField(TEXT("a")));
        O->SetObjectField(TEXT("session"),Read(TEXT("{\"mode\":\"idle\",\"action_id\":0,\"step_index\":1,\"replay_length\":0,\"recorded_steps\":0,\"error\":\"\"}")));
        return O;
    };
    uint64 StateId=0;
    auto Deliver = [&](TSharedPtr<FJsonObject> O)
    {
        O->SetNumberField(TEXT("state_id"),++StateId);
        FString Text;
        FJsonSerializer::Serialize(O.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
        Bridge->HandleMessage(Text);
    };
    auto Hello = Packet();
    Hello->SetStringField(TEXT("type"), TEXT("hello"));
    Hello->SetNumberField(TEXT("protocol"), 4);
    Hello->SetStringField(TEXT("units"), TEXT("m"));
    Deliver(Hello);
    Deliver(Packet());
    TestTrue(TEXT("valid protocol 4 accepted"), Bridge->bHandshake && Bridge->bHasToolState && Bridge->ToolStates.Num() == 2);
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
    Split->SetArrayField(TEXT("node_ids"),Read(TEXT("{\"a\":[0,1,2,3,4,5]}"))->GetArrayField(TEXT("a")));
    Split->SetArrayField(TEXT("material_node_ids"),Read(TEXT("{\"a\":[0,1,2,3,1,2]}"))->GetArrayField(TEXT("a")));
    Split->SetArrayField(TEXT("parent_node_ids"),Read(TEXT("{\"a\":[-1,-1,-1,-1,1,2]}"))->GetArrayField(TEXT("a")));
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
    const uint64 BeforeBadMetadata=Bridge->MeshRevision;
    auto BadIds=Packet(); BadIds->SetNumberField(TEXT("reset_id"),1);
    BadIds->SetArrayField(TEXT("node_ids"),Read(TEXT("{\"a\":[0,1,1,3]}"))->GetArrayField(TEXT("a")));
    Deliver(BadIds);
    TestEqual(TEXT("duplicate identity rejects all geometry"),Bridge->MeshRevision,BeforeBadMetadata);
    auto BadSession=Packet(); BadSession->SetNumberField(TEXT("reset_id"),1);
    BadSession->GetObjectField(TEXT("session"))->SetStringField(TEXT("mode"),TEXT("visual_fake"));
    Deliver(BadSession);
    TestEqual(TEXT("invalid session mode rejects entire packet"),Bridge->MeshRevision,BeforeBadMetadata);
    auto BadShape=Packet(); BadShape->SetNumberField(TEXT("reset_id"),1); BadShape->SetStringField(TEXT("specimen"),TEXT("curved"));
    Deliver(BadShape);
    TestEqual(TEXT("specimen cannot change without reset"),Bridge->MeshRevision,BeforeBadMetadata);
    auto WrongIdentity=Packet(); WrongIdentity->SetNumberField(TEXT("reset_id"),1);
    WrongIdentity->SetArrayField(TEXT("material_node_ids"),Read(TEXT("{\"a\":[0,1,2,99]}"))->GetArrayField(TEXT("a")));
    Deliver(WrongIdentity);
    TestEqual(TEXT("material identity cannot drift within topology"),Bridge->MeshRevision,BeforeBadMetadata);
    auto BadConfig=Packet(); BadConfig->SetNumberField(TEXT("reset_id"),1);
    BadConfig->GetObjectField(TEXT("config"))->SetNumberField(TEXT("young_modulus_pa"),30000);
    Deliver(BadConfig); TestEqual(TEXT("effective material cannot mutate within simulation"),Bridge->MeshRevision,BeforeBadMetadata);
    auto BadFrame=Packet(); BadFrame->SetNumberField(TEXT("reset_id"),1); BadFrame->SetNumberField(TEXT("frame"),-.5);
    Deliver(BadFrame); TestEqual(TEXT("invalid native frame rejected atomically"),Bridge->MeshRevision,BeforeBadMetadata);
    auto BadParent=Packet(); BadParent->SetNumberField(TEXT("reset_id"),1);
    BadParent->SetArrayField(TEXT("parent_node_ids"),Read(TEXT("{\"a\":[-1,-1,-2,-1]}"))->GetArrayField(TEXT("a")));
    Deliver(BadParent); TestEqual(TEXT("invalid ancestry rejected atomically"),Bridge->MeshRevision,BeforeBadMetadata);
    auto BadTime=Packet(); BadTime->SetNumberField(TEXT("reset_id"),1); BadTime->SetNumberField(TEXT("time"),1);
    Deliver(BadTime); TestEqual(TEXT("timestamp must match accepted step timebase"),Bridge->MeshRevision,BeforeBadMetadata);
    auto RegressTime=Packet(); RegressTime->SetNumberField(TEXT("reset_id"),1); RegressTime->SetNumberField(TEXT("time"),0);
    RegressTime->GetObjectField(TEXT("session"))->SetNumberField(TEXT("step_index"),0);
    Deliver(RegressTime); TestEqual(TEXT("timeline cannot regress within simulation"),Bridge->MeshRevision,BeforeBadMetadata);
    auto ValidSnapshot=Packet(); ValidSnapshot->SetNumberField(TEXT("reset_id"),1);
    Deliver(ValidSnapshot);
    TestTrue(TEXT("accepted snapshot carries exact committed native mesh"),Bridge->AcceptedState.IsValid() && Bridge->NativeStateId==StateId && Bridge->NodeIds.Num()==Bridge->VerticesCm.Num());
    FString Stale; FJsonSerializer::Serialize(ValidSnapshot.ToSharedRef(),TJsonWriterFactory<>::Create(&Stale));
    const uint64 Fresh=Bridge->MeshRevision; Bridge->HandleMessage(Stale);
    TestEqual(TEXT("duplicate state id cannot refresh or overwrite"),Bridge->MeshRevision,Fresh);
    Bridge->RemoveFromRoot();
    Bridge=NewObject<USimulationBridge>();Bridge->AddToRoot();Bridge->ExpectedProtocol=5;
    auto AnatomyPacket=[&]()
    {
        auto O=Packet();O->SetStringField(TEXT("specimen"),TEXT("gallbladder"));O->GetObjectField(TEXT("config"))->SetStringField(TEXT("name"),TEXT("gallbladder"));
        O->SetStringField(TEXT("model_id"),TEXT("test-anatomy"));O->SetNumberField(TEXT("model_version"),1);O->SetStringField(TEXT("asset_fingerprint"),TEXT("fnv1a64:test"));
        for(const auto& T:O->GetArrayField(TEXT("tools")))T->AsObject()->SetArrayField(TEXT("pivot_m"),Read(TEXT("{\"a\":[0.12,-0.14,0.15]}"))->GetArrayField(TEXT("a")));
        return O;
    };
    auto AnatomyHello=AnatomyPacket();AnatomyHello->SetStringField(TEXT("type"),TEXT("hello"));AnatomyHello->SetNumberField(TEXT("protocol"),5);AnatomyHello->SetStringField(TEXT("units"),TEXT("m"));Deliver(AnatomyHello);Deliver(AnatomyPacket());
    TestTrue(TEXT("anatomy protocol accepts numeric asset version"),Bridge->bHandshake&&Bridge->bHasToolState&&Bridge->IsPhase5());
    const auto AnatomyRevision=Bridge->MeshRevision;auto WrongAnatomy=AnatomyPacket();WrongAnatomy->SetStringField(TEXT("asset_fingerprint"),TEXT("fnv1a64:changed"));Deliver(WrongAnatomy);
    TestEqual(TEXT("anatomy identity drift rejects entire snapshot"),Bridge->MeshRevision,AnatomyRevision);
    auto MissingPivot=AnatomyPacket();MissingPivot->GetArrayField(TEXT("tools"))[1]->AsObject()->RemoveField(TEXT("pivot_m"));Deliver(MissingPivot);
    TestEqual(TEXT("missing anatomy trocar frame rejects atomically"),Bridge->MeshRevision,AnatomyRevision);
    auto ChangedPolicy=AnatomyPacket();ChangedPolicy->GetObjectField(TEXT("config"))->SetNumberField(TEXT("liver_alarm_guard_m"),.0001);Deliver(ChangedPolicy);
    TestEqual(TEXT("anatomy contact policy cannot change within a connection"),Bridge->MeshRevision,AnatomyRevision);
    Bridge->RemoveFromRoot();
    Bridge=NewObject<USimulationBridge>();Bridge->AddToRoot();Bridge->ExpectedProtocol=5;Bridge->bPhase6Commands=true;
    auto Phase6Packet=[&]()
    {
        auto O=AnatomyPacket();O->SetNumberField(TEXT("applied_command_seq"),0);const auto Config=O->GetObjectField(TEXT("config"));
        Config->SetStringField(TEXT("asset_fingerprint"),TEXT("fnv1a64:test"));
        Config->SetBoolField(TEXT("grasp_contact_diagnostics"),false);
        Config->SetArrayField(TEXT("tool_pivots_m"),Read(TEXT("{\"a\":[[0.12,-0.14,0.15],[0.12,-0.14,0.15]]}"))->GetArrayField(TEXT("a")));
        Config->SetStringField(TEXT("force_scope"),TEXT("soft_tissue_contact_impulse_only; rigid_liver_motion_guard_has_no_reaction_force"));
        Config->SetObjectField(TEXT("tool_motion_guard"),Read(TEXT(R"JSON({"implementation":"phase6-rcm-jaw-liver-ccd-v1","clearance_margin_m":0.00015,"maximum_intervals":512,"maximum_depth":26,"minimum_fraction":0.00000001490116119384765625,"static_geometry_asset_fingerprint":"fnv1a64:test"})JSON")));
        for(const auto& T:O->GetArrayField(TEXT("tools")))T->AsObject()->SetObjectField(TEXT("motion_guard"),Read(TEXT(R"JSON({"implementation":"phase6-rcm-jaw-liver-ccd-v1","blocked":false,"initial_valid":true,"reason":"clear","accepted_fraction":1,"witness_triangle":-1,"clearance_margin_m":0.00015,"initial_clearance_m":0.003,"endpoint_clearance_m":0.003,"work_count":1})JSON")));
        return O;
    };
    auto Phase6Hello=Phase6Packet();Phase6Hello->SetStringField(TEXT("type"),TEXT("hello"));Phase6Hello->SetNumberField(TEXT("protocol"),5);Phase6Hello->SetStringField(TEXT("units"),TEXT("m"));Deliver(Phase6Hello);Deliver(Phase6Packet());
    TestTrue(TEXT("Phase6 accepts nested immutable collision configuration"),Bridge->bHandshake&&Bridge->bHasToolState);
    auto BlockedPacket=Phase6Packet();auto G=BlockedPacket->GetArrayField(TEXT("tools"))[0]->AsObject()->GetObjectField(TEXT("motion_guard"));
    G->SetBoolField(TEXT("blocked"),true);G->SetStringField(TEXT("reason"),TEXT("rigid_liver_clearance"));G->SetNumberField(TEXT("accepted_fraction"),.5);Deliver(BlockedPacket);
    TestTrue(TEXT("geometric block is committed without numerical failure"),Bridge->bHealthy&&Bridge->ToolStates.Num()==2&&Bridge->ToolStates[0].bMotionBlocked);
    const uint64 GuardRevision=Bridge->MeshRevision;
    auto MissingGuard=Phase6Packet();MissingGuard->GetArrayField(TEXT("tools"))[1]->AsObject()->RemoveField(TEXT("motion_guard"));Deliver(MissingGuard);
    TestEqual(TEXT("missing guard rejects entire snapshot"),Bridge->MeshRevision,GuardRevision);
    auto BadGuard=Phase6Packet();BadGuard->GetArrayField(TEXT("tools"))[1]->AsObject()->GetObjectField(TEXT("motion_guard"))->SetNumberField(TEXT("accepted_fraction"),.5);Deliver(BadGuard);
    TestEqual(TEXT("unblocked partial admission rejected atomically"),Bridge->MeshRevision,GuardRevision);
    auto WrongGuard=Phase6Packet();WrongGuard->GetObjectField(TEXT("config"))->GetObjectField(TEXT("tool_motion_guard"))->SetStringField(TEXT("static_geometry_asset_fingerprint"),TEXT("fnv1a64:other"));Deliver(WrongGuard);
    TestEqual(TEXT("guard cannot reference another liver"),Bridge->MeshRevision,GuardRevision);
    auto WrongRig=Phase6Packet();WrongRig->GetObjectField(TEXT("config"))->SetArrayField(TEXT("tool_pivots_m"),Read(TEXT("{\"a\":[[0.11,-0.14,0.15],[0.12,-0.14,0.15]]}"))->GetArrayField(TEXT("a")));Deliver(WrongRig);
    TestEqual(TEXT("nested trocar change rejects entire snapshot"),Bridge->MeshRevision,GuardRevision);
    Bridge->RemoveFromRoot();
    return true;
}
#endif
