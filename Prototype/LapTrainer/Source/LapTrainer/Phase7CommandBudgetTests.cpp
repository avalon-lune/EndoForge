#include "Phase7CommandBudget.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPhase7CommandBudgetTest,"EndoForge.Phase7.OutstandingCommandPath",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)

bool FPhase7CommandBudgetTest::RunTest(const FString& Parameters)
{
    // Deterministic transport/kinematic fixture, not native physics evidence:
    // 60Hz input, 30Hz movement, independently delayed commands/feedback,
    // coalesced commands, abrupt reversals and release while packets remain.
    struct FCommand {int Delivery;uint64 Sequence;FVector Target;bool Hold;};
    struct FFeedback {int Delivery;uint64 Applied;FVector Actual,Target;};
    double WorstStopMm=0,WorstLatencyMs=0;
    for(int FeedbackDelay:{1,2,4})for(int CommandDelay:{1,2})for(double Angle:{45.,90.,180.})
    {
        Phase7CommandBudget::FState Budget;
        TArray<FCommand> Commands;TArray<FFeedback> Feedback;
        FVector Actual=FVector::ZeroVector,NativeTarget=Actual,KnownActual=Actual,KnownTarget=Actual,Intent=Actual;
        uint64 Applied=0,KnownApplied=0;double StopPath=0,FirstResponse=-1;constexpr int ReleaseTick=48;
        for(int Tick=0;Tick<90;++Tick)
        {
            for(const auto& F:Feedback)if(F.Delivery<=Tick){KnownActual=F.Actual;KnownTarget=F.Target;KnownApplied=F.Applied;}
            Feedback.RemoveAll([&](const FFeedback& F){return F.Delivery<=Tick;});
            if(FirstResponse<0&&KnownActual.Size()>.005)FirstResponse=Tick/60.0;
            const bool Hold=Tick>=ReleaseTick;
            if(!Hold)
            {
                const double A=Tick<16?0:Tick<32?Angle:-Angle;
                const FVector Delta=FVector(FMath::Cos(FMath::DegreesToRadians(A)),FMath::Sin(FMath::DegreesToRadians(A)),0)*.025;
                Intent=KnownActual+(Intent+Delta-KnownActual).GetClampedToMaxSize(.1);
            }
            else Intent=KnownActual;
            const auto Result=Budget.Queue(Tick+1,KnownApplied,KnownActual,KnownTarget,Intent,Hold);
            TestTrue(TEXT("Actual queued wire target remains within1mm of acknowledged pose"),FVector::Distance(Result.Tip,KnownActual)<=.1+1e-10);
            TestTrue(TEXT("Whole pending executable path remains within1mm"),Result.OutstandingPathCm<=.1+1e-10);
            Commands.Add({Tick+CommandDelay,uint64(Tick+1),Result.Tip,Result.Hold});
            if(Tick%2==0)
            {
                for(const auto& C:Commands)if(C.Delivery<=Tick){Applied=C.Sequence;NativeTarget=C.Hold?Actual:C.Target;}
                Commands.RemoveAll([&](const FCommand& C){return C.Delivery<=Tick;});
                const FVector Before=Actual;Actual+=(NativeTarget-Actual).GetClampedToMaxSize(.06);
                if(Hold)StopPath+=FVector::Distance(Before,Actual);
                Feedback.Add({Tick+FeedbackDelay,Applied,Actual,NativeTarget});
            }
        }
        WorstStopMm=FMath::Max(WorstStopMm,StopPath*10);WorstLatencyMs=FMath::Max(WorstLatencyMs,FirstResponse*1000);
        TestTrue(TEXT("Release with outstanding reversal packets travels at most1mm"),StopPath<=.1+1e-10);
        TestTrue(TEXT("Delayed first accepted movement responds within150ms"),FirstResponse>0&&FirstResponse<=.15);
    }
    // A small mouse gesture must survive the interval between native updates.
    Phase7CommandBudget::FState Pulse;FVector Actual=FVector::ZeroVector,Target(.02,0,0);uint64 Ack=0;
    for(uint64 Seq=1;Seq<=6;++Seq)
    {
        const auto R=Pulse.Queue(Seq,Ack,Actual,Actual,Target,false);
        if(Seq%2==0){Actual=R.Tip;Ack=Seq;}
    }
    TestTrue(TEXT("Finite0.2mm mouse intent is delivered without loss"),Actual.Equals(Target,1e-12));
    Pulse.Reset();TestEqual(TEXT("Reset or switch discards only the previous transport frontier"),Pulse.Pending.Num(),0);
    const auto PresetStop=Pulse.Queue(1,0,FVector::ZeroVector,FVector(2,0,0),FVector(.02,0,0),false);
    TestTrue(TEXT("Manual takeover of unbounded preset first requests native hold"),PresetStop.Hold);
    const auto Resume=Pulse.Queue(2,1,FVector(.03,0,0),FVector(.03,0,0),FVector(.05,0,0),false);
    TestTrue(TEXT("Manual intent resumes after hold acknowledgement"),!Resume.Hold&&Resume.Tip.Equals(FVector(.05,0,0),1e-12));
    AddInfo(FString::Printf(TEXT("18 delayed transport cases: maximum stop path %.9fmm, maximum first-response %.3fms"),WorstStopMm,WorstLatencyMs));
    return true;
}
#endif
