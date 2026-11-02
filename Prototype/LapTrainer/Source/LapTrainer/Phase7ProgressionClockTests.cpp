#include "Phase7ProgressionClock.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPhase7ProgressionClockTest,"EndoForge.Phase7.PairedProgressionClock",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)

bool FPhase7ProgressionClockTest::RunTest(const FString& Parameters)
{
    using namespace EndoForgePhase7;
    auto O=[](uint64_t P,double W,double N,uint64_t S=1,
              const std::string& M="idle",uint64_t State=0)
    { return FProgressionObservation{P,W,N,S,M,State}; };
    auto Near=[&](const TCHAR* Name,double A,double B)
    { return TestTrue(Name,std::abs(A-B)<1e-11); };

    // 60Hz actor / 30Hz native, with accounting before the next socket poll.
    FProgressionClock Shifted;Shifted.Boundary("startup");Shifted.Feed(O(0,0,0));
    double LegacyWall=0,LegacyNative=0,PreviousNative=0;
    for(unsigned Actor=1;Actor<=7;++Actor)
    {
        const unsigned P=Actor-1;const double Native=double(P/2)/30;
        LegacyWall+=1./60;LegacyNative+=Native-PreviousNative;PreviousNative=Native;
        TestTrue(TEXT("Same-boundary poll accepted"),Shifted.Feed(O(P,double(P)/60,Native)));
    }
    Near(TEXT("Legacy stale endpoint counterexample reproduced"),LegacyNative/LegacyWall,6./7);
    Near(TEXT("Paired native duration"),Shifted.GetNativeSeconds(),.1);
    Near(TEXT("Paired wall duration"),Shifted.GetWallSeconds(),.1);

    FProgressionClock Stall;
    Stall.Feed(O(1,0,0));Stall.Feed(O(2,.1,0));Stall.Feed(O(3,.2,0));Stall.Feed(O(4,.3,.1));
    Near(TEXT("No-state polls still charge wall time"),Stall.GetWallSeconds(),.3);
    Near(TEXT("No phantom native progress during wait"),Stall.GetNativeSeconds(),.1);

    FProgressionClock Boundary;
    Boundary.Feed(O(1,10,1));Boundary.Feed(O(2,10.2,1.2));Boundary.Boundary("frozen_capture");
    Boundary.Boundary("fence_recovery");Boundary.Feed(O(8,20,11));Boundary.Feed(O(9,20.3,11.3));
    Boundary.Boundary("finish");
    Near(TEXT("Frozen recovery gap excluded at actual paired endpoints"),Boundary.GetWallSeconds(),.5);
    Near(TEXT("Both terminal live polls retained"),Boundary.GetNativeSeconds(),.5);
    TestTrue(TEXT("Final segment keeps last actual observation"),Boundary.GetSegments().back().EndSampleIndex==3);

    FProgressionClock Modes;
    for(const auto& V:{O(1,0,10),O(2,1,11),O(3,2,0,2,"recording"),O(4,3,1,2,"recording"),
        O(5,4,0,3,"replaying"),O(6,20,16,3,"replay_complete"),O(7,21,17,3),O(8,22,18,3)})
        TestTrue(TEXT("Mode or simulation transition recorded"),Modes.Feed(V));
    Near(TEXT("Replay and reset do not add native time jumps"),Modes.GetNativeSeconds(),3);
    Near(TEXT("Only three live intervals counted"),Modes.GetWallSeconds(),3);
    TestTrue(TEXT("Raw replay polls remain inspectable"),Modes.GetSamples().size()==8);

    FProgressionClock Gap;Gap.Feed(O(1,1,1));
    TestFalse(TEXT("Omitted active poll rejected"),Gap.Feed(O(3,2,2)));
    FProgressionClock Reverse;Reverse.Feed(O(1,1,1));
    TestFalse(TEXT("Unannounced time reversal rejected"),Reverse.Feed(O(2,2,.5)));
    FProgressionClock Duplicate;Duplicate.Feed(O(1,1,1));
    TestTrue(TEXT("Exact cached pair is idempotent"),Duplicate.Feed(O(1,1,1)));
    TestFalse(TEXT("Mutated cached pair rejected"),Duplicate.Feed(O(1,1,2)));
    FProgressionClock Unknown;
    TestFalse(TEXT("Arbitrary slow-step exclusion rejected"),Unknown.Boundary("slow-step"));
    FProgressionClock Bad;
    TestFalse(TEXT("Nonfinite clock rejected"),Bad.Feed(O(1,std::numeric_limits<double>::infinity(),0)));

    for(unsigned Start=0;Start<20;++Start)for(unsigned Length=1;Length<30;++Length)
    {
        FProgressionClock Window;
        for(unsigned P=Start;P<=Start+Length;++P)
            TestTrue(TEXT("Quantized sample accepted"),Window.Feed(O(P,double(P)/60,double(P/2)/30)));
        Near(TEXT("Exact wall endpoint support"),Window.GetWallSeconds(),double(Length)/60);
        Near(TEXT("Exact quantized native endpoint support"),Window.GetNativeSeconds(),double((Start+Length)/2-Start/2)/30);
    }
    AddInfo(TEXT("Paired-clock synthetic fixtures plus580 quantized endpoint windows; actual runtime acceptance requires fresh captured observations."));
    return true;
}
#endif
