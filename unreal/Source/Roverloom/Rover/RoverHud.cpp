#include "RoverHud.h"

#include "Engine/Canvas.h"

#include "../Roverloom.h"
#include "RoverDrive.h"
#include "RoverPawn.h"

namespace
{
struct FHudLine
{
	FString Text;
	FLinearColor Color;
	float Scale;
	float GapBefore;
};
}

void ARoverHud::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas)
	{
		return;
	}
	const ARoverPawn* Rover = Cast<ARoverPawn>(GetOwningPawn());
	TArray<FHudLine> Lines;
	float Gap = 0.0f;
	auto Line = [&Lines, &Gap](const FString& Text, const FLinearColor& Color, float Scale = 1.1f)
	{
		Lines.Add(FHudLine{Text, Color, Scale, Gap});
		Gap = 0.0f;
	};
	const FLinearColor Amber(1.0f, 0.72f, 0.2f);
	const FLinearColor White(0.95f, 0.95f, 0.95f);
	const FLinearColor Red(1.0f, 0.3f, 0.25f);
	const FLinearColor Green(0.45f, 1.0f, 0.5f);

	// The label comes first and is always drawn: model P is a provisional choice by the owner's decision of 2026-11-07.
	Line(TEXT("PROVISIONAL DRIVE MODEL P: WheelSpike wheel model, gated PGS"), Amber, 1.3f);
	Line(TEXT("Not validated. Phase C failed. Real-time runs are not scored or ranked."), Amber);
	Gap = 8.0f;
	const FRoverStatus* S = Rover ? &Rover->GetStatus() : nullptr;
	if (!Rover)
	{
		Line(TEXT("No rover"), Red);
	}
	else if (!S->bReady)
	{
		Line(TEXT("Rig starting..."), White);
	}
	else
	{
		Line(FString::Printf(TEXT("Speed      %+.2f m/s   (command %+.2f, limit %.2f)"), S->ForwardMps, S->Applied.LinearVelocityMps,
			RoverloomRover::MaxSpeedMps), White);
		Line(FString::Printf(TEXT("Yaw rate   %+.3f rad/s (command %+.3f, limit %.4f; + is left)"), S->YawRateRadps, S->Applied.YawRateRadps,
			RoverloomRover::MaxYawRateRadps), White);
		Line(FString::Printf(TEXT("Tilt       %.1f deg     Wheels on ground %d/6"), S->TiltDeg, S->WheelsInContact), White);
		Line(FString::Printf(TEXT("Site       x %.2f m, y %.2f m, z %.2f m"), S->SitePositionM.X, S->SitePositionM.Y, S->SitePositionM.Z), White);
		Line(TEXT("Battery    not modeled"), White);
		Line(FString::Printf(TEXT("Camera     %s"), ARoverPawn::CameraName(S->Camera)), White);
		const FString Watchdog = !S->bHasCommanded ? TEXT("waiting for first command")
			: S->bWatchdogExpired                 ? TEXT("STOPPED: no command for over 2 s")
												  : TEXT("ok");
		Line(FString::Printf(TEXT("Input      %s%s   Watchdog %s"), *S->Source, S->bClamped ? TEXT(" (clamped)") : TEXT(""), *Watchdog),
			S->bHasCommanded && S->bWatchdogExpired ? Amber : White);
		if (S->FrameMsMean > 0.0)
		{
			Line(FString::Printf(TEXT("Frame      %.1f ms mean, %.1f ms p95 (%.0f fps), last 10 s%s"), S->FrameMsMean, S->FrameMsP95,
				1000.0 / S->FrameMsMean, S->FocusShare < 1.0 ? TEXT(", window not always in focus") : TEXT("")), White);
		}
		if (S->bStepClamped)
		{
			Line(FString::Printf(TEXT("Frame slower than the physics limit: step %.4f s"), S->StepDtS), Amber);
		}
		if (S->Resets > 0)
		{
			Line(FString::Printf(TEXT("Rig resets %d, last: %s"), S->Resets, *S->LastReset), Red);
		}
		Gap = 8.0f;
		if (!S->MissionLine.IsEmpty())
		{
			Line(S->MissionLine, S->bMissionEnded ? Green : Amber);
		}
		Line(TEXT("W/S drive   A/D turn   C camera   R reset"), White, 1.0f);
		Line(TEXT("Free camera: mouse to look, arrows to move, Page Up/Down to rise"), White, 1.0f);
	}

	// A translucent dark panel behind the text, sized from the measured text, so it stays legible over sky and ground.
	const float X = 24.0f;
	const float Top = 20.0f;
	const float Pad = 10.0f;
	float Y = Top;
	float Width = 0.0f;
	for (const FHudLine& L : Lines)
	{
		float W = 0.0f;
		float H = 0.0f;
		GetTextSize(L.Text, W, H, nullptr, L.Scale);
		Width = FMath::Max(Width, W);
		Y += L.GapBefore + 20.0f * L.Scale;
	}
	const FIntRect Panel(FMath::FloorToInt32(X - Pad), FMath::FloorToInt32(Top - Pad), FMath::CeilToInt32(X + Width + Pad),
		FMath::CeilToInt32(Y + Pad));
	DrawRect(FLinearColor(0.0f, 0.0f, 0.0f, 0.55f), Panel.Min.X, Panel.Min.Y, Panel.Width(), Panel.Height());
	if (Panel != LoggedPanel)
	{
		// Logged on change only, so image metrics can use the exact region of the shot.
		LoggedPanel = Panel;
		UE_LOG(LogRoverloom, Display, TEXT("Rover HUD panel: x %d y %d w %d h %d"), Panel.Min.X, Panel.Min.Y, Panel.Width(), Panel.Height());
	}

	Y = Top;
	for (const FHudLine& L : Lines)
	{
		Y += L.GapBefore;
		DrawText(L.Text, L.Color, X, Y, nullptr, L.Scale);
		Y += 20.0f * L.Scale;
	}
}
