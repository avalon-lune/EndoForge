using UnrealBuildTool;

public class LapTrainerTarget : TargetRules
{
    public LapTrainerTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V6;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_7;
        ExtraModuleNames.Add("LapTrainer");
    }
}
