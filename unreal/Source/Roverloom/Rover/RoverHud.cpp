#include "RoverHud.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/Font.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

#include "../Roverloom.h"
#include "../Bridge/Frames.h"
#include "RoverDrive.h"
#include "RaceCourse.h"
#include "RaceOpponent.h"
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
	if (Rover && Rover->GetStatus().bRace)
	{
		float RaceUi = FMath::Clamp(Canvas->ClipY / 720.0f, 1.0f, 3.0f);
		FParse::Value(FCommandLine::Get(), TEXT("RoverHudScale="), RaceUi);
		DrawRace(Rover, RaceUi);
		return;
	}
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
	if (FParse::Param(FCommandLine::Get(), TEXT("RoverRally")))
	{
		Line(TEXT("ROVERLOOM RALLY | experimental game rules | SPACE boost"), Green);
	}
	if (FParse::Param(FCommandLine::Get(), TEXT("RoverTutorial")))
	{
		Line(TEXT("FIRST MISSION: drive forward into the green target, 8 m ahead (120 s)."), Green);
		Line(TEXT("Click this window, hold W. Python judges arrival; a lost link is not success."), White, 1.0f);
		Gap = 8.0f;
	}

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
		if (FParse::Param(FCommandLine::Get(), TEXT("RoverRally")))
		{
			Line(S->MissionLine, S->bMissionEnded ? Green : White);
			Line(S->RallyLine, White, 1.0f);
			Line(FString::Printf(TEXT("Speed %.2f m/s | %s camera"), S->ForwardMps, ARoverPawn::CameraName(S->Camera)), White);
			Line(TEXT("W/S drive | A/D turn | SPACE boost | C camera | R rescue (+60 s)"), White, 1.0f);
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
	}

	// The sizes below were chosen for a 720 p window. Everything scales with the viewport height, so that at 1080 p the text takes the
	// same share of the screen and is as easy to read (a 720 p HUD looks small on a 1080 p screen). -RoverHudScale=F overrides it.
	float Ui = FMath::Clamp(Canvas->ClipY / 720.0f, 1.0f, 3.0f);
	FParse::Value(FCommandLine::Get(), TEXT("RoverHudScale="), Ui);
	// A translucent dark panel behind the text, sized from the measured text, so it stays legible over sky and ground.
	const float X = 24.0f * Ui;
	const float Top = 20.0f * Ui;
	const float Pad = 10.0f * Ui;
	float Y = Top;
	float Width = 0.0f;
	for (const FHudLine& L : Lines)
	{
		float W = 0.0f;
		float H = 0.0f;
		GetTextSize(L.Text, W, H, nullptr, L.Scale * Ui);
		Width = FMath::Max(Width, W);
		Y += (L.GapBefore + 20.0f * L.Scale) * Ui;
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
		Y += L.GapBefore * Ui;
		DrawText(L.Text, L.Color, X, Y, nullptr, L.Scale * Ui);
		Y += 20.0f * L.Scale * Ui;
	}
}

void ARoverHud::Panel(float X, float Y, float W, float H, float Alpha)
{
	DrawRect(FLinearColor(0.02f, 0.02f, 0.025f, Alpha), X, Y, W, H);
}

void ARoverHud::Text(const FString& Value, const FLinearColor& Color, float X, float Y, float Scale, bool bLarge, bool bCenter)
{
	UFont* Font = bLarge && GEngine ? GEngine->GetLargeFont() : nullptr;
	if (bCenter)
	{
		float W = 0.0f;
		float H = 0.0f;
		GetTextSize(Value, W, H, Font, Scale);
		X -= W / 2.0f;
	}
	// A one-pixel shadow keeps light text legible over a bright sky
	DrawText(Value, FLinearColor(0.0f, 0.0f, 0.0f, 0.6f * Color.A), X + 1.5f, Y + 1.5f, Font, Scale);
	DrawText(Value, Color, X, Y, Font, Scale);
}

void ARoverHud::DrawRace(const ARoverPawn* Rover, float Ui)
{
	const FRoverStatus& S = Rover->GetStatus();
	const float W = Canvas->ClipX;
	const float H = Canvas->ClipY;
	const FLinearColor White(0.96f, 0.95f, 0.92f);
	const FLinearColor Dim(0.72f, 0.72f, 0.70f);
	const FLinearColor Accent(0.98f, 0.55f, 0.18f);
	const FLinearColor Teal(0.35f, 0.85f, 0.88f);
	const FLinearColor Warn(1.0f, 0.78f, 0.25f);
	const float M = 18.0f * Ui;

	// Name tags over the rivals, faded with distance
	if (APlayerController* PC = GetOwningPlayerController())
	{
		const FVector Me = Rover->GetActorLocation();
		for (const auto& Pair : Rover->GetOpponents())
		{
			const ARaceOpponent* O = Pair.Value;
			if (!O) continue;
			FVector2D Screen;
			const FVector Head = O->GetActorLocation() + FVector(0, 0, 210);
			const double Dist = FVector::Dist(Me, Head) / 100.0;
			if (Dist > 40.0 || !PC->ProjectWorldLocationToScreen(Head, Screen, true)) continue;
			const float A = FMath::Clamp(1.2f - static_cast<float>(Dist) / 40.0f, 0.25f, 1.0f);
			const FString Tag = FString::Printf(TEXT("%d  %s"), O->Position, *O->DisplayName);
			float TW = 0.0f, TH = 0.0f;
			GetTextSize(Tag, TW, TH, nullptr, 0.95f * Ui);
			Panel(Screen.X - TW / 2 - 6 * Ui, Screen.Y - 3 * Ui, TW + 12 * Ui, TH + 6 * Ui, 0.45f * A);
			Text(Tag, (O->bIsGhost ? Teal : White).CopyWithNewOpacity(A), Screen.X, Screen.Y, 0.95f * Ui, false, true);
		}
		// Flag numbers over the pins within 80 m, as on a golf course
		const FRaceCourse& Pins = RoverloomRace::Course();
		if (Pins.Style == TEXT("flags"))
		{
			for (int32 I = 0; I + 1 < Pins.Checkpoints.Num(); ++I) // The last gate is the finish banner
			{
				const FVector2D G = Pins.Checkpoints[I];
				const double D = FVector2D::Distance(G, FVector2D(S.SitePositionM.X, S.SitePositionM.Y));
				FVector2D Screen;
				if (D > 80.0 || D < 3.0) continue;
				const FVector Foot = RoverloomFrames::SiteToUnrealPosition(FVector(G.X, G.Y, 0.0));
				FHitResult Hit;
				double GroundZ = Me.Z - 70.0;
				if (GetWorld()->LineTraceSingleByObjectType(Hit, FVector(Foot.X, Foot.Y, Me.Z + 5000.0), FVector(Foot.X, Foot.Y, Me.Z - 5000.0),
						FCollisionObjectQueryParams(ECC_WorldStatic)))
				{
					GroundZ = Hit.ImpactPoint.Z;
				}
				if (!PC->ProjectWorldLocationToScreen(FVector(Foot.X, Foot.Y, GroundZ + 450.0), Screen, true)) continue;
				const bool bNext = I + 1 == S.RaceFlag;
				Text(FString::Printf(TEXT("%d"), I + 1), (bNext ? Accent : White).CopyWithNewOpacity(bNext ? 1.0f : 0.6f), Screen.X, Screen.Y,
					(bNext ? 1.4f : 1.0f) * Ui, false, true);
			}
		}
		// The next gate: a marker and its distance, so the route is never in doubt
		if (S.bHasNextCheckpoint && S.RaceBanner.IsEmpty())
		{
			const FVector Gate = RoverloomFrames::SiteToUnrealPosition(FVector(S.NextCheckpointM.X, S.NextCheckpointM.Y, 0.0));
			FVector2D Screen;
			const FVector At(Gate.X, Gate.Y, Me.Z + 150.0);
			const double Dist = FVector2D::Distance(S.NextCheckpointM, FVector2D(S.SitePositionM.X, S.SitePositionM.Y));
			if (PC->ProjectWorldLocationToScreen(At, Screen, true))
			{
				const float X = FMath::Clamp(static_cast<float>(Screen.X), M, W - M);
				const float Y = FMath::Clamp(static_cast<float>(Screen.Y), M, H * 0.7f);
				DrawLine(X - 10 * Ui, Y - 8 * Ui, X, Y + 4 * Ui, Accent, 3.0f * Ui);
				DrawLine(X, Y + 4 * Ui, X + 10 * Ui, Y - 8 * Ui, Accent, 3.0f * Ui);
				const FString What = S.RaceFlags > 0 && S.RaceFlag == S.RaceFlags ? FString(TEXT("FINISH"))
					: S.RaceFlags > 0 ? FString::Printf(TEXT("FLAG %d/%d"), S.RaceFlag, S.RaceFlags) : FString(TEXT("NEXT"));
				Text(FString::Printf(TEXT("%s  %.0f m"), *What, Dist), Accent, X, Y + 8 * Ui, 0.9f * Ui, false, true);
			}
		}
	}

	// Top left: lap, time, best lap
	Panel(M, M, 250 * Ui, 92 * Ui);
	Text(FString::Printf(TEXT("LAP %d/%d"), FMath::Max(1, S.RaceLap), FMath::Max(1, S.RaceLaps)), White, M + 12 * Ui, M + 8 * Ui, 0.75f * Ui, true);
	Text(FString::Printf(TEXT("TIME  %s"), *S.RaceTime), White, M + 12 * Ui, M + 46 * Ui, 1.15f * Ui);
	Text(S.RaceBestLap.IsEmpty() ? FString(TEXT("BEST  --")) : FString::Printf(TEXT("BEST  %s"), *S.RaceBestLap), Dim, M + 12 * Ui, M + 68 * Ui, 1.0f * Ui);

	// Top centre: position
	if (S.RacePosition > 0)
	{
		const FString Pos = FString::Printf(TEXT("%d"), S.RacePosition);
		const TCHAR* Suffix = S.RacePosition == 1 ? TEXT("st") : S.RacePosition == 2 ? TEXT("nd") : S.RacePosition == 3 ? TEXT("rd") : TEXT("th");
		Text(Pos + Suffix, S.RacePosition == 1 ? Accent : White, W / 2, M, 1.3f * Ui, true, true);
		Text(FString::Printf(TEXT("of %d"), S.RaceRacers), Dim, W / 2, M + 58 * Ui, 1.0f * Ui, false, true);
	}

	// Top right: standings
	const float RowH = 24 * Ui;
	const float TW = 270 * Ui;
	const float TX = W - M - TW;
	Panel(TX, M, TW, (S.Standings.Num() + 0.6f) * RowH);
	for (int32 I = 0; I < S.Standings.Num(); ++I)
	{
		const FRoverStatus::FStanding& R = S.Standings[I];
		const float Y = M + 6 * Ui + I * RowH;
		if (R.bIsYou) DrawRect(FLinearColor(1.0f, 1.0f, 1.0f, 0.12f), TX, Y - 2 * Ui, TW, RowH);
		DrawRect(R.Color, TX + 10 * Ui, Y + 3 * Ui, 10 * Ui, 14 * Ui);
		const FLinearColor C = R.Kind == TEXT("ghost") ? Teal : R.bIsYou ? Accent : White;
		Text(FString::Printf(TEXT("%d  %s"), R.Pos, *R.Name), C, TX + 28 * Ui, Y, 1.0f * Ui);
		Text(R.Gap, Dim, TX + TW - 72 * Ui, Y, 0.95f * Ui);
	}

	// Bottom left: charge, boosts, speed and conditions
	const float BY = H - M - 96 * Ui;
	Panel(M, BY, 300 * Ui, 96 * Ui);
	Text(TEXT("CHARGE"), Dim, M + 12 * Ui, BY + 8 * Ui, 0.9f * Ui);
	const float BarX = M + 90 * Ui;
	const float BarW = 190 * Ui;
	DrawRect(FLinearColor(1, 1, 1, 0.15f), BarX, BY + 10 * Ui, BarW, 12 * Ui);
	const FLinearColor ChargeColor = S.RaceCharge < 0.25 ? FLinearColor(1.0f, 0.3f, 0.2f) : S.RaceCharge < 0.5 ? Warn : Teal;
	DrawRect(ChargeColor, BarX, BY + 10 * Ui, BarW * static_cast<float>(S.RaceCharge), 12 * Ui);
	Text(TEXT("BOOST"), Dim, M + 12 * Ui, BY + 32 * Ui, 0.9f * Ui);
	for (int32 I = 0; I < 3; ++I)
	{
		const bool bOn = I < S.RaceBoosts;
		DrawRect(bOn ? Accent : FLinearColor(1, 1, 1, 0.15f), BarX + I * 26 * Ui, BY + 33 * Ui, 20 * Ui, 14 * Ui);
	}
	if (S.bRaceBoosting) Text(TEXT("BOOSTING"), Accent, BarX + 90 * Ui, BY + 31 * Ui, 1.0f * Ui);
	Text(FString::Printf(TEXT("%.2f m/s"), FMath::Abs(S.ForwardMps)), White, M + 12 * Ui, BY + 56 * Ui, 1.25f * Ui);
	FString Tags;
	if (S.bRaceSand) Tags += TEXT("SAND  ");
	if (S.bRaceDust) Tags += TEXT("DUST STORM  ");
	else if (S.bRaceDustWarning) Tags += TEXT("DUST AHEAD  ");
	if (!S.RaceController.IsEmpty() && S.RaceController != TEXT("human")) Tags += FString::Printf(TEXT("[%s]"), *S.RaceController.ToUpper());
	Text(Tags, Warn, M + 120 * Ui, BY + 60 * Ui, 0.95f * Ui);

	// Bottom right: minimap of the course with every racer
	const FRaceCourse& Course = RoverloomRace::Course();
	if (Course.IsValid())
	{
		FBox2D Bounds(ForceInit);
		for (const FVector2D& P : Course.Line) Bounds += P;
		Bounds = Bounds.ExpandBy(3.0);
		const float MapW = 210 * Ui;
		const float MapH = 170 * Ui;
		const float MX = W - M - MapW;
		const float MY = H - M - MapH;
		Panel(MX, MY, MapW, MapH);
		const FVector2D Size = Bounds.GetSize();
		const float K = FMath::Min(MapW / Size.X, MapH / Size.Y) * 0.92f;
		const FVector2D Mid = Bounds.GetCenter();
		auto ToMap = [&](const FVector2D& P) // Site north is up, east is right
		{
			return FVector2D(MX + MapW / 2 + (P.X - Mid.X) * K, MY + MapH / 2 - (P.Y - Mid.Y) * K);
		};
		for (const FBox2D& B : Course.Sand)
		{
			const FVector2D A = ToMap(FVector2D(B.Min.X, B.Max.Y));
			const FVector2D C = ToMap(FVector2D(B.Max.X, B.Min.Y));
			DrawRect(FLinearColor(0.8f, 0.55f, 0.3f, 0.35f), A.X, A.Y, C.X - A.X, C.Y - A.Y);
		}
		for (int32 I = 0; I + 1 < Course.Line.Num(); ++I)
		{
			const FVector2D A = ToMap(Course.Line[I]);
			const FVector2D B = ToMap(Course.Line[I + 1]);
			DrawLine(A.X, A.Y, B.X, B.Y, FLinearColor(1, 1, 1, 0.55f), 3.0f * Ui);
		}
		for (const FVector2D& G : Course.Checkpoints)
		{
			const FVector2D A = ToMap(G);
			DrawRect(FLinearColor(0.92f, 0.38f, 0.10f, 0.8f), A.X - 3 * Ui, A.Y - 3 * Ui, 6 * Ui, 6 * Ui);
		}
		for (const FVector2D& P : Course.Pads)
		{
			const FVector2D A = ToMap(P);
			DrawRect(Teal, A.X - 3 * Ui, A.Y - 3 * Ui, 6 * Ui, 6 * Ui);
		}
		if (S.bHasNextCheckpoint)
		{
			const FVector2D A = ToMap(S.NextCheckpointM);
			DrawRect(Accent.CopyWithNewOpacity(0.6f), A.X - 5 * Ui, A.Y - 5 * Ui, 10 * Ui, 10 * Ui);
		}
		for (const auto& Pair : Rover->GetOpponents())
		{
			if (!Pair.Value) continue;
			const FVector Site = RoverloomFrames::UnrealToSitePosition(Pair.Value->GetActorLocation());
			const FVector2D A = ToMap(FVector2D(Site.X, Site.Y));
			DrawRect(Pair.Value->bIsGhost ? Teal : White, A.X - 4 * Ui, A.Y - 4 * Ui, 8 * Ui, 8 * Ui);
		}
		const FVector2D Me = ToMap(FVector2D(S.SitePositionM.X, S.SitePositionM.Y));
		DrawRect(Accent, Me.X - 6 * Ui, Me.Y - 6 * Ui, 12 * Ui, 12 * Ui);
		const FVector2D Nose = Me + FVector2D(FMath::Cos(S.YawRad), -FMath::Sin(S.YawRad)) * 14.0 * Ui;
		DrawLine(Me.X, Me.Y, Nose.X, Nose.Y, Accent, 3.0f * Ui);
	}

	// Centre: countdown, GO and the finish, then short messages
	if (!S.RaceBanner.IsEmpty())
	{
		const bool bCount = S.RaceBanner.Len() == 1;
		Text(S.RaceBanner, bCount ? White : Accent, W / 2, H * 0.32f, (bCount ? 3.0f : 2.0f) * Ui, true, true);
	}
	else if (!S.bRaceState)
	{
		Text(S.MissionLine.IsEmpty() ? FString(TEXT("Waiting for the race to start...")) : S.MissionLine, White, W / 2, H * 0.36f, 1.2f * Ui, false, true);
	}
	if (!S.RaceMessage.IsEmpty())
	{
		Text(S.RaceMessage, Accent, W / 2, H * 0.46f, 1.4f * Ui, false, true);
	}

	// Bottom centre: controls and the model label, small but always present (model P is provisional)
	Text(TEXT("W/S drive   A/D turn   SPACE boost   C camera   R rescue (+30 s)"), Dim, W / 2, H - M - 34 * Ui, 0.9f * Ui, false, true);
	Text(TEXT("Experimental game rules on provisional drive model P. Not a validated rover model; real-time runs are not benchmarks."),
		Dim.CopyWithNewOpacity(0.8f), W / 2, H - M - 16 * Ui, 0.8f * Ui, false, true);
}
