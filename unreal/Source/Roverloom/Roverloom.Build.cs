using UnrealBuildTool;

public class Roverloom : ModuleRules
{
	public Roverloom(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		// Compile each .cpp on its own. Several files open different namespaces with the same constant names
		// (RoverloomRover and RoverloomSpike both define NumWheels), which collide when unity builds merge them.
		bUseUnity = false;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "PhysicsCore" });
		// The playable rover: Enhanced Input built in C++, JSON for the frame conformance test, and frame timing.
		PrivateDependencyModuleNames.AddRange(new string[] { "InputCore", "EnhancedInput", "Json", "RenderCore", "RHI", "Sockets", "Networking", "Landscape", "Niagara" });
	}
}
