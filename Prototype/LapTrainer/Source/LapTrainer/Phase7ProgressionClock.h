#pragma once

// Wall/native pairs are captured at the same completed bridge read attempt.
// A read with no newer state is still an observation and must charge wall time.
// This class never extrapolates simulation progress or filters slow steps.
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace EndoForgePhase7
{
struct FProgressionObservation
{
    uint64_t PollId = 0;
    double WallSeconds = 0;
    double NativeSeconds = 0;
    uint64_t SimulationId = 0;
    std::string Mode;
    uint64_t StateId = 0;
};

struct FProgressionSegment
{
    std::size_t StartSampleIndex = 0;
    std::size_t EndSampleIndex = 0;
    double WallSeconds = 0;
    double NativeSeconds = 0;
};

struct FProgressionBoundary
{
    std::string Reason;
    std::size_t AfterSampleCount = 0;
    uint64_t LastPollId = 0;
    bool HasLastPoll = false;
};

class FProgressionClock
{
public:
    bool Feed(const FProgressionObservation& Observation)
    {
        if (!IsValid()) return false;
        if (!std::isfinite(Observation.WallSeconds) ||
            !std::isfinite(Observation.NativeSeconds) || Observation.WallSeconds < 0 || Observation.NativeSeconds < 0)
            return Fail("Nonfinite or negative progression observation");
        const bool Live = Observation.Mode == "idle" || Observation.Mode == "recording";
        const bool Replay = Observation.Mode == "replaying" || Observation.Mode == "replay_complete";
        if (!Live && !Replay) return Fail("Unknown progression session mode");

        if (!Samples.empty())
        {
            const auto& Previous = Samples.back();
            if (Observation.PollId == Previous.PollId)
            {
                if (Equal(Observation, Previous)) return true;
                return Fail("Cached poll identity changed without a new read attempt");
            }
            if (Observation.PollId < Previous.PollId || Observation.WallSeconds <= Previous.WallSeconds)
                return Fail("Progression poll or wall clock is not monotonic");
            if (Active && Observation.PollId != Previous.PollId + 1)
                return Fail("An ordinary live bridge poll was omitted");
            if (Observation.SimulationId == Previous.SimulationId &&
                Observation.NativeSeconds < Previous.NativeSeconds)
                return Fail("Native time reversed without a new simulation identity");
            if (Observation.SimulationId != Previous.SimulationId)
                Boundary("simulation_change");
            if (Observation.Mode != Previous.Mode)
                Boundary("mode_change");
        }

        Samples.push_back(Observation);
        if (Replay)
        {
            // Replay is retained in the raw stream but is not live throughput.
            // No caller-supplied success flag can count these native time jumps.
            if (Samples.size() == 1 || Samples[Samples.size()-2].Mode != Observation.Mode)
                Boundary("replay");
            Active = false;
            return true;
        }

        const std::size_t Index = Samples.size()-1;
        if (!Active)
        {
            Segments.push_back({Index, Index, 0, 0});
            Active = true;
            return true;
        }
        const auto& Previous = Samples[Index-1];
        const double WallDelta = Observation.WallSeconds-Previous.WallSeconds;
        const double NativeDelta = Observation.NativeSeconds-Previous.NativeSeconds;
        auto& Segment = Segments.back();
        Segment.EndSampleIndex = Index;
        Segment.WallSeconds += WallDelta;
        Segment.NativeSeconds += NativeDelta;
        WallSeconds += WallDelta;
        NativeSeconds += NativeDelta;
        return true;
    }

    bool Boundary(const std::string& Reason)
    {
        if (!IsValid()) return false;
        if (Reason != "startup" && Reason != "frozen_capture" &&
            Reason != "render_proof" && Reason != "fence_recovery" &&
            Reason != "finish" && Reason != "disconnect" &&
            Reason != "simulation_change" && Reason != "mode_change" && Reason != "replay")
            return Fail("Unknown progression boundary reason");
        Active = false;
        // Repeated frozen heartbeats may declare the same boundary without
        // contributing a poll; one explicit record fully describes that gap.
        if (!Boundaries.empty() && Boundaries.back().Reason == Reason &&
            Boundaries.back().AfterSampleCount == Samples.size()) return true;
        Boundaries.push_back({Reason, Samples.size(),
                              Samples.empty() ? 0 : Samples.back().PollId, !Samples.empty()});
        return true;
    }

    const std::vector<FProgressionObservation>& GetSamples() const { return Samples; }
    const std::vector<FProgressionSegment>& GetSegments() const { return Segments; }
    const std::vector<FProgressionBoundary>& GetBoundaries() const { return Boundaries; }
    double GetWallSeconds() const { return WallSeconds; }
    double GetNativeSeconds() const { return NativeSeconds; }
    bool IsValid() const { return Error.empty(); }
    const std::string& GetError() const { return Error; }

private:
    static bool Equal(const FProgressionObservation& A, const FProgressionObservation& B)
    {
        return A.PollId == B.PollId && A.WallSeconds == B.WallSeconds &&
               A.NativeSeconds == B.NativeSeconds && A.SimulationId == B.SimulationId &&
               A.Mode == B.Mode && A.StateId == B.StateId;
    }
    bool Fail(const std::string& Message) { Error = Message; return false; }
    std::vector<FProgressionObservation> Samples;
    std::vector<FProgressionSegment> Segments;
    std::vector<FProgressionBoundary> Boundaries;
    double WallSeconds = 0;
    double NativeSeconds = 0;
    bool Active = false;
    std::string Error;
};
}
