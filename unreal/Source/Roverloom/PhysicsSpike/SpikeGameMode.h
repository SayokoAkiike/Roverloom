#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "Math/RandomStream.h"

#include "SpikeParameters.h"

#include "SpikeGameMode.generated.h"

class ASpikeRover;
class UPhysicalMaterial;

// Runs one physics spike scenario, writes its record to -SpikeOut, and exits. Start it with
// /Engine/Maps/Entry?game=/Script/Roverloom.SpikeGameMode -game -SpikeScenario=<name>. See unreal/README.md.
UCLASS(NotBlueprintable)
class ASpikeGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ASpikeGameMode();

	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	void SpawnBlock(const FVector& Center, const FRotator& Rotation, const FVector& SizeCm);
	void CommandAt(double TimeS, double& OutForwardCmps, double& OutYawRateDegps);
	void Record(double DeltaSeconds, double WallFrameMs, double ForwardCmps, double YawRateDegps);
	void Finish(const FString& Outcome);

	UPROPERTY()
	TObjectPtr<ASpikeRover> Rover;

	UPROPERTY()
	TObjectPtr<UPhysicalMaterial> Material;

	FString Scenario;
	FString OutDir;
	double SlopeDeg = 0.0;
	double ObstacleCm = 0.0;
	double DriveMaxTorqueUsed = RoverloomSpike::DriveMaxTorque;
	double DurationS = 0.0;
	int32 Seed = 42;
	FRandomStream Random;
	double NextRandomChangeS = 0.0;
	double RandomForwardCmps = 0.0;
	double RandomYawRateDegps = 0.0;

	double SimTimeS = 0.0;
	int64 Frame = 0;
	double LastWallS = 0.0;
	double StartWallS = 0.0;
	bool bViewSet = false;
	bool bConnectAttempted = false;
	bool bFinished = false;
	TArray<FString> Rows;
};
