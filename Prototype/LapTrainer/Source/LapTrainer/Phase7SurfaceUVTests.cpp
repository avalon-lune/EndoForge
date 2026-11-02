#include "Phase7SurfaceUV.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPhase7SurfaceUVTest,"EndoForge.Phase7.PeriodicSurfaceUV",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)

bool FPhase7SurfaceUVTest::RunTest(const FString& Parameters)
{
    auto Periodic=[](double U){return FVector2D(FMath::Cos(2*UE_DOUBLE_PI*U),FMath::Sin(2*UE_DOUBLE_PI*U));};
    const FVector2D A(23.0/24,.4),B(0,.4),C(0,.5);
    const FVector W(.5,.5,0);
    const auto Mid=Phase7SurfaceUV::Interpolate(A,B,C,W);
    TestTrue(TEXT("Seam midpoint follows short periodic arc"),FMath::IsNearlyEqual(Mid.X,47.0/48,1e-12));
    TestTrue(TEXT("V remains linear and unchanged"),FMath::IsNearlyEqual(Mid.Y,.4,1e-12));
    TestTrue(TEXT("Old seam compression is meaningfully rejected"),
        FVector2D::Distance(Periodic((A.X+B.X)*.5),Periodic(Mid.X))>1.9);
    const auto LowSide=Phase7SurfaceUV::Interpolate(FVector2D(0,.4),FVector2D(1.0/24,.4),FVector2D(0,.5),FVector(.7,0,.3));
    const auto HighSide=Phase7SurfaceUV::Interpolate(A,B,C,FVector(0,.7,.3));
    TestTrue(TEXT("Both charts sample identical periodic seam values"),Periodic(LowSide.X).Equals(Periodic(HighSide.X),1e-12));
    TestTrue(TEXT("Shared edge has identical V"),FMath::IsNearlyEqual(LowSide.Y,HighSide.Y,1e-12));
    FVector2D Pole(.5,1),P(23.0/24,.9),Q(0,.9);
    Phase7SurfaceUV::UnwrapTriangle(Pole,P,Q);
    TestTrue(TEXT("Pole uses local incident-chart longitude"),FMath::IsNearlyEqual(Pole.X,47.0/48,1e-12));
    TestTrue(TEXT("Pole chart never traverses texture circumference"),FMath::Max3(Pole.X,P.X,Q.X)-FMath::Min3(Pole.X,P.X,Q.X)<=1.0/24+1e-12);
    FVector2D I(.2,.3),J(.23,.35),K(.24,.4);const auto Original=I*W.X+J*W.Y+K*W.Z;
    TestTrue(TEXT("Ordinary nonseam patch is exactly unchanged"),Phase7SurfaceUV::Interpolate(I,J,K,W)==Original);

    FString ScenePath;
    if(FParse::Value(FCommandLine::Get(),TEXT("LapPhase7UVFixtureScene="),ScenePath))
    {
        FString Raw;TSharedPtr<FJsonObject> Scene;
        if(!TestTrue(TEXT("Read actual authored UV scene"),FFileHelper::LoadFileToString(Raw,*ScenePath)&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),Scene)&&Scene.IsValid()))return false;
        const auto Dynamic=Scene->GetObjectField(TEXT("dynamic_surface"));
        const auto& SourceUV=Dynamic->GetArrayField(TEXT("uvs"));
        const auto& Faces=Dynamic->GetArrayField(TEXT("triangles"));
        int SeamFaces=0;double MaxSpan=0;
        for(const auto& Face:Faces)
        {
            FVector2D UV[3],Before[3];const auto& Indices=Face->AsArray();
            for(int N=0;N<3;++N){const auto& Value=SourceUV[int(Indices[N]->AsNumber())]->AsArray();Before[N]=UV[N]=FVector2D(Value[0]->AsNumber(),1-Value[1]->AsNumber());}
            if(FMath::Max3(UV[0].X,UV[1].X,UV[2].X)-FMath::Min3(UV[0].X,UV[1].X,UV[2].X)>.5)++SeamFaces;
            Phase7SurfaceUV::UnwrapTriangle(UV[0],UV[1],UV[2]);
            const double Span=FMath::Max3(UV[0].X,UV[1].X,UV[2].X)-FMath::Min3(UV[0].X,UV[1].X,UV[2].X);MaxSpan=FMath::Max(MaxSpan,Span);
            TestTrue(TEXT("Actual patch traverses at most one circumference segment"),Span<=1.0/24+1e-12);
            for(int N=0;N<3;++N)
            {
                TestEqual(TEXT("Authored V is unchanged"),UV[N].Y,Before[N].Y);
                if(Before[N].Y>1e-8&&Before[N].Y<1-1e-8)
                    TestTrue(TEXT("Nonpole corner samples same periodic coordinate"),Periodic(UV[N].X).Equals(Periodic(Before[N].X),1e-12));
            }
        }
        TestEqual(TEXT("Actual authored seam problem reproduced"),SeamFaces,22);
        AddInfo(FString::Printf(TEXT("Actual scene: %d faces, %d formerly wrapped seam faces, maximum corrected U span %.12f"),Faces.Num(),SeamFaces,MaxSpan));
    }
    return true;
}
#endif
