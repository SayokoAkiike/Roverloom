using UnrealBuildTool;

public class Roverloom : ModuleRules
{
	public Roverloom(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "PhysicsCore" });
		// The playable rover: Enhanced Input built in C++, and JSON for the frame conformance test.
		PrivateDependencyModuleNames.AddRange(new string[] { "InputCore", "EnhancedInput", "Json" });
	}
}
