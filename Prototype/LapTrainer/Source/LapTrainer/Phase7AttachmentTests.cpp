#include "Phase7AttachmentGeometry.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Misc/SecureHash.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPhase7AttachmentTest,"EndoForge.Phase7.BoundedAttachmentEnvelope",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)

bool FPhase7AttachmentTest::RunTest(const FString& Parameters)
{
    TArray<int32> Ids;TArray<FVector> Pairs;TArray<FIntPoint> Edges;
    constexpr int Count=8;
    for(int I=0;I<Count;++I)
    {
        Ids.Add(100+I);const double A=2*PI*I/Count;
        Pairs.Add(FVector(FMath::Cos(A),FMath::Sin(A),.4));Pairs.Add(FVector(FMath::Cos(A)*1.1,FMath::Sin(A)*1.1,0));
        // Deliberately inconsistent input winding and nonsequential edges.
        const int E=(I*3)%Count;Edges.Add(I%2?FIntPoint(100+(E+1)%Count,100+E):FIntPoint(100+E,100+(E+1)%Count));
    }
    Ids.Add(900);Pairs.Append({FVector(0,0,.4),FVector::ZeroVector}); // Unused interior spring still retained.
    for(int State=0;State<3;++State)
    {
        TArray<FVector> Input=Pairs;
        if(State==1)for(int I=0;I<Count;++I)Input[I*2].Z+=.07*I;
        if(State==2)for(int I=0;I<Count;++I){Input[I*2].X+=.18*FMath::Sin(I*1.7);Input[I*2].Z+=.11*FMath::Cos(I*1.4);}
        FTrainingRenderMesh Mesh;Phase7AttachmentGeometry::FBinding Binding;FString Error;
        if(!TestTrue(TEXT("Build finite deformed endpoint envelope"),Phase7AttachmentGeometry::Build(Ids,Input,Edges,Mesh,Binding,Error)))return false;
        TestEqual(TEXT("Closed loop includes every boundary identity"),Binding.ClosedBoundaryMaterialIds.Num(),Count);
        TestEqual(TEXT("One patch label for each face"),Binding.TrianglePatchIndices.Num(),Mesh.Triangles.Num()/3);
        TestEqual(TEXT("Every vertex has reconstructable binding"),Binding.VertexBindings.Num(),Mesh.Positions.Num());
        for(int I=0;I<Input.Num();++I)TestTrue(TEXT("Native endpoint exactly unchanged"),Mesh.Positions[I]==Input[I]);
        TestTrue(TEXT("Curve cap is active for curved boundary"),Binding.MeasuredMaximumOffsetCm>.001);
        TestTrue(TEXT("Departure never exceeds 0.12mm"),Binding.MeasuredMaximumOffsetCm<=Phase7AttachmentGeometry::MaximumOffsetCm+1e-12);
        for(const auto& S:Binding.SeamVertexPairs)TestTrue(TEXT("UV seam has no spatial gap"),Mesh.Positions[S.X].Equals(Mesh.Positions[S.Y],1e-12));
        TMap<int32,int32> Seam;for(const auto& S:Binding.SeamVertexPairs)Seam.Add(S.Y,S.X);
        auto Weld=[&](int I){if(const auto* Found=Seam.Find(I))return *Found;return I;};
        TMap<FIntPoint,FIntPoint> EdgeUses;
        for(int F=0;F<Mesh.Triangles.Num();F+=3)
        {
            for(int J=0;J<3;++J)if(!TestTrue(TEXT("No invalid triangle indices"),Mesh.Positions.IsValidIndex(Mesh.Triangles[F+J])))return false;
            const FVector A=Mesh.Positions[Mesh.Triangles[F]],B=Mesh.Positions[Mesh.Triangles[F+1]],C=Mesh.Positions[Mesh.Triangles[F+2]];
            TestTrue(TEXT("Nondegenerate triangles"),FVector::CrossProduct(B-A,C-A).SizeSquared()>1e-24);
            const int Patch=Binding.TrianglePatchIndices[F/3];double Minimum=1e10,Maximum=-1e10;
            for(int J=0;J<3;++J)
            {
                const FVector Sample=Binding.VertexBindings[Mesh.Triangles[F+J]];double U=Sample.Y,V=Sample.Z;
                if(Sample.X<0){const int Id=Ids[int(Sample.Y)];U=Id==Binding.ClosedBoundaryMaterialIds[Patch]?0:1;}
                else if(int(Sample.X)!=Patch)U=1;
                const double Side=Binding.OriginalEdgeDirections[Patch]>0?V-U:U+V-1;
                Minimum=FMath::Min(Minimum,Side);Maximum=FMath::Max(Maximum,Side);
            }
            TestTrue(TEXT("Whole face stays on one side of original diagonal"),Minimum>=-1e-12||Maximum<=1e-12);
            for(int J=0;J<3;++J){const int X=Weld(Mesh.Triangles[F+J]),Y=Weld(Mesh.Triangles[F+(J+1)%3]);auto& Use=EdgeUses.FindOrAdd(FIntPoint(FMath::Min(X,Y),FMath::Max(X,Y)));Use.X++;Use.Y+=X<Y?1:-1;}
        }
        int OpenEdges=0;
        for(const auto& Entry:EdgeUses)
        {
            TestTrue(TEXT("Each edge belongs to one or two faces"),Entry.Value.X==1||Entry.Value.X==2);
            if(Entry.Value.X==1)++OpenEdges;else TestEqual(TEXT("Shared faces have consistent winding"),Entry.Value.Y,0);
        }
        TestEqual(TEXT("Only top and bottom boundaries are open"),OpenEdges,2*Count*Phase7AttachmentGeometry::AlongSubdivisions);
    }
    FTrainingRenderMesh Mesh;Phase7AttachmentGeometry::FBinding Binding;FString Error;
    auto Bad=Edges;Bad.Add(Edges[0]);TestFalse(TEXT("Reject duplicate edge"),Phase7AttachmentGeometry::Build(Ids,Pairs,Bad,Mesh,Binding,Error));
    Bad=Edges;Bad.RemoveAt(0);TestFalse(TEXT("Reject open or branched boundary"),Phase7AttachmentGeometry::Build(Ids,Pairs,Bad,Mesh,Binding,Error));
    Bad={FIntPoint(100,101),FIntPoint(101,102),FIntPoint(102,100),FIntPoint(103,104),FIntPoint(104,105),FIntPoint(105,103)};
    TestFalse(TEXT("Reject disconnected loops"),Phase7AttachmentGeometry::Build(Ids,Pairs,Bad,Mesh,Binding,Error));
    // Optional CPU-only fixture for a separate auditor. This editor-test path
    // cannot authorize dataset capture or pretend to be an actual rendered run.
    FString Source,Output;
    if(FParse::Value(FCommandLine::Get(),TEXT("LapPhase7GeometryFixtureSource="),Source))
    {
        if(!TestTrue(TEXT("Fixture output explicitly specified"),FParse::Value(FCommandLine::Get(),TEXT("LapPhase7GeometryFixtureOutput="),Output)))return false;
        FString Raw;TSharedPtr<FJsonObject> Recorded;
        if(!TestTrue(TEXT("Read recorded native state"),FFileHelper::LoadFileToString(Raw,*Source)&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),Recorded)&&Recorded.IsValid()))return false;
        const auto Native=Recorded->GetObjectField(TEXT("native_state"));
        TArray<int32> NativeIds,Materials;TArray<FVector> NativePairs;TSet<int32> Attached;
        for(const auto& Id:Native->GetArrayField(TEXT("attachment_vertex_ids"))){NativeIds.Add(int(Id->AsNumber()));Attached.Add(int(Id->AsNumber()));}
        for(const auto& Id:Native->GetArrayField(TEXT("material_node_ids")))Materials.Add(int(Id->AsNumber()));
        for(const auto& Segment:Native->GetArrayField(TEXT("attachment_segments_m")))for(const auto& Endpoint:Segment->AsArray())
        {const auto& V=Endpoint->AsArray();NativePairs.Add(FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber())*100);}
        TMap<FIntPoint,int32> Incidence;
        for(const auto& Triangle:Native->GetArrayField(TEXT("triangles")))
        {
            const auto& F=Triangle->AsArray();int Face[3];bool Inside=true;
            for(int J=0;J<3;++J){Face[J]=Materials[int(F[J]->AsNumber())];Inside&=Attached.Contains(Face[J]);}
            if(Inside)for(int J=0;J<3;++J)++Incidence.FindOrAdd(FIntPoint(FMath::Min(Face[J],Face[(J+1)%3]),FMath::Max(Face[J],Face[(J+1)%3])));
        }
        TArray<FIntPoint> Original;for(const auto& Edge:Incidence)if(Edge.Value==1)Original.Add(Edge.Key);
        Original.Sort([](const FIntPoint& A,const FIntPoint& B){return A.X==B.X?A.Y<B.Y:A.X<B.X;});
        if(!TestTrue(TEXT("Build actual recorded-state geometry with production function"),Phase7AttachmentGeometry::Build(NativeIds,NativePairs,Original,Mesh,Binding,Error)))return false;
        auto Object=MakeShared<FJsonObject>();Object->SetNumberField(TEXT("object_id"),500);Object->SetStringField(TEXT("name"),TEXT("hepatic_attachment_visual_membrane"));
        Object->SetObjectField(TEXT("attachment_visual_binding"),Phase7AttachmentGeometry::ToJson(Binding,Original,NativeIds.Num()));
        TArray<TSharedPtr<FJsonValue>> Vertices,UV,Triangles;
        for(const auto& P:Mesh.Positions)Vertices.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)}));
        for(const auto& U:Mesh.UV)UV.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(U.X),MakeShared<FJsonValueNumber>(U.Y)}));
        // Match the production A5Normals conversion to UE clockwise winding.
        for(int I=0;I<Mesh.Triangles.Num();I+=3)for(int J:{0,2,1})Triangles.Add(MakeShared<FJsonValueNumber>(Mesh.Triangles[I+J]));
        Object->SetArrayField(TEXT("vertices_cm"),Vertices);Object->SetArrayField(TEXT("uvs"),UV);Object->SetArrayField(TEXT("triangles"),Triangles);
        auto Report=MakeShared<FJsonObject>();Report->SetStringField(TEXT("schema"),TEXT("endoforge.phase7.attachment-cpu-fixture.v1"));Report->SetBoolField(TEXT("actual_render_evidence"),false);
        Report->SetStringField(TEXT("scope"),TEXT("Editor automation CPU replay of recorded native spring endpoints through production Build(); no live rendering, simulation execution or acceptance claim."));
        Report->SetStringField(TEXT("source_snapshot"),Source);Report->SetObjectField(TEXT("native_state"),Native);Report->SetObjectField(TEXT("geometry"),Object);
        TArray<uint8> Bytes;if(FFileHelper::LoadFileToArray(Bytes,*Source)){uint8 Digest[20];FSHA1::HashBuffer(Bytes.GetData(),Bytes.Num(),Digest);Report->SetStringField(TEXT("source_snapshot_sha1"),BytesToHex(Digest,20).ToLower());}
        FString Text;FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Text));
        if(!TestTrue(TEXT("Save explicit CPU fixture"),FFileHelper::SaveStringToFile(Text,*Output,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)))return false;
        UE_LOG(LogTemp,Display,TEXT("LAP_PHASE7_ATTACHMENT_CPU_FIXTURE %s"),*Output);
    }
    return true;
}
#endif
