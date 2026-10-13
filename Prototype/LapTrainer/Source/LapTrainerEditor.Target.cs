using UnrealBuildTool;

public class LapTrainerEditorTarget : TargetRules
{
    public LapTrainerEditorTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Editor;
        DefaultBuildSettings = BuildSettingsVersion.V6;
        IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_7;
        ExtraModuleNames.Add("LapTrainer");
    }
}
