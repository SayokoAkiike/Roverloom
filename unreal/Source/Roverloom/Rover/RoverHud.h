#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"

#include "RoverHud.generated.h"

// A canvas HUD for the greybox: the drive model's provisional label first, then speed, yaw rate, tilt, camera, input,
// and watchdog. Every number is read from the rover; the HUD changes nothing.
UCLASS(NotBlueprintable)
class ARoverHud : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;
};
