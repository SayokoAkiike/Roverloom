using UnrealBuildTool;

public class RoverloomTarget : TargetRules
{
	public RoverloomTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("Roverloom");
	}
}
