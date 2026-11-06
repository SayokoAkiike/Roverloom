#include "RoverHud.h"

#include "Engine/Canvas.h"

#include "RoverDrive.h"
#include "RoverPawn.h"

void ARoverHud::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas)
	{
		return;
	}
	const ARoverPawn* Rover = Cast<ARoverPawn>(GetOwningPawn());
	const float X = 24.0f;
	float Y = 20.0f;
	auto Line = [this, X, &Y](const FString& Text, const FLinearColor& Color, float Scale = 1.1f)
	{
		DrawText(Text, Color, X, Y, nullptr, Scale);
		Y += 20.0f * Scale;
	};
	const FLinearColor Amber(1.0f, 0.72f, 0.2f);
	const FLinearColor White(0.95f, 0.95f, 0.95f);
	const FLinearColor Red(1.0f, 0.3f, 0.25f);

	// The label comes first and is always drawn: model P is a provisional choice by the owner's decision of 2026-11-07.
	Line(TEXT("PROVISIONAL DRIVE MODEL P: WheelSpike wheel model, gated PGS"), Amber, 1.3f);
	Line(TEXT("Not validated. Phase C failed. Real-time runs are not scored or ranked."), Amber);
	Y += 8.0f;
	if (!Rover)
	{
		Line(TEXT("No rover"), Red);
		return;
	}
	const FRoverStatus& S = Rover->GetStatus();
	if (!S.bReady)
	{
		Line(TEXT("Rig starting..."), White);
		return;
	}
	Line(FString::Printf(TEXT("Speed      %+.2f m/s   (command %+.2f, limit %.2f)"), S.ForwardMps, S.Applied.LinearVelocityMps,
		RoverloomRover::MaxSpeedMps), White);
	Line(FString::Printf(TEXT("Yaw rate   %+.3f rad/s (command %+.3f, limit %.4f; + is left)"), S.YawRateRadps, S.Applied.YawRateRadps,
		RoverloomRover::MaxYawRateRadps), White);
	Line(FString::Printf(TEXT("Tilt       %.1f deg     Wheels on ground %d/6"), S.TiltDeg, S.WheelsInContact), White);
	Line(FString::Printf(TEXT("Site       x %.2f m, y %.2f m, z %.2f m"), S.SitePositionM.X, S.SitePositionM.Y, S.SitePositionM.Z), White);
	Line(TEXT("Battery    not modeled"), White);
	Line(FString::Printf(TEXT("Camera     %s"), ARoverPawn::CameraName(S.Camera)), White);
	const FString Watchdog = !S.bHasCommanded ? TEXT("waiting for first command")
		: S.bWatchdogExpired                ? TEXT("STOPPED: no command for over 2 s")
											: TEXT("ok");
	Line(FString::Printf(TEXT("Input      %s%s   Watchdog %s"), *S.Source, S.bClamped ? TEXT(" (clamped)") : TEXT(""), *Watchdog),
		S.bHasCommanded && S.bWatchdogExpired ? Amber : White);
	if (S.FrameMsMean > 0.0)
	{
		Line(FString::Printf(TEXT("Frame      %.1f ms mean, %.1f ms p95 (%.0f fps), last 10 s%s"), S.FrameMsMean, S.FrameMsP95,
			1000.0 / S.FrameMsMean, S.FocusShare < 1.0 ? TEXT(", window not always in focus") : TEXT("")), White);
	}
	if (S.bStepClamped)
	{
		Line(FString::Printf(TEXT("Frame slower than the physics limit: step %.4f s"), S.StepDtS), Amber);
	}
	if (S.Resets > 0)
	{
		Line(FString::Printf(TEXT("Rig resets %d, last: %s"), S.Resets, *S.LastReset), Red);
	}
	Y += 8.0f;
	Line(TEXT("W/S drive   A/D turn   C camera   R reset"), White, 1.0f);
	Line(TEXT("Free camera: mouse to look, arrows to move, Page Up/Down to rise"), White, 1.0f);
}
