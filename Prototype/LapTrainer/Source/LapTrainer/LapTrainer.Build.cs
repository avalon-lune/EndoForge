using UnrealBuildTool;

public class LapTrainer : ModuleRules
{
    public LapTrainer(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] {
            "Core", "CoreUObject", "Engine", "InputCore", "ProceduralMeshComponent",
            "Sockets", "Networking", "Json", "JsonUtilities", "RenderCore", "RHI", "ImageWrapper"
        });
        PrivateDependencyModuleNames.AddRange(new[] { "Slate", "SlateCore", "ApplicationCore" });
    }
}
