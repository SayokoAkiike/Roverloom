#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"

#include "RoverHud.generated.h"

// A canvas HUD for the greybox: the drive model's provisional label first, then speed, yaw rate, tilt, camera, input,
// and watchdog, over a translucent dark panel. Every number is read from the rover; the HUD changes nothing.
UCLASS(NotBlueprintable)
class ARoverHud : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

private:
	// The race layout (docs/race.md): lap and time, position, standings, charge and boosts, a minimap, name tags and the
	// countdown and finish banner. Everything shown comes from Python's race state.
	void DrawRace(const class ARoverPawn* Rover, float Ui);
	void Panel(float X, float Y, float W, float H, float Alpha = 0.5f);
	void Text(const FString& Value, const FLinearColor& Color, float X, float Y, float Scale, bool bLarge = false, bool bCenter = false);

	// The text panel's last logged rectangle, in canvas pixels; logged again only when it changes.
	FIntRect LoggedPanel;
};
