#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"

#include "RoverPlaygroundGameMode.generated.h"

class ARoverPawn;
class UPhysicalMaterial;

// G2's greybox test ground, spawned from C++ with no project assets: flat ground, a 25 cm step, 10 and 15 degree
// slopes with plateaus, and a few rocks, under a sun, sky, and fog. One rover is spawned and given to the player.
// Start it with /Engine/Maps/Entry?game=/Script/Roverloom.RoverPlaygroundGameMode -game, or set it as a level's
// game mode override for Play In Editor.
UCLASS(NotBlueprintable)
class ARoverPlaygroundGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ARoverPlaygroundGameMode();

	virtual void StartPlay() override;
	virtual void RestartPlayer(AController* NewPlayer) override;

private:
	void SpawnTerrain();
	void SpawnLights();
	void SpawnRover();
	AActor* SpawnBlock(const FVector& Center, const FRotator& Rotation, const FVector& SizeCm, const FLinearColor& Color,
		const TCHAR* MeshPath = TEXT("/Engine/BasicShapes/Cube.Cube"));
	void SpawnRamp(double StartXCm, double LaneYCm, double SlopeDeg, double LengthCm, double WidthCm, const FLinearColor& Color);

	UPROPERTY()
	TObjectPtr<ARoverPawn> Rover;

	UPROPERTY()
	TObjectPtr<UPhysicalMaterial> GroundMaterial;

	bool bTerrainSpawned = false;
};
